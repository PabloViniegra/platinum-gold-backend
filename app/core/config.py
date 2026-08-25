from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_name: str = "The Binding of Isaac API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr
    redis_url: SecretStr
    clerk_secret_key: SecretStr | None = None
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: object) -> object:
        if not isinstance(value, str) or urlsplit(value).scheme != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_url(cls, value: object) -> object:
        if not isinstance(value, str) or urlsplit(value).scheme not in {
            "redis",
            "rediss",
        }:
            raise ValueError("REDIS_URL must use redis or rediss")
        return value

    @model_validator(mode="after")
    def require_production_tls(self) -> "Settings":
        if self.environment != "production":
            return self

        database = urlsplit(self.database_url.get_secret_value())
        database_query = parse_qs(database.query)
        if self.database_requires_tls and {"ssl", "sslmode"} & database_query.keys():
            raise ValueError("Production DATABASE_URL TLS is configured by the driver")

        redis = urlsplit(self.redis_url.get_secret_value())
        if redis.hostname not in {"localhost", "127.0.0.1", "::1"} and (
            redis.scheme != "rediss"
        ):
            raise ValueError("Production REDIS_URL must use rediss")
        return self

    @property
    def database_requires_tls(self) -> bool:
        database = urlsplit(self.database_url.get_secret_value())
        return self.environment == "production" and database.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
