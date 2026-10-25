"""Major research checkpoint API (roadmap Phase 25)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.checkpoint import MajorCheckpoint
from ..services import major_checkpoint as svc
from ..services.reality_gap_dashboard import MIN_SAMPLES

router = APIRouter(prefix="/api/checkpoint", tags=["checkpoint"])


class SnapshotIn(BaseModel):
    min_samples: int = MIN_SAMPLES


@router.get("/preview")
def preview(min_samples: int = MIN_SAMPLES, db: Session = Depends(get_db)) -> dict:
    return svc.build_checkpoint(db, min_samples=max(1, min_samples))


@router.post("", status_code=status.HTTP_201_CREATED)
def snapshot(payload: SnapshotIn, db: Session = Depends(get_db)) -> dict:
    return svc.snapshot_checkpoint(db, min_samples=max(1, payload.min_samples))


@router.get("")
def list_snapshots(db: Session = Depends(get_db)) -> list[dict]:
    return [svc.checkpoint_dict(row) for row in svc.list_checkpoints(db)]


@router.get("/{checkpoint_id}")
def get_snapshot(checkpoint_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(MajorCheckpoint, checkpoint_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="checkpoint not found"
        )
    return svc.checkpoint_dict(row)
