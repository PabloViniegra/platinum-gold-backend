import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from secrets import randbelow
from typing import Protocol, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import (
    DEFAULT_CACHE_ITEM_TTL_SECONDS,
    DEFAULT_CACHE_LIST_TTL_SECONDS,
    DEFAULT_CACHE_META_TTL_SECONDS,
    MAX_CACHE_TTL_SECONDS,
)
from app.items.schemas import (
    ItemListParams,
    ItemListResponse,
    ItemResponse,
    MetaResponse,
)

CACHE_GENERATION_KEY = "cache:items:generation"
CACHE_KEY_VERSION = "v1"
ITEM_TTL_SECONDS = DEFAULT_CACHE_ITEM_TTL_SECONDS
LIST_TTL_SECONDS = DEFAULT_CACHE_LIST_TTL_SECONDS
META_TTL_SECONDS = DEFAULT_CACHE_META_TTL_SECONDS
MAX_GENERATION = 9223372036854775807
MAX_GENERATION_DIGITS = len(str(MAX_GENERATION))
MAX_CACHE_PAYLOAD_BYTES = 2 * 1024 * 1024
MAX_CACHED_LIST_ITEMS = 100
cache_logger = logging.getLogger("app.cache")

CacheResponse = TypeVar("CacheResponse", bound=BaseModel)


@dataclass(frozen=True)
class CacheLookup[CacheResponse: BaseModel]:
    value: CacheResponse | None
    generation: str | None


class ListCacheEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    cache_key: str = Field(alias="cacheKey")
    payload: dict[str, object]


class RedisCacheClient(Protocol):
    def get(self, name: str) -> Awaitable[bytes | str | None]: ...

    def getrange(self, name: str, start: int, end: int) -> Awaitable[bytes | str]: ...

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> Awaitable[object]: ...

    def incr(self, name: str) -> Awaitable[int]: ...


class ItemCache(Protocol):
    async def get_item(self, game_id: int) -> CacheLookup[ItemResponse]: ...

    async def set_item(self, item: ItemResponse, generation: str | None) -> None: ...

    async def get_list(
        self,
        params: ItemListParams,
    ) -> CacheLookup[ItemListResponse]: ...

    async def set_list(
        self,
        params: ItemListParams,
        response: ItemListResponse,
        generation: str | None,
    ) -> None: ...

    async def get_meta(self, api_version: str) -> CacheLookup[MetaResponse]: ...

    async def set_meta(
        self,
        response: MetaResponse,
        generation: str | None,
    ) -> None: ...


