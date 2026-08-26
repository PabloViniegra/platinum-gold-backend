from collections.abc import Callable
from typing import cast

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class FakeRedis:
    def __init__(self, close_error: Exception | None = None) -> None:
        self.closed = False
        self.close_error = close_error

    async def aclose(self) -> None:
        self.closed = True
        if self.close_error:
            raise self.close_error


def build_database_factory(
    engine: FakeEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[Settings], tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    def create_database(
        _settings: Settings,
    ) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
        return cast(AsyncEngine, engine), session_factory

    return create_database


def build_redis_factory(redis: FakeRedis) -> Callable[[Settings], Redis]:
    def create_redis(_settings: Settings) -> Redis:
        return cast(Redis, redis)

    return create_redis


def fail_redis_creation(_settings: Settings) -> Redis:
    raise RuntimeError("redis creation failed")


@pytest.mark.asyncio
async def test_lifespan_creates_and_closes_runtime_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    redis = FakeRedis()
    session_factory = cast(async_sessionmaker[AsyncSession], object())
    settings = Settings.model_validate(
        {
            "database_url": "postgresql+asyncpg://localhost/isaac_api",
            "redis_url": "redis://localhost:6379/0",
            "clerk_secret_key": None,
            "app_version": "9.8.7",
        }
    )
    database_factory = build_database_factory(engine, session_factory)
    redis_factory = build_redis_factory(redis)
    monkeypatch.setattr("app.main.create_database", database_factory)
    monkeypatch.setattr("app.main.create_redis", redis_factory)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        assert app.state.database_engine is engine
        assert app.state.session_factory is session_factory
        assert app.state.redis is redis
        assert app.version == "9.8.7"

    assert engine.disposed is True
    assert redis.closed is True


@pytest.mark.asyncio
async def test_lifespan_disposes_database_when_redis_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    session_factory = cast(async_sessionmaker[AsyncSession], object())
    database_factory = build_database_factory(engine, session_factory)
    monkeypatch.setattr("app.main.create_database", database_factory)
    monkeypatch.setattr(
        "app.main.create_redis",
        fail_redis_creation,
    )
    app = create_app(
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://localhost/isaac_api",
                "redis_url": "redis://localhost:6379/0",
                "clerk_secret_key": None,
            }
        )
    )

    with pytest.raises(RuntimeError, match="redis creation failed"):
        async with app.router.lifespan_context(app):
            pass

    assert engine.disposed is True


@pytest.mark.asyncio
async def test_lifespan_disposes_database_when_redis_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    redis = FakeRedis(RuntimeError("redis close failed"))
    session_factory = cast(async_sessionmaker[AsyncSession], object())
    database_factory = build_database_factory(engine, session_factory)
    redis_factory = build_redis_factory(redis)
    monkeypatch.setattr("app.main.create_database", database_factory)
    monkeypatch.setattr("app.main.create_redis", redis_factory)
    app = create_app(
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://localhost/isaac_api",
                "redis_url": "redis://localhost:6379/0",
                "clerk_secret_key": None,
            }
        )
    )

    with pytest.raises(RuntimeError, match="redis close failed"):
        async with app.router.lifespan_context(app):
            pass

    assert redis.closed is True
    assert engine.disposed is True
