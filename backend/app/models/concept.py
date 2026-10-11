"""Concept model — candidate episode concepts generated before simulation (roadmap 3.1)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ConceptSet(Base):
    """One generation request returning a pool of candidate concepts."""

    __tablename__ = "concept_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True, nullable=False)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id"), index=True, nullable=True
    )
    topic: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("concept_sets.id"), index=True, nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    premise: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    angle: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")  # comma-separated format tags
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
