import json
from pathlib import Path

import asyncpg  # type: ignore[reportMissingTypeStubs]
import pytest
from pydantic import ValidationError

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


class FakeRedis:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        fail_invalidation: Exception | None = None,
    ) -> None:
        self.closed = False
        self.events = events if events is not None else []
        self.fail_invalidation = fail_invalidation

    async def aclose(self) -> None:
        self.closed = True


class FakeInvalidationCache:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis

    async def invalidate(self) -> int:
        self.redis.events.append("invalidate")
        if self.redis.fail_invalidation is not None:
            raise self.redis.fail_invalidation
        return 101


def patch_redis(
    monkeypatch: pytest.MonkeyPatch,
    redis: FakeRedis,
) -> None:
    def fake_create_redis(_settings: object) -> FakeRedis:
        return redis

    monkeypatch.setattr(ingest_module, "create_redis", fake_create_redis)
    monkeypatch.setattr(ingest_module, "RedisItemCache", FakeInvalidationCache)


def test_cli_ingests_snapshot_and_disposes_database_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = snapshot_path(tmp_path)
    engine = FakeEngine()
    events: list[str] = []
    redis = FakeRedis(events=events)
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, session_factory: object) -> None:
            captured["session_factory"] = session_factory

        async def ingest(self, snapshot: ItemSnapshot) -> None:
            captured["snapshot"] = snapshot
            events.append("committed")

    def fake_create_database(_settings: object) -> tuple[FakeEngine, str]:
        return engine, "session-factory"

    monkeypatch.setattr(ingest_module, "IngestionSettings", lambda: "settings")
    monkeypatch.setattr(ingest_module, "create_database", fake_create_database)
    monkeypatch.setattr(ingest_module, "IngestionService", FakeService)
    patch_redis(monkeypatch, redis)

    result = ingest_module.main(["--input", str(path)])

    assert result == 0
    assert engine.disposed is True
    assert redis.closed is True
    assert events == ["committed", "invalidate"]
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

    calls: list[str] = []

    def unexpected_settings() -> str:
        calls.append("settings")
        return "settings"

    def unexpected_database(_settings: object) -> tuple[FakeEngine, str]:
        calls.append("database")
        raise AssertionError("database should not be created")

    monkeypatch.setattr(ingest_module, "IngestionSettings", unexpected_settings)
    monkeypatch.setattr(ingest_module, "create_database", unexpected_database)

    result = ingest_module.main(["--input", str(path)])

    assert result == 2
    assert calls == []
    assert "not-a-secret" not in capsys.readouterr().err


def test_cli_reports_database_failure_without_connection_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = FakeEngine()
    redis = FakeRedis()

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

    monkeypatch.setattr(ingest_module, "IngestionSettings", lambda: "settings")
    monkeypatch.setattr(ingest_module, "create_database", fake_create_database)
    monkeypatch.setattr(ingest_module, "IngestionService", FakeService)
    patch_redis(monkeypatch, redis)

    result = ingest_module.main(["--input", str(snapshot_path(tmp_path))])

    assert result != 0
    assert engine.disposed is True
    assert redis.closed is True
    assert "DATABASE_URL" not in capsys.readouterr().err


def test_cli_sanitizes_asyncpg_driver_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeService:
        def __init__(self, _session_factory: object) -> None:
            pass

        async def ingest(self, _snapshot: ItemSnapshot) -> None:
            raise asyncpg.InvalidPasswordError(
                "password authentication failed for user postgres"
            )

    engine = FakeEngine()
    redis = FakeRedis()

    def fake_create_database(_settings: object) -> tuple[FakeEngine, str]:
        return engine, "session-factory"

    monkeypatch.setattr(ingest_module, "IngestionSettings", lambda: "settings")
    monkeypatch.setattr(ingest_module, "create_database", fake_create_database)
    monkeypatch.setattr(ingest_module, "IngestionService", FakeService)
    patch_redis(monkeypatch, redis)

    result = ingest_module.main(["--input", str(snapshot_path(tmp_path))])

    assert result == 1
    error = capsys.readouterr().err
    assert error == "Ingestion failed: required service is unavailable\n"
    assert "postgres" not in error
    assert redis.closed is True


def test_cli_reports_configuration_failure_separately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_class = ingest_module.IngestionSettings

    def invalid_settings() -> object:
        raise ValidationError.from_exception_data(
            settings_class.__name__,
            [
                {
                    "type": "missing",
                    "loc": ("database_url",),
                    "input": {},
                }
            ],
        )

    monkeypatch.setattr(ingest_module, "IngestionSettings", invalid_settings)

    result = ingest_module.main(["--input", str(snapshot_path(tmp_path))])

    assert result == 2
    error = capsys.readouterr().err
    assert "configuration is invalid" in error
    assert "Invalid snapshot" not in error
    assert "DATABASE_URL" not in error


