from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import DataError

from app.auth.dependencies import get_api_key_verifier
from app.auth.principal import ApiPrincipal
from app.core.config import Settings
from app.items.cache import CacheLookup
from app.items.dependencies import get_item_cache, get_item_repository
from app.items.repository import CatalogMetaRecord, DatasetMetadataRecord, ItemRecord
from app.items.schemas import (
    ItemListParams,
    ItemListResponse,
    ItemResponse,
    MetaResponse,
)
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
    def __init__(
        self,
        items: list[ItemRecord] | None = None,
        metadata: DatasetMetadataRecord | None = None,
    ) -> None:
        self.items = items or []
        self.metadata = metadata
        self.get_calls = 0
        self.list_calls = 0
        self.count_calls = 0
        self.random_calls = 0
        self.meta_calls = 0

    async def get_catalog_meta(self) -> CatalogMetaRecord:
        self.meta_calls += 1
        return CatalogMetaRecord(items=len(self.items), metadata=self.metadata)

    async def get_by_game_id(self, game_id: int) -> ItemRecord | None:
        self.get_calls += 1
        return next((item for item in self.items if item.game_id == game_id), None)

    async def list_items(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
        sort: str,
        order: str,
        limit: int,
        offset: int,
    ) -> list[ItemRecord]:
        self.list_calls += 1
        items = self._filtered(search, quality, item_type, version)
        reverse = order == "desc"
        items.sort(
            key=lambda item: (getattr(item, sort), item.game_id),
            reverse=reverse,
        )
        return items[offset : offset + limit]

    async def count_items(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
    ) -> int:
        self.count_calls += 1
        return len(self._filtered(search, quality, item_type, version))

    def _filtered(
        self,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
    ) -> list[ItemRecord]:
        items = list(self.items)
        if search is not None:
            needle = search.casefold()
            items = [item for item in items if needle in item.name.casefold()]
        if quality is not None:
            items = [item for item in items if item.quality == quality]
        if item_type is not None:
            items = [item for item in items if item.item_type == item_type]
        if version is not None:
            items = [item for item in items if item.introduced_in_version == version]
        return items

    async def get_random(
        self,
        *,
        search: str | None,
        quality: int | None,
        item_type: str | None,
        version: str | None,
    ) -> ItemRecord | None:
        self.random_calls += 1
        items = self._filtered(search, quality, item_type, version)
        return items[0] if items else None


class FakeItemCache:
    def __init__(
        self,
        *,
        item: ItemResponse | None = None,
        item_list: ItemListResponse | None = None,
        meta: MetaResponse | None = None,
        failure: Exception | None = None,
        write_failure: Exception | None = None,
    ) -> None:
        self.item = item
        self.item_list = item_list
        self.meta = meta
        self.failure = failure
        self.write_failure = write_failure
        self.item_reads = 0
        self.list_reads = 0
        self.meta_reads = 0
        self.item_writes = 0
        self.list_writes = 0
        self.meta_writes = 0

    async def get_item(self, _game_id: int) -> CacheLookup[ItemResponse]:
        self.item_reads += 1
        self._raise_if_failed()
        return CacheLookup(value=self.item, generation="100")

    async def set_item(self, item: ItemResponse, _generation: str | None) -> None:
        self.item_writes += 1
        self._raise_if_failed(self.write_failure)
        self.item = item

    async def get_list(self, _params: ItemListParams) -> CacheLookup[ItemListResponse]:
        self.list_reads += 1
        self._raise_if_failed()
        return CacheLookup(value=self.item_list, generation="100")

    async def set_list(
        self,
        _params: ItemListParams,
        item_list: ItemListResponse,
        _generation: str | None,
    ) -> None:
        self.list_writes += 1
        self._raise_if_failed(self.write_failure)
        self.item_list = item_list

    async def get_meta(self, _api_version: str) -> CacheLookup[MetaResponse]:
        self.meta_reads += 1
        self._raise_if_failed()
        return CacheLookup(value=self.meta, generation="100")

    async def set_meta(self, meta: MetaResponse, _generation: str | None) -> None:
        self.meta_writes += 1
        self._raise_if_failed(self.write_failure)
        self.meta = meta

    def _raise_if_failed(self, failure: Exception | None = None) -> None:
        selected_failure = failure if failure is not None else self.failure
        if selected_failure is not None:
            raise selected_failure


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

