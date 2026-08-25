import asyncio
from typing import cast

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.health.checks import ReadinessChecks, RedisHealthClient


class FakeConnection:
    def __init__(
        self,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.error = error
        self.delay = delay

    async def __aenter__(self) -> "FakeConnection":
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _statement: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnection:
        return self.connection


class FakeRedis:
    def __init__(
        self,
        response: bool = True,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.response = response
        self.error = error
        self.delay = delay

    async def ping(self) -> bool:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.response


class CoordinatedFailureConnection(FakeConnection):
    def __init__(self, redis_started: asyncio.Event) -> None:
        super().__init__()
        self.redis_started = redis_started

    async def __aenter__(self) -> "FakeConnection":
        await self.redis_started.wait()
        raise RuntimeError("bug")


class CancellableRedis(FakeRedis):
    def __init__(self, started: asyncio.Event) -> None:
        super().__init__()
        self.started = started
        self.cancelled = False

    async def ping(self) -> bool:
        self.started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return True


def build_checks(
    connection: FakeConnection | None = None,
    redis: FakeRedis | None = None,
    timeout: float = 0.1,
) -> ReadinessChecks:
    return ReadinessChecks(
        database_engine=cast(AsyncEngine, FakeEngine(connection or FakeConnection())),
        redis=cast(RedisHealthClient, redis or FakeRedis()),
        timeout=timeout,
    )


@pytest.mark.asyncio
async def test_readiness_checks_report_healthy_dependencies() -> None:
    result = await build_checks().run()

    assert result.database is True
    assert result.redis is True


@pytest.mark.asyncio
async def test_readiness_checks_preserve_negative_redis_ping() -> None:
    result = await build_checks(redis=FakeRedis(response=False)).run()

    assert result.database is True
    assert result.redis is False


@pytest.mark.asyncio
async def test_readiness_checks_convert_expected_failures_to_down() -> None:
    database_error = OperationalError("SELECT 1", {}, Exception("connection"))
    redis_error = RedisConnectionError("connection")

    result = await build_checks(
        connection=FakeConnection(error=database_error),
        redis=FakeRedis(error=redis_error),
    ).run()

    assert result.database is False
    assert result.redis is False


@pytest.mark.asyncio
async def test_readiness_checks_enforce_timeout() -> None:
    result = await build_checks(
        connection=FakeConnection(delay=0.05),
        redis=FakeRedis(delay=0.05),
        timeout=0.001,
    ).run()

    assert result.database is False
    assert result.redis is False


@pytest.mark.asyncio
async def test_readiness_checks_do_not_hide_programming_errors() -> None:
    checks = build_checks(connection=FakeConnection(error=RuntimeError("bug")))

    with pytest.raises(RuntimeError, match="bug"):
        await checks.run()


@pytest.mark.asyncio
async def test_readiness_checks_cancel_sibling_after_programming_error() -> None:
    redis_started = asyncio.Event()
    redis = CancellableRedis(redis_started)
    checks = build_checks(
        connection=CoordinatedFailureConnection(redis_started),
        redis=redis,
    )

    with pytest.raises(RuntimeError, match="bug"):
        await checks.run()

    assert redis.cancelled is True
