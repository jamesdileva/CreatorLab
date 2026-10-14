"""Creator relationships — social continuity for the ecosystem (roadmap 13.1).

Pairs are unordered (creator_a_id < creator_b_id) so each relationship exists
exactly once. Dimensions are 0..1 intensities; story events shift them with
clamping, and every shift is recorded as a RelationshipEvent.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

DIMENSIONS = ("friendship", "rivalry", "respect", "annoyance", "collaboration")


class StoryEventType(str, enum.Enum):
    COLLABORATION_SUCCESS = "collaboration_success"
    COLLABORATION_FAILURE = "collaboration_failure"
    RIVALRY_MATCH = "rivalry_match"
    PRANK = "prank"
    RECONCILIATION = "reconciliation"
    SHARED_VICTORY = "shared_victory"


# dimension deltas applied by each story event (roadmap 13.1)
EVENT_DELTAS: dict[str, dict[str, float]] = {
    StoryEventType.COLLABORATION_SUCCESS.value: {
        "friendship": 0.2, "collaboration": 0.3, "rivalry": -0.1, "respect": 0.1,
    },
    StoryEventType.COLLABORATION_FAILURE.value: {
        "annoyance": 0.2, "collaboration": -0.1, "friendship": -0.05,
    },
    StoryEventType.RIVALRY_MATCH.value: {
        "rivalry": 0.3, "respect": 0.1, "annoyance": 0.05,
    },
    StoryEventType.PRANK.value: {
        "annoyance": 0.25, "friendship": -0.15, "rivalry": 0.1,
    },
    StoryEventType.RECONCILIATION.value: {
        "friendship": 0.25, "annoyance": -0.3, "respect": 0.1,
    },
    StoryEventType.SHARED_VICTORY.value: {
        "respect": 0.2, "friendship": 0.15, "collaboration": 0.1,
    },
}


class CreatorRelationship(Base):
    __tablename__ = "creator_relationships"
    __table_args__ = (UniqueConstraint("creator_a_id", "creator_b_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_a_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True, nullable=False)
    creator_b_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True, nullable=False)
    friendship: Mapped[float] = mapped_column(Float, default=0.0)
    rivalry: Mapped[float] = mapped_column(Float, default=0.0)
    respect: Mapped[float] = mapped_column(Float, default=0.0)
    annoyance: Mapped[float] = mapped_column(Float, default=0.0)
    collaboration: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RelationshipEvent(Base):
    __tablename__ = "relationship_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("creator_relationships.id"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    deltas: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
