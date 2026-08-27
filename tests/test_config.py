from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from app.core.config import IngestionSettings, Settings


def test_settings_accept_valid_runtime_configuration() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql+asyncpg://user:password@localhost/isaac_api",
            "redis_url": "redis://localhost:6379/0",
        }
    )

    assert settings.environment == "development"
    assert settings.log_level == "INFO"


def test_settings_accept_safe_asyncpg_query_options() -> None:
    settings = Settings.model_validate(
        {
            "database_url": (
                "postgresql+asyncpg://user:password@localhost/isaac_api"
                "?prepared_statement_cache_size=0"
            ),
            "redis_url": "redis://localhost:6379/0",
        }
    )

    assert settings.database_url.get_secret_value().endswith(
        "?prepared_statement_cache_size=0"
    )


def test_settings_require_database_and_redis_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings.model_validate({})


def test_ingestion_settings_require_only_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    settings = IngestionSettings.model_validate(
        {"database_url": "postgresql+asyncpg://localhost/isaac_api"}
    )

    assert settings.database_url.get_secret_value().startswith("postgresql+asyncpg://")


def test_ingestion_settings_accept_local_unix_socket_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    for database_url in (
        "postgresql+asyncpg:///isaac_api?host=%2Fvar%2Frun%2Fpostgresql",
        "postgresql+asyncpg://user:password@/isaac_api?host=%2Fvar%2Frun%2Fpostgresql",
    ):
        settings = IngestionSettings.model_validate({"database_url": database_url})

        assert settings.database_requires_tls is False


@pytest.mark.parametrize("variable", ["PGHOST", "PGSERVICE"])
def test_ingestion_settings_reject_driver_remote_target_override(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    monkeypatch.setenv(variable, "database.example")

    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {"database_url": ("postgresql+asyncpg://user:password@localhost/isaac_api")}
        )


@pytest.mark.parametrize(
    ("variable", "database_url"),
    [
        (
            "PGPORT",
            "postgresql+asyncpg://user:password@database.example/isaac_api",
        ),
        (
            "PGSERVICE",
            "postgresql+asyncpg://user:password@database.example:5432/isaac_api",
        ),
        (
            "PGUSER",
            "postgresql+asyncpg://user:password@localhost/isaac_api",
        ),
    ],
)
def test_ingestion_settings_rejects_unpinned_driver_target_fields(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    database_url: str,
) -> None:
    monkeypatch.setenv(variable, "5433" if variable == "PGPORT" else "remote")

    with pytest.raises(ValidationError):
        IngestionSettings.model_validate({"database_url": database_url})


@pytest.mark.parametrize("variable", ["PGPASSWORD", "PGPASSFILE"])
def test_ingestion_settings_rejects_empty_driver_credentials(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    monkeypatch.setenv(variable, "")

    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {"database_url": "postgresql+asyncpg://user@localhost/isaac_api"}
        )


@pytest.mark.parametrize(
    "variable",
    ["PGSSLMODE", "PGTARGETSESSIONATTRS", "SSL_CERT_FILE", "SSL_CERT_DIR"],
)
def test_ingestion_settings_rejects_ambient_connection_options(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    monkeypatch.setenv(variable, "disable")

    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {"database_url": ("postgresql+asyncpg://user:password@localhost/isaac_api")}
        )


def test_ingestion_settings_reject_ssl_keylog_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SSLKEYLOGFILE", "/tmp/postgres-keylog")

    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {"database_url": "postgresql+asyncpg://user:password@localhost/isaac_api"}
        )


