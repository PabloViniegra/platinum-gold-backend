import ssl
from collections.abc import AsyncGenerator
from typing import cast

from fastapi import Request
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings
from app.core.exceptions import AppError

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_database(
    settings: Settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        connect_args=database_connect_args(settings),
        pool_pre_ping=True,
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def database_connect_args(settings: Settings) -> dict[str, object]:
    connect_args: dict[str, object] = {
        "timeout": settings.dependency_timeout_seconds,
    }
    if settings.database_requires_tls:
        connect_args["ssl"] = ssl.create_default_context()
    return connect_args


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    session_factory = cast(
        async_sessionmaker[AsyncSession] | None,
        getattr(request.app.state, "session_factory", None),
    )
    if session_factory is None:
        raise AppError(
            503,
            "SERVICE_UNAVAILABLE",
            "A required service is unavailable",
        )
    async with session_factory() as session:
        yield session
