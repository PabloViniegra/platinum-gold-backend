from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from app.core.exceptions import AppError
from app.ingestion.schemas import ItemImport
from app.items.models import Item
from app.meta.models import DatasetMetadata


class SqlAlchemyIngestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_items(self, items: Sequence[ItemImport]) -> None:
        if not items:
            return

        statement = insert(Item).values(
            [
                {
                    "game_id": item.game_id,
                    "name": item.name,
                    "description": item.description,
                    "quality": item.quality,
                    "item_type": item.item_type,
                    "recharge_time": item.recharge_time,
                    "image_url": item.image_url,
                    "introduced_in_version": item.introduced_in_version,
                }
                for item in items
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[Item.game_id],
            set_={
                "name": statement.excluded.name,
                "description": statement.excluded.description,
                "quality": statement.excluded.quality,
                "item_type": statement.excluded.item_type,
                "recharge_time": statement.excluded.recharge_time,
                "image_url": statement.excluded.image_url,
                "introduced_in_version": statement.excluded.introduced_in_version,
                "updated_at": func.now(),
            },
        )
        await self._execute(statement)

    async def upsert_metadata(
        self,
        *,
        dataset_version: str,
        game_version: str | None,
        last_sync: datetime,
    ) -> None:
        statement = insert(DatasetMetadata).values(
            {
                "id": 1,
                "dataset_version": dataset_version,
                "game_version": game_version,
                "last_sync": last_sync,
            }
        )
        statement = statement.on_conflict_do_update(
            index_elements=[DatasetMetadata.id],
            set_={
                "dataset_version": statement.excluded.dataset_version,
                "game_version": statement.excluded.game_version,
                "last_sync": statement.excluded.last_sync,
            },
        )
        await self._execute(statement)

    async def _execute(self, statement: Executable) -> None:
        try:
            await self._session.execute(statement)
        except (OSError, TimeoutError, SQLAlchemyError) as exc:
            raise AppError(
                503,
                "SERVICE_UNAVAILABLE",
                "A required service is unavailable",
            ) from exc
