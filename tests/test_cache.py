import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from app.items.cache import MAX_CACHE_PAYLOAD_BYTES, RedisItemCache
from app.items.schemas import (
    ItemListParams,
    ItemListResponse,
    ItemResponse,
    MetaResponse,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.reads: list[str] = []
        self.range_reads: list[tuple[str, int, int]] = []
        self.writes: list[str] = []
        self.after_generation_read: Callable[[], None] | None = None

    async def get(self, name: str) -> str | None:
        self.reads.append(name)
        value = self.values.get(name)
        if name == "cache:items:generation" and self.after_generation_read:
            callback = self.after_generation_read
            self.after_generation_read = None
            callback()
        return value

    async def getrange(self, name: str, start: int, end: int) -> str:
        value = self.values.get(name, "")
        if name == "cache:items:generation" and self.after_generation_read:
            callback = self.after_generation_read
            self.after_generation_read = None
            callback()
        self.range_reads.append((name, start, end))
        return value[start : end + 1]

    async def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        if nx and name in self.values:
            return None
        self.writes.append(name)
        self.values[name] = value
        if ex is not None:
            self.expirations[name] = ex
        return True

    async def incr(self, name: str) -> int:
        value = int(self.values.get(name, "0")) + 1
        self.values[name] = str(value)
        return value


BRIMSTONE = ItemResponse(
    game_id=118,
    name="Brimstone",
    description="Tears are replaced by a laser beam.",
    quality=4,
    type="passive",
    recharge_time=None,
    image_url="https://example.com/118.png",
    introduced_in_version="rebirth",
)


@pytest.mark.asyncio
async def test_item_cache_round_trips_public_schema_with_ttl() -> None:
    redis = FakeRedis()
    cache = RedisItemCache(redis, generation_factory=lambda: 100)

    miss = await cache.get_item(118)
    await cache.set_item(BRIMSTONE, miss.generation)
    result = await cache.get_item(118)

    key = "cache:v1:100:item:118"
    assert result.value == BRIMSTONE
    assert redis.expirations[key] == 86400
    assert '"gameId":118' in redis.values[key]


@pytest.mark.asyncio
async def test_list_cache_uses_deterministic_hashed_key() -> None:
    redis = FakeRedis()
    cache = RedisItemCache(redis, generation_factory=lambda: 100)
    first_params = ItemListParams.model_validate(
        {"search": "secret search", "quality": 4, "limit": 20}
    )
    second_params = ItemListParams.model_validate(
        {"limit": 20, "quality": 4, "search": "secret search"}
    )
    response = ItemListResponse(items=[BRIMSTONE], total=1, limit=20, offset=0)

    first_miss = await cache.get_list(first_params)
    await cache.set_list(first_params, response, first_miss.generation)
    first_key = next(key for key in redis.values if ":list:" in key)
    second_miss = await cache.get_list(second_params)
    await cache.set_list(second_params, response, second_miss.generation)
    list_keys = [key for key in redis.values if ":list:" in key]

    assert list_keys == [first_key]
    assert "secret" not in first_key
    assert redis.expirations[first_key] == 900
    assert (await cache.get_list(second_params)).value == response


@pytest.mark.asyncio
async def test_meta_cache_round_trips_datetime_and_api_version() -> None:
    redis = FakeRedis()
    cache = RedisItemCache(redis, generation_factory=lambda: 100)
    response = MetaResponse(
        api_version="0.1.0",
        dataset_version="platinum-god-2026-08-26",
        game_version="repentance",
        last_sync=datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
        items=1,
    )

    miss = await cache.get_meta("0.1.0")
    await cache.set_meta(response, miss.generation)

    key = "cache:v1:100:meta:0.1.0"
    assert (await cache.get_meta("0.1.0")).value == response
    assert redis.expirations[key] == 86400


@pytest.mark.asyncio
async def test_cache_treats_invalid_payload_as_miss() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "100"
    redis.values["cache:v1:100:item:118"] = '{"gameId":"invalid"}'
    cache = RedisItemCache(redis, generation_factory=lambda: 200)

    result = await cache.get_item(118)

    assert result.value is None
    assert result.generation == "100"


@pytest.mark.asyncio
async def test_cache_rejects_item_payload_bound_to_another_game_id() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "100"
    cache = RedisItemCache(redis, generation_factory=lambda: 200)
    wrong_item = BRIMSTONE.model_copy(update={"game_id": 119})
    redis.values["cache:v1:100:item:118"] = wrong_item.model_dump_json(by_alias=True)

    result = await cache.get_item(118)

    assert result.value is None


@pytest.mark.asyncio
async def test_cache_rejects_meta_payload_bound_to_another_api_version() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "100"
    response = MetaResponse(
        api_version="0.2.0",
        dataset_version=None,
        game_version=None,
        last_sync=None,
        items=0,
    )
    redis.values["cache:v1:100:meta:0.1.0"] = response.model_dump_json(by_alias=True)
    cache = RedisItemCache(redis, generation_factory=lambda: 200)

    result = await cache.get_meta("0.1.0")

    assert result.value is None


@pytest.mark.asyncio
async def test_cache_rejects_list_payload_with_different_pagination() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "100"
    params = ItemListParams(limit=20, offset=0)
    response = ItemListResponse(items=[BRIMSTONE], total=1, limit=10, offset=0)
    cache = RedisItemCache(redis, generation_factory=lambda: 200)
    serialized = json.dumps(
        params.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    suffix = f"list:{hashlib.sha256(serialized.encode()).hexdigest()}"
    redis.values[f"cache:v1:100:{suffix}"] = json.dumps(
        {
            "cacheKey": suffix,
            "payload": response.model_dump(mode="json", by_alias=True),
        }
    )

    result = await cache.get_list(params)

    assert result.value is None


@pytest.mark.asyncio
async def test_invalidation_moves_new_entries_to_next_generation() -> None:
    redis = FakeRedis()
    cache = RedisItemCache(redis, generation_factory=lambda: 100)
    first_miss = await cache.get_item(118)
    await cache.set_item(BRIMSTONE, first_miss.generation)

    generation = await cache.invalidate()
    second_miss = await cache.get_item(118)
    await cache.set_item(BRIMSTONE, second_miss.generation)

    assert generation == 101
    assert redis.values["cache:items:generation"] == "101"
    assert "cache:v1:100:item:118" in redis.values
    assert "cache:v1:101:item:118" in redis.values


@pytest.mark.asyncio
async def test_repopulation_uses_generation_observed_before_database_read() -> None:
    redis = FakeRedis()
    cache = RedisItemCache(redis, generation_factory=lambda: 100)
    miss = await cache.get_item(118)

    await cache.invalidate()
    await cache.set_item(BRIMSTONE, miss.generation)

    assert "cache:v1:100:item:118" in redis.values
    assert (await cache.get_item(118)).value is None


@pytest.mark.asyncio
async def test_missing_generation_does_not_resurrect_old_entries() -> None:
    redis = FakeRedis()
    first_cache = RedisItemCache(redis, generation_factory=lambda: 100)
    miss = await first_cache.get_item(118)
    await first_cache.set_item(BRIMSTONE, miss.generation)
    await first_cache.invalidate()
    del redis.values["cache:items:generation"]

    recovered_cache = RedisItemCache(redis, generation_factory=lambda: 200)
    result = await recovered_cache.get_item(118)

    assert result.value is None
    assert result.generation == "200"
    assert redis.values["cache:items:generation"] == "200"


@pytest.mark.asyncio
async def test_cache_rejects_oversized_payload_before_validation() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "100"
    redis.values["cache:v1:100:item:118"] = "x" * (MAX_CACHE_PAYLOAD_BYTES + 1)
    cache = RedisItemCache(redis, generation_factory=lambda: 200)

    result = await cache.get_item(118)

    assert result.value is None


@pytest.mark.asyncio
async def test_cache_rejects_list_larger_than_endpoint_limit() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "100"
    params = ItemListParams()
    response = ItemListResponse(
        items=[BRIMSTONE] * 101,
        total=101,
        limit=params.limit,
        offset=0,
    )
    key_cache = RedisItemCache(redis, generation_factory=lambda: 200)
    miss = await key_cache.get_list(params)
    await key_cache.set_list(params, response, miss.generation)

    result = await key_cache.get_list(params)

    assert result.value is None
    assert not any(":list:" in key for key in redis.writes)


@pytest.mark.asyncio
async def test_cache_uses_bounded_redis_read_for_payloads() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "100"
    redis.values["cache:v1:100:item:118"] = BRIMSTONE.model_dump_json(by_alias=True)
    cache = RedisItemCache(redis, generation_factory=lambda: 200)

    await cache.get_item(118)

    assert redis.range_reads == [
        ("cache:items:generation", 0, 19),
        ("cache:v1:100:item:118", 0, MAX_CACHE_PAYLOAD_BYTES),
        ("cache:items:generation", 0, 19),
    ]


@pytest.mark.asyncio
async def test_cache_misses_when_generation_changes_during_read() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "100"
    redis.values["cache:v1:100:item:118"] = BRIMSTONE.model_dump_json(by_alias=True)
    cache = RedisItemCache(redis, generation_factory=lambda: 200)
    generation_reads = 0

    def invalidate_after_first_read() -> None:
        nonlocal generation_reads
        generation_reads += 1
        if generation_reads == 1:
            redis.values["cache:items:generation"] = "101"

    redis.after_generation_read = invalidate_after_first_read

    result = await cache.get_item(118)

    assert result.value is None
    assert result.generation == "101"


@pytest.mark.asyncio
async def test_generation_read_is_bounded_before_validation() -> None:
    redis = FakeRedis()
    redis.values["cache:items:generation"] = "9" * 1000
    cache = RedisItemCache(redis, generation_factory=lambda: 200)

    result = await cache.get_item(118)

    assert result.value is None
    assert redis.range_reads == [("cache:items:generation", 0, 19)]


@pytest.mark.asyncio
async def test_cache_treats_redis_decode_failure_as_miss() -> None:
    class DecodeFailureRedis(FakeRedis):
        async def getrange(self, name: str, start: int, end: int) -> str:
            if name != "cache:items:generation":
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
            return await super().getrange(name, start, end)

    redis = DecodeFailureRedis()
    redis.values["cache:items:generation"] = "100"
    cache = RedisItemCache(redis, generation_factory=lambda: 200)

    result = await cache.get_item(118)

    assert result.value is None
    assert result.generation == "100"


def test_cache_rejects_invalid_item_ttl_configuration() -> None:
    with pytest.raises(ValueError, match="TTL"):
        RedisItemCache(FakeRedis(), item_ttl_seconds=0)


def test_cache_rejects_invalid_list_ttl_configuration() -> None:
    with pytest.raises(ValueError, match="TTL"):
        RedisItemCache(FakeRedis(), list_ttl_seconds=0)


def test_cache_rejects_invalid_meta_ttl_configuration() -> None:
    with pytest.raises(ValueError, match="TTL"):
        RedisItemCache(FakeRedis(), meta_ttl_seconds=0)
