import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.health.checks import ReadinessResult, get_readiness_checks
from app.main import create_app


@pytest.mark.asyncio
async def test_liveness_does_not_require_infrastructure() -> None:
    app = create_app(
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://localhost/isaac_api",
                "redis_url": "redis://localhost:6379/0",
                "clerk_secret_key": None,
            }
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_is_documented_as_health() -> None:
    app = create_app(
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://localhost/isaac_api",
                "redis_url": "redis://localhost:6379/0",
                "clerk_secret_key": None,
            }
        )
    )

    operation = app.openapi()["paths"]["/health"]["get"]

    assert operation["tags"] == ["health"]
    assert "X-Request-ID" in operation["responses"]["200"]["headers"]
    assert "500" in operation["responses"]


class FakeReadinessChecks:
    def __init__(self, result: ReadinessResult) -> None:
        self.result = result

    async def run(self) -> ReadinessResult:
        return self.result


@pytest.mark.asyncio
async def test_readiness_reports_available_dependencies() -> None:
    app = create_app(
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://localhost/isaac_api",
                "redis_url": "redis://localhost:6379/0",
                "clerk_secret_key": None,
            }
        )
    )
    app.dependency_overrides[get_readiness_checks] = lambda: FakeReadinessChecks(
        ReadinessResult(database=True, redis=True)
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "services": {"database": "up", "redis": "up"},
    }


@pytest.mark.asyncio
async def test_readiness_hides_dependency_failure_details() -> None:
    app = create_app(
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://localhost/isaac_api",
                "redis_url": "redis://localhost:6379/0",
                "clerk_secret_key": None,
            }
        )
    )
    app.dependency_overrides[get_readiness_checks] = lambda: FakeReadinessChecks(
        ReadinessResult(database=False, redis=True)
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "A required service is unavailable",
        },
        "services": {"database": "down", "redis": "up"},
    }
    assert "postgresql" not in response.text
