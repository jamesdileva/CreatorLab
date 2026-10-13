"""Creator CRUD + prompt-versioned generation API — Sprints 1.1 + 1.2.

DELETE soft-deactivates (sets active=False); records stay viewable.
All publishes still require explicit human approval (MVP gate, later sprints).
"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.prompts import get_prompt_versions
from ..ai.providers import ProviderError
from ..core.database import get_db
from ..models.creator import Creator
from ..models.creator_memory import CreatorMemory, MemoryType
from ..services.character_service import (
    IDENTITY_VERSION,
    CharacterIdentity,
    identity_for_creator,
    identity_snapshot,
    validate_palette,
)
from ..services.creator_service import generate_creator_response
from ..services.creator_strategy import build_strategy
from ..services.performance_memory import (
    distill_performance_memories,
    summarize_performance,
)

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


@router.get("/strategy")
def get_strategy(db: Session = Depends(get_db)) -> dict:
    """Cross-creator strategy observations (Sprint 10.2). Literal route kept
    above /{creator_id} so 'strategy' is never read as a creator id."""
    return build_strategy(db)


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


class GenerateIn(BaseModel):
    user_message: str
    prompt_version: str | None = None
    provider: str | None = None


class GenerateOut(BaseModel):
    creator_id: int
    creator_name: str
    text: str
    model: str
    prompt_version: str
    provider: str
    memories_used: list[str]


@router.post("/{creator_id}/generate", response_model=GenerateOut)
def generate_creator_voice(
    creator_id: int, payload: GenerateIn, db: Session = Depends(get_db)
) -> GenerateOut:
    creator = _get_or_404(db, creator_id)
    message = payload.user_message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="user_message is required"
        )
    try:
        response, version, provider_name, memories_used = generate_creator_response(
            db,
            creator,
            message,
            prompt_version=payload.prompt_version,
            provider_name=payload.provider,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown prompt version: {exc}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return GenerateOut(
        creator_id=creator.id,
        creator_name=creator.name,
        text=response.text,
        model=response.model,
        prompt_version=version,
        provider=provider_name,
        memories_used=memories_used,
    )


@router.get("/prompts/versions", response_model=list[str])
def list_prompt_versions() -> list[str]:
    return get_prompt_versions()


# ---------- Character visual identity (Sprint 5.2) ----------


class PaletteUpdateIn(BaseModel):
    palette: dict | None = None
    accessories: list[str] | None = None
    display_name: str | None = None


class IdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    display_name: str
    palette: dict
    accessories: list[str]
    props: list[str]
    style: str
    version: str
    created_at: datetime


@router.get("/{creator_id}/identity", response_model=IdentityRead)
def get_identity(creator_id: int, db: Session = Depends(get_db)) -> CharacterIdentity:
    creator = _get_or_404(db, creator_id)
    try:
        return identity_for_creator(db, creator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/{creator_id}/identity", response_model=IdentityRead)
def update_identity(
    creator_id: int, payload: PaletteUpdateIn, db: Session = Depends(get_db)
) -> CharacterIdentity:
    creator = _get_or_404(db, creator_id)
    try:
        identity = identity_for_creator(db, creator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    try:
        if payload.palette is not None:
            identity.palette_json = validate_palette(payload.palette)
        if payload.accessories is not None:
            identity.accessories = [str(a).strip().lower() for a in payload.accessories]
        if payload.display_name is not None:
            name = payload.display_name.strip()
            if not name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="display_name is required"
                )
            identity.display_name = name
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    db.refresh(identity)
    return identity


@router.post("/{creator_id}/identity/portrait", response_model=IdentityRead)
def render_identity_portrait(creator_id: int, db: Session = Depends(get_db)) -> IdentityRead:
    """Render a preview portrait; returns the identity (assets served under /media)."""
    creator = _get_or_404(db, creator_id)
    try:
        identity = identity_for_creator(db, creator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    from ..services.video_service import render_episode_identity_preview

    render_episode_identity_preview(identity)
    return identity


class MemoryCreate(BaseModel):
    type: str
    content: str
    importance: float = 0.5
    confidence: float = 1.0


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    type: str
    content: str
    importance: float
    confidence: float
    created_at: datetime


def _memory_or_404(db: Session, creator_id: int, memory_id: int) -> CreatorMemory:
    memory = db.get(CreatorMemory, memory_id)
    if memory is None or memory.creator_id != creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="memory not found"
        )
    return memory


@router.post(
    "/{creator_id}/memories",
    status_code=status.HTTP_201_CREATED,
    response_model=MemoryRead,
)
def create_memory(
    creator_id: int, payload: MemoryCreate, db: Session = Depends(get_db)
) -> CreatorMemory:
    _get_or_404(db, creator_id)  # 404 if creator missing
    content = payload.content.strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="content is required"
        )
    try:
        memory_type = MemoryType(payload.type.strip().upper())
    except ValueError:
        valid = sorted(t.value for t in MemoryType)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"type must be one of {valid}",
        )
    if not 0.0 <= payload.importance <= 1.0 or not 0.0 <= payload.confidence <= 1.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="importance and confidence must be in [0, 1]",
        )
    memory = CreatorMemory(
        creator_id=creator_id,
        type=memory_type,
        content=content,
        importance=payload.importance,
        confidence=payload.confidence,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


@router.get("/{creator_id}/memories", response_model=list[MemoryRead])
def list_memories(
    creator_id: int, type: str | None = None, db: Session = Depends(get_db)
) -> list[CreatorMemory]:
    _get_or_404(db, creator_id)
    q = db.query(CreatorMemory).filter(CreatorMemory.creator_id == creator_id)
    if type:
        try:
            q = q.filter(CreatorMemory.type == MemoryType(type.strip().upper()))
        except ValueError:
            valid = sorted(t.value for t in MemoryType)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"type must be one of {valid}",
            )
    return q.order_by(
        CreatorMemory.importance.desc(),
        CreatorMemory.created_at.desc(),
        CreatorMemory.id.desc(),
    ).all()


@router.delete("/{creator_id}/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    creator_id: int, memory_id: int, db: Session = Depends(get_db)
) -> None:
    memory = _memory_or_404(db, creator_id, memory_id)
    db.delete(memory)
    db.commit()


# ---------- Performance memory (Sprint 10.1) ----------


@router.get("/{creator_id}/performance")
def get_performance(creator_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return summarize_performance(db, creator_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{creator_id}/distill-performance", status_code=status.HTTP_201_CREATED)
def distill_performance(creator_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        memories = distill_performance_memories(db, creator_id)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if "creator not found" in message
                else status.HTTP_409_CONFLICT
            ),
            detail=message,
        )
    return {
        "creator_id": creator_id,
        "memories_created": len(memories),
        "memories": [
            {"id": m.id, "type": m.type.value, "content": m.content} for m in memories
        ],
    }
