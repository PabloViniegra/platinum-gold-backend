from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime, Integer, PrimaryKeyConstraint, Text

from app.core.database import Base
from app.meta.models import DatasetMetadata


def metadata_table():
    return Base.metadata.tables["dataset_metadata"]


def test_dataset_metadata_is_registered_on_base_metadata() -> None:
    assert DatasetMetadata.__tablename__ == "dataset_metadata"
    assert "dataset_metadata" in Base.metadata.tables


def test_dataset_metadata_columns_match_contract() -> None:
    table = metadata_table()

    assert set(table.c.keys()) == {
        "id",
        "dataset_version",
        "game_version",
        "last_sync",
    }
    assert isinstance(table.c.id.type, Integer)
    assert isinstance(table.c.dataset_version.type, Text)
    assert isinstance(table.c.game_version.type, Text)
    assert isinstance(table.c.last_sync.type, DateTime)
    assert table.c.last_sync.type.timezone is True
    assert table.c.id.autoincrement is False


def test_dataset_metadata_has_singleton_constraints() -> None:
    table = metadata_table()
    checks = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    primary_keys = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, PrimaryKeyConstraint)
    ]

    check_sql = {str(constraint.sqltext) for constraint in checks}
    assert "id = 1" in check_sql
    assert "btrim(dataset_version) <> ''" in check_sql
    assert "game_version IS NULL OR btrim(game_version) <> ''" in check_sql
    assert any(list(constraint.columns.keys()) == ["id"] for constraint in primary_keys)
    assert table.c.dataset_version.nullable is False
    assert table.c.game_version.nullable is True
    assert table.c.last_sync.nullable is False


def test_alembic_env_imports_dataset_metadata_model() -> None:
    assert "app.meta.models" in Path("alembic/env.py").read_text()


def test_latest_migration_creates_and_drops_dataset_metadata() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head = script.get_current_head()
    assert head is not None
    revision = script.get_revision(head)
    source = " ".join(Path(revision.path).read_text().split())

    assert "op.create_table(" in source
    assert '"dataset_metadata"' in source
    assert "op.drop_table(" in source
