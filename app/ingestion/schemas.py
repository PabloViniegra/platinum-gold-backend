from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class ItemImport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    game_id: StrictInt = Field(gt=0, alias="gameId")
    name: NonEmptyString
    description: NonEmptyString
    quality: StrictInt | None = Field(default=None, ge=0, le=4)
    item_type: NonEmptyString | None = Field(default=None, alias="type")
    recharge_time: NonEmptyString | None = Field(
        default=None,
        alias="rechargeTime",
    )
    image_url: NonEmptyString = Field(alias="imageUrl")
    introduced_in_version: NonEmptyString | None = Field(
        default=None,
        alias="introducedInVersion",
    )

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("imageUrl must be an absolute HTTP(S) URL")
        return value


class ItemSnapshot(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    dataset_version: NonEmptyString = Field(alias="datasetVersion")
    game_version: NonEmptyString | None = Field(default=None, alias="gameVersion")
    items: list[ItemImport] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_game_ids(self) -> "ItemSnapshot":
        game_ids = [item.game_id for item in self.items]
        if len(game_ids) != len(set(game_ids)):
            raise ValueError("items.gameId must be unique")
        return self
