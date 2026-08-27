from typing import cast

import pytest
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.redis import create_redis


def build_settings(redis_url: str) -> Settings:
    return Settings.model_validate(
        {
            "database_url": "postgresql+asyncpg://localhost/isaac_api",
            "redis_url": redis_url,
            "dependency_timeout_seconds": 1.5,
        }
    )


def test_create_redis_bounds_pool_and_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    client = cast(Redis, object())

    def fake_from_url(url: str, **kwargs: object) -> Redis:
        captured["url"] = url
        captured.update(kwargs)
        return client

    monkeypatch.setattr("app.core.redis.from_url", fake_from_url)

    result = create_redis(build_settings("redis://localhost:6379/0"))

    assert result is client
    assert captured == {
        "url": "redis://localhost:6379/0",
        "decode_responses": True,
        "socket_connect_timeout": 1.5,
        "socket_timeout": 1.5,
        "max_connections": 20,
    }


def test_create_redis_enforces_tls_certificate_and_hostname_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_from_url(_url: str, **kwargs: object) -> Redis:
        captured.update(kwargs)
        return cast(Redis, object())

    monkeypatch.setattr("app.core.redis.from_url", fake_from_url)

    create_redis(build_settings("rediss://default:token@cache.example:6379/0"))

    assert captured["ssl_cert_reqs"] == "required"
    assert captured["ssl_check_hostname"] is True


def test_create_redis_detects_tls_scheme_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_from_url(_url: str, **kwargs: object) -> Redis:
        captured.update(kwargs)
        return cast(Redis, object())

    monkeypatch.setattr("app.core.redis.from_url", fake_from_url)

    create_redis(build_settings("REDISS://default:token@cache.example:6379/0"))

    assert captured["ssl_cert_reqs"] == "required"
    assert captured["ssl_check_hostname"] is True
