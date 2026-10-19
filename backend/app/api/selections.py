"""Automated candidate selection API (Sprint 21.1).

Recommends candidates from the simulated pool. Selection never publishes;
human approval still gates publication.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..services import selection_service as svc

router = APIRouter(prefix="/api/selections", tags=["selections"])


class SelectionIn(BaseModel):
    candidate_type: str
    candidate_ids: list[int]
    method: str = "combined"
    metric: str = "watch_probability"
    count: int = 1
    seed: int = 0
    note: str = ""


class FromConceptSetIn(BaseModel):
    set_id: int
    method: str = "combined"
    metric: str = "watch_probability"
    count: int = 1
    seed: int = 0
    note: str = ""


def _bad(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_selection(payload: SelectionIn, db: Session = Depends(get_db)) -> dict:
    try:
        result = svc.select_candidates(
            db,
            payload.candidate_type,
            payload.candidate_ids,
            method=payload.method,
            metric=payload.metric,
            count=payload.count,
            seed=payload.seed,
            note=payload.note,
        )
    except ValueError as exc:
        raise _bad(exc)
    out = svc.selection_dict(result.selection)
    out["ranked"] = result.ranked
    out["selected"] = result.selected
    return out


@router.post("/from-concept-set", status_code=status.HTTP_201_CREATED)
def create_selection_from_concept_set(
    payload: FromConceptSetIn, db: Session = Depends(get_db)
) -> dict:
    try:
        result = svc.select_from_concept_set(
            db,
            payload.set_id,
            method=payload.method,
            metric=payload.metric,
            count=payload.count,
            seed=payload.seed,
            note=payload.note,
        )
    except ValueError as exc:
        raise _bad(exc)
    out = svc.selection_dict(result.selection)
    out["ranked"] = result.ranked
    out["selected"] = result.selected
    return out


@router.get("")
def list_selections(limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    return [svc.selection_dict(s) for s in svc.list_selections(db, limit)]


@router.get("/{selection_id}")
def get_selection(selection_id: int, db: Session = Depends(get_db)) -> dict:
    from ..models.selection import CandidateSelection

    row = db.get(CandidateSelection, selection_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="selection not found")
    return svc.selection_dict(row)
