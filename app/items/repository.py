from dataclasses import dataclass
from typing import Protocol

from app.core.exceptions import AppError


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


class ItemRepository(Protocol):
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


async def get_item_repository() -> ItemRepository:
    raise AppError(
        503,
        "SERVICE_UNAVAILABLE",
        "A required service is unavailable",
    )
