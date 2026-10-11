"""StoryThread ORM model — unresolved narrative threads (roadmap Sprint 2.1/2.3)."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ThreadStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ABANDONED = "ABANDONED"


class StoryThread(Base):
    __tablename__ = "story_threads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ThreadStatus] = mapped_column(
        Enum(ThreadStatus), default=ThreadStatus.OPEN, nullable=False
    )
    introduced_episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("episodes.id"), nullable=True
    )
    resolved_episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("episodes.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
