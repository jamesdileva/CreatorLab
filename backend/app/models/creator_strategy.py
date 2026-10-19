"""Creator strategy + evidence-backed evolution proposals (roadmap Sprint 22.1).

`CreatorStrategy` is a creator's current applied strategy profile (format mix,
topic mix, pacing, episode structure, humor style). `StrategyProposal` is an
immutable, evidence-backed proposal to change one dimension — the creator never
changes strategy on an unbacked hunch (guide: "no 'the AI thinks this will
work'"). Proposals are only applied on an explicit human decision.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

STRATEGY_VERSION = "strategy-v1"
STRATEGY_DIMENSIONS = (
    "topic_mix",
    "format_mix",
    "pacing",
    "episode_structure",
    "humor_style",
)
PROPOSAL_STATUSES = ("PENDING", "APPROVED", "REJECTED")


class CreatorStrategy(Base):
    __tablename__ = "creator_strategies"
    __table_args__ = (UniqueConstraint("creator_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id"), index=True, nullable=False
    )
    topic_mix: Mapped[list] = mapped_column(JSON, default=list)
    format_mix: Mapped[list] = mapped_column(JSON, default=list)
    pacing: Mapped[str] = mapped_column(String(32), default="")
    episode_structure: Mapped[str] = mapped_column(String(32), default="")
    humor_style: Mapped[str] = mapped_column(String(64), default="")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    strategy_version: Mapped[str] = mapped_column(String(32), default=STRATEGY_VERSION)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StrategyProposal(Base):
    __tablename__ = "strategy_proposals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id"), index=True, nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    current_value: Mapped[object] = mapped_column(JSON, nullable=True)
    proposed_value: Mapped[object] = mapped_column(JSON, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    min_evidence: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    source_version: Mapped[str] = mapped_column(String(32), default=STRATEGY_VERSION)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
