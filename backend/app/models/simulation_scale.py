"""Large-scale simulation studies (roadmap Phase 24).

One row records a ladder study: the same episodes simulated at increasing
audience sizes, then compared against real-world views. The research question
is whether a larger population improves predictive validity — not assumed.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

SCALE_VERSION = "scale-v1"
SCALE_LADDER = (25, 100, 500, 1000, 10000)


class SimulationScaleStudy(Base):
    __tablename__ = "simulation_scale_studies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    metric: Mapped[str] = mapped_column(String(40), default="watch_probability")
    seed: Mapped[int] = mapped_column(Integer, default=0)
    sizes: Mapped[list[int]] = mapped_column(JSON, default=list)
    episode_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    creator_id: Mapped[int | None] = mapped_column(
        ForeignKey("creators.id"), nullable=True
    )
    min_pairs: Mapped[int] = mapped_column(Integer, default=3)
    threshold: Mapped[float] = mapped_column(default=0.6)
    results: Mapped[list] = mapped_column(JSON, default=list)
    min_useful_viewer_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str] = mapped_column(String(80), default="stub/deterministic-v1")
    prompt_version: Mapped[str] = mapped_column(String(40), default=SCALE_VERSION)
    audience_version: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
