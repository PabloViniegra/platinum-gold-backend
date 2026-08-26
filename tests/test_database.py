import ssl
from pathlib import Path

import pytest

from app.core.config import IngestionSettings, Settings
from app.core.database import database_connect_args


def test_remote_production_database_uses_verified_tls() -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "database_url": (
                "postgresql+asyncpg://user:password@database.example/isaac_api"
            ),
            "redis_url": "rediss://cache.example/0",
        }
    )

    context = database_connect_args(settings)["ssl"]

    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_remote_ingestion_database_uses_verified_tls() -> None:
    settings = IngestionSettings.model_validate(
        {
            "database_url": (
                "postgresql+asyncpg://user:password@database.example/isaac_api"
            )
        }
    )

    context = database_connect_args(settings)["ssl"]

    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_remote_database_tls_disables_key_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = IngestionSettings.model_validate(
        {
            "database_url": (
                "postgresql+asyncpg://user:password@database.example/isaac_api"
            )
        }
    )
    monkeypatch.setenv("SSLKEYLOGFILE", "/tmp/postgres-keylog")

    context = database_connect_args(settings)["ssl"]

    assert isinstance(context, ssl.SSLContext)
    assert context.keylog_filename is None


def test_remote_database_tls_does_not_create_keylog_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = IngestionSettings.model_validate(
        {
            "database_url": (
                "postgresql+asyncpg://user:password@database.example/isaac_api"
            )
        }
    )
    keylog_path = tmp_path / "postgres-keylog"
    monkeypatch.setenv("SSLKEYLOGFILE", str(keylog_path))

    database_connect_args(settings)

    assert not keylog_path.exists()


def test_database_command_timeout_matches_dependency_timeout() -> None:
    settings = IngestionSettings.model_validate(
        {
            "database_url": (
                "postgresql+asyncpg://user:password@database.example/isaac_api"
            )
        }
    )

    assert database_connect_args(settings)["command_timeout"] == (
        settings.dependency_timeout_seconds
    )


def test_production_unix_socket_does_not_use_network_tls() -> None:
    settings = IngestionSettings.model_validate(
        {
            "environment": "production",
            "database_url": (
                "postgresql+asyncpg://user:password@/isaac_api?host=%2Fvar%2Frun%2Fpostgresql"
            ),
        }
    )

    assert "ssl" not in database_connect_args(settings)
