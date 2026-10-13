"""Sprint 10.1 — performance memory: distill real history into lessons."""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.published_video import PublishedVideo
from app.models.video_metrics import VideoMetrics

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


def _new_creator(client):
    tag = uuid.uuid4().hex[:8]
    resp = client.post("/api/creators", json={"name": f"Hank {tag}", "slug": f"hank-{tag}"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _published_episode(client, series_id, variant, premise, views):
    ep = client.post(
        f"/api/series/{series_id}/generate-episode", json={"variant": variant}
    ).json()["episode"]
    client.patch(f"/api/episodes/{ep['id']}", json={"premise": premise})
    ep = client.get(f"/api/episodes/{ep['id']}").json()
    client.post("/api/simulations/run", json={"target_type": "episode", "target_id": ep["id"]})
    db = TestingSession()
    record = PublishedVideo(
        episode_id=ep["id"], render_id=1, channel_id="UC_X", video_id=f"v{ep['id']}",
        title="t", status="uploaded", upload_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    db.add(
        VideoMetrics(
            published_video_id=record.id, video_id=record.video_id,
            views=views, likes=1, comments=0, subscriber_count=9, raw_json={},
        )
    )
    db.commit()
    db.close()
    return ep


def _setup_four(client):
    creator = _new_creator(client)
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": f"S{uuid.uuid4().hex[:6]}"}
    ).json()
    _published_episode(client, series["id"], 0, "tractor harvest at dawn", 300)
    _published_episode(client, series["id"], 1, "tractor engine rebuild saga", 300)
    _published_episode(client, series["id"], 2, "robotics startup pitch night", 50)
    _published_episode(client, series["id"], 3, "robotics gadget unboxing fail", 50)
    return creator


def test_distill_needs_min_episodes(client):
    creator = _new_creator(client)
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": f"S{uuid.uuid4().hex[:6]}"}
    ).json()
    _published_episode(client, series["id"], 0, "tractor harvest at dawn", 300)
    _published_episode(client, series["id"], 1, "tractor engine rebuild saga", 300)

    resp = client.post(f"/api/creators/{creator['id']}/distill-performance")
    assert resp.status_code == 409
    assert "at least 3" in resp.json()["detail"]


def test_distill_creates_topic_lessons(client):
    creator = _setup_four(client)

    summary = client.get(f"/api/creators/{creator['id']}/performance").json()
    assert summary["episodes_with_metrics"] == 4
    assert summary["overall_avg_views"] == 175.0
    assert summary["topics"]["tractor"]["verdict"] == "strong"
    assert summary["topics"]["robotics"]["verdict"] == "weak"

    resp = client.post(f"/api/creators/{creator['id']}/distill-performance")
    assert resp.status_code == 201
    body = resp.json()
    assert body["memories_created"] >= 4  # summary + 2 discoveries + 1 lesson
    types = [m["type"] for m in body["memories"]]
    assert "AUDIENCE_DISCOVERY" in types
    assert "CONTENT_LESSON" in types
    assert all("Sample:" in m["content"] and "Confidence:" in m["content"] for m in body["memories"])


def test_distilled_lessons_reach_generation(client):
    creator = _setup_four(client)
    client.post(f"/api/creators/{creator['id']}/distill-performance")

    gen = client.post(
        f"/api/creators/{creator['id']}/generate", json={"user_message": "pitch the next episode"}
    ).json()
    assert any("PERF:" in m for m in gen["memories_used"])


def test_distill_refreshes_without_duplicates(client):
    creator = _setup_four(client)
    first = client.post(f"/api/creators/{creator['id']}/distill-performance").json()
    second = client.post(f"/api/creators/{creator['id']}/distill-performance").json()
    assert second["memories_created"] == first["memories_created"]

    memories = client.get(f"/api/creators/{creator['id']}/memories").json()
    perf = [m for m in memories if m["content"].startswith("PERF:")]
    assert len(perf) == first["memories_created"]


def test_performance_404(client):
    assert client.get("/api/creators/99999/performance").status_code == 404
    assert client.post("/api/creators/99999/distill-performance").status_code == 404
