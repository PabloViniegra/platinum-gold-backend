import asyncio
from collections.abc import Callable
from logging.config import fileConfig
from typing import cast

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import Settings
from app.core.database import database_connect_args
from app.items.models import Item

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings_factory = cast(Callable[[], Settings], Settings)
settings = settings_factory()
database_url = settings.database_url.get_secret_value()
target_metadata = Item.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(
        database_url,
        connect_args=database_connect_args(settings),
        poolclass=pool.NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
