import json
from json import JSONDecodeError
from pathlib import Path

from app.ingestion.schemas import ItemSnapshot


class SnapshotLoadError(ValueError):
    pass


def load_snapshot(path: Path) -> ItemSnapshot:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SnapshotLoadError("Unable to read snapshot") from exc

    try:
        payload = json.loads(content)
    except JSONDecodeError as exc:
        raise SnapshotLoadError("Snapshot contains invalid JSON") from exc

    return ItemSnapshot.model_validate(payload)
