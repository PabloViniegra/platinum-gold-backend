"""create dataset metadata"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4f7c8e9a1b2d"
down_revision: str | Sequence[str] | None = "2a06a50207ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dataset_metadata",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_version", sa.Text(), nullable=False),
        sa.Column("game_version", sa.Text(), nullable=True),
        sa.Column("last_sync", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "id = 1",
            name=op.f("ck_dataset_metadata_singleton_key"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_metadata")),
    )


def downgrade() -> None:
    op.drop_table("dataset_metadata")
