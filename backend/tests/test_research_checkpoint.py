"""Sprint 9.3 — first research checkpoint: simulator vs random baseline."""
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
from app.services.research_checkpoint import (
    OUTCOME_A,
    OUTCOME_B,
    OUTCOME_C,
    OUTCOME_INSUFFICIENT,
    compare_to_random,
)

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


def test_compare_to_random_boundaries():
    assert compare_to_random(None, 10) == OUTCOME_INSUFFICIENT
    assert compare_to_random(1.0, 3) == OUTCOME_INSUFFICIENT  # below min_samples
    assert compare_to_random(1.0, 5) == OUTCOME_A
    assert compare_to_random(0.0, 5) == OUTCOME_C
    assert compare_to_random(0.5, 5) == OUTCOME_B
    assert compare_to_random(0.6, 5) == OUTCOME_B  # inside the margin
    assert compare_to_random(0.65, 5) == OUTCOME_A  # clears the margin
    assert compare_to_random(0.35, 5) == OUTCOME_C


def test_checkpoint_empty(client):
    body = client.get("/api/experiments/research-checkpoint").json()
    assert body["experiments_scored"] == 0
    assert body["verdict"] == OUTCOME_INSUFFICIENT
    assert body["interpretation_allowed"] is False
    assert body["random_baseline"]["directional_accuracy"] == 0.5
    assert body["random_baseline"]["spearman"] == 0.0
    assert body["human_baseline"] is None


def test_checkpoint_sufficient_five_experiments(client):
    creator = _new_creator(client)
    for _ in range(5):
        _scored_experiment(client, n_episodes=2, views_per_episode=[100, 300],
                           topic="tractor", creator=creator)

    body = client.get("/api/experiments/research-checkpoint").json()
    assert body["experiments_scored"] == 5
    assert body["simulator"]["comparisons"] == 5
    assert body["verdict"] in (OUTCOME_A, OUTCOME_B, OUTCOME_C)
    assert body["interpretation_allowed"] is True
    # random baselines are fixed expectations, not fitted
    assert body["random_baseline"]["directional_accuracy"] == 0.5
    assert body["random_baseline"]["top_1_hit_rate"] == 0.5  # mean(1/2) over n=2
    assert body["deltas"]["directional"] is not None


def test_checkpoint_respects_min_samples(client):
    creator = _new_creator(client)
    for _ in range(3):
        _scored_experiment(client, n_episodes=2, views_per_episode=[100, 300],
                           topic="checkpoint", creator=creator)

    body = client.get("/api/experiments/research-checkpoint").json()
    assert body["verdict"] == OUTCOME_INSUFFICIENT
    assert body["interpretation_allowed"] is False

    loosened = client.get("/api/experiments/research-checkpoint?min_samples=2").json()
    assert loosened["verdict"] in (OUTCOME_A, OUTCOME_B, OUTCOME_C)
    assert loosened["interpretation_allowed"] is True
