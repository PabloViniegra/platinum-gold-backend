import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from typing import NoReturn, cast

from asyncpg import (  # type: ignore[reportMissingTypeStubs]
    InterfaceError,
    PostgresError,
)
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import IngestionSettings
from app.core.database import create_database
from app.core.exceptions import AppError
from app.core.redis import create_redis
from app.ingestion.loader import SnapshotLoadError, load_snapshot
from app.ingestion.service import IngestionService
from app.items.cache import RedisCacheClient, RedisItemCache

MAX_VALIDATION_ERRORS = 20
MAX_VALIDATION_TEXT = 160


class ConfigurationError(Exception):
    pass


class CacheInvalidationError(Exception):
    pass


class IngestionArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.exit(2, "Invalid command-line arguments\n")


def build_parser() -> argparse.ArgumentParser:
    parser = IngestionArgumentParser(description="Publish an item snapshot")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to the UTF-8 JSON snapshot",
    )
    return parser


def _safe_validation_text(value: object) -> str:
    escaped = str(value).encode("unicode_escape").decode("ascii")
    if len(escaped) > MAX_VALIDATION_TEXT:
        return escaped[:MAX_VALIDATION_TEXT] + "..."
    return escaped


def format_validation_error(error: ValidationError) -> str:
    details = error.errors()
    messages = [
        f"{_safe_validation_text('.'.join(str(part) for part in detail['loc']))}: "
        f"{_safe_validation_text(detail['msg'])}"
        for detail in details[:MAX_VALIDATION_ERRORS]
    ]
    if len(details) > MAX_VALIDATION_ERRORS:
        messages.append("additional validation errors omitted")
    return "; ".join(messages)


async def run_ingestion(input_path: Path) -> None:
    snapshot = load_snapshot(input_path)
    settings_factory = cast(Callable[[], IngestionSettings], IngestionSettings)
    try:
        settings = settings_factory()
        engine, session_factory = create_database(settings)
    except ValidationError as exc:
        raise ConfigurationError from exc
    except ValueError as exc:
        raise ConfigurationError from exc
    async with AsyncExitStack() as stack:
        stack.push_async_callback(engine.dispose)
        redis = create_redis(settings)
        stack.push_async_callback(redis.aclose)
        cache = RedisItemCache(cast(RedisCacheClient, redis))
        await IngestionService(session_factory).ingest(snapshot)
        try:
            await cache.invalidate()
        except (OSError, TimeoutError, RedisError, ValueError) as exc:
            raise CacheInvalidationError from exc


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        asyncio.run(run_ingestion(args.input))
    except SnapshotLoadError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValidationError as exc:
        print(f"Invalid snapshot: {format_validation_error(exc)}", file=sys.stderr)
        return 2
    except ConfigurationError:
        print("Ingestion failed: configuration is invalid", file=sys.stderr)
        return 2
    except CacheInvalidationError:
        print(
            "Ingestion failed: data was published but cache invalidation failed; "
            "repeat ingestion to retry",
            file=sys.stderr,
        )
        return 1
    except (
        AppError,
        InterfaceError,
        OSError,
        PostgresError,
        SQLAlchemyError,
        TimeoutError,
    ):
        print("Ingestion failed: required service is unavailable", file=sys.stderr)
        return 1
    except Exception:
        print("Ingestion failed: unexpected internal error", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
