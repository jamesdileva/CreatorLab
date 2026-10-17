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


# ---------- Prediction calibration (Sprint 15.1) ----------


@router.get("/calibration")
def calibration_report(db: Session = Depends(get_db)) -> dict:
    from ..services.calibration_service import evaluate_calibration

    return evaluate_calibration(db)


# ---------- Hook experiment (Sprint 16.1) ----------


@router.get("/hook-experiment")
def hook_experiment(creator_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    from ..services.hook_experiment_service import hook_experiment_report

    return hook_experiment_report(db, creator_id=creator_id)


# ---------- Episode length experiment (Sprint 16.2) ----------


@router.get("/length-experiment")
def length_experiment(creator_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    from ..services.length_experiment_service import length_experiment_report

    return length_experiment_report(db, creator_id=creator_id)


# ---------- Story vs meme (Sprint 16.3) ----------


@router.get("/story-vs-meme")
def story_vs_meme(creator_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    from ..services.story_vs_meme_service import story_vs_meme_report

    return story_vs_meme_report(db, creator_id=creator_id)


# ---------- Simulation vs human baseline (Sprint 17.1) ----------


class HumanPanelIn(BaseModel):
    candidate_type: str
    order: list[int]
    note: str = ""


class HumanPanelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_type: str
    order: list[int]
    note: str
    created_at: datetime


@router.post(
    "/human-panel",
    status_code=status.HTTP_201_CREATED,
    response_model=HumanPanelRead,
)
def create_human_panel(payload: HumanPanelIn, db: Session = Depends(get_db)):
    from ..services.human_baseline import PanelError, record_panel_ranking

    try:
        return record_panel_ranking(db, payload.candidate_type, payload.order, payload.note)
    except PanelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/judge-comparison")
def judge_comparison(series_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    from ..services.human_baseline import judge_comparison as compare

    return compare(db, series_id=series_id)


# ---------- Simulation failure catalog (Sprint 17.2) ----------


@router.get("/failure-catalog")
def failure_catalog(creator_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    from ..services.failure_catalog import failure_catalog as build_catalog

    return build_catalog(db, creator_id=creator_id)


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
