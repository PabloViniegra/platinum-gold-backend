from app.core.exceptions import AppError
from app.items.repository import ItemRecord, ItemRepository
from app.items.schemas import (
    ItemFilterParams,
    ItemListParams,
    ItemListResponse,
    ItemResponse,
    MetaResponse,
)


class ItemService:
    def __init__(self, repository: ItemRepository) -> None:
        self._repository = repository

    async def get_by_game_id(self, game_id: int) -> ItemResponse:
        item = await self._repository.get_by_game_id(game_id)
        if item is None:
            raise AppError(404, "ITEM_NOT_FOUND", f"Item {game_id} does not exist")
        return to_item_response(item)

    async def list_items(self, params: ItemListParams) -> ItemListResponse:
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
        return ItemListResponse(
            items=[to_item_response(item) for item in items],
            total=total,
            limit=params.limit,
            offset=params.offset,
        )

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
        total = await self._repository.count_items(
            search=None,
            quality=None,
            item_type=None,
            version=None,
        )
        return MetaResponse(
            api_version=api_version,
            game_version=None,
            last_sync=None,
            items=total,
        )


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
