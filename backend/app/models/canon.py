"""Canon ORM model — persistent fictional-universe facts for a series (roadmap 2.1/14.1)."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class CanonCategory(str, enum.Enum):
    CHARACTER = "CHARACTER"
    LOCATION = "LOCATION"
    OBJECT = "OBJECT"
    EVENT = "EVENT"
    RELATIONSHIP = "RELATIONSHIP"
    RUNNING_JOKE = "RUNNING_JOKE"
    OTHER = "OTHER"


class Canon(Base):
    __tablename__ = "canon"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True, nullable=False)
    category: Mapped[CanonCategory] = mapped_column(Enum(CanonCategory), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
