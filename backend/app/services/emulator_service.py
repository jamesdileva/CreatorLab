"""Emulator service — the controlled social sandbox (roadmap 20.1).

Pure, self-contained: no external calls, no real-platform engagement. Provides a
minimal feed / video / comment / profile / follow model so agents can interact
safely. See `models/emulator.py` for the isolation rationale.
"""
import re

from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.emulator import (
    AccountKind,
    EmulatorAccount,
    EmulatorComment,
    EmulatorFollow,
    EmulatorPost,
    EmulatorView,
)

_HANDLE_RE = re.compile(r"^[a-z0-9_.-]{1,64}$")
_VALID_KINDS = {k.value for k in AccountKind}


def normalize_handle(handle: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_.-]+", "_", (handle or "").strip().lower()).strip("_.-")
    if not _HANDLE_RE.match(cleaned):
        raise ValueError("handle must be 1-64 chars of [a-z0-9_.-]")
    return cleaned


def get_account(db: Session, handle: str) -> EmulatorAccount | None:
    try:
        cleaned = normalize_handle(handle)
    except ValueError:
        return None
    return db.query(EmulatorAccount).filter(EmulatorAccount.handle == cleaned).first()


def _require_account(db: Session, handle: str) -> EmulatorAccount:
    account = get_account(db, handle)
    if account is None:
        raise ValueError(f"account '{handle}' not found")
    return account