def test_cli_escapes_control_characters_in_validation_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = snapshot_path(tmp_path).read_text(encoding="utf-8")
    data = json.loads(payload)
    data["\x1b[31msecret"] = True
    data["x" * 1000] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    result = ingest_module.main(["--input", str(path)])

    assert result == 2
    error = capsys.readouterr().err
    assert "\x1b" not in error
    assert "\\x1b[31msecret" in error
    assert len(error) < 500


def test_cli_sanitizes_database_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid_database(_settings: object) -> tuple[FakeEngine, str]:
        raise ValueError("invalid database URL with db-secret")

    monkeypatch.setattr(ingest_module, "IngestionSettings", lambda: "settings")
    monkeypatch.setattr(ingest_module, "create_database", invalid_database)

    result = ingest_module.main(["--input", str(snapshot_path(tmp_path))])

    assert result == 2
    error = capsys.readouterr().err
    assert error == "Ingestion failed: configuration is invalid\n"
    assert "db-secret" not in error


def test_cli_sanitizes_unexpected_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeService:
        def __init__(self, _session_factory: object) -> None:
            pass

        async def ingest(self, _snapshot: ItemSnapshot) -> None:
            raise RuntimeError("driver details with db-secret")

    redis = FakeRedis()
    monkeypatch.setattr(ingest_module, "IngestionSettings", lambda: "settings")

    def fake_create_database(_settings: object) -> tuple[FakeEngine, str]:
        return FakeEngine(), "session-factory"

    monkeypatch.setattr(ingest_module, "create_database", fake_create_database)
    monkeypatch.setattr(ingest_module, "IngestionService", FakeService)
    patch_redis(monkeypatch, redis)

    result = ingest_module.main(["--input", str(snapshot_path(tmp_path))])

    assert result == 1
    error = capsys.readouterr().err
    assert error == "Ingestion failed: unexpected internal error\n"
    assert "db-secret" not in error
    assert redis.closed is True


def test_cli_reports_post_commit_invalidation_failure_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    engine = FakeEngine()
    redis = FakeRedis(events=events, fail_invalidation=OSError("redis-secret"))

    class FakeService:
        def __init__(self, _session_factory: object) -> None:
            pass

        async def ingest(self, _snapshot: ItemSnapshot) -> None:
            events.append("committed")

    monkeypatch.setattr(ingest_module, "IngestionSettings", lambda: "settings")

    def fake_create_database(_settings: object) -> tuple[FakeEngine, str]:
        return engine, "session-factory"

    monkeypatch.setattr(
        ingest_module,
        "create_database",
        fake_create_database,
    )
    monkeypatch.setattr(ingest_module, "IngestionService", FakeService)
    patch_redis(monkeypatch, redis)

    result = ingest_module.main(["--input", str(snapshot_path(tmp_path))])

    assert result == 1
    assert events == ["committed", "invalidate"]
    assert engine.disposed is True
    assert redis.closed is True
    error = capsys.readouterr().err
    assert error == (
        "Ingestion failed: data was published but cache invalidation failed; "
        "repeat ingestion to retry\n"
    )
    assert "redis-secret" not in error


def test_cli_can_retry_post_commit_invalidation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state = {"fail": True, "attempts": 0}
    engines: list[FakeEngine] = []
    redises: list[FakeRedis] = []

    class FakeService:
        def __init__(self, _session_factory: object) -> None:
            pass

        async def ingest(self, _snapshot: ItemSnapshot) -> None:
            pass

    def fake_create_database(_settings: object) -> tuple[FakeEngine, str]:
        engine = FakeEngine()
        engines.append(engine)
        return engine, "session-factory"

    def fake_create_redis(_settings: object) -> FakeRedis:
        redis = FakeRedis()
        redises.append(redis)
        return redis

    class RetryableCache(FakeInvalidationCache):
        async def invalidate(self) -> int:
            state["attempts"] += 1
            if state["fail"]:
                state["fail"] = False
                self.redis.events.append("invalidate")
                raise OSError("redis-secret")
            return await super().invalidate()

    monkeypatch.setattr(ingest_module, "IngestionSettings", lambda: "settings")
    monkeypatch.setattr(ingest_module, "create_database", fake_create_database)
    monkeypatch.setattr(ingest_module, "create_redis", fake_create_redis)
    monkeypatch.setattr(ingest_module, "RedisItemCache", RetryableCache)
    monkeypatch.setattr(ingest_module, "IngestionService", FakeService)

    first = ingest_module.main(["--input", str(snapshot_path(tmp_path))])
    second = ingest_module.main(["--input", str(snapshot_path(tmp_path))])

    assert first == 1
    assert second == 0
    assert state["attempts"] == 2
    assert all(engine.disposed for engine in engines)
    assert all(redis.closed for redis in redises)


def test_cli_rejects_invalid_arguments_without_echoing_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = ingest_module.main(["--unexpected", "\x1b[31msecret"])

    assert result == 2
    error = capsys.readouterr().err
    assert error == "Invalid command-line arguments\n"
    assert "\x1b" not in error
