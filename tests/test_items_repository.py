from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.items.repository import SqlAlchemyItemRepository


class FailingSession:
    async def execute(self, statement: object) -> object:
        raise ConnectionRefusedError("database is unavailable")


@pytest.mark.asyncio
async def test_repository_maps_connection_failure_to_service_unavailable() -> None:
    repository = SqlAlchemyItemRepository(cast(AsyncSession, FailingSession()))

    with pytest.raises(AppError) as caught:
        await repository.count_items(
            search=None,
            quality=None,
            item_type=None,
            version=None,
        )

    assert caught.value.status_code == 503
    assert caught.value.code == "SERVICE_UNAVAILABLE"
