"""Emulator Laboratory — a controlled fake social app (roadmap 20.1).

An isolated, self-contained social environment (feed, video, comment, profile,
follow) that **never touches a real platform**. It exists so simulated agents
can interact in a sandbox where consent, labeling, and scope are ours to define
(see `docs/reddit-feasibility.md` / `docs/tiktok-feasibility.md` for why real
platforms are gated).

None of this manufactures engagement anywhere real — it is the roadmap-mandated
sandbox. Accounts may optionally link to an existing fictional `Creator`.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class AccountKind(str, enum.Enum):
    CREATOR = "creator"
    VIEWER = "viewer"
    AGENT = "agent"


class EmulatorAccount(Base):
    __tablename__ = "emulator_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    handle: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[AccountKind] = mapped_column(
        Enum(AccountKind), default=AccountKind.AGENT, nullable=False
    )
    creator_id: Mapped[int | None] = mapped_column(
        ForeignKey("creators.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class EmulatorPost(Base):
    __tablename__ = "emulator_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(
        ForeignKey("emulator_accounts.id"), index=True, nullable=False
    )
    episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("episodes.id"), nullable=True
    )
    caption: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class EmulatorComment(Base):
    __tablename__ = "emulator_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("emulator_posts.id"), index=True, nullable=False
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("emulator_accounts.id"), index=True, nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("emulator_comments.id"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class EmulatorFollow(Base):
    __tablename__ = "emulator_follows"
    __table_args__ = (UniqueConstraint("follower_id", "followed_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    follower_id: Mapped[int] = mapped_column(
        ForeignKey("emulator_accounts.id"), index=True, nullable=False
    )
    followed_id: Mapped[int] = mapped_column(
        ForeignKey("emulator_accounts.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class EmulatorView(Base):
    __tablename__ = "emulator_views"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("emulator_posts.id"), index=True, nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("emulator_accounts.id"), index=True, nullable=False
    )
    watch_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    liked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
