"""SyntheticViewer model — heterogeneous audience, not one generic judge (arch §10)."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

AUDIENCE_VERSION = "audience-v1"


class SyntheticViewer(Base):
    __tablename__ = "synthetic_viewers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    handle: Mapped[str] = mapped_column(String(64), nullable=False)
    age_bracket: Mapped[str] = mapped_column(String(16), default="")
    region: Mapped[str] = mapped_column(String(64), default="")
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    personality: Mapped[str] = mapped_column(String(64), default="")
    humor_preferences: Mapped[list[str]] = mapped_column(JSON, default=list)
    attention_level: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    creator_affinities: Mapped[dict] = mapped_column(JSON, default=dict)
    response_style: Mapped[str] = mapped_column(String(32), default="lurker")
    audience_version: Mapped[str] = mapped_column(String(32), default=AUDIENCE_VERSION)
    seed_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
