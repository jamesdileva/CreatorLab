"""Large-scale simulation study API (roadmap Phase 24)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.simulation_scale import SimulationScaleStudy
from ..services import simulation_scale as svc

router = APIRouter(prefix="/api/simulation-scale", tags=["simulation-scale"])


class StudyIn(BaseModel):
    sizes: list[int] | None = None
    seed: int = 0
    metric: str = svc.DEFAULT_METRIC
    creator_id: int | None = None
    episode_ids: list[int] | None = None
    min_pairs: int = svc.DEFAULT_MIN_PAIRS
    threshold: float = svc.DEFAULT_THRESHOLD


@router.post("/studies", status_code=status.HTTP_201_CREATED)
def create_study(payload: StudyIn, db: Session = Depends(get_db)) -> dict:
    try:
        return svc.run_scale_study(
            db,
            sizes=payload.sizes,
            seed=payload.seed,
            metric=payload.metric,
            creator_id=payload.creator_id,
            episode_ids=payload.episode_ids,
            min_pairs=payload.min_pairs,
            threshold=payload.threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/studies")
def list_studies(db: Session = Depends(get_db)) -> list[dict]:
    return [svc.study_dict(study) for study in svc.list_studies(db)]


@router.get("/studies/{study_id}")
def get_study(study_id: int, db: Session = Depends(get_db)) -> dict:
    study = db.get(SimulationScaleStudy, study_id)
    if study is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="study not found")
    return svc.study_dict(study)
