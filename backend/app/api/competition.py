"""Artificial creator competition API (Phase 23).

Organic-only leaderboard over real published-video metrics. No artificial
engagement is read or produced.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..services import competition_service as svc

router = APIRouter(prefix="/api/competition", tags=["competition"])


@router.get("/leaderboard")
def get_leaderboard(min_episodes: int = svc.MIN_EPISODES, db: Session = Depends(get_db)) -> dict:
    return svc.build_leaderboard(db, min_episodes=max(1, min_episodes))


@router.get("/creators/{creator_id}")
def get_creator_standing(
    creator_id: int, min_episodes: int = svc.MIN_EPISODES, db: Session = Depends(get_db)
) -> dict:
    try:
        return svc.creator_standing(db, creator_id, min_episodes=max(1, min_episodes))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
