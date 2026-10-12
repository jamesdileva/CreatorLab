"""PublishedVideo model — what actually went to YouTube (roadmap Sprint 7.2/7.3)."""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class PublishedVideo(Base):
    __tablename__ = "published_videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("episodes.id"), index=True, nullable=False
    )
    render_id: Mapped[int] = mapped_column(
        ForeignKey("renders.id"), index=True, nullable=False
    )
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    video_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    privacy_status: Mapped[str] = mapped_column(String(16), default="private")
    status: Mapped[str] = mapped_column(String(24), default="uploaded")
    youtube_status: Mapped[str] = mapped_column(String(32), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    video_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    total_duration: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    upload_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
