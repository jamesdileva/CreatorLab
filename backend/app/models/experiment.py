"""ContentExperiment model — one immutable lifecycle record (roadmap 8.2, arch §9).

Links: simulation + episode + render + YouTube video + analytics in one row.
`reality_gap` is computed in Sprint 9.1; until then it stays null.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ContentExperiment(Base):
    __tablename__ = "content_experiments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id"), index=True, nullable=False
    )
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("episodes.id"), index=True, nullable=False
    )
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    variant: Mapped[str] = mapped_column(String(64), default="")
    simulation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=True
    )
    simulation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    simulation_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_video_id: Mapped[int | None] = mapped_column(
        ForeignKey("published_videos.id"), nullable=True
    )
    real_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reality_gap: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    conclusions: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
