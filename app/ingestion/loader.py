import json
import os
import stat
from pathlib import Path

from app.ingestion.schemas import ItemSnapshot

MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024


class SnapshotLoadError(ValueError):
    pass


def _read_snapshot_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SnapshotLoadError("Snapshot path is not a regular file")
        snapshot_file = os.fdopen(descriptor, "rb")
        descriptor = None
        with snapshot_file:
            return snapshot_file.read(MAX_SNAPSHOT_BYTES + 1)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_snapshot(path: Path) -> ItemSnapshot:
    try:
        raw_content = _read_snapshot_bytes(path)
    except (OSError, UnicodeError) as exc:
        raise SnapshotLoadError("Unable to read snapshot") from exc
    if len(raw_content) > MAX_SNAPSHOT_BYTES:
        raise SnapshotLoadError("Snapshot is too large")

    try:
        payload = json.loads(raw_content.decode("utf-8"))
    except (RecursionError, UnicodeError, ValueError) as exc:
        raise SnapshotLoadError("Snapshot contains invalid JSON") from exc

    return ItemSnapshot.model_validate(payload)
