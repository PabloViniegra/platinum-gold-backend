import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.ingestion import loader as loader_module
from app.ingestion.loader import SnapshotLoadError, load_snapshot
from app.ingestion.schemas import (
    MAX_SNAPSHOT_ITEMS,
    MAX_SNAPSHOT_STRING_LENGTH,
    ItemSnapshot,
)

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
    ("raw", "expected"),
    [
        ("Passive", "passive"),
        ("ACTIVE", "active"),
        (" Familiar ", "familiar"),
    ],
)
def test_snapshot_normalizes_item_type_to_lowercase(raw: str, expected: str) -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    items[0]["type"] = raw

    snapshot = ItemSnapshot.model_validate(payload)

    assert snapshot.items[0].item_type == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gameId", "118"),
        ("name", "   "),
        ("quality", 5),
        ("imageUrl", "ftp://example.com/118.png"),
        ("imageUrl", "https://:443/118.png"),
        ("imageUrl", "https://example.com:bad/118.png"),
        ("imageUrl", "https:example.com/118.png"),
        ("imageUrl", "http:/example.com/118.png"),
        ("imageUrl", "https://user:password@example.com/118.png"),
        ("gameId", 2147483648),
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
    "field",
    [
        "datasetVersion",
        "gameVersion",
        "name",
        "description",
        "type",
        "rechargeTime",
        "introducedInVersion",
    ],
)
def test_snapshot_rejects_nul_in_persisted_strings(field: str) -> None:
    payload = valid_payload()
    if field in {"datasetVersion", "gameVersion"}:
        payload[field] = "value\x00"
    else:
        items = payload["items"]
        assert isinstance(items, list)
        assert isinstance(items[0], dict)
        items[0][field] = "value\x00"

    with pytest.raises(ValidationError):
        ItemSnapshot.model_validate(payload)


def test_snapshot_fails_fast_on_invalid_items() -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    item = cast(dict[str, Any], items[0])
    payload["items"] = [dict(item, name="") for _ in range(1000)]

    with pytest.raises(ValidationError) as error:
        ItemSnapshot.model_validate(payload)

    assert len(error.value.errors()) == 1


def test_snapshot_fails_fast_on_unknown_top_level_fields() -> None:
    payload = valid_payload()
    payload.update({f"unknown{index}": True for index in range(1000)})

    with pytest.raises(ValidationError) as error:
        ItemSnapshot.model_validate(payload)

    assert len(error.value.errors()) == 1


def test_snapshot_rejects_excessive_item_count() -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    payload["items"] = [
        {**items[0], "gameId": game_id} for game_id in range(1, MAX_SNAPSHOT_ITEMS + 2)
    ]

    with pytest.raises(ValidationError):
        ItemSnapshot.model_validate(payload)


def test_snapshot_rejects_excessive_string_length() -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    items[0]["description"] = " " * MAX_SNAPSHOT_STRING_LENGTH + "x"

    with pytest.raises(ValidationError):
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


def test_load_snapshot_rejects_non_regular_file(tmp_path: Path) -> None:
    with pytest.raises(SnapshotLoadError, match="regular file"):
        load_snapshot(tmp_path)


def test_load_snapshot_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "items.json"
    target.write_text(json.dumps(valid_payload()), encoding="utf-8")
    link = tmp_path / "items-link.json"
    link.symlink_to(target)

    with pytest.raises(SnapshotLoadError):
        load_snapshot(link)


def test_load_snapshot_rejects_symlinked_parent(tmp_path: Path) -> None:
    target_directory = tmp_path / "target"
    target_directory.mkdir()
    (target_directory / "items.json").write_text(
        json.dumps(valid_payload()),
        encoding="utf-8",
    )
    linked_directory = tmp_path / "linked"
    linked_directory.symlink_to(target_directory, target_is_directory=True)

    with pytest.raises(SnapshotLoadError):
        load_snapshot(linked_directory / "items.json")


def test_load_snapshot_fails_closed_without_secure_opening(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "items.json"
    path.write_text(json.dumps(valid_payload()), encoding="utf-8")
    monkeypatch.setattr(loader_module.os, "supports_dir_fd", set[object]())

    with pytest.raises(SnapshotLoadError, match="Secure snapshot opening"):
        load_snapshot(path)


def test_snapshot_requires_quality_field() -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    del items[0]["quality"]

    with pytest.raises(ValidationError):
        ItemSnapshot.model_validate(payload)


def test_snapshot_accepts_long_http_url() -> None:
    payload = valid_payload()
    items = payload["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    items[0]["imageUrl"] = "https://example.com/" + "x" * 2100

    ItemSnapshot.model_validate(payload)


def test_load_snapshot_rejects_json_integer_overflow(tmp_path: Path) -> None:
    path = tmp_path / "items.json"
    path.write_text("9" * 4301, encoding="utf-8")

    with pytest.raises(SnapshotLoadError):
        load_snapshot(path)


def test_load_snapshot_rejects_oversized_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(loader_module, "MAX_SNAPSHOT_BYTES", 10)
    path = tmp_path / "items.json"
    path.write_text("{" + " " * 10 + "}", encoding="utf-8")

    with pytest.raises(SnapshotLoadError):
        load_snapshot(path)
