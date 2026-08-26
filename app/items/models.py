from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (CheckConstraint("quality BETWEEN 0 AND 4", name="quality_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(Text, index=True)
    description: Mapped[str] = mapped_column(Text)
    quality: Mapped[int | None] = mapped_column(Integer, index=True)
    item_type: Mapped[str | None] = mapped_column(Text, index=True)
    recharge_time: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(Text)
    introduced_in_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
