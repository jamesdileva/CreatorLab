"""HumanPanelRanking — humans ranking the same candidate videos (roadmap 17.1).

A controlled human evaluation: panel members order a candidate list best-first
for comparison against the synthetic audience and the real YouTube audience
(Phase 17). Generic candidate_type keeps future panel experiments possible;
Sprint 17.1 ranks "episode" candidates.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class HumanPanelRanking(Base):
    __tablename__ = "human_panel_rankings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_type: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    order: Mapped[list] = mapped_column(JSON, nullable=False)  # candidate ids, best-first
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