@pytest.mark.parametrize("variable", ["PGHOST", "SSLKEYLOGFILE"])
def test_runtime_settings_allow_driver_environment_compatibility(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    monkeypatch.setenv(variable, "ambient-value")

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://user:password@localhost/isaac_api"
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    settings_factory = cast(Callable[[], Settings], Settings)
    settings = settings_factory()

    assert settings.database_url.get_secret_value().endswith("/isaac_api")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "postgresql://localhost/isaac_api"),
        (
            "database_url",
            "postgresql+asyncpg://localhost:not-a-port/isaac_api",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?host=remote.example",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?Host=remote.example",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api#?host=remote.example",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api#",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?sslmode=disable",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?ssl=require",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?database=other",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?user=other",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?password=other",
        ),
        (
            "database_url",
            "postgresql+asyncpg://user:@localhost/isaac_api",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?passfile=/tmp/pgpass",
        ),
        (
            "database_url",
            "postgresql+asyncpg://u:p@remote@@localhost/isaac_api",
        ),
        (
            "database_url",
            "postgresql+asyncpg://host1,host2:5432/isaac_api",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?prepared_statement_cache_size=abc",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?prepared_statement_cache_size=-1",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?prepared_statement_cache_size=",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?prepared_statement_cache_size=1&prepared_statement_cache_size=2",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?prepared_statement_cache_size=0&PREPARED_STATEMENT_CACHE_SIZE=999",
        ),
        (
            "database_url",
            "postgresql+asyncpg://localhost/isaac_api?prepared_statement_cache_size=1001",
        ),
        ("database_url", "postgresql+asyncpg://localhost"),
        (
            "database_url",
            "postgresql+asyncpg://localhost:0/isaac_api",
        ),
        (
            "database_url",
            "postgresql+asyncpg:///isaac_api?host=%2Flocal%2Cremote",
        ),
        (
            "database_url",
            "postgresql+asyncpg:///isaac_api?host=%2Ftmp%2Fpg%00socket",
        ),
        (
            "database_url",
            "postgresql+asyncpg:///isaac_api?service=remote",
        ),
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


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_ingestion_settings_require_explicit_database_target(
    environment: str,
) -> None:
    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {
                "environment": environment,
                "database_url": "postgresql+asyncpg:///isaac_api",
            }
        )


def test_ingestion_settings_reject_unapproved_socket_directory() -> None:
    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {"database_url": "postgresql+asyncpg:///isaac_api?host=%2Ftmp"}
        )


def test_settings_rejects_oversized_cache_representation() -> None:
    cache_size = "0" * 4301 + "1"
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "database_url": (
                    "postgresql+asyncpg://localhost/isaac_api?"
                    f"prepared_statement_cache_size={cache_size}"
                ),
                "redis_url": "redis://localhost:6379/0",
            }
        )


def test_ingestion_settings_require_user_for_remote_database() -> None:
    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {"database_url": "postgresql+asyncpg://database.example/isaac_api"}
        )


def test_ingestion_settings_require_password_for_remote_database() -> None:
    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {"database_url": "postgresql+asyncpg://user@database.example/isaac_api"}
        )


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
            "redis_url": "rediss://default:token@cache.example/0",
        }
    )

    assert settings.database_requires_tls is True


@pytest.mark.parametrize(
    "redis_url",
    [
        "redis://localhost:6379/0?socket_timeout=60",
        "redis://localhost:6379/0#fragment",
        "redis://localhost:6379/not-a-database",
        "redis://localhost:6379/16",
        "redis://localhost:0/0",
        "redis://host1,host2:6379/0",
        "redis://host1%2Chost2:6379/0",
        "redis://host%40other:6379/0",
        "redis://host%2Fother:6379/0",
        "redis://host%5Cother:6379/0",
        "redis://host%3Fother:6379/0",
        "redis://host%23other:6379/0",
        "redis://user:@localhost:6379/0",
        "redis://localhost:6379/0\n",
    ],
)
def test_settings_reject_unsafe_redis_urls(redis_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://localhost/isaac_api",
                "redis_url": redis_url,
            }
        )


def test_production_remote_redis_requires_password() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "environment": "production",
                "database_url": (
                    "postgresql+asyncpg://user:password@database.example/isaac_api"
                ),
                "redis_url": "rediss://cache.example:6379/0",
            }
        )


@pytest.mark.parametrize(
    "redis_url",
    [
        "redis://127.0.0.2:6379/0",
        "redis://[0:0:0:0:0:0:0:1]:6379/0",
    ],
)
def test_production_accepts_unencrypted_loopback_redis(redis_url: str) -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "database_url": (
                "postgresql+asyncpg://user:password@database.example/isaac_api"
            ),
            "redis_url": redis_url,
        }
    )

    assert settings.redis_url.get_secret_value() == redis_url


@pytest.mark.parametrize(
    "redis_url",
    [
        "redis://localhost:6379",
        "redis://localhost:6379/",
        "redis://localhost:6379/0",
        "rediss://default:token@cache.example:6379/15",
    ],
)
def test_settings_accept_safe_redis_urls(redis_url: str) -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql+asyncpg://localhost/isaac_api",
            "redis_url": redis_url,
        }
    )

    assert settings.redis_url.get_secret_value() == redis_url


@pytest.mark.parametrize(
    "field",
    [
        "cache_item_ttl_seconds",
        "cache_list_ttl_seconds",
        "cache_meta_ttl_seconds",
    ],
)
def test_settings_require_positive_cache_ttls(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://localhost/isaac_api",
                "redis_url": "redis://localhost:6379/0",
                field: 0,
            }
        )
