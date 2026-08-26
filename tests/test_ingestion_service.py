from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.repository import IngestionRepository
from app.ingestion.schemas import ItemImport, ItemSnapshot
from app.ingestion.service import IngestionService


class FakeTransaction(AbstractAsyncContextManager[AsyncSession]):
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> AsyncSession:
        return cast(AsyncSession, object())

    async def __aexit__(self, exc_type: object, *_args: object) -> None:
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True


class FakeSessionFactory:
    def __init__(self, transaction: FakeTransaction) -> None:
        self.transaction = transaction

    def begin(self) -> FakeTransaction:
        return self.transaction


class RecordingRepository:
    def __init__(self, *, fail_on_metadata: bool = False) -> None:
        self.items: list[ItemImport] = []
        self.metadata: tuple[str, str | None, datetime] | None = None
        self.fail_on_metadata = fail_on_metadata

    async def upsert_items(self, items: Sequence[ItemImport]) -> None:
        self.items = list(items)

    async def upsert_metadata(
        self,
        *,
        dataset_version: str,
        game_version: str | None,
        last_sync: datetime,
    ) -> None:
        if self.fail_on_metadata:
            raise RuntimeError("metadata write failed")
        self.metadata = (dataset_version, game_version, last_sync)


def build_snapshot() -> ItemSnapshot:
    return ItemSnapshot.model_validate(
        {
            "datasetVersion": "platinum-god-2026-08-26",
            "gameVersion": "repentance",
            "items": [
                {
                    "gameId": 118,
                    "name": "Brimstone",
                    "description": "Tears are replaced by a laser beam.",
                    "quality": 4,
                    "type": "passive",
                    "rechargeTime": None,
                    "imageUrl": "https://example.com/118.png",
                    "introducedInVersion": "rebirth",
                }
            ],
        }
    )


def build_service(
    transaction: FakeTransaction,
    repository: IngestionRepository,
    *,
    clock: Callable[[], datetime],
) -> IngestionService:
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        FakeSessionFactory(transaction),
    )
    return IngestionService(
        session_factory,
        repository_factory=lambda _session: repository,
        clock=clock,
    )


@pytest.mark.asyncio
async def test_ingestion_service_commits_items_and_metadata_together() -> None:
    transaction = FakeTransaction()
    repository = RecordingRepository()
    sync_time = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)
    service = build_service(transaction, repository, clock=lambda: sync_time)

    result = await service.ingest(build_snapshot())

    assert result == sync_time
    assert transaction.committed is True
    assert transaction.rolled_back is False
    assert len(repository.items) == 1
    assert repository.metadata == (
        "platinum-god-2026-08-26",
        "repentance",
        sync_time,
    )


@pytest.mark.asyncio
async def test_ingestion_service_rolls_back_when_metadata_fails() -> None:
    transaction = FakeTransaction()
    repository = RecordingRepository(fail_on_metadata=True)
    service = build_service(
        transaction,
        repository,
        clock=lambda: datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="metadata write failed"):
        await service.ingest(build_snapshot())

    assert transaction.committed is False
    assert transaction.rolled_back is True
    assert repository.metadata is None
