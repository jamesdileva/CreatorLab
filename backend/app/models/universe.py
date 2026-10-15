"""Universe canon — shared world facts across every creator (roadmap 14.1).

Three context tiers, smallest first:
1. creator memory (identity-level, Sprint 1.3)
2. series canon (one show, Sprint 2.1)
3. universe canon (shared world, THIS file) — generation must never contradict it
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class UniverseKind(str, enum.Enum):
    LOCATION = "LOCATION"
    CHARACTER = "CHARACTER"
    EVENT = "EVENT"
    OBJECT = "OBJECT"
    RELATIONSHIP = "RELATIONSHIP"
    TIMELINE = "TIMELINE"


class UniverseEntity(Base):
    __tablename__ = "universe_entities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
