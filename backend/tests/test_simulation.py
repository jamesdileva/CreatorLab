"""Sprint 4.2 — audience reactions: per-viewer probabilities + aggregation."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.audience_service import build_viewer
from app.services.simulation_service import aggregate_reactions, compute_reaction

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
    c = TestClient(app)
    c.creator_id = c.post(  # type: ignore[attr-defined]
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()["id"]
    c.series_id = c.post(  # type: ignore[attr-defined]
        "/api/series", json={"creator_id": c.creator_id, "name": "Hank's World"}
    ).json()["id"]
    gen = c.post(
        f"/api/series/{c.series_id}/generate-concepts",
        json={"topic": "AI tractors", "count": 5},
    ).json()
    c.concept_id = gen["concepts"][0]["id"]  # type: ignore[attr-defined]
    ep = c.post(
        f"/api/series/{c.series_id}/generate-episode", json={"variant": 0}
    ).json()
    c.episode_id = ep["episode"]["id"]  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_reaction_probabilities_bounded():
    for i in range(25):
        r = compute_reaction(
            build_viewer(i), "AI tractors — the mishap", "Hank tries the new thing once."
        )
        for p in (r.watch, r.like, r.comment, r.share, r.follow):
            assert 0.0 <= p <= 1.0
        assert r.reason_codes


def test_like_never_exceeds_watch():
    for i in range(25):
        r = compute_reaction(build_viewer(i), "title", "premise text here")
        assert r.like <= r.watch
        assert r.comment <= r.watch
        assert r.share <= r.watch
        assert r.follow <= r.watch


def test_sharer_shares_more_than_lurker():
    lurker = build_viewer(0)  # lurker
    sharer = build_viewer(5)  # sharer
    rl = compute_reaction(lurker, "same title", "same premise")
    rs = compute_reaction(sharer, "same title", "same premise")
    assert rs.share > rl.share
    assert rs.comment >= rl.comment


def test_run_concept_returns_aggregate(client):
    body = client.post(
        "/api/simulations/run",
        json={"target_type": "concept", "target_id": client.concept_id},
    ).json()
    assert body["run"]["viewer_count"] == 25
    assert body["run"]["audience_version"] == "audience-v1"
    assert body["run"]["model"] == "stub/deterministic-v1"
    assert body["run"]["prompt_version"] == "reaction-v1"
    agg = body["aggregate"]
    for key in (
        "watch_probability",
        "like_probability",
        "comment_probability",
        "share_probability",
        "follow_probability",
    ):
        assert 0.0 <= agg["means"][key] <= 1.0
    assert agg["viewer_count"] == 25
    assert sum(agg["watch_buckets"].values()) == 25
    assert agg["reason_counts"]


def test_run_episode_returns_aggregate(client):
    body = client.post(
        "/api/simulations/run",
        json={"target_type": "episode", "target_id": client.episode_id},
    ).json()
    assert body["run"]["target_type"] == "episode"
    assert body["aggregate"]["viewer_count"] == 25


def test_run_stores_per_viewer_reactions(client):
    run_id = client.post(
        "/api/simulations/run",
        json={"target_type": "concept", "target_id": client.concept_id},
    ).json()["run"]["id"]
    reactions = client.get(f"/api/simulations/{run_id}/reactions").json()
    assert len(reactions) == 25
    assert all(r["run_id"] == run_id for r in reactions)
    assert len({r["watch_probability"] for r in reactions}) >= 2


def test_same_episode_rerun_reproducible(client):
    a = client.post(
        "/api/simulations/run",
        json={"target_type": "episode", "target_id": client.episode_id},
    ).json()["aggregate"]["means"]
    b = client.post(
        "/api/simulations/run",
        json={"target_type": "episode", "target_id": client.episode_id},
    ).json()["aggregate"]["means"]
    assert a == b


def test_run_listing_and_detail(client):
    run_id = client.post(
        "/api/simulations/run",
        json={"target_type": "concept", "target_id": client.concept_id},
    ).json()["run"]["id"]
    runs = client.get("/api/simulations").json()
    assert any(r["id"] == run_id for r in runs)
    detail = client.get(f"/api/simulations/{run_id}").json()
    assert detail["aggregate"]["viewer_count"] == 25


def test_run_validation(client):
    assert client.post(
        "/api/simulations/run", json={"target_type": "video", "target_id": 1}
    ).status_code == 400
    assert client.post(
        "/api/simulations/run",
        json={"target_type": "concept", "target_id": 9999},
    ).status_code == 400
    assert client.get("/api/simulations/9999").status_code == 404
    assert client.get("/api/simulations/9999/reactions").status_code == 404


def test_affinity_increases_follow():
    v = build_viewer(0)
    before = compute_reaction(v, "new episode", "a new episode just dropped").follow
    v.creator_affinities = {"hank": 1.0}
    after = compute_reaction(v, "new episode", "a new episode just dropped").follow
    assert after > before
