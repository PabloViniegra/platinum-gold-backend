import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import create_database
from app.ingestion.repository import SqlAlchemyIngestionRepository
from app.ingestion.schemas import ItemSnapshot
from app.ingestion.service import IngestionService
from app.items.models import Item
from app.meta.models import DatasetMetadata
from scripts.validate_test_database import validate_test_database_url

configured_test_database_url = os.getenv("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        configured_test_database_url is None,
        reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests",
    ),
]


TEST_DATABASE_URL = configured_test_database_url


@pytest.fixture
async def database_session() -> AsyncIterator[AsyncSession]:
    if TEST_DATABASE_URL is None:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    try:
        database_url = validate_test_database_url(TEST_DATABASE_URL)
    except ValueError as exc:
        pytest.fail(str(exc), pytrace=False)
    if database_url is None:
        pytest.fail("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    settings = Settings.model_validate(
        {
            "database_url": database_url,
            "redis_url": "redis://localhost:6379/0",
            "clerk_secret_key": None,
            "environment": "test",
        }
    )
    engine, _ = create_database(settings)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                await session.execute(delete(Item))
                await session.execute(delete(DatasetMetadata))
                yield session
            finally:
                try:
                    await session.close()
                finally:
                    if transaction.is_active:
                        await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def committed_session_factory() -> AsyncIterator[
    async_sessionmaker[AsyncSession]
]:
    if TEST_DATABASE_URL is None:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    try:
        database_url = validate_test_database_url(TEST_DATABASE_URL)
    except ValueError as exc:
        pytest.fail(str(exc), pytrace=False)
    if database_url is None:
        pytest.fail("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    settings = Settings.model_validate(
        {
            "database_url": database_url,
            "redis_url": "redis://localhost:6379/0",
            "clerk_secret_key": None,
            "environment": "test",
        }
    )
    engine, session_factory = create_database(settings)
    try:
        yield session_factory
    finally:
        await engine.dispose()


def snapshot(*items: dict[str, object]) -> ItemSnapshot:
    return ItemSnapshot.model_validate(
        {
            "datasetVersion": "platinum-god-2026-08-26",
            "gameVersion": "repentance",
            "items": list(items),
        }
    )


def item_payload(
    game_id: int,
    name: str,
    *,
    quality: int,
    item_type: str,
) -> dict[str, object]:
    return {
        "gameId": game_id,
        "name": name,
        "description": f"Description for {name}",
        "quality": quality,
        "type": item_type,
        "rechargeTime": None,
        "imageUrl": f"https://example.com/{game_id}.png",
        "introducedInVersion": "repentance",
    }


async def capture_item_state(
    session: AsyncSession,
    game_id: int,
) -> dict[str, object] | None:
    item = await session.scalar(select(Item).where(Item.game_id == game_id))
    if item is None:
        return None
    return {
        "id": item.id,
        "game_id": item.game_id,
        "name": item.name,
        "description": item.description,
        "quality": item.quality,
        "item_type": item.item_type,
        "recharge_time": item.recharge_time,
        "image_url": item.image_url,
        "introduced_in_version": item.introduced_in_version,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


async def capture_metadata_state(
    session: AsyncSession,
) -> dict[str, object] | None:
    metadata = await session.scalar(select(DatasetMetadata))
    if metadata is None:
        return None
    return {
        "id": metadata.id,
        "dataset_version": metadata.dataset_version,
        "game_version": metadata.game_version,
        "last_sync": metadata.last_sync,
    }


async def restore_test_state(
    session_factory: async_sessionmaker[AsyncSession],
    game_id: int,
    item_state: dict[str, object] | None,
    metadata_state: dict[str, object] | None,
) -> None:
    async with session_factory.begin() as session:
        await session.execute(delete(Item).where(Item.game_id == game_id))
        if item_state is not None:
            await session.execute(insert(Item).values(item_state))
        await session.execute(delete(DatasetMetadata))
        if metadata_state is not None:
            await session.execute(insert(DatasetMetadata).values(metadata_state))


@pytest.mark.asyncio
async def test_repository_upserts_items_and_dataset_metadata(
    database_session: AsyncSession,
) -> None:
    first_snapshot = snapshot(
        item_payload(118, "Brimstone", quality=4, item_type="passive"),
        item_payload(1, "The Sad Onion", quality=3, item_type="passive"),
    )
    repository = SqlAlchemyIngestionRepository(database_session)
    first_sync = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)

    await repository.upsert_items(first_snapshot.items)
    await repository.upsert_metadata(
        dataset_version=first_snapshot.dataset_version,
        game_version=first_snapshot.game_version,
        last_sync=first_sync,
    )
    await database_session.flush()

    initial = await database_session.scalar(
        select(Item).where(Item.game_id == 118),
    )
    assert initial is not None
    initial_id = initial.id
    initial_created_at = initial.created_at

    second_snapshot = snapshot(
        item_payload(118, "Brimstone Updated", quality=3, item_type="active"),
    )
    second_sync = datetime(2026, 8, 26, 11, 30, tzinfo=UTC)

    await repository.upsert_items(second_snapshot.items)
    await repository.upsert_metadata(
        dataset_version="platinum-god-2026-08-27",
        game_version="repentance",
        last_sync=second_sync,
    )
    await database_session.flush()
    await database_session.refresh(initial)

    updated = await database_session.scalar(
        select(Item).where(Item.game_id == 118),
    )
    rows = (await database_session.scalars(select(Item))).all()
    metadata = await database_session.scalar(select(DatasetMetadata))

    assert updated is not None
    assert updated.id == initial_id
    assert updated.created_at == initial_created_at
    assert updated.name == "Brimstone Updated"
    assert updated.quality == 3
    assert updated.item_type == "active"
    assert len(rows) == 2
    assert metadata is not None
    assert metadata.id == 1
    assert metadata.dataset_version == "platinum-god-2026-08-27"
    assert metadata.game_version == "repentance"
    assert metadata.last_sync == second_sync


