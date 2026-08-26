from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_scopes
from app.items.repository import ItemRepository, get_item_repository
from app.items.schemas import ItemResponse
from app.items.service import ItemService

router = APIRouter(
    prefix="/v1/items",
    tags=["items"],
    dependencies=[Depends(require_scopes("api:access"))],
)


async def get_item_service(
    repository: Annotated[ItemRepository, Depends(get_item_repository)],
) -> ItemService:
    return ItemService(repository)


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int,
    service: Annotated[ItemService, Depends(get_item_service)],
) -> ItemResponse:
    return await service.get_by_game_id(item_id)
