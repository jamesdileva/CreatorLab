"""Creator strategy evolution API (Sprint 22.1).

Read the current strategy, gather per-dimension evidence, generate
evidence-backed proposals, and record a human decision. Proposals never apply
themselves; approval is explicit.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.creator_strategy import STRATEGY_DIMENSIONS
from ..services import strategy_evolution as svc

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


class DecideIn(BaseModel):
    approve: bool
    note: str = ""


def _bad(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/creators/{creator_id}")
def get_creator_strategy(creator_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        strategy = svc.get_strategy(db, creator_id)
        evidence = svc.gather_evidence(db, creator_id)
    except ValueError as exc:
        raise _bad(exc)
    return {
        "strategy": svc.strategy_dict(strategy),
        "dimensions": list(STRATEGY_DIMENSIONS),
        "evidence": evidence,
        "proposals": [
            svc.proposal_dict(p)
            for p in svc.list_proposals(db, creator_id)
        ],
    }


@router.get("/creators/{creator_id}/evidence")
def get_creator_evidence(creator_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return svc.gather_evidence(db, creator_id)
    except ValueError as exc:
        raise _bad(exc)


@router.post("/creators/{creator_id}/propose", status_code=status.HTTP_201_CREATED)
def propose_changes(creator_id: int, db: Session = Depends(get_db)) -> list[dict]:
    try:
        proposals = svc.propose_changes(db, creator_id)
    except ValueError as exc:
        raise _bad(exc)
    return [svc.proposal_dict(p) for p in proposals]


@router.get("/proposals")
def list_proposals(
    creator_id: int | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        svc.proposal_dict(p)
        for p in svc.list_proposals(db, creator_id, status_filter)
    ]


@router.post("/proposals/{proposal_id}/decide")
def decide_proposal(
    proposal_id: int, payload: DecideIn, db: Session = Depends(get_db)
) -> dict:
    try:
        proposal = svc.decide_proposal(db, proposal_id, payload.approve, payload.note)
    except ValueError as exc:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(exc))
    return svc.proposal_dict(proposal)
