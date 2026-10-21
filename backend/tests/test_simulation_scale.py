"""Phase 24 — large-scale simulation ladder + predictive validity."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.models.episode import Episode, EpisodeStatus
from app.models.published_video import PublishedVideo
from app.models.render import Render
from app.models.series import Series
from app.models.video_metrics import VideoMetrics
from app.services import simulation_scale as scale
from app.services.audience_service import seed_audience
from app.services.simulation_service import run_simulation

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


def _seed(name="Hank", slug="hank"):
    db = _db()
    creator = Creator(name=name, slug=slug)
    db.add(creator)
    db.flush()
    series = Series(creator_id=creator.id, name=f"{name}'s World")
    db.add(series)
    db.commit()
    out = (creator.id, series.id)
    db.close()
    return out


def _episode(cid, sid, number, premise, views):
    db = _db()
    ep = Episode(
        creator_id=cid, series_id=sid, episode_number=number,
        title=f"Episode {number}", premise=premise,
        status=EpisodeStatus.PUBLISHED,
    )
    db.add(ep)
    db.flush()
    render = Render(episode_id=ep.id, status="READY", total_duration=60.0)
    db.add(render)
    db.flush()
    video = PublishedVideo(
        episode_id=ep.id, render_id=render.id, channel_id="chan",
        video_id=f"v{number}", total_duration=60.0,
    )
    db.add(video)
    db.flush()
    db.add(
        VideoMetrics(
            published_video_id=video.id, video_id=video.video_id, views=views,
            likes=0, comments=0, subscriber_count=0, subscribers_gained=0,
        )
    )
    db.commit()
    out = ep.id
    db.close()
    return out


def test_run_simulation_accepts_viewer_count(client):
    cid, sid = _seed()
    eid = _episode(cid, sid, 1, "A broken tractor on delivery morning.", 100)

    res = client.post(
        "/api/simulations/run",
        json={"target_type": "episode", "target_id": eid, "viewer_count": 5},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["run"]["viewer_count"] == 5
    assert body["aggregate"]["viewer_count"] == 5

    db = _db()
    first = run_simulation(db, "episode", eid, seed=0, viewer_count=5)
    second = run_simulation(db, "episode", eid, seed=0, viewer_count=5)
    db.close()
    assert first.aggregate["means"] == second.aggregate["means"]


def test_scale_study_persists_ladder(client):
    cid, sid = _seed()
    _episode(cid, sid, 1, "A broken tractor on delivery morning.", 900)
    _episode(cid, sid, 2, "An AI assistant tries to plan a barn build.", 500)
    _episode(cid, sid, 3, "Cooking dinner with only a wood stove.", 100)

    res = client.post(
        "/api/simulation-scale/studies", json={"sizes": [3, 5]}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["sizes"] == [3, 5]
    assert body["metric"] == "watch_probability"
    assert len(body["results"]) == 2
    for row in body["results"]:
        assert row["comparisons"] == 3
        assert len(row["simulation_run_ids"]) == 3
        assert row["episodes"] == 3
    assert body["interpretation_allowed"] is True

    listing = client.get("/api/simulation-scale/studies")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["study_id"] == body["study_id"]

    detail = client.get(f"/api/simulation-scale/studies/{body['study_id']}")
    assert detail.status_code == 200
    assert detail.json()["run_uuid"] == body["run_uuid"]


def test_audience_population_scales_past_old_cap(client):
    db = _db()
    viewers = seed_audience(db, count=600)
    assert len(viewers) == 600
    assert viewers[-1].seed_index == 599
    with pytest.raises(ValueError):
        seed_audience(db, count=10001)
    db.close()


def test_minimum_useful_size_helper():
    rows = [
        {"viewer_count": 25, "comparisons": 3, "directional_accuracy": 0.4},
        {"viewer_count": 100, "comparisons": 3, "directional_accuracy": 0.8},
        {"viewer_count": 500, "comparisons": 3, "directional_accuracy": 0.9},
        {"viewer_count": 1000, "comparisons": 1, "directional_accuracy": 1.0},
    ]
    assert scale.minimum_useful_size(rows, min_pairs=3, threshold=0.6) == 100
    assert scale.minimum_useful_size(rows, min_pairs=3, threshold=0.95) is None
    assert scale.minimum_useful_size(rows, min_pairs=5, threshold=0.1) is None


def test_study_validation(client):
    assert (
        client.post(
            "/api/simulation-scale/studies", json={"metric": "nope"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/simulation-scale/studies", json={"sizes": [0]}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/simulation-scale/studies", json={"sizes": [10001]}
        ).status_code
        == 400
    )
    assert (
        client.post("/api/simulation-scale/studies", json={}).status_code == 400
    )
    assert client.get("/api/simulation-scale/studies/999").status_code == 404
