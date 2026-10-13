"""Simulation runs + per-viewer reactions (roadmap Sprint 4.2, arch §10).

Every run stores the full reproducibility record (guide §9): model,
prompt version, audience version, seed, viewer count, timestamp.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .viewer import AUDIENCE_VERSION

REACTION_VERSION = "reaction-v2"
RANKING_VERSION = "ranking-v1"


class TargetType(str, enum.Enum):
    CONCEPT = "concept"
    EPISODE = "episode"


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_uuid: Mapped[str] = mapped_column(
        String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="stub/deterministic-v1")
    prompt_version: Mapped[str] = mapped_column(String(64), default=REACTION_VERSION)
    audience_version: Mapped[str] = mapped_column(String(32), default=AUDIENCE_VERSION)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    viewer_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class ViewerReaction(Base):
    __tablename__ = "viewer_reactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id"), index=True, nullable=False
    )
    viewer_id: Mapped[int] = mapped_column(
        ForeignKey("synthetic_viewers.id"), index=True, nullable=False
    )
    watch_probability: Mapped[float] = mapped_column(Float, nullable=False)
    like_probability: Mapped[float] = mapped_column(Float, nullable=False)
    comment_probability: Mapped[float] = mapped_column(Float, nullable=False)
    share_probability: Mapped[float] = mapped_column(Float, nullable=False)
    follow_probability: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class RankingRun(Base):
    """One ranking of several candidates through the same audience (Sprint 4.3)."""

    __tablename__ = "ranking_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_uuid: Mapped[str] = mapped_column(
        String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )
    candidate_type: Mapped[str] = mapped_column(String(16), nullable=False)
    candidate_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    metric: Mapped[str] = mapped_column(String(32), default="watch_probability")
    ranking: Mapped[list[int]] = mapped_column(JSON, default=list)
    simulation_run_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(64), default="stub/deterministic-v1")
    prompt_version: Mapped[str] = mapped_column(String(64), default=RANKING_VERSION)
    audience_version: Mapped[str] = mapped_column(String(32), default=AUDIENCE_VERSION)
    viewer_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
