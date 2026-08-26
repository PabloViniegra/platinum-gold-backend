import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import create_database
from app.items.models import Item
from app.items.repository import SqlAlchemyItemRepository
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


def item(
    game_id: int,
    name: str,
    *,
    item_id: int,
    quality: int,
    item_type: str,
    version: str,
) -> Item:
    return Item(
        id=item_id,
        game_id=game_id,
        name=name,
        description=f"Description for {name}",
        quality=quality,
        item_type=item_type,
        recharge_time=None,
        image_url=f"https://example.com/{game_id}.png",
        introduced_in_version=version,
    )


@pytest.mark.asyncio
async def test_repository_reads_and_filters_items(
    database_session: AsyncSession,
) -> None:
    database_session.add_all(
        [
            item(
                118,
                "Brimstone",
                item_id=1,
                quality=4,
                item_type="passive",
                version="rebirth",
            ),
            item(
                1,
                "The Sad Onion",
                item_id=2,
                quality=3,
                item_type="passive",
                version="rebirth",
            ),
            item(
                999,
                "100%_Damage",
                item_id=3,
                quality=2,
                item_type="active",
                version="repentance",
            ),
            item(
                1000,
                "100xxDamage",
                item_id=4,
                quality=2,
                item_type="active",
                version="repentance",
            ),
            item(
                1001,
                "100%XDamage",
                item_id=5,
                quality=2,
                item_type="active",
                version="repentance",
            ),
            item(
                1002,
                "100QualityOther",
                item_id=6,
                quality=3,
                item_type="active",
                version="repentance",
            ),
            item(
                1003,
                "100TypeOther",
                item_id=7,
                quality=2,
                item_type="passive",
                version="repentance",
            ),
            item(
                1004,
                "100VersionOther",
                item_id=8,
                quality=2,
                item_type="active",
                version="rebirth",
            ),
        ]
    )
    await database_session.flush()
    repository = SqlAlchemyItemRepository(database_session)

    result = await repository.get_by_game_id(118)
    escaped_search = await repository.list_items(
        search="100%_",
        quality=2,
        item_type="active",
        version="repentance",
        sort="name",
        order="asc",
        limit=20,
        offset=0,
    )
    first_page = await repository.list_items(
        search="100",
        quality=2,
        item_type="active",
        version="repentance",
        sort="game_id",
        order="asc",
        limit=1,
        offset=0,
    )
    second_page = await repository.list_items(
        search="100",
        quality=2,
        item_type="active",
        version="repentance",
        sort="game_id",
        order="asc",
        limit=1,
        offset=1,
    )
    total = await repository.count_items(
        search=None,
        quality=2,
        item_type="active",
        version="repentance",
    )
    catalog_meta = await repository.get_catalog_meta()

    assert result is not None
    assert result.name == "Brimstone"
    assert [matching.name for matching in escaped_search] == ["100%_Damage"]
    assert [matching.name for matching in first_page] == ["100%_Damage"]
    assert [matching.name for matching in second_page] == ["100xxDamage"]
    assert total == 3
    assert catalog_meta.items == 8
    assert catalog_meta.metadata is None


@pytest.mark.asyncio
async def test_repository_random_returns_matching_item(
    database_session: AsyncSession,
) -> None:
    database_session.add_all(
        [
            item(
                118,
                "Brimstone",
                item_id=10,
                quality=4,
                item_type="passive",
                version="rebirth",
            ),
            item(
                1,
                "The Sad Onion",
                item_id=11,
                quality=3,
                item_type="passive",
                version="rebirth",
            ),
        ]
    )
    await database_session.flush()
    repository = SqlAlchemyItemRepository(database_session)

    no_match = await repository.get_random(
        search=None,
        quality=0,
        item_type="active",
        version="repentance",
    )

    result = await repository.get_random(
        search=None,
        quality=4,
        item_type="passive",
        version="rebirth",
    )

    assert no_match is None
    assert result is not None
    assert result.game_id == 118