class RedisItemCache:
    def __init__(
        self,
        redis: RedisCacheClient,
        *,
        generation_factory: Callable[[], int] | None = None,
        item_ttl_seconds: int = ITEM_TTL_SECONDS,
        list_ttl_seconds: int = LIST_TTL_SECONDS,
        meta_ttl_seconds: int = META_TTL_SECONDS,
    ) -> None:
        self._redis = redis
        self._generation_factory = generation_factory or new_generation
        self._item_ttl_seconds = validate_ttl("item", item_ttl_seconds)
        self._list_ttl_seconds = validate_ttl("list", list_ttl_seconds)
        self._meta_ttl_seconds = validate_ttl("meta", meta_ttl_seconds)

    async def get_item(self, game_id: int) -> CacheLookup[ItemResponse]:
        lookup = await self._get(f"item:{game_id}", ItemResponse)
        if lookup.value is not None and lookup.value.game_id != game_id:
            self._log_invalid_payload()
            return CacheLookup(value=None, generation=lookup.generation)
        return lookup

    async def set_item(self, item: ItemResponse, generation: str | None) -> None:
        await self._set(
            f"item:{item.game_id}",
            item,
            self._item_ttl_seconds,
            generation,
        )

    async def get_list(
        self,
        params: ItemListParams,
    ) -> CacheLookup[ItemListResponse]:
        lookup = await self._get(self._list_suffix(params), ItemListResponse)
        if lookup.value is not None and (
            lookup.value.limit != params.limit or lookup.value.offset != params.offset
        ):
            self._log_invalid_payload()
            return CacheLookup(value=None, generation=lookup.generation)
        return lookup

    async def set_list(
        self,
        params: ItemListParams,
        response: ItemListResponse,
        generation: str | None,
    ) -> None:
        if response.limit != params.limit or response.offset != params.offset:
            self._log_invalid_payload()
            return
        await self._set(
            self._list_suffix(params),
            response,
            self._list_ttl_seconds,
            generation,
        )

    async def get_meta(self, api_version: str) -> CacheLookup[MetaResponse]:
        lookup = await self._get(f"meta:{api_version}", MetaResponse)
        if lookup.value is not None and lookup.value.api_version != api_version:
            self._log_invalid_payload()
            return CacheLookup(value=None, generation=lookup.generation)
        return lookup

    async def set_meta(self, response: MetaResponse, generation: str | None) -> None:
        await self._set(
            f"meta:{response.api_version}",
            response,
            self._meta_ttl_seconds,
            generation,
        )

    async def invalidate(self) -> int:
        if await self._generation() is None:
            raise ValueError("cache generation is invalid")
        return await self._redis.incr(CACHE_GENERATION_KEY)

    async def _get(
        self,
        suffix: str,
        model: type[CacheResponse],
    ) -> CacheLookup[CacheResponse]:
        generation = await self._generation()
        if generation is None:
            return CacheLookup(value=None, generation=None)
        try:
            payload = await self._redis.getrange(
                self._key(generation, suffix),
                0,
                MAX_CACHE_PAYLOAD_BYTES,
            )
        except UnicodeDecodeError:
            self._log_invalid_payload()
            return CacheLookup(value=None, generation=generation)
        current_generation = await self._generation()
        if current_generation != generation:
            return CacheLookup(value=None, generation=current_generation)
        payload_text = self._payload_text(payload)
        if payload_text is None:
            return CacheLookup(value=None, generation=generation)
        if model is ItemListResponse and not self._has_valid_list_size(payload_text):
            self._log_invalid_payload()
            return CacheLookup(value=None, generation=generation)
        try:
            if model is ItemListResponse:
                envelope = ListCacheEnvelope.model_validate_json(payload_text)
                if envelope.cache_key != suffix:
                    self._log_invalid_payload()
                    return CacheLookup(value=None, generation=generation)
                value = cast(CacheResponse, model.model_validate(envelope.payload))
            else:
                value = model.model_validate_json(payload_text)
        except ValidationError:
            self._log_invalid_payload()
            return CacheLookup(value=None, generation=generation)
        return CacheLookup(value=value, generation=generation)

    async def _set(
        self,
        suffix: str,
        value: BaseModel,
        ttl: int,
        generation: str | None,
    ) -> None:
        if generation is None:
            return
        if (
            isinstance(value, ItemListResponse)
            and len(value.items) > MAX_CACHED_LIST_ITEMS
        ):
            self._log_invalid_payload()
            return
        if isinstance(value, ItemListResponse):
            payload = ListCacheEnvelope(
                cacheKey=suffix,
                payload=cast(
                    dict[str, object],
                    value.model_dump(mode="json", by_alias=True),
                ),
            ).model_dump_json(by_alias=True)
        else:
            payload = value.model_dump_json(by_alias=True)
        if len(payload.encode("utf-8")) > MAX_CACHE_PAYLOAD_BYTES:
            self._log_invalid_payload()
            return
        await self._redis.set(
            self._key(generation, suffix),
            payload,
            ex=ttl,
        )

    async def _generation(self) -> str | None:
        try:
            value = await self._redis.getrange(
                CACHE_GENERATION_KEY,
                0,
                MAX_GENERATION_DIGITS,
            )
        except UnicodeDecodeError:
            self._log_invalid_payload()
            return None
        if value == "" or value == b"":
            candidate = str(self._generation_factory())
            if self._parse_generation(candidate) is None:
                raise ValueError("cache generation factory returned an invalid value")
            if await self._redis.set(CACHE_GENERATION_KEY, candidate, nx=True):
                return candidate
            try:
                value = await self._redis.getrange(
                    CACHE_GENERATION_KEY,
                    0,
                    MAX_GENERATION_DIGITS,
                )
            except UnicodeDecodeError:
                self._log_invalid_payload()
                return None
            if value == "" or value == b"":
                return None
        generation = self._parse_generation(value)
        if generation is None:
            cache_logger.warning(
                "cache_generation_invalid",
                extra={"event": "cache_generation_invalid"},
            )
        return generation

    @staticmethod
    def _payload_text(payload: bytes | str | None) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, bytes):
            if len(payload) > MAX_CACHE_PAYLOAD_BYTES:
                return None
            try:
                return payload.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if len(payload.encode("utf-8")) > MAX_CACHE_PAYLOAD_BYTES:
            return None
        return payload

    @staticmethod
    def _has_valid_list_size(payload: str) -> bool:
        try:
            raw: object = json.loads(payload)
        except (RecursionError, ValueError):
            return False
        if not isinstance(raw, dict):
            return False
        raw_dict = cast(dict[str, object], raw)
        envelope_payload = raw_dict.get("payload")
        if not isinstance(envelope_payload, dict):
            return False
        items = cast(dict[str, object], envelope_payload).get("items")
        return (
            isinstance(items, list)
            and len(cast(list[object], items)) <= MAX_CACHED_LIST_ITEMS
        )

    @staticmethod
    def _parse_generation(value: bytes | str) -> str | None:
        if isinstance(value, bytes):
            try:
                value = value.decode("ascii")
            except UnicodeDecodeError:
                return None
        if (
            not value.isascii()
            or not value.isdigit()
            or len(value) > MAX_GENERATION_DIGITS
        ):
            return None
        generation = int(value)
        return str(generation) if generation <= MAX_GENERATION else None

    @staticmethod
    def _log_invalid_payload() -> None:
        cache_logger.warning(
            "cache_payload_invalid",
            extra={"event": "cache_payload_invalid"},
        )

    @staticmethod
    def _key(generation: str, suffix: str) -> str:
        return f"cache:{CACHE_KEY_VERSION}:{generation}:{suffix}"

    @staticmethod
    def _list_suffix(params: ItemListParams) -> str:
        serialized = json.dumps(
            params.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        return f"list:{digest}"


def new_generation() -> int:
    return randbelow(MAX_GENERATION - 1) + 1


def validate_ttl(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= MAX_CACHE_TTL_SECONDS
    ):
        raise ValueError(
            f"{name} cache TTL must be between 1 and {MAX_CACHE_TTL_SECONDS}"
        )
    return value
