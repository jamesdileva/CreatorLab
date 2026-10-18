"""Sprint 20.1 — emulator laboratory: controlled fake social environment."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.services import emulator_service as svc

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def _override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _db():
    return TestingSession()


def _seed_creators():
    db = _db()
    db.add(Creator(name="Hank", slug="hank"))
    db.add(Creator(name="Alex.exe", slug="alex-exe"))
    db.commit()
    db.close()


# ---------- accounts ----------


def test_create_account_and_duplicate(client):
    _seed_creators()
    db = _db()
    acc = svc.create_account(db, "Viewer One!", "Viewer One", "viewer")
    assert acc.handle == "viewer_one"
    with pytest.raises(ValueError):
        svc.create_account(db, "viewer_one")
    with pytest.raises(ValueError):
        svc.create_account(db, "   ")
    with pytest.raises(ValueError):
        svc.create_account(db, "x", kind="robot")
    db.close()


def test_sync_creator_accounts_is_idempotent(client):
    _seed_creators()
    db = _db()
    first = svc.sync_creator_accounts(db)
    assert {a.handle for a in first} == {"hank", "alex-exe"}
    assert svc.sync_creator_accounts(db) == []
    db.close()


# ---------- follow + feed ----------


def test_follow_rules_and_feed(client):
    db = _db()
    svc.create_account(db, "fan", "Fan")
    svc.create_account(db, "star", "Star")
    svc.create_account(db, "other", "Other")
    with pytest.raises(ValueError):
        svc.follow(db, "fan", "fan")

    svc.create_post(db, "star", "star post")
    svc.create_post(db, "other", "other post")
    # no follows yet → global feed sees both
    assert len(svc.feed(db, "fan")) == 2
    svc.follow(db, "fan", "star")
    ranked = svc.feed(db, "fan")
    assert [p["author"] for p in ranked] == ["star"]
    svc.unfollow(db, "fan", "star")
    assert len(svc.feed(db, "fan")) == 2
    db.close()


def test_feed_ranks_by_engagement(client):
    db = _db()
    svc.create_account(db, "a", "A")
    svc.create_account(db, "b", "B")
    low = svc.create_post(db, "a", "low")
    high = svc.create_post(db, "b", "high")
    svc.record_view(db, high.id, "a", watch_seconds=10, liked=True)
    svc.record_view(db, high.id, "b", watch_seconds=5, liked=True)
    order = [p["id"] for p in svc.feed(db)]
    assert order == [high.id, low.id]
    db.close()


# ---------- posts + comments ----------


def test_post_comment_thread_and_detail(client):
    db = _db()
    svc.create_account(db, "creator", "Creator", "creator")
    svc.create_account(db, "fan", "Fan", "viewer")
    post = svc.create_post(db, "creator", "hello world")
    top = svc.add_comment(db, post.id, "fan", "nice!")
    svc.add_comment(db, post.id, "creator", "thanks", parent_id=top.id)

    detail = svc.post_detail(db, post.id)
    assert detail["author"] == "creator"
    assert len(detail["comments"]) == 2
    assert detail["comments"][1]["parent_id"] == top.id
    assert detail["engagement"]["comments"] == 2

    with pytest.raises(ValueError):
        svc.add_comment(db, post.id, "fan", "   ")
    with pytest.raises(ValueError):
        svc.add_comment(db, 999, "fan", "ghost")
    db.close()


def test_comment_parent_must_match_post(client):
    db = _db()
    svc.create_account(db, "u", "U")
    p1 = svc.create_post(db, "u", "one")
    p2 = svc.create_post(db, "u", "two")
    c1 = svc.add_comment(db, p1.id, "u", "on one")
    with pytest.raises(ValueError):
        svc.add_comment(db, p2.id, "u", "reply", parent_id=c1.id)
    db.close()


# ---------- views + profile ----------


def test_record_view_and_engagement(client):
    db = _db()
    svc.create_account(db, "creator", "Creator")
    svc.create_account(db, "fan", "Fan")
    post = svc.create_post(db, "creator", "video")
    svc.record_view(db, post.id, "fan", watch_seconds=8, liked=True)
    svc.record_view(db, post.id, "creator", watch_seconds=3)

    eng = svc.post_detail(db, post.id)["engagement"]
    assert eng == {"views": 2, "likes": 1, "comments": 0, "score": 4}
    with pytest.raises(ValueError):
        svc.record_view(db, post.id, "fan", watch_seconds=-1)
    with pytest.raises(ValueError):
        svc.record_view(db, 999, "fan")
    db.close()


def test_profile_counts(client):
    db = _db()
    svc.create_account(db, "creator", "Creator", "creator")
    svc.create_account(db, "fan", "Fan", "viewer")
    svc.create_account(db, "fan2", "Fan2", "viewer")
    svc.create_post(db, "creator", "p1")
    svc.create_post(db, "creator", "p2")
    svc.follow(db, "fan", "creator")
    svc.follow(db, "fan2", "creator")
    svc.follow(db, "creator", "fan")

    prof = svc.profile(db, "creator")
    assert prof["followers"] == 2
    assert prof["following"] == 1
    assert prof["post_count"] == 2
    db.close()


# ---------- endpoints ----------


def test_endpoints_roundtrip(client):
    _seed_creators()
    assert client.post("/api/emulator/accounts/sync").status_code == 200
    assert client.post(
        "/api/emulator/accounts",
        json={"handle": "fan", "display_name": "Fan", "kind": "viewer"},
    ).status_code == 201
    assert client.post("/api/emulator/accounts", json={"handle": "fan"}).status_code == 400

    created = client.post(
        "/api/emulator/posts", json={"author": "hank", "caption": "first video"}
    )
    assert created.status_code == 201
    post_id = created.json()["id"]

    assert client.post(
        f"/api/emulator/posts/{post_id}/comments",
        json={"author": "fan", "body": "love it"},
    ).status_code == 201
    assert client.post(
        f"/api/emulator/posts/{post_id}/view",
        json={"account": "fan", "watch_seconds": 9, "liked": True},
    ).status_code == 201
    assert client.post(
        "/api/emulator/follow", json={"follower": "fan", "followed": "hank"}
    ).json()["following"] is True

    feed = client.get("/api/emulator/feed", params={"handle": "fan"}).json()
    assert feed and feed[0]["author"] == "hank"
    assert feed[0]["engagement"]["likes"] == 1

    profile = client.get("/api/emulator/accounts/hank").json()
    assert profile["kind"] == "creator"
    assert profile["post_count"] == 1
    assert client.get("/api/emulator/accounts/ghost").status_code == 404
    assert client.get("/api/emulator/posts/999").status_code == 404
