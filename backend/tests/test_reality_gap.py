"""Sprint 9.1 — reality gap: simulated vs real rankings, disagreements flagged."""
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
from app.services.reality_gap import compare_rankings

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


def _episode(c, variant):
    return c.post(
        f"/api/series/{c.series_id}/generate-episode", json={"variant": variant}
    ).json()["episode"]


@pytest.fixture
def three_episodes(client):
    client.creator_id = client.post(  # type: ignore[attr-defined]
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()["id"]
    client.series_id = client.post(  # type: ignore[attr-defined]
        "/api/series", json={"creator_id": client.creator_id, "name": "Hank's World"}
    ).json()["id"]
    eps = [_episode(client, v) for v in (0, 1, 2)]
    for ep in eps:
        client.post(
            "/api/simulations/run",
            json={"target_type": "episode", "target_id": ep["id"]},
        )
    return eps


# Roadmap verification shape: sim says A > B > C, reality says B > A > C.
def test_compare_identifies_disagreement():
    gap = compare_rankings(["A", "B", "C"], ["B", "A", "C"])
    assert gap["correlation"]["spearman"] == 0.5
    assert gap["correlation"]["kendall_tau"] == 0.333
    assert gap["agreement"]["directional_accuracy"] == 0.667
    assert len(gap["disagreements"]) == 1
    missed = gap["disagreements"][0]
    assert missed["sim_order"] == "A > B"
    assert missed["real_order"] == "B > A"
    assert gap["rank_deltas"] == {"A": -1, "B": 1, "C": 0}


def test_compare_perfect_agreement():
    gap = compare_rankings(["A", "B"], ["A", "B"])
    assert gap["correlation"]["spearman"] == 1.0
    assert gap["disagreements"] == []


def test_compare_single_common_item():
    gap = compare_rankings(["A", "B"], ["B"])
    assert gap["sample_size"] == 1
    assert gap["correlation"]["spearman"] is None
    # only one comparable item, so it is trivially the shared top-1
    assert gap["agreement"]["top_1_match"] is True


def _publish_with_metrics(client, episode_id, views, likes=0):
    db = TestingSession()
    record = PublishedVideo(
        episode_id=episode_id, render_id=1, channel_id="UC_X", video_id=f"vid_{episode_id}",
        title="t", status="uploaded", upload_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    record_id, video_id = record.id, record.video_id
    db.add(
        VideoMetrics(
            published_video_id=record_id, video_id=video_id,
            views=views, likes=likes, comments=0, subscriber_count=10,
        )
    )
    db.commit()
    db.close()
    return record_id


def test_compute_gap_end_to_end(client, three_episodes):
    a, b, c = (ep["id"] for ep in three_episodes)
    # force reality: B > A > C
    _publish_with_metrics(client, a, views=100)
    _publish_with_metrics(client, b, views=300)
    _publish_with_metrics(client, c, views=50)

    exp = client.post("/api/experiments", json={"episode_id": a}).json()
    gap = client.post(f"/api/experiments/{exp['id']}/reality-gap").json()

    assert gap["experiment_id"] == exp["id"]
    assert gap["sample_size"] == 3
    assert gap["real_order"] == [b, a, c]
    assert set(gap["sim_order"]) == {a, b, c}
    assert "computed_at" in gap

    # persisted on the row
    detail = client.get(f"/api/experiments/{exp['id']}").json()
    assert detail["experiment"]["reality_gap"]["real_order"] == [b, a, c]

    # readable via the gap endpoint
    reread = client.get(f"/api/experiments/{exp['id']}/reality-gap").json()
    assert reread["sample_size"] == 3


def test_gap_requires_both_sides(client):
    client.creator_id = client.post(  # type: ignore[attr-defined]
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()["id"]
    client.series_id = client.post(  # type: ignore[attr-defined]
        "/api/series", json={"creator_id": client.creator_id, "name": "S"}
    ).json()["id"]
    ep = _episode(client, 0)
    exp = client.post("/api/experiments", json={"episode_id": ep["id"]}).json()

    # sim only, no real metrics
    client.post("/api/simulations/run", json={"target_type": "episode", "target_id": ep["id"]})
    assert client.post(f"/api/experiments/{exp['id']}/reality-gap").status_code == 409
    assert client.get(f"/api/experiments/{exp['id']}/reality-gap").status_code == 404


def test_gap_unknown_experiment_404(client):
    assert client.post("/api/experiments/9999/reality-gap").status_code == 404
    assert client.get("/api/experiments/9999/reality-gap").status_code == 404
