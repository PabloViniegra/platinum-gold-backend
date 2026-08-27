from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AppError
from app.items.cache import ItemCache
from app.items.repository import ItemRepository, SqlAlchemyItemRepository


async def get_item_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ItemRepository:
    return SqlAlchemyItemRepository(session)


async def get_item_cache(request: Request) -> ItemCache:
    cache = getattr(request.app.state, "item_cache", None)
    if cache is None:
        raise AppError(
            503,
            "SERVICE_UNAVAILABLE",
            "A required service is unavailable",
        )
    return cache
