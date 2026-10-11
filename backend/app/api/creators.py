"""Creator CRUD API — Sprint 1.1.

DELETE soft-deactivates (sets active=False); records stay viewable.
All publishes still require explicit human approval (MVP gate, later sprints).
"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.creator import Creator

router = APIRouter(prefix="/api/creators", tags=["creators"])

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _check_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not SLUG_RE.match(slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="slug must be lowercase alphanumeric with single hyphens (e.g. 'alex-exe')",
        )
    return slug


class CreatorBase(BaseModel):
    description: str = ""
    personality: str = ""
    values: list[str] = []
    interests: list[str] = []
    humor_style: str = ""
    visual_style: str = ""
    voice_style: str = ""
    goals: list[str] = []
    constraints: str = ""
    system_prompt: str = ""


class CreatorCreate(CreatorBase):
    name: str
    slug: str


class CreatorUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    personality: str | None = None
    values: list[str] | None = None
    interests: list[str] | None = None
    humor_style: str | None = None
    visual_style: str | None = None
    voice_style: str | None = None
    goals: list[str] | None = None
    constraints: str | None = None
    system_prompt: str | None = None
    active: bool | None = None


class CreatorRead(CreatorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    active: bool
    created_at: datetime
    updated_at: datetime


def _get_or_404(db: Session, creator_id: int) -> Creator:
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="creator not found")
    return creator


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreatorRead)
def create_creator(payload: CreatorCreate, db: Session = Depends(get_db)) -> Creator:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    slug = _check_slug(payload.slug)
    clash = db.query(Creator).filter((Creator.slug == slug) | (Creator.name == name)).first()
    if clash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="creator with this name or slug already exists",
        )
    creator = Creator(**{**payload.model_dump(), "name": name, "slug": slug})
    db.add(creator)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="creator with this name or slug already exists",
        )
    db.refresh(creator)
    return creator


@router.get("", response_model=list[CreatorRead])
def list_creators(active_only: bool = True, db: Session = Depends(get_db)) -> list[Creator]:
    q = db.query(Creator).order_by(Creator.id)
    if active_only:
        q = q.filter(Creator.active.is_(True))
    return q.all()


@router.get("/{creator_id}", response_model=CreatorRead)
def get_creator(creator_id: int, db: Session = Depends(get_db)) -> Creator:
    return _get_or_404(db, creator_id)


@router.patch("/{creator_id}", response_model=CreatorRead)
def update_creator(creator_id: int, payload: CreatorUpdate, db: Session = Depends(get_db)) -> Creator:
    creator = _get_or_404(db, creator_id)
    patch = payload.model_dump(exclude_unset=True)
    if "slug" in patch and patch["slug"] is not None:
        patch["slug"] = _check_slug(patch["slug"])
    if "name" in patch and patch["name"] is not None:
        patch["name"] = patch["name"].strip()
        if not patch["name"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    for field in ("slug", "name"):
        if field in patch and patch[field] is not None:
            clash = (
                db.query(Creator)
                .filter(getattr(Creator, field) == patch[field], Creator.id != creator_id)
                .first()
            )
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"another creator already uses this {field}",
                )
    for key, value in patch.items():
        if value is not None:
            setattr(creator, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="creator name/slug conflict"
        )
    db.refresh(creator)
    return creator


@router.delete("/{creator_id}", response_model=CreatorRead)
def deactivate_creator(creator_id: int, db: Session = Depends(get_db)) -> Creator:
    creator = _get_or_404(db, creator_id)
    creator.active = False
    db.commit()
    db.refresh(creator)
    return creator
