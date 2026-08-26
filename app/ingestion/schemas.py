from typing import Annotated, cast
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    FailFast,
    Field,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)


def reject_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("strings must not contain NUL")
    return value


def reject_oversized_string(value: object) -> object:
    if isinstance(value, str) and len(value) > MAX_SNAPSHOT_STRING_LENGTH:
        raise ValueError("strings exceed the maximum length")
    return value


MAX_GAME_ID = 2_147_483_647
MAX_SNAPSHOT_ITEMS = 10_000
MAX_SNAPSHOT_STRING_LENGTH = 4_096
NonEmptyString = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=MAX_SNAPSHOT_STRING_LENGTH,
        strip_whitespace=True,
    ),
    BeforeValidator(reject_oversized_string),
    AfterValidator(reject_nul),
]
ITEM_IMPORT_FIELDS = frozenset(
    {
        "gameId",
        "name",
        "description",
        "quality",
        "type",
        "rechargeTime",
        "imageUrl",
        "introducedInVersion",
    }
)
SNAPSHOT_FIELDS = frozenset({"datasetVersion", "gameVersion", "items"})


def reject_unknown_fields(
    value: object,
    allowed_fields: frozenset[str],
    title: str,
) -> object:
    if isinstance(value, dict):
        fields = cast(dict[object, object], value)
        for key, field_value in fields.items():
            if key not in allowed_fields:
                location = key if isinstance(key, (str, int)) else repr(key)
                raise ValidationError.from_exception_data(
                    title,
                    [
                        {
                            "type": "extra_forbidden",
                            "loc": (location,),
                            "input": field_value,
                        }
                    ],
                )
    return cast(object, value)


class ItemImport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    game_id: StrictInt = Field(gt=0, le=MAX_GAME_ID, alias="gameId")
    name: NonEmptyString
    description: NonEmptyString
    quality: StrictInt | None = Field(ge=0, le=4)
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

    @model_validator(mode="before")
    @classmethod
    def validate_known_fields(cls, value: object) -> object:
        return reject_unknown_fields(value, ITEM_IMPORT_FIELDS, cls.__name__)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.hostname is None
                or parsed.netloc.endswith(":")
                or parsed.username is not None
                or parsed.password is not None
                or "\\" in value
                or any(
                    character.isspace() or ord(character) < 32 or ord(character) == 127
                    for character in value
                )
            ):
                raise ValueError
            port = parsed.port
            if port is not None and not 0 <= port <= 65535:
                raise ValueError
        except ValueError as exc:
            raise ValueError("imageUrl must be an absolute HTTP(S) URL") from exc
        return value


class ItemSnapshot(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    dataset_version: NonEmptyString = Field(alias="datasetVersion")
    game_version: NonEmptyString | None = Field(default=None, alias="gameVersion")
    items: Annotated[list[ItemImport], FailFast()] = Field(
        min_length=1,
        max_length=MAX_SNAPSHOT_ITEMS,
    )

    @model_validator(mode="before")
    @classmethod
    def validate_known_fields(cls, value: object) -> object:
        return reject_unknown_fields(value, SNAPSHOT_FIELDS, cls.__name__)

    @model_validator(mode="after")
    def reject_duplicate_game_ids(self) -> "ItemSnapshot":
        game_ids = [item.game_id for item in self.items]
        if len(game_ids) != len(set(game_ids)):
            raise ValueError("items.gameId must be unique")
        return self
