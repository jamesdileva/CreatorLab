"""Audience simulation API — viewer population (Sprint 4.1, arch §8)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.viewer import AUDIENCE_VERSION, SyntheticViewer
from ..services.audience_service import _DEFAULT_COUNT, baseline_interest, seed_audience

router = APIRouter(prefix="/api/audience", tags=["simulation"])


class SeedIn(BaseModel):
    count: int = _DEFAULT_COUNT


class ViewerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handle: str
    age_bracket: str
    region: str
    interests: list[str]
    personality: str
    humor_preferences: list[str]
    attention_level: float
    creator_affinities: dict
    response_style: str
    audience_version: str
    seed_index: int
    created_at: datetime


class AffinityIn(BaseModel):
    creator_slug: str
    familiarity: float


class PreviewIn(BaseModel):
    text: str
    tags: list[str] = []


class PreviewOut(BaseModel):
    viewer_id: int
    handle: str
    interest: float


@router.post("/seed", status_code=status.HTTP_201_CREATED, response_model=list[ViewerRead])
def seed_population(payload: SeedIn, db: Session = Depends(get_db)) -> list[SyntheticViewer]:
    try:
        return seed_audience(db, count=payload.count)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=list[ViewerRead])
def list_viewers(db: Session = Depends(get_db)) -> list[SyntheticViewer]:
    return (
        db.query(SyntheticViewer)
        .filter(SyntheticViewer.audience_version == AUDIENCE_VERSION)
        .order_by(SyntheticViewer.seed_index)
        .all()
    )


@router.get("/{viewer_id}", response_model=ViewerRead)
def get_viewer(viewer_id: int, db: Session = Depends(get_db)) -> SyntheticViewer:
    viewer = db.get(SyntheticViewer, viewer_id)
    if viewer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="viewer not found")
    return viewer


@router.patch("/{viewer_id}/affinity", response_model=ViewerRead)
def set_affinity(
    viewer_id: int, payload: AffinityIn, db: Session = Depends(get_db)
) -> SyntheticViewer:
    viewer = db.get(SyntheticViewer, viewer_id)
    if viewer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="viewer not found")
    if not 0.0 <= payload.familiarity <= 1.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="familiarity must be in [0, 1]",
        )
    affinities = dict(viewer.creator_affinities or {})
    affinities[payload.creator_slug.strip().lower()] = payload.familiarity
    viewer.creator_affinities = affinities
    db.commit()
    db.refresh(viewer)
    return viewer


@router.post("/{viewer_id}/preview", response_model=PreviewOut)
def preview_interest(
    viewer_id: int, payload: PreviewIn, db: Session = Depends(get_db)
) -> PreviewOut:
    viewer = db.get(SyntheticViewer, viewer_id)
    if viewer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="viewer not found")
    return PreviewOut(
        viewer_id=viewer.id,
        handle=viewer.handle,
        interest=baseline_interest(viewer, payload.text, payload.tags),
    )
