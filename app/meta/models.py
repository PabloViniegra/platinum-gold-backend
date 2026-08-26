from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DatasetMetadata(Base):
    __tablename__ = "dataset_metadata"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version: Mapped[str] = mapped_column(Text)
    game_version: Mapped[str | None] = mapped_column(Text)
    last_sync: Mapped[datetime] = mapped_column(DateTime(timezone=True))
