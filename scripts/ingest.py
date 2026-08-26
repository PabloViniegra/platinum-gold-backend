import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.database import create_database
from app.core.exceptions import AppError
from app.ingestion.loader import SnapshotLoadError, load_snapshot
from app.ingestion.service import IngestionService


class ConfigurationError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish an item snapshot")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to the UTF-8 JSON snapshot",
    )
    return parser


def format_validation_error(error: ValidationError) -> str:
    return "; ".join(
        ".".join(str(part) for part in detail["loc"]) + f": {detail['msg']}"
        for detail in error.errors()
    )


async def run_ingestion(input_path: Path) -> None:
    snapshot = load_snapshot(input_path)
    settings_factory = cast(Callable[[], Settings], Settings)
    try:
        settings = settings_factory()
    except ValidationError as exc:
        raise ConfigurationError from exc
    engine, session_factory = create_database(settings)
    try:
        await IngestionService(session_factory).ingest(snapshot)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
    except (AppError, OSError, SQLAlchemyError, TimeoutError):
        print("Ingestion failed: required service is unavailable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
