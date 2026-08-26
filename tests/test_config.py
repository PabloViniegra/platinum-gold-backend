from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_accept_valid_runtime_configuration() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql+asyncpg://user:password@localhost/isaac_api",
            "redis_url": "redis://localhost:6379/0",
        }
    )

    assert settings.environment == "development"
    assert settings.log_level == "INFO"


def test_settings_require_database_and_redis_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings.model_validate({})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "postgresql://localhost/isaac_api"),
        ("redis_url", "http://localhost:6379/0"),
    ],
)
def test_settings_reject_incompatible_url_schemes(field: str, value: str) -> None:
    values = {
        "database_url": "postgresql+asyncpg://localhost/isaac_api",
        "redis_url": "redis://localhost:6379/0",
        field: value,
    }

    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_settings_repr_does_not_expose_credentials() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql+asyncpg://user:db-secret@localhost/isaac_api",
            "redis_url": "redis://user:redis-secret@localhost:6379/0",
            "clerk_secret_key": "clerk-secret",
        }
    )

    representation = repr(settings)

    assert "db-secret" not in representation
    assert "redis-secret" not in representation
    assert "clerk-secret" not in representation


def test_validation_errors_do_not_expose_credentials() -> None:
    with pytest.raises(ValidationError) as error:
        Settings.model_validate(
            {
                "database_url": "postgresql://user:db-secret@localhost/isaac_api",
                "redis_url": "http://user:redis-secret@localhost:6379/0",
            }
        )

    message = str(error.value)

    assert "db-secret" not in message
    assert "redis-secret" not in message


@pytest.mark.parametrize(
    ("database_url", "redis_url"),
    [
        (
            "postgresql+asyncpg://user:password@database.example/isaac_api?sslmode=require",
            "rediss://cache.example/0",
        ),
        (
            "postgresql+asyncpg://user:password@database.example/isaac_api?ssl=require",
            "redis://cache.example/0",
        ),
    ],
)
def test_production_requires_tls_for_remote_services(
    database_url: str,
    redis_url: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "environment": "production",
                "database_url": database_url,
                "redis_url": redis_url,
            }
        )


def test_production_enables_driver_tls_for_remote_database() -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "database_url": (
                "postgresql+asyncpg://user:password@database.example/isaac_api"
            ),
            "redis_url": "rediss://cache.example/0",
        }
    )

    assert settings.database_requires_tls is True
