import os
from ipaddress import ip_address
from typing import Literal
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DATABASE_QUERY_OPTIONS = frozenset({"prepared_statement_cache_size"})
MAX_PREPARED_STATEMENT_CACHE_SIZE = 1000
MAX_REDIS_DATABASE = 15
INGESTION_UNIX_SOCKET_PATHS = frozenset({"/run/postgresql", "/var/run/postgresql"})
DATABASE_ENVIRONMENT_OVERRIDES = frozenset(
    {
        "PGHOST",
        "PGPORT",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGUSER",
        "PGPASSWORD",
        "PGPASSFILE",
        "PGDATABASE",
        "PGSSLMODE",
        "PGSSLROOTCERT",
        "PGSSLCERT",
        "PGSSLKEY",
        "PGSSLCRL",
        "PGSSLPASSWORD",
        "PGSSLNEGOTIATION",
        "PGSSLMINPROTOCOLVERSION",
        "PGSSLMAXPROTOCOLVERSION",
        "PGTARGETSESSIONATTRS",
        "PGKRBSRVNAME",
        "PGGSSLIB",
        "SSLKEYLOGFILE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)


def validate_database_url(value: object) -> object:
    if not isinstance(value, str):
        raise ValueError("DATABASE_URL must use postgresql+asyncpg")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        query_values = parse_qs(parsed.query, keep_blank_values=True)
        normalized_query_values: dict[str, list[str]] = {}
        for key, values in query_values.items():
            normalized_query_values.setdefault(key.lower(), []).extend(values)
        query_keys = set(normalized_query_values)
        query_hosts = normalized_query_values.get("host", [])
        host_keys = {key for key in query_values if key.lower() == "host"}
        prepared_cache_values = normalized_query_values.get(
            "prepared_statement_cache_size", []
        )
        prepared_cache_size_valid = False
        if len(prepared_cache_values) == 1:
            prepared_cache_value = prepared_cache_values[0]
            normalized_cache_value = prepared_cache_value.lstrip("0") or "0"
            maximum_cache_value = str(MAX_PREPARED_STATEMENT_CACHE_SIZE)
            prepared_cache_size_valid = (
                len(prepared_cache_value) <= len(maximum_cache_value)
                and prepared_cache_value.isascii()
                and prepared_cache_value.isdigit()
                and (
                    len(normalized_cache_value) < len(maximum_cache_value)
                    or (
                        len(normalized_cache_value) == len(maximum_cache_value)
                        and normalized_cache_value <= maximum_cache_value
                    )
                )
            )
        decoded_hostname = (
            unquote(parsed.hostname) if parsed.hostname is not None else ""
        )
        invalid_hostname_characters = {",", "@", "/", "\\", "?", "#", "[", "]"}
        unix_socket = (
            parsed.hostname is None
            and (parsed.netloc == "" or parsed.netloc.endswith("@"))
            and (
                not host_keys
                or (
                    host_keys == {"host"}
                    and len(query_hosts) == 1
                    and query_hosts[0].startswith("/")
                    and "," not in query_hosts[0]
                )
            )
        )
        if (
            parsed.scheme != "postgresql+asyncpg"
            or any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for character in value
            )
            or parsed.fragment
            or "#" in value
            or (parsed.hostname is None and not unix_socket)
            or (bool(host_keys) and not unix_socket)
            or parsed.username == ""
            or parsed.password == ""
            or parsed.netloc.count("@") > 1
            or "," in parsed.netloc
            or any(
                character.isspace()
                or ord(character) < 32
                or ord(character) == 127
                or character in invalid_hostname_characters
                for character in decoded_hostname
            )
            or any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for host in query_hosts
                for character in host
            )
            or parsed.netloc.endswith(":")
            or (port is not None and not 1 <= port <= 65535)
            or parsed.path in {"", "/"}
            or set(query_values)
            - (DATABASE_QUERY_OPTIONS | ({"host"} if unix_socket else set()))
            or (
                "prepared_statement_cache_size" in query_keys
                and not prepared_cache_size_valid
            )
        ):
            raise ValueError
    except ValueError as exc:
        raise ValueError("DATABASE_URL must use postgresql+asyncpg") from exc
    return value