BRIMSTONE_RESPONSE = ItemResponse.model_validate(BRIMSTONE_JSON)


def build_items_app(
    repository: FakeItemRepository,
    *,
    scopes: frozenset[str] = frozenset({"api:access"}),
    cache: FakeItemCache | None = None,
):
    app = create_app(build_settings())
    app.dependency_overrides[get_api_key_verifier] = lambda: FakeVerifier(
        ApiPrincipal(user_id="user_1", scopes=scopes)
    )
    app.dependency_overrides[get_item_repository] = lambda: repository
    app.dependency_overrides[get_item_cache] = lambda: cache or FakeItemCache()
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/v1/items", "/v1/items/random", "/v1/items/118", "/v1/meta"],
)
async def test_item_routes_without_api_key_return_401(path: str) -> None:
    app = build_items_app(FakeItemRepository([BRIMSTONE]))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "API_KEY_REQUIRED", "message": "API key required"}
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/v1/items", "/v1/items/random", "/v1/items/118", "/v1/meta"],
)
async def test_item_routes_without_required_scope_return_403(path: str) -> None:
    app = build_items_app(
        FakeItemRepository([BRIMSTONE]),
        scopes=frozenset({"items:read"}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(path, headers={"X-API-Key": "ak_valid"})

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


SAD_ONION = ItemRecord(
    game_id=1,
    name="The Sad Onion",
    description="Tears up.",
    quality=3,
    item_type="passive",
    recharge_time=None,
    image_url="https://example.com/1.png",
    introduced_in_version="rebirth",
)


@pytest.mark.asyncio
async def test_list_items_empty_returns_zero_total() -> None:
    app = build_items_app(FakeItemRepository())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


@pytest.mark.asyncio
async def test_list_items_filters_by_quality_and_search() -> None:
    app = build_items_app(FakeItemRepository([BRIMSTONE, SAD_ONION]))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        by_quality = await client.get(
            "/v1/items",
            params={"quality": 4},
            headers={"X-API-Key": "ak_valid"},
        )
        by_search = await client.get(
            "/v1/items",
            params={"search": "brim"},
            headers={"X-API-Key": "ak_valid"},
        )

    assert by_quality.status_code == 200
    assert by_quality.json()["total"] == 1
    assert by_quality.json()["items"] == [BRIMSTONE_JSON]
    assert by_search.status_code == 200
    assert by_search.json()["items"] == [BRIMSTONE_JSON]


@pytest.mark.asyncio
async def test_list_items_reflects_limit_and_offset() -> None:
    app = build_items_app(FakeItemRepository([BRIMSTONE, SAD_ONION]))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items",
            params={"limit": 1, "offset": 1, "sort": "game_id"},
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert body["total"] == 2
    assert body["items"] == [BRIMSTONE_JSON]


@pytest.mark.asyncio
async def test_list_items_rejects_invalid_query() -> None:
    app = build_items_app(FakeItemRepository())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        bad_quality = await client.get(
            "/v1/items",
            params={"quality": 9},
            headers={"X-API-Key": "ak_valid"},
        )
        bad_limit = await client.get(
            "/v1/items",
            params={"limit": 0},
            headers={"X-API-Key": "ak_valid"},
        )

    assert bad_quality.status_code == 422
    assert bad_quality.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad_limit.status_code == 422
    assert bad_limit.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_random_item_returns_item() -> None:
    app = build_items_app(FakeItemRepository([BRIMSTONE]))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items/random",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json() == BRIMSTONE_JSON


@pytest.mark.asyncio
async def test_random_item_without_match_returns_404() -> None:
    app = build_items_app(FakeItemRepository())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items/random",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "ITEM_NOT_FOUND",
            "message": "No item matches the given filters",
        }
    }


@pytest.mark.asyncio
async def test_meta_returns_api_version_and_item_count() -> None:
    app = build_items_app(FakeItemRepository([BRIMSTONE, SAD_ONION]))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/meta",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "apiVersion": "0.1.0",
        "datasetVersion": None,
        "gameVersion": None,
        "lastSync": None,
        "items": 2,
    }


