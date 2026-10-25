"""Major research checkpoint snapshots (roadmap Phase 25).

Immutable records of the simulator-vs-random-vs-human evaluation, so the
project's direction stays evidence-driven and reproducible.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

CHECKPOINT_VERSION = "checkpoint-v1"


class MajorCheckpoint(Base):
    __tablename__ = "major_checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    min_samples: Mapped[int] = mapped_column(Integer, default=5)
    experiments_scored: Mapped[int] = mapped_column(Integer, default=0)
    panel_rankings_recorded: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(20), default="insufficient")
    recommendation: Mapped[str] = mapped_column(String(24), default="collect_more_data")
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_version: Mapped[str] = mapped_column(
        String(40), default=CHECKPOINT_VERSION
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
