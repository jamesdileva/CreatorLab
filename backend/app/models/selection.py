"""Automated candidate selection — pick from the simulated pool (roadmap 21.1).

Records an automated *recommendation* of which candidate(s) in a pool to advance
(by heuristic score, by synthetic-audience simulation, or a combination). It does
**not** publish or approve anything: human approval still gates publication
(architecture §5.6). Purpose: remove low-value manual selection, never oversight.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

SELECTION_METHODS = ("score", "simulation", "combined")


class CandidateSelection(Base):
    __tablename__ = "candidate_selections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_type: Mapped[str] = mapped_column(String(16), nullable=False)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), nullable=True)
    concept_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("concept_sets.id"), nullable=True
    )
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), default="")
    count: Mapped[int] = mapped_column(Integer, default=1)
    selected_ids: Mapped[list] = mapped_column(JSON, default=list)  # best-first
    ranked_ids: Mapped[list] = mapped_column(JSON, default=list)  # full ranking
    scores: Mapped[dict] = mapped_column(JSON, default=dict)  # id(str) -> score
    ranking_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ranking_runs.id"), nullable=True
    )
    scorer_version: Mapped[str] = mapped_column(String(64), default="")
    audience_version: Mapped[str] = mapped_column(String(32), default="")
    seed: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
