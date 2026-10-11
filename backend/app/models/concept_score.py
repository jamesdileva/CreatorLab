"""Concept scoring + human-judgment records (roadmap Sprint 3.2)."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ConceptScore(Base):
    __tablename__ = "concept_scores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id"), index=True, nullable=False
    )
    set_id: Mapped[int] = mapped_column(ForeignKey("concept_sets.id"), index=True, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    hook_score: Mapped[float] = mapped_column(Float, nullable=False)
    character_fit_score: Mapped[float] = mapped_column(Float, nullable=False)
    novelty_score: Mapped[float] = mapped_column(Float, nullable=False)
    story_potential_score: Mapped[float] = mapped_column(Float, nullable=False)
    audience_relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    episode_continuity_score: Mapped[float] = mapped_column(Float, nullable=False)
    composite: Mapped[float] = mapped_column(Float, nullable=False)
    scorer_version: Mapped[str] = mapped_column(String(64), default="heuristic-v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class HumanRanking(Base):
    """A human's ordering of the concepts in a set (the comparison baseline)."""

    __tablename__ = "human_rankings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("concept_sets.id"), index=True, nullable=False)
    order: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of concept ids
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
