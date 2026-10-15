"""AudienceLore — recurring viewer reactions that enter the universe (roadmap 14.2).

Themes are distilled from simulation behavior: phrases that recur across
distinct episodes the audience actually watched (above-median watch). Humans
promote a theme into the series canon as a RUNNING_JOKE — the audience starts
contributing to the fictional world (architecture §13).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class AudienceLore(Base):
    __tablename__ = "audience_lore"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    theme: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id"), index=True, nullable=False
    )
    episode_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    mention_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_watch: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="emerging")
    promoted_canon_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
