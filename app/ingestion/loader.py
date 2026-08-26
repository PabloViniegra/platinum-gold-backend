import json
import os
import stat
from pathlib import Path

from app.ingestion.schemas import ItemSnapshot

MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024


class SnapshotLoadError(ValueError):
    pass


def _open_snapshot_descriptor(path: Path) -> int:
    if (
        os.open in os.supports_dir_fd
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
    ):
        directory_flags = (
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        file_flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | os.O_NOFOLLOW
            | getattr(os, "O_NONBLOCK", 0)
        )
        parts = path.parts
        if path.is_absolute():
            directory_descriptor = os.open(path.anchor, directory_flags)
            parts = parts[1:]
        else:
            directory_descriptor = os.open(".", directory_flags)
        try:
            if not parts:
                raise SnapshotLoadError("Snapshot path is not a regular file")
            for part in parts[:-1]:
                next_descriptor = os.open(
                    part,
                    directory_flags,
                    dir_fd=directory_descriptor,
                )
                os.close(directory_descriptor)
                directory_descriptor = next_descriptor
            return os.open(
                parts[-1],
                file_flags,
                dir_fd=directory_descriptor,
            )
        finally:
            os.close(directory_descriptor)

    raise SnapshotLoadError("Secure snapshot opening is unavailable")


def _read_snapshot_bytes(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = _open_snapshot_descriptor(path)
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
