import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol, cast

from fastapi import Request
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

logger = logging.getLogger("app.health")


class RedisHealthClient(Protocol):
    async def ping(self) -> bool: ...


@dataclass(frozen=True)
class ReadinessResult:
    database: bool
    redis: bool

    @property
    def is_ready(self) -> bool:
        return self.database and self.redis


class ReadinessChecks:
    def __init__(
        self,
        database_engine: AsyncEngine,
        redis: RedisHealthClient,
        timeout: float,
    ) -> None:
        self.database_engine = database_engine
        self.redis = redis
        self.timeout = timeout

    async def run(self) -> ReadinessResult:
        database_task = asyncio.create_task(self._database_is_ready())
        redis_task = asyncio.create_task(self._redis_is_ready())
        try:
            database, redis = await asyncio.gather(database_task, redis_task)
        except BaseException:
            database_task.cancel()
            redis_task.cancel()
            await asyncio.gather(database_task, redis_task, return_exceptions=True)
            raise
        return ReadinessResult(database=database, redis=redis)

    async def _database_is_ready(self) -> bool:
        try:
            async with asyncio.timeout(self.timeout):
                async with self.database_engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
        except (TimeoutError, OSError, SQLAlchemyError) as exception:
            self._log_failure("database", exception)
            return False
        return True

    async def _redis_is_ready(self) -> bool:
        try:
            async with asyncio.timeout(self.timeout):
                return await self.redis.ping()
        except (TimeoutError, OSError, RedisError) as exception:
            self._log_failure("redis", exception)
            return False

    @staticmethod
    def _log_failure(dependency: str, exception: Exception) -> None:
        logger.warning(
            "readiness_check_failed",
            extra={
                "event": "readiness_check_failed",
                "dependency": dependency,
                "exception_type": type(exception).__name__,
            },
        )


def get_readiness_checks(request: Request) -> ReadinessChecks:
    settings = cast(Settings, request.app.state.settings)
    return ReadinessChecks(
        database_engine=cast(AsyncEngine, request.app.state.database_engine),
        redis=cast(RedisHealthClient, request.app.state.redis),
        timeout=settings.dependency_timeout_seconds,
    )