@pytest.mark.asyncio
async def test_repository_repeating_snapshot_keeps_one_row(
    database_session: AsyncSession,
) -> None:
    repeated_snapshot = snapshot(
        item_payload(200000, "Repeated Item", quality=2, item_type="passive"),
    )
    repository = SqlAlchemyIngestionRepository(database_session)
    sync_time = datetime(2026, 8, 26, 12, 30, tzinfo=UTC)

    await repository.upsert_items(repeated_snapshot.items)
    await repository.upsert_metadata(
        dataset_version=repeated_snapshot.dataset_version,
        game_version=repeated_snapshot.game_version,
        last_sync=sync_time,
    )
    await database_session.flush()
    await repository.upsert_items(repeated_snapshot.items)
    await repository.upsert_metadata(
        dataset_version=repeated_snapshot.dataset_version,
        game_version=repeated_snapshot.game_version,
        last_sync=sync_time,
    )
    await database_session.flush()
    older_sync = datetime(2026, 8, 26, 11, 30, tzinfo=UTC)
    await repository.upsert_metadata(
        dataset_version=repeated_snapshot.dataset_version,
        game_version=repeated_snapshot.game_version,
        last_sync=older_sync,
    )
    await database_session.flush()

    rows = (
        await database_session.scalars(
            select(Item).where(Item.game_id == 200000),
        )
    ).all()
    metadata = await database_session.scalar(select(DatasetMetadata))

    assert len(rows) == 1
    assert rows[0].name == "Repeated Item"
    assert metadata is not None
    await database_session.refresh(metadata)
    assert metadata.dataset_version == repeated_snapshot.dataset_version
    assert metadata.last_sync == sync_time

    stale_snapshot = ItemSnapshot.model_validate(
        {
            "datasetVersion": "platinum-god-2026-08-25",
            "gameVersion": "rebirth",
            "items": repeated_snapshot.model_dump(by_alias=True)["items"],
        }
    )
    await repository.upsert_metadata(
        dataset_version=stale_snapshot.dataset_version,
        game_version=stale_snapshot.game_version,
        last_sync=older_sync,
    )
    await database_session.flush()
    await database_session.refresh(metadata)

    assert metadata.dataset_version == repeated_snapshot.dataset_version
    assert metadata.game_version == repeated_snapshot.game_version
    assert metadata.last_sync == sync_time


@pytest.mark.asyncio
async def test_ingestion_service_commit_is_visible_to_new_session(
    committed_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    game_id = 200001
    sync_time = datetime(2026, 8, 26, 13, 30, tzinfo=UTC)
    async with committed_session_factory() as session:
        previous_item = await capture_item_state(session, game_id)
        previous_metadata = await capture_metadata_state(session)
    if previous_metadata is not None:
        previous_sync = previous_metadata["last_sync"]
        if isinstance(previous_sync, datetime):
            sync_time = max(sync_time, previous_sync + timedelta(microseconds=1))

    try:
        await IngestionService(
            committed_session_factory,
            clock=lambda: sync_time,
        ).ingest(
            snapshot(
                item_payload(game_id, "Committed Item", quality=1, item_type="active")
            )
        )

        async with committed_session_factory() as session:
            persisted = await session.scalar(
                select(Item).where(Item.game_id == game_id),
            )
            metadata = await session.scalar(select(DatasetMetadata))

        assert persisted is not None
        assert persisted.name == "Committed Item"
        assert metadata is not None
        assert metadata.last_sync == sync_time
    finally:
        await restore_test_state(
            committed_session_factory,
            game_id,
            previous_item,
            previous_metadata,
        )


class FailingMetadataRepository(SqlAlchemyIngestionRepository):
    async def upsert_metadata(
        self,
        *,
        dataset_version: str,
        game_version: str | None,
        last_sync: datetime,
    ) -> None:
        raise RuntimeError("metadata write failed")


@pytest.mark.asyncio
async def test_ingestion_service_rolls_back_items_when_metadata_fails(
    committed_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    game_id = 200002
    sync_time = datetime(2026, 8, 26, 13, 30, tzinfo=UTC)
    async with committed_session_factory() as session:
        previous_item = await capture_item_state(session, game_id)
        previous_metadata = await capture_metadata_state(session)
    if previous_metadata is not None:
        previous_sync = previous_metadata["last_sync"]
        if isinstance(previous_sync, datetime):
            sync_time = max(sync_time, previous_sync + timedelta(microseconds=1))

    try:
        with pytest.raises(RuntimeError, match="metadata write failed"):
            await IngestionService(
                committed_session_factory,
                repository_factory=FailingMetadataRepository,
                clock=lambda: sync_time,
            ).ingest(
                snapshot(
                    item_payload(
                        game_id,
                        "Rolled Back Item",
                        quality=1,
                        item_type="active",
                    )
                )
            )

        async with committed_session_factory() as session:
            persisted = await capture_item_state(session, game_id)
            metadata = await capture_metadata_state(session)

        assert persisted == previous_item
        assert metadata == previous_metadata
    finally:
        await restore_test_state(
            committed_session_factory,
            game_id,
            previous_item,
            previous_metadata,
        )
