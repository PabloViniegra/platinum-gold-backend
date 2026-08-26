from pydantic import BaseModel, ConfigDict
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
