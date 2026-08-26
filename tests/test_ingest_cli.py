import json
from pathlib import Path

import pytest

from app.core.exceptions import AppError
from app.ingestion.schemas import ItemSnapshot
from scripts import ingest as ingest_module


def snapshot_path(tmp_path: Path) -> Path:
    path = tmp_path / "items.json"
    path.write_text(
        json.dumps(
            {
                "datasetVersion": "platinum-god-2026-08-26",
                "gameVersion": "repentance",
                "items": [
                    {
                        "gameId": 118,
                        "name": "Brimstone",
                        "description": "Tears are replaced by a laser beam.",
                        "quality": 4,
                        "type": "passive",
                        "rechargeTime": None,
                        "imageUrl": "https://example.com/118.png",
                        "introducedInVersion": "rebirth",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


def test_cli_ingests_snapshot_and_disposes_database_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = snapshot_path(tmp_path)
    engine = FakeEngine()
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, session_factory: object) -> None:
            captured["session_factory"] = session_factory

        async def ingest(self, snapshot: ItemSnapshot) -> None:
            captured["snapshot"] = snapshot

    def fake_create_database(_settings: object) -> tuple[FakeEngine, str]:
        return engine, "session-factory"

    monkeypatch.setattr(ingest_module, "Settings", lambda: "settings")
    monkeypatch.setattr(ingest_module, "create_database", fake_create_database)
    monkeypatch.setattr(ingest_module, "IngestionService", FakeService)

    result = ingest_module.main(["--input", str(path)])

    assert result == 0
    assert engine.disposed is True
    assert captured["session_factory"] == "session-factory"
    snapshot = captured["snapshot"]
    assert isinstance(snapshot, ItemSnapshot)
    assert snapshot.items[0].game_id == 118


def test_cli_rejects_invalid_snapshot_before_creating_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "items.json"
    path.write_text(
        json.dumps(
            {
                "datasetVersion": "not-a-secret",
                "gameVersion": None,
                "items": [],
            }
        ),
        encoding="utf-8",
    )

    def unexpected_settings() -> None:
        raise AssertionError("configuration should not be loaded")

    monkeypatch.setattr(ingest_module, "Settings", unexpected_settings)

    result = ingest_module.main(["--input", str(path)])

    assert result != 0
    assert "not-a-secret" not in capsys.readouterr().err


def test_cli_reports_database_failure_without_connection_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = FakeEngine()

    class FakeService:
        def __init__(self, _session_factory: object) -> None:
            pass

        async def ingest(self, _snapshot: ItemSnapshot) -> None:
            raise AppError(
                503,
                "SERVICE_UNAVAILABLE",
                "A required service is unavailable",
            )

    def fake_create_database(_settings: object) -> tuple[FakeEngine, str]:
        return engine, "session-factory"

    monkeypatch.setattr(ingest_module, "Settings", lambda: "settings")
    monkeypatch.setattr(ingest_module, "create_database", fake_create_database)
    monkeypatch.setattr(ingest_module, "IngestionService", FakeService)

    result = ingest_module.main(["--input", str(snapshot_path(tmp_path))])

    assert result != 0
    assert engine.disposed is True
    assert "DATABASE_URL" not in capsys.readouterr().err
