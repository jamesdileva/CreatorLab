"""Relationship service — pairwise social state + story-event shifts (13.1)."""
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.relationship import (
    DIMENSIONS,
    EVENT_DELTAS,
    CreatorRelationship,
    RelationshipEvent,
    StoryEventType,
)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, round(x, 3)))


def ordered_pair(a_id: int, b_id: int) -> tuple[int, int]:
    if a_id == b_id:
        raise ValueError("a creator cannot have a relationship with itself")
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


def get_or_create_relationship(
    db: Session, a_id: int, b_id: int
) -> CreatorRelationship:
    lo, hi = ordered_pair(a_id, b_id)
    for cid in (lo, hi):
        if db.get(Creator, cid) is None:
            raise ValueError(f"creator {cid} not found")
    existing = (
        db.query(CreatorRelationship)
        .filter_by(creator_a_id=lo, creator_b_id=hi)
        .one_or_none()
    )
    if existing is not None:
        return existing
    rel = CreatorRelationship(creator_a_id=lo, creator_b_id=hi)
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def dimensions(rel: CreatorRelationship) -> dict[str, float]:
    return {dim: getattr(rel, dim) for dim in DIMENSIONS}


def apply_story_event(
    db: Session,
    relationship_id: int,
    event_type: str,
    note: str = "",
) -> tuple[CreatorRelationship, RelationshipEvent]:
    rel = db.get(CreatorRelationship, relationship_id)
    if rel is None:
        raise ValueError("relationship not found")
    try:
        deltas = EVENT_DELTAS[StoryEventType(event_type.strip().lower()).value]
    except ValueError:
        valid = sorted(EVENT_DELTAS)
        raise ValueError(f"event_type must be one of {valid}")
    applied: dict[str, float] = {}
    for dim, delta in deltas.items():
        new_value = _clamp(getattr(rel, dim) + delta)
        setattr(rel, dim, new_value)
        applied[dim] = round(delta, 3)
    event = RelationshipEvent(
        relationship_id=rel.id, event_type=event_type.strip().lower(),
        deltas=applied, note=note.strip(),
    )
    db.add(event)
    db.commit()
    db.refresh(rel)
    db.refresh(event)
    return rel, event


def set_note(db: Session, relationship_id: int, note: str) -> CreatorRelationship:
    rel = db.get(CreatorRelationship, relationship_id)
    if rel is None:
        raise ValueError("relationship not found")
    rel.note = note.strip()
    db.commit()
    db.refresh(rel)
    return rel
