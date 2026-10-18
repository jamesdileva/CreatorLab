"""Emulator sandbox API — controlled fake social app (Sprint 20.1).

Isolated from all real platforms. Routes deliberately mirror a social app
(accounts, feed, posts, comments, follow, profile) so agents can interact safely.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.emulator import EmulatorAccount
from ..services import emulator_service as svc
from ..services import visual_agent

router = APIRouter(prefix="/api/emulator", tags=["emulator"])


class AccountIn(BaseModel):
    handle: str
    display_name: str = ""
    kind: str = "agent"
    creator_id: int | None = None


class AccountOut(BaseModel):
    id: int
    handle: str
    display_name: str
    kind: str
    creator_id: int | None


def _account_out(account: EmulatorAccount) -> AccountOut:
    return AccountOut(
        id=account.id,
        handle=account.handle,
        display_name=account.display_name,
        kind=account.kind.value,
        creator_id=account.creator_id,
    )


class FollowIn(BaseModel):
    follower: str
    followed: str


class PostIn(BaseModel):
    author: str
    caption: str = ""
    episode_id: int | None = None


class CommentIn(BaseModel):
    author: str
    body: str
    parent_id: int | None = None


class ViewIn(BaseModel):
    account: str
    watch_seconds: float = 0.0
    liked: bool = False


def _bad(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# NOTE: literal routes precede "/accounts/{handle}" (FastAPI matches in order).


@router.post("/accounts", status_code=status.HTTP_201_CREATED, response_model=AccountOut)
def create_account(payload: AccountIn, db: Session = Depends(get_db)) -> AccountOut:
    try:
        account = svc.create_account(
            db, payload.handle, payload.display_name, payload.kind, payload.creator_id
        )
    except ValueError as exc:
        raise _bad(exc)
    return _account_out(account)


@router.post("/accounts/sync", response_model=list[AccountOut])
def sync_accounts(db: Session = Depends(get_db)) -> list[AccountOut]:
    return [_account_out(a) for a in svc.sync_creator_accounts(db)]


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)) -> list[AccountOut]:
    accounts = db.query(EmulatorAccount).order_by(EmulatorAccount.id).all()
    return [_account_out(a) for a in accounts]


@router.post("/follow")
def follow(payload: FollowIn, db: Session = Depends(get_db)) -> dict:
    try:
        return svc.follow(db, payload.follower, payload.followed)
    except ValueError as exc:
        raise _bad(exc)


@router.post("/unfollow")
def unfollow(payload: FollowIn, db: Session = Depends(get_db)) -> dict:
    try:
        return svc.unfollow(db, payload.follower, payload.followed)
    except ValueError as exc:
        raise _bad(exc)


@router.get("/feed")
def feed(handle: str | None = None, limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    return svc.feed(db, account_handle=handle, limit=limit)


@router.post("/posts", status_code=status.HTTP_201_CREATED)
def create_post(payload: PostIn, db: Session = Depends(get_db)) -> dict:
    try:
        post = svc.create_post(db, payload.author, payload.caption, payload.episode_id)
    except ValueError as exc:
        raise _bad(exc)
    return svc.post_detail(db, post.id)


@router.get("/posts/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return svc.post_detail(db, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
def add_comment(post_id: int, payload: CommentIn, db: Session = Depends(get_db)) -> dict:
    try:
        svc.add_comment(db, post_id, payload.author, payload.body, payload.parent_id)
    except ValueError as exc:
        raise _bad(exc)
    return svc.post_detail(db, post_id)


@router.get("/posts/{post_id}/comments")
def list_comments(post_id: int, db: Session = Depends(get_db)) -> list[dict]:
    try:
        svc.post_detail(db, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return svc.comments_for(db, post_id)


@router.post("/posts/{post_id}/view", status_code=status.HTTP_201_CREATED)
def record_view(post_id: int, payload: ViewIn, db: Session = Depends(get_db)) -> dict:
    try:
        svc.record_view(db, post_id, payload.account, payload.watch_seconds, payload.liked)
    except ValueError as exc:
        raise _bad(exc)
    return svc.post_detail(db, post_id)


@router.get("/accounts/{handle}")
def get_profile(handle: str, db: Session = Depends(get_db)) -> dict:
    try:
        return svc.profile(db, handle)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ---------- Visual/social agent (Sprint 20.2) ----------


class AgentRunIn(BaseModel):
    account: str
    goal: str = ""
    max_steps: int = 8
    provider: str | None = None


@router.post("/agent/run", status_code=status.HTTP_201_CREATED)
def run_agent(payload: AgentRunIn, db: Session = Depends(get_db)) -> dict:
    try:
        session = visual_agent.run_agent(
            db,
            payload.account,
            goal=payload.goal,
            max_steps=payload.max_steps,
            provider_name=payload.provider,
        )
    except ValueError as exc:
        raise _bad(exc)
    return visual_agent.session_detail(db, session.id)


@router.get("/agent/sessions")
def list_agent_sessions(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": s.id,
            "account_handle": s.account_handle,
            "goal": s.goal,
            "provider": s.provider,
            "model": s.model,
            "step_count": s.step_count,
            "stopped_reason": s.stopped_reason,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in visual_agent.list_sessions(db)
    ]


@router.get("/agent/sessions/{session_id}")
def get_agent_session(session_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return visual_agent.session_detail(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
