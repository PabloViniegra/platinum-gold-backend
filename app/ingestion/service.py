from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.repository import (
    IngestionRepository,
    SqlAlchemyIngestionRepository,
)
from app.ingestion.schemas import ItemSnapshot


def utc_now() -> datetime:
    return datetime.now(UTC)


class IngestionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        repository_factory: Callable[
            [AsyncSession], IngestionRepository
        ] = SqlAlchemyIngestionRepository,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._repository_factory = repository_factory
        self._clock = clock

    async def ingest(self, snapshot: ItemSnapshot) -> datetime:
        last_sync = self._clock()
        async with self._session_factory.begin() as session:
            repository = self._repository_factory(session)
            await repository.acquire_lock()
            current_last_sync = await repository.get_last_sync()
            if current_last_sync is not None and last_sync <= current_last_sync:
                return current_last_sync
            await repository.upsert_items(snapshot.items)
            await repository.upsert_metadata(
                dataset_version=snapshot.dataset_version,
                game_version=snapshot.game_version,
                last_sync=last_sync,
            )
        return last_sync
