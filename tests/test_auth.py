from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.auth.clerk import UnavailableApiKeyVerifier
from app.auth.dependencies import get_api_key_verifier, require_scopes
from app.auth.principal import (
    ApiPrincipal,
    AuthUnavailableError,
    InvalidApiKeyError,
)
from app.core.config import Settings
from app.main import create_app


def build_settings() -> Settings:
    return Settings.model_validate(
        {
            "database_url": "postgresql+asyncpg://localhost/isaac_api",
            "redis_url": "redis://localhost:6379/0",
            "clerk_secret_key": None,
        }
    )


class FakeVerifier:
    def __init__(
        self,
        principal: ApiPrincipal | None = None,
        error: Exception | None = None,
    ) -> None:
        self.principal = principal
        self.error = error

    async def verify(self, secret: str) -> ApiPrincipal:
        if self.error is not None:
            raise self.error
        assert self.principal is not None
        return self.principal


async def auth_probe(
    principal: Annotated[ApiPrincipal, Depends(require_scopes("api:access"))],
) -> dict[str, str]:
    return {"user_id": principal.user_id}


def build_protected_app(verifier: FakeVerifier):
    app = create_app(build_settings())
    app.dependency_overrides[get_api_key_verifier] = lambda: verifier
    app.add_api_route("/v1/__auth_probe", auth_probe)
    return app


@pytest.mark.asyncio
async def test_missing_api_key_returns_401() -> None:
    app = build_protected_app(
        FakeVerifier(principal=ApiPrincipal(user_id="user_1", scopes=frozenset()))
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/__auth_probe")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "API_KEY_REQUIRED", "message": "API key required"}
    }


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401() -> None:
    app = build_protected_app(FakeVerifier(error=InvalidApiKeyError()))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/__auth_probe",
            headers={"X-API-Key": "ak_invalid"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "INVALID_API_KEY", "message": "Invalid API key"}
    }


@pytest.mark.asyncio
async def test_missing_scope_returns_403() -> None:
    app = build_protected_app(
        FakeVerifier(
            principal=ApiPrincipal(
                user_id="user_1",
                scopes=frozenset({"items:read"}),
            )
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/__auth_probe",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "INSUFFICIENT_PERMISSIONS",
            "message": "Insufficient permissions",
        }
    }


@pytest.mark.asyncio
async def test_valid_api_key_with_required_scope_returns_principal() -> None:
    app = build_protected_app(
        FakeVerifier(
            principal=ApiPrincipal(
                user_id="user_1",
                scopes=frozenset({"api:access"}),
            )
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/__auth_probe",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json() == {"user_id": "user_1"}


@pytest.mark.asyncio
async def test_unavailable_verifier_returns_503() -> None:
    app = build_protected_app(FakeVerifier(error=AuthUnavailableError()))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/__auth_probe",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "A required service is unavailable",
        }
    }


def test_openapi_documents_api_key_header() -> None:
    schema = create_app(build_settings()).openapi()
    scheme = schema["components"]["securitySchemes"]["X-API-Key"]

    assert scheme == {"type": "apiKey", "in": "header", "name": "X-API-Key"}
    assert "security" not in schema["paths"]["/health"]["get"]
    assert "security" not in schema["paths"]["/health/ready"]["get"]


@pytest.mark.asyncio
async def test_health_does_not_require_api_key() -> None:
    app = create_app(build_settings())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_lifespan_uses_unavailable_verifier_without_clerk_secret() -> None:
    app = create_app(build_settings())

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.api_key_verifier, UnavailableApiKeyVerifier)


@pytest.mark.asyncio
async def test_protected_route_without_clerk_secret_returns_503() -> None:
    app = create_app(build_settings())
    app.add_api_route("/v1/__auth_probe", auth_probe)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/__auth_probe",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "A required service is unavailable",
        }
    }