def create_account(
    db: Session,
    handle: str,
    display_name: str = "",
    kind: str = AccountKind.AGENT.value,
    creator_id: int | None = None,
) -> EmulatorAccount:
    cleaned = normalize_handle(handle)
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(_VALID_KINDS)}")
    if db.query(EmulatorAccount).filter(EmulatorAccount.handle == cleaned).first():
        raise ValueError(f"handle '{cleaned}' already exists")
    if creator_id is not None and db.get(Creator, creator_id) is None:
        raise ValueError("creator not found")
    account = EmulatorAccount(
        handle=cleaned,
        display_name=(display_name or cleaned).strip(),
        kind=AccountKind(kind),
        creator_id=creator_id,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def sync_creator_accounts(db: Session) -> list[EmulatorAccount]:
    """Give every fictional Creator an emulator presence (idempotent)."""
    created: list[EmulatorAccount] = []
    for creator in db.query(Creator).order_by(Creator.id).all():
        handle = normalize_handle(creator.slug or creator.name)
        if db.query(EmulatorAccount).filter(EmulatorAccount.handle == handle).first():
            continue
        account = EmulatorAccount(
            handle=handle,
            display_name=creator.name,
            kind=AccountKind.CREATOR,
            creator_id=creator.id,
        )
        db.add(account)
        created.append(account)
    if created:
        db.commit()
        for account in created:
            db.refresh(account)
    return created


def follow(db: Session, follower_handle: str, followed_handle: str) -> dict:
    follower = _require_account(db, follower_handle)
    followed = _require_account(db, followed_handle)
    if follower.id == followed.id:
        raise ValueError("an account cannot follow itself")
    existing = (
        db.query(EmulatorFollow)
        .filter(
            EmulatorFollow.follower_id == follower.id,
            EmulatorFollow.followed_id == followed.id,
        )
        .first()
    )
    if existing is None:
        db.add(EmulatorFollow(follower_id=follower.id, followed_id=followed.id))
        db.commit()
    return {"follower": follower.handle, "followed": followed.handle, "following": True}


def unfollow(db: Session, follower_handle: str, followed_handle: str) -> dict:
    follower = _require_account(db, follower_handle)
    followed = _require_account(db, followed_handle)
    db.query(EmulatorFollow).filter(
        EmulatorFollow.follower_id == follower.id,
        EmulatorFollow.followed_id == followed.id,
    ).delete()
    db.commit()
    return {"follower": follower.handle, "followed": followed.handle, "following": False}


def create_post(
    db: Session, author_handle: str, caption: str, episode_id: int | None = None
) -> EmulatorPost:
    author = _require_account(db, author_handle)
    post = EmulatorPost(author_id=author.id, caption=caption or "", episode_id=episode_id)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def add_comment(
    db: Session,
    post_id: int,
    author_handle: str,
    body: str,
    parent_id: int | None = None,
) -> EmulatorComment:
    if not (body or "").strip():
        raise ValueError("comment body must not be empty")
    if db.get(EmulatorPost, post_id) is None:
        raise ValueError("post not found")
    author = _require_account(db, author_handle)
    if parent_id is not None:
        parent = db.get(EmulatorComment, parent_id)
        if parent is None or parent.post_id != post_id:
            raise ValueError("parent comment not found on this post")
    comment = EmulatorComment(
        post_id=post_id, author_id=author.id, body=body.strip(), parent_id=parent_id
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def record_view(
    db: Session, post_id: int, account_handle: str, watch_seconds: float = 0.0, liked: bool = False
) -> EmulatorView:
    if db.get(EmulatorPost, post_id) is None:
        raise ValueError("post not found")
    if watch_seconds < 0:
        raise ValueError("watch_seconds must be >= 0")
    account = _require_account(db, account_handle)
    view = EmulatorView(
        post_id=post_id, account_id=account.id, watch_seconds=watch_seconds, liked=liked
    )
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


def _engagement(db: Session, post_id: int) -> dict:
    views = (
        db.query(EmulatorView).filter(EmulatorView.post_id == post_id).all()
    )
    comments = (
        db.query(EmulatorComment).filter(EmulatorComment.post_id == post_id).count()
    )
    like_count = sum(1 for v in views if v.liked)
    score = len(views) + 2 * like_count + 3 * comments
    return {
        "views": len(views),
        "likes": like_count,
        "comments": comments,
        "score": score,
    }


def _post_dict(db: Session, post: EmulatorPost) -> dict:
    author = db.get(EmulatorAccount, post.author_id)
    return {
        "id": post.id,
        "author": author.handle if author else "?",
        "author_display": author.display_name if author else "?",
        "episode_id": post.episode_id,
        "caption": post.caption,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "engagement": _engagement(db, post.id),
    }


def feed(db: Session, account_handle: str | None = None, limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 100))
    query = db.query(EmulatorPost)
    if account_handle is not None:
        account = get_account(db, account_handle)
        if account is not None:
            followed_ids = [
                row.followed_id
                for row in db.query(EmulatorFollow)
                .filter(EmulatorFollow.follower_id == account.id)
                .all()
            ]
            if followed_ids:
                query = query.filter(EmulatorPost.author_id.in_(followed_ids))
    posts = query.all()
    posts.sort(key=lambda p: (_engagement(db, p.id)["score"], p.id), reverse=True)
    return [_post_dict(db, p) for p in posts[:limit]]


def comments_for(db: Session, post_id: int) -> list[dict]:
    rows = (
        db.query(EmulatorComment)
        .filter(EmulatorComment.post_id == post_id)
        .order_by(EmulatorComment.id)
        .all()
    )
    out = []
    for row in rows:
        author = db.get(EmulatorAccount, row.author_id)
        out.append(
            {
                "id": row.id,
                "author": author.handle if author else "?",
                "author_display": author.display_name if author else "?",
                "parent_id": row.parent_id,
                "body": row.body,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def post_detail(db: Session, post_id: int) -> dict:
    post = db.get(EmulatorPost, post_id)
    if post is None:
        raise ValueError("post not found")
    detail = _post_dict(db, post)
    detail["comments"] = comments_for(db, post_id)
    return detail


def profile(db: Session, handle: str) -> dict:
    account = _require_account(db, handle)
    posts = (
        db.query(EmulatorPost)
        .filter(EmulatorPost.author_id == account.id)
        .order_by(EmulatorPost.id.desc())
        .all()
    )
    followers = (
        db.query(EmulatorFollow)
        .filter(EmulatorFollow.followed_id == account.id)
        .count()
    )
    following = (
        db.query(EmulatorFollow)
        .filter(EmulatorFollow.follower_id == account.id)
        .count()
    )
    return {
        "handle": account.handle,
        "display_name": account.display_name,
        "kind": account.kind.value,
        "creator_id": account.creator_id,
        "followers": followers,
        "following": following,
        "post_count": len(posts),
        "posts": [_post_dict(db, p) for p in posts],
    }
