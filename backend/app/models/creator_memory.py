"""CreatorMemory ORM model — structured memory (architecture §9, guide Phase 3).

Explicit structured memory first; embeddings/RAG only if needed later.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class MemoryType(str, enum.Enum):
    CANON = "CANON"
    EVENT = "EVENT"
    PREFERENCE = "PREFERENCE"
    RELATIONSHIP = "RELATIONSHIP"
    RUNNING_JOKE = "RUNNING_JOKE"
    CONTENT_LESSON = "CONTENT_LESSON"
    AUDIENCE_DISCOVERY = "AUDIENCE_DISCOVERY"


class CreatorMemory(Base):
    __tablename__ = "creator_memories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id"), index=True, nullable=False
    )
    type: Mapped[MemoryType] = mapped_column(Enum(MemoryType), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
