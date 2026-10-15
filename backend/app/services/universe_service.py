"""Universe canon service — shared world facts + context for generation (14.1)."""
from sqlalchemy.orm import Session

from ..models.universe import UniverseEntity, UniverseKind


def universe_entities(db: Session) -> list[UniverseEntity]:
    return db.query(UniverseEntity).order_by(UniverseEntity.id).all()


def universe_statements(db: Session) -> list[str]:
    return [e.statement for e in universe_entities(db)]


def upsert_entity(
    db: Session, kind: str, name: str, statement: str
) -> UniverseEntity:
    try:
        kind_value = UniverseKind(kind.strip().upper()).value
    except ValueError:
        valid = sorted(k.value for k in UniverseKind)
        raise ValueError(f"kind must be one of {valid}")
    name = name.strip()
    statement = statement.strip()
    if not name:
        raise ValueError("name is required")
    if not statement:
        raise ValueError("statement is required")
    entity = UniverseEntity(kind=kind_value, name=name, statement=statement)
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def delete_entity(db: Session, entity_id: int) -> None:
    entity = db.get(UniverseEntity, entity_id)
    if entity is None:
        raise ValueError("universe entity not found")
    db.delete(entity)
    db.commit()
