"""Sprint 9.3 gap-fill — empirical random selector (seeded, deterministic).

The first checkpoint (d260c4f) compared the simulator against analytic random
expectations. The roadmap's experiment is stronger: a random selector that
shuffles the simulated order and is scored on the same pairwise comparisons,
so the baseline is measured, not assumed.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.research_checkpoint import (
    MARGIN,
    RANDOM_SEED,
    RANDOM_TRIALS,
    empirical_random_selector,
)
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


def _scored(client, n_episodes: int, views: list[int], topic: str):
    tag = datetime.now().strftime("%f")
    creator = client.post(
        "/api/creators", json={"name": f"H {tag}", "slug": f"h-{tag}"}
    ).json()
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": f"S{topic}"}
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
    for ep, v in zip(episodes, views):
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
                views=v, likes=1, comments=0, subscriber_count=9, raw_json={},
            )
        )
        db.commit()
        db.close()
    exp = client.post("/api/experiments", json={"episode_id": episodes[0]["id"]}).json()
    client.post(f"/api/experiments/{exp['id']}/reality-gap", json={})
    return exp


def test_empirical_selector_is_near_chance():
    # shuffles discard simulator info: 3-order tasks average 0.5 directional
    orders = [([1, 2, 3], [3, 2, 1]), ([1, 2, 3, 4], [4, 3, 2, 1])]
    result = empirical_random_selector(orders, trials=RANDOM_TRIALS, seed=RANDOM_SEED)
    assert result["trials"] == RANDOM_TRIALS
    assert abs(result["directional_accuracy"] - 0.5) < 0.05
    assert abs(result["top_1_hit_rate"] - 1 / 3) < 0.05


def test_empirical_selector_deterministic_per_seed():
    orders = [([1, 2, 3], [1, 2, 3])]
    first = empirical_random_selector(orders, seed=7)
    second = empirical_random_selector(orders, seed=7)
    assert first == second


def test_empirical_selector_empty():
    assert empirical_random_selector([])["directional_accuracy"] is None
    # single-item tasks carry no pairwise signal
    assert empirical_random_selector([([1], [1])])["directional_accuracy"] is None


def test_checkpoint_reports_empirical_baseline(client):
    for i in range(6):
        _scored(client, n_episodes=3, views=[100, 300, 50], topic="tractor")
    body = client.get("/api/experiments/research-checkpoint").json()

    assert body["random_selector"]["trials"] == RANDOM_TRIALS
    assert abs(body["random_selector"]["directional_accuracy"] - 0.5) < 0.05
    assert body["deltas"]["directional"] is not None
    assert body["verdict"] in ("A_beats_random", "B_similar_to_random", "C_worse_than_random")
    assert body["verdict_text"]
    assert body["interpretation_allowed"] is True


def test_checkpoint_without_data_stays_insufficient(client):
    body = client.get("/api/experiments/research-checkpoint").json()
    assert body["verdict"] == "insufficient_data"
    assert body["random_selector"]["trials"] == 0
    assert "Not enough comparisons" in body["verdict_text"]
    assert body["interpretation_allowed"] is False
