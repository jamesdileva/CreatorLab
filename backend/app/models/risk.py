"""Risk assessment records for risk-based approval (roadmap Sprint 21.2).

Immutable audit rows: each time the deterministic classifier is applied to an
episode (on assessment or on a fast-lane approval), the verdict is stored so
approval decisions keep their provenance. Classification never approves or
publishes anything by itself.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    fast_lane: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    classifier_version: Mapped[str] = mapped_column(String(32), default="")
    actor: Mapped[str] = mapped_column(String(32), default="human")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
