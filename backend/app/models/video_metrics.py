"""VideoMetrics — append-only analytics snapshots (roadmap Sprint 8.1, guide §14).

Never overwrite previous values: every snapshot is a new row with captured_at,
so each experiment keeps a measurable real-world history.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class VideoMetrics(Base):
    __tablename__ = "video_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    published_video_id: Mapped[int] = mapped_column(
        ForeignKey("published_videos.id"), index=True, nullable=False
    )
    video_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    subscriber_count: Mapped[int] = mapped_column(Integer, default=0)
    # gained since the previous snapshot (first snapshot: 0)
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0)
    estimated_minutes_watched: Mapped[float] = mapped_column(Float, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(16), default="api")
