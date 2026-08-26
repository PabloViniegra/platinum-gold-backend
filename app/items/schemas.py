from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ItemResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    game_id: int
    name: str
    description: str
    quality: int | None
    type: str | None
    recharge_time: str | None
    image_url: str
    introduced_in_version: str | None


class ItemFilterParams(BaseModel):
    search: str | None = None
    quality: int | None = Field(default=None, ge=0, le=4)
    type: str | None = None
    version: str | None = None


class ItemListParams(ItemFilterParams):
    sort: Literal["name", "quality", "game_id"] = "name"
    order: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int
    limit: int
    offset: int


class MetaResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    api_version: str
    dataset_version: str | None
    game_version: str | None
    last_sync: datetime | None
    items: int
