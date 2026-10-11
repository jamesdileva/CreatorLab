"""Render records + scene asset provenance (roadmap Sprint 5.3)."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class RenderStatus(str, enum.Enum):
    RENDERING = "RENDERING"
    READY = "READY"
    FAILED = "FAILED"


class AssetKind(str, enum.Enum):
    CARD = "card"
    VOICE = "voice"
    CLIP = "clip"
    CAPTIONS = "captions"
    VIDEO = "video"
    MANIFEST = "manifest"


class Render(Base):
    __tablename__ = "renders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("episodes.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default=RenderStatus.RENDERING.value)
    render_version: Mapped[str] = mapped_column(String(32), default="render-v1")
    card_version: Mapped[str] = mapped_column(String(32), default="card-v1")
    identity_version: Mapped[str] = mapped_column(String(32), default="")
    voice_id: Mapped[str] = mapped_column(String(64), default="")
    total_duration: Mapped[float] = mapped_column(Float, default=0.0)
    artifact_dir: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class SceneAsset(Base):
    __tablename__ = "scene_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    render_id: Mapped[int] = mapped_column(
        ForeignKey("renders.id"), index=True, nullable=False
    )
    scene_number: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
