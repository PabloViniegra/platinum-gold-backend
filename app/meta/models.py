from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DatasetMetadata(Base):
    __tablename__ = "dataset_metadata"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_key"),
        CheckConstraint(
            "btrim(dataset_version) <> ''",
            name="dataset_version_nonempty",
        ),
        CheckConstraint(
            "game_version IS NULL OR btrim(game_version) <> ''",
            name="game_version_nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    dataset_version: Mapped[str] = mapped_column(Text)
    game_version: Mapped[str | None] = mapped_column(Text)
    last_sync: Mapped[datetime] = mapped_column(DateTime(timezone=True))
