"""Experiment records — one immutable lifecycle per episode (Sprint 8.2)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.experiment import ContentExperiment
from ..services.experiment_service import (
    bind_experiment,
    full_lifecycle,
    refresh_experiment,
    write_notebook_record,
)
from ..services.reality_gap import compute_reality_gap, gap_summary
from ..services.reality_gap_dashboard import build_dashboard
from ..services.research_checkpoint import build_checkpoint

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class ExperimentIn(BaseModel):
    episode_id: int
    hypothesis: str = ""
    variant: str = ""


class ConclusionsIn(BaseModel):
    conclusions: str


class ExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    episode_id: int
    hypothesis: str
    variant: str
    simulation_run_id: int | None
    simulation_score: float | None
    simulation_rank: int | None
    published_video_id: int | None
    real_metrics: dict | None
    reality_gap: dict | None
    conclusions: str
    created_at: datetime


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ExperimentRead)
def create_experiment(payload: ExperimentIn, db: Session = Depends(get_db)) -> ContentExperiment:
    try:
        return bind_experiment(db, payload.episode_id, payload.hypothesis, payload.variant)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("", response_model=list[ExperimentRead])
def list_experiments(
    episode_id: int | None = None, creator_id: int | None = None, db: Session = Depends(get_db)
) -> list[ContentExperiment]:
    q = db.query(ContentExperiment)
    if episode_id is not None:
        q = q.filter(ContentExperiment.episode_id == episode_id)
    if creator_id is not None:
        q = q.filter(ContentExperiment.creator_id == creator_id)
    return q.order_by(ContentExperiment.id.desc()).all()


@router.get("/reality-gap/dashboard")
def reality_gap_dashboard(min_samples: int = 5, db: Session = Depends(get_db)) -> dict:
    return build_dashboard(db, min_samples=min_samples)


# ---------- First research checkpoint (Sprint 9.3) ----------


@router.get("/research-checkpoint")
def research_checkpoint(min_samples: int = 5, db: Session = Depends(get_db)) -> dict:
    return build_checkpoint(db, min_samples=min_samples)


@router.get("/{experiment_id}")
def get_experiment_lifecycle(experiment_id: int, db: Session = Depends(get_db)) -> dict:
    experiment = db.get(ContentExperiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="experiment not found")
    return full_lifecycle(db, experiment)


@router.patch("/{experiment_id}/conclusions", response_model=ExperimentRead)
def update_conclusions(
    experiment_id: int, payload: ConclusionsIn, db: Session = Depends(get_db)
) -> ContentExperiment:
    experiment = db.get(ContentExperiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="experiment not found")
    experiment.conclusions = payload.conclusions.strip()
    db.commit()
    db.refresh(experiment)
    write_notebook_record(db, experiment)
    return experiment


@router.post("/{experiment_id}/refresh", response_model=ExperimentRead)
def refresh_experiment_record(
    experiment_id: int, db: Session = Depends(get_db)
) -> ContentExperiment:
    experiment = db.get(ContentExperiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="experiment not found")
    return refresh_experiment(db, experiment)


@router.post("/{experiment_id}/reality-gap")
def compute_experiment_gap(experiment_id: int, db: Session = Depends(get_db)) -> dict:
    experiment = db.get(ContentExperiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="experiment not found")
    try:
        return compute_reality_gap(db, experiment)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/{experiment_id}/reality-gap")
def get_experiment_gap(experiment_id: int, db: Session = Depends(get_db)) -> dict:
    experiment = db.get(ContentExperiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="experiment not found")
    summary = gap_summary(db, experiment)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no reality gap computed yet"
        )
    return summary
