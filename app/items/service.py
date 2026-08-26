from app.core.exceptions import AppError
from app.items.repository import ItemRecord, ItemRepository
from app.items.schemas import ItemListParams, ItemListResponse, ItemResponse


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
