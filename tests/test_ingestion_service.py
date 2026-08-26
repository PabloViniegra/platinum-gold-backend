from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.repository import IngestionRepository
from app.ingestion.schemas import ItemImport, ItemSnapshot
from app.ingestion.service import IngestionService


class RecordingRepository:
    def __init__(self, *, fail_on_metadata: bool = False) -> None:
        self.items: list[ItemImport] = []
        self.metadata: tuple[str, str | None, datetime] | None = None
        self.fail_on_metadata = fail_on_metadata

    async def upsert_items(self, items: Sequence[ItemImport]) -> None:
        self.items = list(items)

    async def acquire_lock(self) -> None:
        pass

    async def get_last_sync(self) -> datetime | None:
        return None if self.metadata is None else self.metadata[2]

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


class OrderingRepository(RecordingRepository):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    async def acquire_lock(self) -> None:
        self.events.append("lock")


class FakeTransaction(AbstractAsyncContextManager[AsyncSession]):
    def __init__(self, repository: RecordingRepository) -> None:
        self.repository = repository
        self.initial_items: list[ItemImport] = []
        self.initial_metadata: tuple[str, str | None, datetime] | None = None
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> AsyncSession:
        self.initial_items = list(self.repository.items)
        self.initial_metadata = self.repository.metadata
        return cast(AsyncSession, object())

    async def __aexit__(self, exc_type: object, *_args: object) -> None:
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True
            self.repository.items = self.initial_items
            self.repository.metadata = self.initial_metadata


class FakeSessionFactory:
    def __init__(self, transaction: FakeTransaction) -> None:
        self.transaction = transaction

    def begin(self) -> FakeTransaction:
        return self.transaction


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
    repository: RecordingRepository,
    *,
    clock: Callable[[], datetime],
) -> tuple[IngestionService, FakeTransaction]:
    transaction = FakeTransaction(repository)
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        FakeSessionFactory(transaction),
    )
    service = IngestionService(
        session_factory,
        repository_factory=lambda _session: cast(IngestionRepository, repository),
        clock=clock,
    )
    return service, transaction


@pytest.mark.asyncio
async def test_ingestion_service_commits_items_and_metadata_together() -> None:
    repository = RecordingRepository()
    sync_time = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)
    service, transaction = build_service(repository, clock=lambda: sync_time)

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
    repository = RecordingRepository(fail_on_metadata=True)
    service, transaction = build_service(
        repository,
        clock=lambda: datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="metadata write failed"):
        await service.ingest(build_snapshot())

    assert transaction.committed is False
    assert transaction.rolled_back is True
    assert repository.items == []
    assert repository.metadata is None


@pytest.mark.asyncio
async def test_ingestion_service_skips_an_older_snapshot() -> None:
    existing_sync = datetime(2026, 8, 26, 11, 30, tzinfo=UTC)
    repository = RecordingRepository()
    repository.items = list(build_snapshot().items)
    repository.metadata = ("newer-dataset", "repentance", existing_sync)
    older_snapshot = ItemSnapshot.model_validate(
        {
            "datasetVersion": "older-dataset",
            "gameVersion": "rebirth",
            "items": [
                {
                    **build_snapshot().model_dump(by_alias=True)["items"][0],
                    "name": "Older name",
                }
            ],
        }
    )
    service, transaction = build_service(
        repository,
        clock=lambda: datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
    )

    result = await service.ingest(older_snapshot)

    assert result == existing_sync
    assert transaction.committed is True
    assert repository.items == list(build_snapshot().items)
    assert repository.metadata == ("newer-dataset", "repentance", existing_sync)


@pytest.mark.asyncio
async def test_ingestion_service_timestamps_before_waiting_for_lock() -> None:
    events: list[str] = []
    repository = OrderingRepository(events)
    sync_time = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)

    def clock() -> datetime:
        events.append("clock")
        return sync_time

    service, _transaction = build_service(repository, clock=clock)

    await service.ingest(build_snapshot())

    assert events[:2] == ["clock", "lock"]