@pytest.mark.asyncio
async def test_meta_returns_dataset_metadata_after_ingestion() -> None:
    metadata = DatasetMetadataRecord(
        dataset_version="platinum-god-2026-08-26",
        game_version="repentance",
        last_sync=datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
    )
    app = build_items_app(FakeItemRepository([BRIMSTONE, SAD_ONION], metadata))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/meta",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "apiVersion": "0.1.0",
        "datasetVersion": "platinum-god-2026-08-26",
        "gameVersion": "repentance",
        "lastSync": "2026-08-26T10:30:00Z",
        "items": 2,
    }


@pytest.mark.asyncio
async def test_item_cache_hit_skips_postgres_repository() -> None:
    repository = FakeItemRepository()
    cache = FakeItemCache(item=BRIMSTONE_RESPONSE)
    app = build_items_app(repository, cache=cache)

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
    assert repository.get_calls == 0


@pytest.mark.asyncio
async def test_item_cache_miss_populates_cache_and_next_read_hits() -> None:
    repository = FakeItemRepository([BRIMSTONE])
    cache = FakeItemCache()
    app = build_items_app(repository, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.get(
            "/v1/items/118",
            headers={"X-API-Key": "ak_valid"},
        )
        second = await client.get(
            "/v1/items/118",
            headers={"X-API-Key": "ak_valid"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == BRIMSTONE_JSON
    assert repository.get_calls == 1
    assert cache.item_writes == 1


@pytest.mark.asyncio
async def test_list_cache_hit_skips_postgres_repository() -> None:
    repository = FakeItemRepository()
    cached = ItemListResponse(
        items=[BRIMSTONE_RESPONSE],
        total=1,
        limit=20,
        offset=0,
    )
    cache = FakeItemCache(item_list=cached)
    app = build_items_app(repository, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [BRIMSTONE_JSON],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }
    assert repository.list_calls == 0
    assert repository.count_calls == 0


@pytest.mark.asyncio
async def test_meta_cache_hit_skips_postgres_repository() -> None:
    cached = MetaResponse(
        api_version="0.1.0",
        dataset_version="dataset-1",
        game_version="repentance",
        last_sync=datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
        items=1,
    )
    repository = FakeItemRepository()
    cache = FakeItemCache(meta=cached)
    app = build_items_app(repository, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/meta",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json()["datasetVersion"] == "dataset-1"
    assert repository.meta_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/items", "/v1/items/118", "/v1/meta"])
async def test_redis_read_failure_falls_back_to_postgres(path: str) -> None:
    repository = FakeItemRepository([BRIMSTONE])
    cache = FakeItemCache(failure=RedisConnectionError("redis-secret"))
    app = build_items_app(repository, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            path,
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert "redis-secret" not in response.text


@pytest.mark.asyncio
async def test_redis_write_failure_does_not_change_database_response() -> None:
    repository = FakeItemRepository([BRIMSTONE])
    cache = FakeItemCache(write_failure=RedisConnectionError("redis-secret"))
    app = build_items_app(repository, cache=cache)

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
    assert cache.item_writes == 1


@pytest.mark.asyncio
async def test_unexpected_cache_failure_is_not_silently_ignored() -> None:
    repository = FakeItemRepository([BRIMSTONE])
    cache = FakeItemCache(failure=RuntimeError("programming failure"))
    app = build_items_app(repository, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items/118",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
        }
    }
    assert repository.get_calls == 0


@pytest.mark.asyncio
async def test_redis_data_error_is_not_treated_as_availability_failure() -> None:
    repository = FakeItemRepository([BRIMSTONE])
    cache = FakeItemCache(failure=DataError("invalid cache command"))
    app = build_items_app(repository, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items/118",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 500
    assert repository.get_calls == 0


@pytest.mark.asyncio
async def test_random_item_bypasses_cache() -> None:
    repository = FakeItemRepository([BRIMSTONE])
    cache = FakeItemCache(item=BRIMSTONE_RESPONSE)
    app = build_items_app(repository, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/items/random",
            headers={"X-API-Key": "ak_valid"},
        )

    assert response.status_code == 200
    assert response.json() == BRIMSTONE_JSON
    assert repository.random_calls == 1
    assert cache.item_reads == 0


@pytest.mark.asyncio
async def test_health_remains_public() -> None:
    app = build_items_app(FakeItemRepository())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_documents_item_routes() -> None:
    paths = create_app(build_settings()).openapi()["paths"]

    for path in (
        "/v1/items",
        "/v1/items/{item_id}",
        "/v1/items/random",
        "/v1/meta",
    ):
        assert paths[path]["get"]["security"] == [{"X-API-Key": []}]
