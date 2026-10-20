"""Character development — evolving traits + append-only arc (roadmap Sprint 22.2).

Characters change over time (e.g. Hank: `anti_ai` -> `cautiously_accepts` ->
`automation_interested`) instead of staying frozen in a static prompt.

`CharacterTrait` holds the *current* value of a named trait; every change is an
immutable `CharacterDevelopment` row (from -> to, with a required reason and an
optional episode/experiment as evidence). Current traits are injected into
generation prompts so the arc actually affects new content.
"""
from datetime import datetime

from sqlalchemy import (
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

DEVELOPMENT_SOURCES = ("human", "evidence")


class CharacterTrait(Base):
    __tablename__ = "character_traits"
    __table_args__ = (UniqueConstraint("creator_id", "trait"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id"), index=True, nullable=False
    )
    trait: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(120), default="")
    stage: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CharacterDevelopment(Base):
    __tablename__ = "character_developments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id"), index=True, nullable=False
    )
    trait: Mapped[str] = mapped_column(String(64), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    to_value: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("episodes.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(16), default="human")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
