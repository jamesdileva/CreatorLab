"""Sprint 9.2 — reality-gap dashboard: aggregation + sample-size gating."""
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
    resp = client.post(
        "/api/creators", json={"name": f"Hank {tag}", "slug": f"hank-{tag}"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _scored_experiment(client, n_episodes: int, views_per_episode: list[int], topic: str, creator=None):
    if creator is None:
        creator = _new_creator(client)
    tag = uuid.uuid4().hex[:8]
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": f"S{topic}-{tag}"}
    ).json()
    episodes = []
    for i in range(n_episodes):
        ep = client.post(
            f"/api/series/{series['id']}/generate-episode", json={"variant": i}
        ).json()["episode"]
        if topic:
            client.patch(f"/api/episodes/{ep['id']}", json={"premise": f"{topic} premise {i}"})
            ep = client.get(f"/api/episodes/{ep['id']}").json()
        client.post(
            "/api/simulations/run", json={"target_type": "episode", "target_id": ep["id"]}
        )
        episodes.append(ep)
    for ep, views in zip(episodes, views_per_episode):
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
    exp = client.post(
        "/api/experiments", json={"episode_id": episodes[0]["id"], "hypothesis": topic}
    ).json()
    client.post(f"/api/experiments/{exp['id']}/reality-gap", json={})
    return exp


def test_dashboard_empty(client):
    body = client.get("/api/experiments/reality-gap/dashboard").json()
    assert body["experiments_scored"] == 0
    assert body["overall"]["comparisons"] == 0
    assert body["overall"]["directional_accuracy"] is None
    assert body["interpretation_allowed"] is False


def test_dashboard_aggregates_comparisons(client):
    creator = _new_creator(client)
    for i in range(5):
        _scored_experiment(client, n_episodes=2, views_per_episode=[100, 300], topic="tractor", creator=creator)

    body = client.get("/api/experiments/reality-gap/dashboard").json()
    assert body["experiments_scored"] == 5
    # each experiment contributes 1 pairwise comparison (2 episodes)
    assert body["overall"]["comparisons"] == 5
    assert body["overall"]["directional_accuracy"] is not None
    assert body["overall"]["top_1_hit_rate"] is not None
    assert sum(v["comparisons"] for v in body["per_creator"].values()) == 5
    creator_key = next(iter(body["per_creator"]))
    assert body["per_creator"][creator_key]["comparisons"] == 5
    assert body["per_creator"][creator_key]["sample_sufficient"] is True
    assert body["per_topic"]["tractor"]["comparisons"] == 5
    assert body["per_format"]["standalone"]["comparisons"] == 5
    assert body["interpretation_allowed"] is True


def test_dashboard_respects_min_samples(client):
    for i in range(3):
        _scored_experiment(client, n_episodes=2, views_per_episode=[100, 300], topic="x")

    body = client.get("/api/experiments/reality-gap/dashboard").json()
    assert body["experiments_scored"] == 3
    assert body["overall"]["sample_sufficient"] is False
    assert body["interpretation_allowed"] is False

    loosened = client.get(
        "/api/experiments/reality-gap/dashboard?min_samples=2"
    ).json()
    assert loosened["overall"]["sample_sufficient"] is True
    assert loosened["interpretation_allowed"] is True


def test_dashboard_counts_disagreements(client):
    # reality reverses the simulator rank in every experiment
    for i in range(6):
        _scored_experiment(client, n_episodes=3,
                           views_per_episode=[100, 300, 50], topic="disagreement")

    body = client.get("/api/experiments/reality-gap/dashboard").json()
    assert body["overall"]["comparisons"] == 6
    # each 3-episode experiment has at least one disagreement
    assert body["overall"]["disagreements"] >= 6
    assert body["overall"]["directional_accuracy"] < 1.0