def validate_redis_url(value: object) -> object:
    if not isinstance(value, str):
        raise ValueError("REDIS_URL must use redis or rediss")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        decoded_hostname = unquote(parsed.hostname or "")
        decoded_parts = (
            unquote(part)
            for part in (
                decoded_hostname,
                parsed.username or "",
                parsed.password or "",
                parsed.path,
            )
        )
        database = parsed.path.removeprefix("/")
        if (
            parsed.scheme not in {"redis", "rediss"}
            or parsed.hostname is None
            or any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for character in value
            )
            or any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for part in decoded_parts
                for character in part
            )
            or "?" in value
            or "#" in value
            or parsed.query
            or parsed.fragment
            or parsed.username == ""
            or parsed.password == ""
            or parsed.netloc.count("@") > 1
            or "," in parsed.netloc
            or any(
                character in {",", "@", "/", "\\", "?", "#", "[", "]"}
                for character in decoded_hostname
            )
            or parsed.netloc.endswith(":")
            or (port is not None and not 1 <= port <= 65535)
            or (
                parsed.path not in {"", "/"}
                and (
                    not database.isascii()
                    or not database.isdigit()
                    or int(database) > MAX_REDIS_DATABASE
                )
            )
        ):
            raise ValueError
    except ValueError as exc:
        raise ValueError("REDIS_URL must use redis or rediss") from exc
    return value


def is_loopback_host(hostname: str | None) -> bool:
    if hostname == "localhost":
        return True
    try:
        return hostname is not None and ip_address(hostname).is_loopback
    except ValueError:
        return False


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: object) -> object:
        return validate_database_url(value)

    @model_validator(mode="after")
    def require_production_database_tls(self) -> "PostgresSettings":
        database = urlsplit(self.database_url.get_secret_value())
        database_query_keys = {
            key.lower() for key in parse_qs(database.query, keep_blank_values=True)
        }
        if self.environment != "production":
            return self

        if database.hostname is None and "host" not in database_query_keys:
            raise ValueError("Production DATABASE_URL must specify a host or socket")

        return self

    @property
    def database_requires_tls(self) -> bool:
        database = urlsplit(self.database_url.get_secret_value())
        return database.hostname is not None and (
            database.hostname
            not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }
        )


class Settings(PostgresSettings):
    app_name: str = "The Binding of Isaac API"
    app_version: str = "0.1.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    redis_url: SecretStr
    redis_max_connections: int = Field(default=20, ge=1, le=100)
    clerk_secret_key: SecretStr | None = None

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_url(cls, value: object) -> object:
        return validate_redis_url(value)

    @model_validator(mode="after")
    def require_production_redis_tls(self) -> "Settings":
        if self.environment != "production":
            return self

        redis = urlsplit(self.redis_url.get_secret_value())
        if not is_loopback_host(redis.hostname):
            if redis.scheme != "rediss":
                raise ValueError("Production REDIS_URL must use rediss")
            if redis.password is None:
                raise ValueError("Production remote REDIS_URL must specify a password")
        return self


class IngestionSettings(PostgresSettings):
    @model_validator(mode="after")
    def require_explicit_database_target(self) -> "IngestionSettings":
        database = urlsplit(self.database_url.get_secret_value())
        query_values = parse_qs(database.query, keep_blank_values=True)
        socket_hosts = query_values.get("host", [])
        if database.hostname is None and (
            len(socket_hosts) != 1 or socket_hosts[0] not in INGESTION_UNIX_SOCKET_PATHS
        ):
            raise ValueError(
                "Ingestion DATABASE_URL must specify a hostname or approved socket"
            )
        return self

    @model_validator(mode="after")
    def reject_database_driver_environment(self) -> "IngestionSettings":
        if any(variable in os.environ for variable in DATABASE_ENVIRONMENT_OVERRIDES):
            raise ValueError("DATABASE_URL must not use driver environment overrides")
        return self

    @model_validator(mode="after")
    def require_remote_database_credentials(self) -> "IngestionSettings":
        database = urlsplit(self.database_url.get_secret_value())
        if self.database_requires_tls and (
            database.username is None or database.password is None
        ):
            raise ValueError("Remote DATABASE_URL must specify credentials")
        return self
