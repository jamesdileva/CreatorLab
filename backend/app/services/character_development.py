"""Character development service (roadmap Sprint 22.2).

Records how a character changes over time as an append-only arc and injects the
current traits into generation so the character stops being a static prompt.
Every change needs a reason (story events drive evolution, not drift), and may
cite an episode as evidence.
"""
from sqlalchemy.orm import Session

from ..models.character_development import CharacterDevelopment, CharacterTrait
from ..models.creator import Creator
from ..models.episode import Episode

MAX_ARC_PROMPT_TRAITS = 12


def _require_creator(db: Session, creator_id: int) -> Creator:
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise ValueError("creator not found")
    return creator


def trait_dict(trait: CharacterTrait) -> dict:
    return {
        "creator_id": trait.creator_id,
        "trait": trait.trait,
        "value": trait.value,
        "stage": trait.stage,
        "updated_at": trait.updated_at.isoformat() if trait.updated_at else None,
    }


def development_dict(row: CharacterDevelopment) -> dict:
    return {
        "id": row.id,
        "creator_id": row.creator_id,
        "trait": row.trait,
        "from_value": row.from_value,
        "to_value": row.to_value,
        "reason": row.reason,
        "episode_id": row.episode_id,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_traits(db: Session, creator_id: int) -> list[CharacterTrait]:
    return (
        db.query(CharacterTrait)
        .filter(CharacterTrait.creator_id == creator_id)
        .order_by(CharacterTrait.trait)
        .all()
    )


def get_trait(db: Session, creator_id: int, trait: str) -> CharacterTrait | None:
    return (
        db.query(CharacterTrait)
        .filter(CharacterTrait.creator_id == creator_id, CharacterTrait.trait == trait)
        .first()
    )


def define_trait(
    db: Session, creator_id: int, trait: str, value: str, source: str = "human"
) -> CharacterTrait:
    """Seed a trait's first value (recorded as its first arc step)."""
    _require_creator(db, creator_id)
    trait = trait.strip()
    value = value.strip()
    if not trait or not value:
        raise ValueError("trait and value are required")
    if get_trait(db, creator_id, trait) is not None:
        raise ValueError(f"trait '{trait}' already exists — record a development instead")

    row = CharacterTrait(creator_id=creator_id, trait=trait, value=value, stage=0)
    db.add(row)
    db.add(
        CharacterDevelopment(
            creator_id=creator_id,
            trait=trait,
            from_value=None,
            to_value=value,
            reason="initial trait value",
            source=source,
        )
    )
    db.commit()
    db.refresh(row)
    return row


def record_development(
    db: Session,
    creator_id: int,
    trait: str,
    to_value: str,
    reason: str,
    episode_id: int | None = None,
    source: str = "human",
) -> CharacterDevelopment:
    """Append one development step. Reason is mandatory; no silent changes."""
    _require_creator(db, creator_id)
    trait = trait.strip()
    to_value = to_value.strip()
    reason = reason.strip()
    if not reason:
        raise ValueError("a development requires a reason")
    if not to_value:
        raise ValueError("a development requires a new value")

    current = get_trait(db, creator_id, trait)
    if current is None:
        raise ValueError(f"trait '{trait}' not defined — define it first")
    if to_value == current.value:
        raise ValueError(f"trait '{trait}' is already '{to_value}'")

    if episode_id is not None:
        episode = db.get(Episode, episode_id)
        if episode is None or episode.creator_id != creator_id:
            raise ValueError("episode evidence must belong to this creator")

    row = CharacterDevelopment(
        creator_id=creator_id,
        trait=trait,
        from_value=current.value,
        to_value=to_value,
        reason=reason,
        episode_id=episode_id,
        source=source,
    )
    current.value = to_value
    current.stage += 1
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def trait_history(db: Session, creator_id: int, trait: str) -> list[CharacterDevelopment]:
    return (
        db.query(CharacterDevelopment)
        .filter(
            CharacterDevelopment.creator_id == creator_id,
            CharacterDevelopment.trait == trait,
        )
        .order_by(CharacterDevelopment.id)
        .all()
    )


def character_arc(db: Session, creator_id: int) -> dict:
    _require_creator(db, creator_id)
    traits = list_traits(db, creator_id)
    history = (
        db.query(CharacterDevelopment)
        .filter(CharacterDevelopment.creator_id == creator_id)
        .order_by(CharacterDevelopment.id)
        .all()
    )
    arcs = []
    for trait in traits:
        steps = [d for d in history if d.trait == trait.trait]
        path = [s.to_value for s in steps]
        arcs.append(
            {
                "trait": trait.trait,
                "current": trait.value,
                "stages": len(path),
                "path": path,
                "text": f"{trait.trait}: " + " -> ".join(path),
            }
        )
    return {
        "creator_id": creator_id,
        "traits": [trait_dict(t) for t in traits],
        "arcs": arcs,
        "history": [development_dict(d) for d in history],
    }


def character_context(db: Session, creator_id: int) -> str:
    """Prompt block describing the character's current (evolved) traits."""
    traits = list_traits(db, creator_id)[:MAX_ARC_PROMPT_TRAITS]
    if not traits:
        return ""
    lines = [
        f"- {t.trait}: {t.value}" + (f" (changed {t.stage}x)" if t.stage else "")
        for t in traits
    ]
    return (
        "## Character development (current traits, evolved over time)\n"
        "Treat these as the character's present stance — they may differ from the "
        "original pitch because the character has grown:\n" + "\n".join(lines)
    )
