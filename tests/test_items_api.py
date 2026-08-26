import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_api_key_verifier
from app.auth.principal import ApiPrincipal
from app.core.config import Settings
from app.items.repository import ItemRecord, get_item_repository
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
    def __init__(self, principal: ApiPrincipal) -> None:
        self.principal = principal

    async def verify(self, secret: str) -> ApiPrincipal:
        return self.principal


class FakeItemRepository:
    def __init__(self, items: list[ItemRecord] | None = None) -> None:
        self.items = items or []

    async def get_by_game_id(self, game_id: int) -> ItemRecord | None:
        return next((item for item in self.items if item.game_id == game_id), None)


BRIMSTONE = ItemRecord(
    game_id=118,
    name="Brimstone",
    description="Tears are replaced by a laser beam.",
    quality=4,
    item_type="passive",
    recharge_time=None,
    image_url="https://example.com/118.png",
    introduced_in_version="rebirth",
)

BRIMSTONE_JSON = {
    "gameId": 118,
    "name": "Brimstone",
    "description": "Tears are replaced by a laser beam.",
    "quality": 4,
    "type": "passive",
    "rechargeTime": None,
    "imageUrl": "https://example.com/118.png",
    "introducedInVersion": "rebirth",
}


def build_items_app(
    repository: FakeItemRepository,
    *,
    scopes: frozenset[str] = frozenset({"api:access"}),
):
    app = create_app(build_settings())
    app.dependency_overrides[get_api_key_verifier] = lambda: FakeVerifier(
        ApiPrincipal(user_id="user_1", scopes=scopes)
    )
    app.dependency_overrides[get_item_repository] = lambda: repository
    return app


@pytest.mark.asyncio
async def test_get_item_without_api_key_returns_401() -> None:
    app = build_items_app(FakeItemRepository([BRIMSTONE]))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/items/118")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "API_KEY_REQUIRED", "message": "API key required"}
    }


@pytest.mark.asyncio
async def test_get_item_without_required_scope_returns_403() -> None:
    app = build_items_app(
        FakeItemRepository([BRIMSTONE]),
        scopes=frozenset({"items:read"}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items/118",
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
async def test_get_item_by_game_id_returns_camel_case_item() -> None:
    app = build_items_app(FakeItemRepository([BRIMSTONE]))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items/118",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json() == BRIMSTONE_JSON
    assert "id" not in response.json()
    assert "createdAt" not in response.json()
    assert "updatedAt" not in response.json()


@pytest.mark.asyncio
async def test_get_missing_item_returns_404() -> None:
    app = build_items_app(FakeItemRepository())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items/9999",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "ITEM_NOT_FOUND",
            "message": "Item 9999 does not exist",
        }
    }
