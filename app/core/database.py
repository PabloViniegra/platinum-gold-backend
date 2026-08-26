import ssl
from collections.abc import AsyncGenerator
from typing import Protocol, cast

from fastapi import Request
from pydantic import SecretStr
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

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


class DatabaseSettings(Protocol):
    database_url: SecretStr
    dependency_timeout_seconds: float

    @property
    def database_requires_tls(self) -> bool: ...


def create_database(
    settings: DatabaseSettings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        connect_args=database_connect_args(settings),
        pool_pre_ping=True,
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def database_connect_args(settings: DatabaseSettings) -> dict[str, object]:
    connect_args: dict[str, object] = {
        "timeout": settings.dependency_timeout_seconds,
        "command_timeout": settings.dependency_timeout_seconds,
    }
    if settings.database_requires_tls:
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        tls_context.verify_mode = ssl.CERT_REQUIRED
        tls_context.check_hostname = True
        tls_context.verify_flags |= (
            ssl.VERIFY_X509_PARTIAL_CHAIN | ssl.VERIFY_X509_STRICT
        )
        tls_context.load_default_certs(ssl.Purpose.SERVER_AUTH)
        connect_args["ssl"] = tls_context
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
