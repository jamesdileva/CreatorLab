"""Character development API (Sprint 22.2).

Read a character's evolving traits and arc, seed traits, and record
development steps. Every step requires a reason; the arc is append-only.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..services import character_development as svc

router = APIRouter(prefix="/api/character-development", tags=["character-development"])


class DefineTraitIn(BaseModel):
    trait: str
    value: str


class DevelopmentIn(BaseModel):
    trait: str
    to_value: str
    reason: str
    episode_id: int | None = None


def _http_error(exc: ValueError) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if "not found" in str(exc)
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/creators/{creator_id}")
def get_character_arc(creator_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return svc.character_arc(db, creator_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/creators/{creator_id}/traits", status_code=status.HTTP_201_CREATED)
def define_trait(
    creator_id: int, payload: DefineTraitIn, db: Session = Depends(get_db)
) -> dict:
    try:
        trait = svc.define_trait(db, creator_id, payload.trait, payload.value)
    except ValueError as exc:
        raise _http_error(exc)
    return svc.trait_dict(trait)


@router.post(
    "/creators/{creator_id}/developments", status_code=status.HTTP_201_CREATED
)
def record_development(
    creator_id: int, payload: DevelopmentIn, db: Session = Depends(get_db)
) -> dict:
    try:
        row = svc.record_development(
            db,
            creator_id,
            payload.trait,
            payload.to_value,
            payload.reason,
            episode_id=payload.episode_id,
        )
    except ValueError as exc:
        raise _http_error(exc)
    return svc.development_dict(row)


@router.get("/creators/{creator_id}/traits/{trait}")
def get_trait_history(
    creator_id: int, trait: str, db: Session = Depends(get_db)
) -> dict:
    try:
        current = svc.get_trait(db, creator_id, trait)
        if current is None:
            raise ValueError("trait not found")
        history = svc.trait_history(db, creator_id, trait)
    except ValueError as exc:
        raise _http_error(exc)
    return {
        "trait": svc.trait_dict(current),
        "history": [svc.development_dict(d) for d in history],
    }
