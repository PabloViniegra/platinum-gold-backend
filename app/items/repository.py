from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from sqlalchemy import Select, func, select
from sqlalchemy.engine import Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.items.models import Item
from app.meta.models import DatasetMetadata

SORT_COLUMNS = {
    "name": Item.name,
    "quality": Item.quality,
    "game_id": Item.game_id,
}


@dataclass(frozen=True)
class ItemRecord:
    game_id: int
    name: str
    description: str
    quality: int | None
    item_type: str | None
    recharge_time: str | None
    image_url: str
    introduced_in_version: str | None


@dataclass(frozen=True)
class DatasetMetadataRecord:
    dataset_version: str
    game_version: str | None
    last_sync: datetime


class ItemRepository(Protocol):
    async def get_metadata(self) -> DatasetMetadataRecord | None: ...

    async def get_by_game_id(self, game_id: int) -> ItemRecord | None: ...

    async def list_items(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
        sort: str,
        order: str,
        limit: int,
        offset: int,
    ) -> list[ItemRecord]: ...

    async def count_items(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
    ) -> int: ...

    async def get_random(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
    ) -> ItemRecord | None: ...


class SqlAlchemyItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_metadata(self) -> DatasetMetadataRecord | None:
        result = await self._execute(
            select(DatasetMetadata).where(DatasetMetadata.id == 1),
        )
        metadata = cast(DatasetMetadata | None, result.scalar_one_or_none())
        return None if metadata is None else to_metadata_record(metadata)

    async def get_by_game_id(self, game_id: int) -> ItemRecord | None:
        item = await self._scalar(
            select(Item).where(Item.game_id == game_id),
        )
        return None if item is None else to_record(item)

    async def list_items(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
        sort: str,
        order: str,
        limit: int,
        offset: int,
    ) -> list[ItemRecord]:
        column = SORT_COLUMNS[sort]
        ordered = column.desc() if order == "desc" else column.asc()
        statement = (
            apply_filters(select(Item), search, quality, item_type, version)
            .order_by(ordered, Item.game_id.asc())
            .offset(offset)
            .limit(limit)
        )
        return [to_record(item) for item in await self._scalars(statement)]

    async def count_items(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
    ) -> int:
        statement = apply_filters(
            select(func.count()).select_from(Item),
            search,
            quality,
            item_type,
            version,
        )
        result = await self._execute(statement)
        return int(result.scalar_one())

    async def get_random(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
    ) -> ItemRecord | None:
        statement = (
            apply_filters(select(Item), search, quality, item_type, version)
            .order_by(func.random())
            .limit(1)
        )
        item = await self._scalar(statement)
        return None if item is None else to_record(item)

    async def _execute(self, statement: Select[Any]) -> Result[Any]:
        try:
            return await self._session.execute(statement)
        except (OSError, TimeoutError, SQLAlchemyError) as exc:
            raise AppError(
                503,
                "SERVICE_UNAVAILABLE",
                "A required service is unavailable",
            ) from exc

    async def _scalar(self, statement: Select[Any]) -> Item | None:
        result = await self._execute(statement)
        return result.scalar_one_or_none()

    async def _scalars(self, statement: Select[Any]) -> Sequence[Item]:
        result = await self._execute(statement)
        return result.scalars().all()


def apply_filters(
    statement: Select[Any],
    search: str | None,
    quality: int | None,
    item_type: str | None,
    version: str | None,
) -> Select[Any]:
    if search is not None:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Item.name.ilike(f"%{escaped}%", escape="\\"))
    if quality is not None:
        statement = statement.where(Item.quality == quality)
    if item_type is not None:
        statement = statement.where(Item.item_type == item_type)
    if version is not None:
        statement = statement.where(Item.introduced_in_version == version)
    return statement


def to_record(item: Item) -> ItemRecord:
    return ItemRecord(
        game_id=item.game_id,
        name=item.name,
        description=item.description,
        quality=item.quality,
        item_type=item.item_type,
        recharge_time=item.recharge_time,
        image_url=item.image_url,
        introduced_in_version=item.introduced_in_version,
    )


def to_metadata_record(metadata: DatasetMetadata) -> DatasetMetadataRecord:
    return DatasetMetadataRecord(
        dataset_version=metadata.dataset_version,
        game_version=metadata.game_version,
        last_sync=metadata.last_sync,
    )
