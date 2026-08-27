import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.exceptions import AppError
from app.items.cache import CacheLookup, ItemCache
from app.items.repository import ItemRecord, ItemRepository
from app.items.schemas import (
    ItemFilterParams,
    ItemListParams,
    ItemListResponse,
    ItemResponse,
    MetaResponse,
)

CacheValue = TypeVar("CacheValue", bound=BaseModel)
CACHE_FAILURES = (
    OSError,
    TimeoutError,
    RedisConnectionError,
    RedisTimeoutError,
    ResponseError,
)
cache_logger = logging.getLogger("app.cache")


class ItemService:
    def __init__(self, repository: ItemRepository, cache: ItemCache) -> None:
        self._repository = repository
        self._cache = cache

    async def get_by_game_id(self, game_id: int) -> ItemResponse:
        lookup = await self._cache_read(
            lambda: self._cache.get_item(game_id),
            "item",
        )
        if lookup is not None and lookup.value is not None:
            return lookup.value
        item = await self._repository.get_by_game_id(game_id)
        if item is None:
            raise AppError(404, "ITEM_NOT_FOUND", f"Item {game_id} does not exist")
        response = to_item_response(item)
        if lookup is not None:
            await self._cache_write(
                lambda: self._cache.set_item(response, lookup.generation),
                "item",
            )
        return response

    async def list_items(self, params: ItemListParams) -> ItemListResponse:
        lookup = await self._cache_read(
            lambda: self._cache.get_list(params),
            "list",
        )
        if lookup is not None and lookup.value is not None:
            return lookup.value
        items = await self._repository.list_items(
            search=params.search,
            quality=params.quality,
            item_type=params.type,
            version=params.version,
            sort=params.sort,
            order=params.order,
            limit=params.limit,
            offset=params.offset,
        )
        total = await self._repository.count_items(
            search=params.search,
            quality=params.quality,
            item_type=params.type,
            version=params.version,
        )
        response = ItemListResponse(
            items=[to_item_response(item) for item in items],
            total=total,
            limit=params.limit,
            offset=params.offset,
        )
        if lookup is not None:
            await self._cache_write(
                lambda: self._cache.set_list(params, response, lookup.generation),
                "list",
            )
        return response

    async def get_random(self, params: ItemFilterParams) -> ItemResponse:
        item = await self._repository.get_random(
            search=params.search,
            quality=params.quality,
            item_type=params.type,
            version=params.version,
        )
        if item is None:
            raise AppError(
                404,
                "ITEM_NOT_FOUND",
                "No item matches the given filters",
            )
        return to_item_response(item)

    async def get_meta(self, api_version: str) -> MetaResponse:
        lookup = await self._cache_read(
            lambda: self._cache.get_meta(api_version),
            "meta",
        )
        if lookup is not None and lookup.value is not None:
            return lookup.value
        catalog_meta = await self._repository.get_catalog_meta()
        metadata = catalog_meta.metadata
        response = MetaResponse(
            api_version=api_version,
            dataset_version=None if metadata is None else metadata.dataset_version,
            game_version=None if metadata is None else metadata.game_version,
            last_sync=None if metadata is None else metadata.last_sync,
            items=catalog_meta.items,
        )
        if lookup is not None:
            await self._cache_write(
                lambda: self._cache.set_meta(response, lookup.generation),
                "meta",
            )
        return response

    async def _cache_read(
        self,
        operation: Callable[[], Awaitable[CacheLookup[CacheValue]]],
        resource: str,
    ) -> CacheLookup[CacheValue] | None:
        try:
            return await operation()
        except CACHE_FAILURES as exception:
            log_cache_failure("read", resource, exception)
            return None

    async def _cache_write(
        self,
        operation: Callable[[], Awaitable[None]],
        resource: str,
    ) -> None:
        try:
            await operation()
        except CACHE_FAILURES as exception:
            log_cache_failure("write", resource, exception)


def to_item_response(item: ItemRecord) -> ItemResponse:
    return ItemResponse(
        game_id=item.game_id,
        name=item.name,
        description=item.description,
        quality=item.quality,
        type=item.item_type,
        recharge_time=item.recharge_time,
        image_url=item.image_url,
        introduced_in_version=item.introduced_in_version,
    )


def log_cache_failure(operation: str, resource: str, exception: Exception) -> None:
    cache_logger.warning(
        "cache_operation_failed",
        extra={
            "event": "cache_operation_failed",
            "dependency": "redis",
            "cache_operation": operation,
            "cache_resource": resource,
            "exception_type": type(exception).__name__,
        },
    )
