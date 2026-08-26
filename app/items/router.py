from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import require_scopes
from app.core.exceptions import ErrorResponse
from app.items.dependencies import get_item_repository
from app.items.repository import ItemRepository
from app.items.schemas import (
    ItemFilterParams,
    ItemListParams,
    ItemListResponse,
    ItemResponse,
    MetaResponse,
)
from app.items.service import ItemService

router = APIRouter(
    prefix="/v1/items",
    tags=["items"],
    dependencies=[Depends(require_scopes("api:access"))],
)

meta_router = APIRouter(
    prefix="/v1",
    tags=["meta"],
    dependencies=[Depends(require_scopes("api:access"))],
)

COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}
LIST_RESPONSES = {**COMMON_ERROR_RESPONSES, 422: {"model": ErrorResponse}}
ITEM_RESPONSES = {
    **LIST_RESPONSES,
    404: {"model": ErrorResponse},
}


async def get_item_service(
    repository: Annotated[ItemRepository, Depends(get_item_repository)],
) -> ItemService:
    return ItemService(repository)


@router.get("", response_model=ItemListResponse, responses=LIST_RESPONSES)
async def list_items(
    params: Annotated[ItemListParams, Depends()],
    service: Annotated[ItemService, Depends(get_item_service)],
) -> ItemListResponse:
    return await service.list_items(params)


@router.get("/random", response_model=ItemResponse, responses=ITEM_RESPONSES)
async def get_random_item(
    params: Annotated[ItemFilterParams, Depends()],
    service: Annotated[ItemService, Depends(get_item_service)],
) -> ItemResponse:
    return await service.get_random(params)


@router.get("/{item_id}", response_model=ItemResponse, responses=ITEM_RESPONSES)
async def get_item(
    item_id: int,
    service: Annotated[ItemService, Depends(get_item_service)],
) -> ItemResponse:
    return await service.get_by_game_id(item_id)


@meta_router.get(
    "/meta",
    response_model=MetaResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def get_meta(
    request: Request,
    service: Annotated[ItemService, Depends(get_item_service)],
) -> MetaResponse:
    return await service.get_meta(request.app.version)
