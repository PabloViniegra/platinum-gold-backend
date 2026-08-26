from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Table, Text, UniqueConstraint

from app.core.database import Base
from app.items.models import Item

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def items_table() -> Table:
    return Base.metadata.tables["items"]


def test_base_uses_official_naming_convention() -> None:
    assert dict(Base.metadata.naming_convention) == NAMING_CONVENTION


def test_item_is_registered_on_base_metadata() -> None:
    assert Item.__tablename__ == "items"
    assert "items" in Base.metadata.tables


def test_item_columns_match_schema_contract() -> None:
    table = items_table()
    assert set(table.c.keys()) == {
        "id",
        "game_id",
        "name",
        "description",
        "quality",
        "item_type",
        "recharge_time",
        "image_url",
        "introduced_in_version",
        "created_at",
        "updated_at",
    }
    assert isinstance(table.c.id.type, Integer)
    assert isinstance(table.c.game_id.type, Integer)
    assert isinstance(table.c.quality.type, Integer)
    assert isinstance(table.c.name.type, Text)
    assert isinstance(table.c.description.type, Text)
    assert isinstance(table.c.item_type.type, Text)
    assert isinstance(table.c.recharge_time.type, Text)
    assert isinstance(table.c.image_url.type, Text)
    assert isinstance(table.c.introduced_in_version.type, Text)
    assert isinstance(table.c.created_at.type, DateTime)
    assert isinstance(table.c.updated_at.type, DateTime)
    assert table.c.created_at.type.timezone is True
    assert table.c.updated_at.type.timezone is True


def test_item_nullability_matches_schema_contract() -> None:
    table = items_table()
    required = {
        "id",
        "game_id",
        "name",
        "description",
        "image_url",
        "created_at",
        "updated_at",
    }
    optional = {
        "quality",
        "item_type",
        "recharge_time",
        "introduced_in_version",
    }
    for name in required:
        assert table.c[name].nullable is False, name
    for name in optional:
        assert table.c[name].nullable is True, name


def test_game_id_is_unique() -> None:
    uniques = [
        constraint
        for constraint in items_table().constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert any(list(constraint.columns.keys()) == ["game_id"] for constraint in uniques)


def test_quality_has_range_check() -> None:
    checks = [
        constraint
        for constraint in items_table().constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert any("BETWEEN 0 AND 4" in str(constraint.sqltext) for constraint in checks)


def test_item_has_filter_indexes() -> None:
    indexed = {
        tuple(column.name for column in index.columns)
        for index in items_table().indexes
    }
    assert ("quality",) in indexed
    assert ("item_type",) in indexed
    assert ("name",) in indexed


def test_timestamps_have_server_default() -> None:
    table = items_table()
    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None
    assert table.c.created_at.type.python_type is datetime
    assert table.c.updated_at.type.python_type is datetime
