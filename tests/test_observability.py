import json
import logging
from typing import Protocol, cast
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.main import create_app


class RequestLogRecord(Protocol):
    request_id: str
    method: str
    path: str
    status: int
    duration_ms: float
    exception_function: str


def build_settings() -> Settings:
    return Settings.model_validate(
        {
            "database_url": "postgresql+asyncpg://localhost/isaac_api",
            "redis_url": "redis://localhost:6379/0",
            "clerk_secret_key": None,
        }
    )


@pytest.mark.asyncio
async def test_response_contains_generated_request_id() -> None:
    app = create_app(build_settings())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert (
        str(UUID(response.headers["X-Request-ID"])) == response.headers["X-Request-ID"]
    )


@pytest.mark.asyncio
async def test_valid_client_request_id_is_preserved() -> None:
    app = create_app(build_settings())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"X-Request-ID": "client-request_123"},
        )

    assert response.headers["X-Request-ID"] == "client-request_123"


@pytest.mark.asyncio
async def test_invalid_client_request_id_is_replaced() -> None:
    app = create_app(build_settings())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"X-Request-ID": "invalid request id"},
        )

    assert response.headers["X-Request-ID"] != "invalid request id"
    UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_request_log_uses_response_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(build_settings())
    caplog.set_level(logging.INFO, logger="app.request")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    record = next(record for record in caplog.records if record.name == "app.request")
    request_record = cast(RequestLogRecord, record)
    assert request_record.request_id == response.headers["X-Request-ID"]
    assert request_record.method == "GET"
    assert request_record.path == "/health"
    assert request_record.status == 200
    assert request_record.duration_ms >= 0


@pytest.mark.asyncio
async def test_unhandled_error_is_generic_and_contains_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(build_settings())
    caplog.set_level(logging.ERROR, logger="app.request")

    async def failure() -> None:
        raise RuntimeError("sensitive internal detail")

    app.add_api_route("/failure", failure)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/failure")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
        }
    }
    UUID(response.headers["X-Request-ID"])
    assert "sensitive internal detail" not in response.text
    record = next(record for record in caplog.records if record.name == "app.request")
    request_record = cast(RequestLogRecord, record)
    assert request_record.exception_function == "failure"
    assert "sensitive internal detail" not in record.getMessage()


@pytest.mark.asyncio
async def test_request_log_redacts_api_keys_in_paths(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(build_settings())
    caplog.set_level(logging.INFO, logger="app.request")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.get("/ak_exposed-secret")

    record = next(record for record in caplog.records if record.name == "app.request")
    request_record = cast(RequestLogRecord, record)
    assert request_record.path == "/ak_[REDACTED]"
    assert "ak_exposed-secret" not in request_record.path


@pytest.mark.asyncio
async def test_not_found_uses_application_error_format() -> None:
    app = create_app(build_settings())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "NOT_FOUND", "message": "Resource not found"}
    }


@pytest.mark.asyncio
async def test_request_validation_uses_application_error_format() -> None:
    app = create_app(build_settings())

    async def requires_integer(value: int) -> int:
        return value

    app.add_api_route("/integer", requires_integer)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/integer", params={"value": "invalid"})

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
        }
    }


@pytest.mark.asyncio
async def test_http_error_preserves_protocol_headers() -> None:
    app = create_app(build_settings())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/health")

    assert response.status_code == 405
    assert "GET" in response.headers["Allow"]


def test_json_formatter_allowlists_fields() -> None:
    record = logging.LogRecord(
        name="app.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-1"
    record.database_url = "postgresql://user:secret@database.example/db"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "request-1"
    assert "database_url" not in payload
    assert "secret" not in json.dumps(payload)
