"""Sprint 10.2 — creator strategy: differentiated + shared observations."""
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


def _new_creator(client, name):
    tag = uuid.uuid4().hex[:8]
    slug = f"{name.lower().replace('.', '').replace(' ', '-')}-{tag}"
    resp = client.post("/api/creators", json={"name": f"{name} {tag}", "slug": slug})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _published_episode(client, series_id, variant, premise, views, long=False):
    ep = client.post(
        f"/api/series/{series_id}/generate-episode", json={"variant": variant}
    ).json()["episode"]
    client.patch(f"/api/episodes/{ep['id']}", json={"premise": premise})
    ep = client.get(f"/api/episodes/{ep['id']}").json()
    if long:
        for i in range(2):  # 3 stub scenes + 2 = 5 → "long"
            resp = client.post(
                f"/api/episodes/{ep['id']}/scenes",
                json={"title": f"extra {i}", "direction": "extended cut"},
            )
            assert resp.status_code == 201, resp.text
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


def _setup_two_creators(client):
    hank = _new_creator(client, "Hank")
    alex = _new_creator(client, "Alex")
    for creator, hi_topic, lo_topic in (
        (hank, "tractor", "robotics"),
        (alex, "cryptid", "blockchain"),
    ):
        series = client.post(
            "/api/series",
            json={"creator_id": creator["id"], "name": f"S{uuid.uuid4().hex[:6]}"},
        ).json()
        _published_episode(client, series["id"], 0, f"{hi_topic} harvest at dawn", 300, long=True)
        _published_episode(client, series["id"], 1, f"{hi_topic} engine rebuild saga", 300, long=True)
        _published_episode(client, series["id"], 2, f"{lo_topic} startup pitch night", 50)
        _published_episode(client, series["id"], 3, f"{lo_topic} gadget unboxing fail", 50)
    return hank, alex


def test_strategy_empty(client):
    body = client.get("/api/creators/strategy").json()
    assert body["sufficient_creators"] == 0
    assert body["per_creator"] == {}
    assert body["shared"] == []
    assert body["interpretation_allowed"] is False


def test_strategy_differentiated_and_shared(client):
    hank, alex = _setup_two_creators(client)

    body = client.get("/api/creators/strategy").json()
    assert body["sufficient_creators"] == 2
    assert body["interpretation_allowed"] is True

    hank_obs = body["per_creator"][hank["slug"]]["observations"]
    assert any(o["tag"] == "tractor" and o["verdict"] == "strong" and o["episodes"] == 2 for o in hank_obs)
    assert any(o["tag"] == "robotics" and o["verdict"] == "weak" for o in hank_obs)
    assert all("2 episodes" in o["text"] for o in hank_obs if o["tag"] in ("tractor", "robotics"))

    alex_obs = body["per_creator"][alex["slug"]]["observations"]
    assert any(o["tag"] == "cryptid" and o["verdict"] == "strong" for o in alex_obs)
    # differentiated: no cross-contamination of topics
    assert not any(o["tag"] == "tractor" for o in alex_obs)
    assert not any(o["tag"] == "cryptid" for o in hank_obs)

    shared_tags = {(o["kind"], o["tag"], o["verdict"]) for o in body["shared"]}
    assert ("structure", "long", "strong") in shared_tags
    long_obs = next(o for o in body["shared"] if o["tag"] == "long")
    assert long_obs["episodes"] == 4
    assert len(long_obs["creators"]) == 2


def test_strategy_single_creator_insufficient(client):
    hank = _new_creator(client, "Hank")
    series = client.post(
        "/api/series", json={"creator_id": hank["id"], "name": f"S{uuid.uuid4().hex[:6]}"}
    ).json()
    for i in range(3):
        _published_episode(client, series["id"], i, f"tractor harvest saga {i}", 100 + i)

    body = client.get("/api/creators/strategy").json()
    assert body["sufficient_creators"] == 1
    assert body["shared"] == []
    assert body["interpretation_allowed"] is False
    assert hank["slug"] in body["per_creator"]
