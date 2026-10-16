"""Sprint 16.2 — episode length experiment: bucket durations, compare sim vs reality."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.models.episode import Episode
from app.models.published_video import PublishedVideo
from app.models.render import Render
from app.models.series import Series
from app.models.simulation import SimulationRun, ViewerReaction
from app.models.video_metrics import VideoMetrics
from app.services.length_experiment_service import (
    episode_length,
    length_bucket,
    length_experiment_report,
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


def _db():
    return TestingSession()


def _seed_world():
    db = _db()
    creator = Creator(name="Hank", slug="hank")
    db.add(creator)
    db.flush()
    series = Series(creator_id=creator.id, name="Hank's Farm")
    db.add(series)
    db.commit()
    creator_id, series_id = creator.id, series.id
    db.close()
    return creator_id, series_id


def _seed_episode(
    creator_id, series_id, number, duration, sim_watch=None, real_views=None,
    source="published",
):
    db = _db()
    episode = Episode(
        creator_id=creator_id,
        series_id=series_id,
        episode_number=number,
        title=f"Episode {number}",
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)

    if source == "published":
        video = PublishedVideo(
            episode_id=episode.id,
            render_id=1,
            channel_id="UC_MOCK",
            video_id=f"vid-{episode.id}",
            total_duration=duration,
        )
        db.add(video)
        db.flush()
        if real_views is not None:
            db.add(
                VideoMetrics(
                    published_video_id=video.id,
                    video_id=video.video_id,
                    views=real_views,
                )
            )
    elif source == "render":
        db.add(
            Render(
                episode_id=episode.id,
                status="READY",
                total_duration=duration,
            )
        )

    if sim_watch is not None:
        run = SimulationRun(target_type="episode", target_id=episode.id)
        db.add(run)
        db.flush()
        db.add(
            ViewerReaction(
                run_id=run.id,
                viewer_id=1,
                watch_probability=sim_watch,
                like_probability=0.5,
                comment_probability=0.1,
                share_probability=0.1,
                follow_probability=0.1,
            )
        )
    db.commit()
    episode_id = episode.id
    db.close()
    return episode_id


# ---------- bucketing ----------


def test_length_bucket_boundaries():
    assert length_bucket(10) == "short"
    assert length_bucket(29.9) == "short"
    assert length_bucket(30) == "medium"
    assert length_bucket(59.9) == "medium"
    assert length_bucket(60) == "long"
    assert length_bucket(300) == "long"


def test_episode_length_prefers_published_then_render(client):
    creator_id, series_id = _seed_world()
    ep = _seed_episode(creator_id, series_id, 1, 40.0, source="render")
    assert episode_length(_db(), ep) == (40.0, "render")

    ep2 = _seed_episode(creator_id, series_id, 2, 52.0, source="published")
    assert episode_length(_db(), ep2) == (52.0, "published")

    # no render, no publish → unknown
    db = _db()
    bare = Episode(creator_id=creator_id, series_id=series_id, episode_number=3, title="bare")
    db.add(bare)
    db.commit()
    bare_id = bare.id
    db.close()
    assert episode_length(_db(), bare_id) is None


# ---------- report ----------


def test_report_prefers_matching_length(client):
    creator_id, series_id = _seed_world()
    _seed_episode(creator_id, series_id, 1, 20.0, 0.9, 900)
    _seed_episode(creator_id, series_id, 2, 25.0, 0.9, 900)
    _seed_episode(creator_id, series_id, 3, 90.0, 0.4, 200)
    _seed_episode(creator_id, series_id, 4, 120.0, 0.4, 200)

    report = length_experiment_report(_db())
    assert report["simulation_preferred"] == "short"
    assert report["reality_preferred"] == "short"
    assert report["agreement"] is True
    assert report["interpretation_allowed"] is True
    assert report["by_bucket"]["short"]["mean_sim_watch"] == 0.9
    assert report["by_bucket"]["long"]["mean_real_views"] == 200.0
    assert "agrees" in report["verdict"]


def test_report_detects_disagreement(client):
    creator_id, series_id = _seed_world()
    _seed_episode(creator_id, series_id, 1, 20.0, 0.9, 100)
    _seed_episode(creator_id, series_id, 2, 25.0, 0.9, 100)
    _seed_episode(creator_id, series_id, 3, 90.0, 0.4, 900)
    _seed_episode(creator_id, series_id, 4, 120.0, 0.4, 900)

    report = length_experiment_report(_db())
    assert report["simulation_preferred"] == "short"
    assert report["reality_preferred"] == "long"
    assert report["agreement"] is False
    assert "disagree" in report["verdict"]


def test_report_gated_and_counts_unknown(client):
    creator_id, series_id = _seed_world()
    _seed_episode(creator_id, series_id, 1, 20.0, 0.9, 900)
    db = _db()
    db.add(Episode(creator_id=creator_id, series_id=series_id, episode_number=2, title="bare"))
    db.commit()
    db.close()

    report = length_experiment_report(_db())
    assert report["episodes_considered"] == 1
    assert report["episodes_without_duration"] == 1
    assert report["interpretation_allowed"] is False
    assert report["verdict"].startswith("insufficient data")


def test_report_notes_simulator_limitation(client):
    report = length_experiment_report(_db())
    assert "no duration input" in report["simulator_note"]


def test_endpoint(client):
    creator_id, series_id = _seed_world()
    _seed_episode(creator_id, series_id, 1, 20.0, 0.9, 900)
    _seed_episode(creator_id, series_id, 2, 25.0, 0.9, 900)
    _seed_episode(creator_id, series_id, 3, 90.0, 0.4, 200)
    _seed_episode(creator_id, series_id, 4, 120.0, 0.4, 200)

    res = client.get("/api/experiments/length-experiment")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["buckets"] == ["short", "medium", "long"]
    assert body["agreement"] is True
    assert {"episode_id", "duration_seconds", "source", "bucket", "sim_watch",
            "real_views"} <= set(body["lengths"][0])

    filtered = client.get(
        "/api/experiments/length-experiment", params={"creator_id": 999}
    ).json()
    assert filtered["episodes_considered"] == 0
