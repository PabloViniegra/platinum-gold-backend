"""create items"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2a06a50207ce"
down_revision: str | Sequence[str] | None = "3159b05b2715"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quality", sa.Integer(), nullable=True),
        sa.Column("item_type", sa.Text(), nullable=True),
        sa.Column("recharge_time", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("introduced_in_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quality BETWEEN 0 AND 4",
            name=op.f("ck_items_quality_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_items")),
        sa.UniqueConstraint("game_id", name=op.f("uq_items_game_id")),
    )
    op.create_index(op.f("ix_items_item_type"), "items", ["item_type"], unique=False)
    op.create_index(op.f("ix_items_name"), "items", ["name"], unique=False)
    op.create_index(op.f("ix_items_quality"), "items", ["quality"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_items_quality"), table_name="items")
    op.drop_index(op.f("ix_items_name"), table_name="items")
    op.drop_index(op.f("ix_items_item_type"), table_name="items")
    op.drop_table("items")
