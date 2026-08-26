import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import create_database
from app.ingestion.repository import SqlAlchemyIngestionRepository
from app.ingestion.schemas import ItemSnapshot
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
                yield session
            finally:
                try:
                    await session.close()
                finally:
                    if transaction.is_active:
                        await transaction.rollback()
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
