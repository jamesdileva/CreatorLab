"""Visual/social agent runs against the emulator sandbox (roadmap 20.2).

An agent perceives a rendered "screen" of the isolated emulator (feed → open →
watch → read → comment → navigate) and chooses one action per step via the LLM
provider abstraction. The full trajectory (observation + reasoning + action) is
stored so visual/social agents can be evaluated **separately from real-world
platform policies** — nothing here touches a real platform.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_handle: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="")
    environment: Mapped[str] = mapped_column(String(32), default="emulator")
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    max_steps: Mapped[int] = mapped_column(Integer, default=8)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    stopped_reason: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("agent_sessions.id"), index=True, nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    watch_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    liked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    observation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
