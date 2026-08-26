from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.items.repository import ItemRepository, SqlAlchemyItemRepository


async def get_item_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ItemRepository:
    return SqlAlchemyItemRepository(session)
