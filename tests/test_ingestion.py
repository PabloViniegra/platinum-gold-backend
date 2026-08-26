import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.ingestion.loader import SnapshotLoadError, load_snapshot
from app.ingestion.schemas import ItemSnapshot

SnapshotPayload = dict[str, Any]


def valid_payload() -> SnapshotPayload:
    return {
        "datasetVersion": "platinum-god-2026-08-26",
        "gameVersion": "repentance",
        "items": [
            {
                "gameId": 118,
                "name": " Brimstone ",
                "description": " Tears are replaced by a laser beam. ",
                "quality": 4,
                "type": " passive ",
                "rechargeTime": None,
                "imageUrl": "https://example.com/118.png",
                "introducedInVersion": " rebirth ",
            }
        ],
    }


def test_load_snapshot_accepts_camel_case_and_strips_strings(tmp_path: Path) -> None:
    path = tmp_path / "items.json"
    path.write_text(json.dumps(valid_payload()), encoding="utf-8")

    snapshot = load_snapshot(path)

    assert snapshot.dataset_version == "platinum-god-2026-08-26"
    assert snapshot.game_version == "repentance"
    assert snapshot.items[0].game_id == 118
    assert snapshot.items[0].name == "Brimstone"
    assert snapshot.items[0].description == "Tears are replaced by a laser beam."
    assert snapshot.items[0].item_type == "passive"
    assert snapshot.items[0].introduced_in_version == "rebirth"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gameId", "118"),
        ("name", "   "),
        ("quality", 5),
        ("imageUrl", "ftp://example.com/118.png"),
    ],
)
def test_snapshot_rejects_invalid_item_fields(field: str, value: object) -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    items[0][field] = value

    with pytest.raises(ValidationError):
        ItemSnapshot.model_validate(payload)


def test_snapshot_rejects_duplicate_game_ids() -> None:
    payload = valid_payload()
    items = cast(list[dict[str, Any]], payload["items"])
    items.append(dict(items[0]))

    with pytest.raises(ValidationError, match="gameId"):
        ItemSnapshot.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {**valid_payload(), "items": []},
        {**valid_payload(), "unexpected": True},
        {
            **valid_payload(),
            "items": [{**valid_payload()["items"][0], "unexpected": True}],
        },
    ],
)
def test_snapshot_rejects_empty_items_and_unknown_fields(
    payload: SnapshotPayload,
) -> None:
    with pytest.raises(ValidationError):
        ItemSnapshot.model_validate(payload)


def test_load_snapshot_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "items.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(SnapshotLoadError):
        load_snapshot(path)


def test_load_snapshot_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SnapshotLoadError):
        load_snapshot(tmp_path / "missing.json")
