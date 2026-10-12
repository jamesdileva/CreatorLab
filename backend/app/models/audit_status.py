"""AuditStatus model — YouTube API verification state (roadmap Sprint 7.4).

Public automated uploads require a passed audit; until then publishing stays
private with human approval (architecture §5.6, §17).
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class AuditStatus(Base):
    __tablename__ = "audit_status"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(String(200), default="CreatorLab")
    # not_submitted | in_review | more_info | approved | denied
    status: Mapped[str] = mapped_column(String(24), default="not_submitted")
    scopes_requested: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
