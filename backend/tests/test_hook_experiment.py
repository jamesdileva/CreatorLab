"""Sprint 16.1 — hook experiment: classify hook types, compare sim vs reality."""
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
from app.models.series import Series
from app.models.simulation import SimulationRun, ViewerReaction
from app.models.video_metrics import VideoMetrics
from app.services.hook_experiment_service import (
    classify_hook,
    episode_hook,
    hook_experiment_report,
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


def _seed_episode(creator_id, series_id, number, hook, sim_watch=None, real_views=None):
    db = _db()
    episode = Episode(
        creator_id=creator_id,
        series_id=series_id,
        episode_number=number,
        title=f"Episode {number}",
        synopsis=hook,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)

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
    if real_views is not None:
        video = PublishedVideo(
            episode_id=episode.id,
            render_id=1,
            channel_id="UC_MOCK",
            video_id=f"vid-{episode.id}",
        )
        db.add(video)
        db.flush()
        db.add(
            VideoMetrics(
                published_video_id=video.id,
                video_id=video.video_id,
                views=real_views,
            )
        )
    db.commit()
    episode_id = episode.id
    db.close()
    return episode_id


# ---------- classification ----------


def test_classify_hook_types():
    assert classify_hook("Today we finally build the fence.") == "direct"
    assert classify_hook("Why does the tractor scream at night?") == "question"
    assert classify_hook("Why the tractor screams") == "question"
    assert classify_hook("Hank rebuilds his tractor.", ("Hank",)) == "character"
    assert classify_hook("My name is Hank.") == "character"
    assert classify_hook("The tractor is possessed.") == "absurd"
    assert classify_hook("") == "direct"
    assert classify_hook(None) == "direct"


def test_classify_priority():
    # explicit question wins even when other markers are present
    assert classify_hook("Why is Hank possessed?", ("Hank",)) == "question"
    # character wins over absurd
    assert classify_hook("Hank is literally possessed.", ("Hank",)) == "character"


def test_episode_hook_uses_first_sentence():
    episode = Episode(creator_id=1, series_id=1, episode_number=1, title="t")
    episode.synopsis = "First beat happens. Second beat follows."
    assert episode_hook(episode) == "First beat happens."
    episode.synopsis = ""
    episode.premise = "Fallback premise here."
    assert episode_hook(episode) == "Fallback premise here."


# ---------- report ----------


def test_report_prefers_matching_hook(client):
    creator_id, series_id = _seed_world()
    _seed_episode(creator_id, series_id, 1, "Why does it rain?", 0.9, 900)
    _seed_episode(creator_id, series_id, 2, "Why so serious?", 0.9, 900)
    _seed_episode(creator_id, series_id, 3, "Today we build a fence.", 0.5, 500)
    _seed_episode(creator_id, series_id, 4, "Today we paint a wall.", 0.5, 500)

    report = hook_experiment_report(_db())
    assert report["simulation_preferred"] == "question"
    assert report["reality_preferred"] == "question"
    assert report["agreement"] is True
    assert report["interpretation_allowed"] is True
    assert report["by_type"]["question"]["mean_sim_watch"] == 0.9
    assert report["by_type"]["question"]["mean_real_views"] == 900.0
    assert report["by_type"]["question"]["sim_sufficient"] is True
    assert "agrees" in report["verdict"]


def test_report_detects_disagreement(client):
    creator_id, series_id = _seed_world()
    _seed_episode(creator_id, series_id, 1, "Why does it rain?", 0.9, 100)
    _seed_episode(creator_id, series_id, 2, "Why so serious?", 0.9, 100)
    _seed_episode(creator_id, series_id, 3, "The barn is haunted.", 0.4, 900)
    _seed_episode(creator_id, series_id, 4, "The goat is possessed.", 0.4, 900)

    report = hook_experiment_report(_db())
    assert report["simulation_preferred"] == "question"
    assert report["reality_preferred"] == "absurd"
    assert report["agreement"] is False
    assert "disagree" in report["verdict"]


def test_report_gated_below_min_total(client):
    creator_id, series_id = _seed_world()
    _seed_episode(creator_id, series_id, 1, "Why does it rain?", 0.9, 900)

    report = hook_experiment_report(_db())
    assert report["episodes_considered"] == 1
    assert report["interpretation_allowed"] is False
    assert report["verdict"].startswith("insufficient data")


def test_endpoint(client):
    creator_id, series_id = _seed_world()
    _seed_episode(creator_id, series_id, 1, "Why does it rain?", 0.9, 900)
    _seed_episode(creator_id, series_id, 2, "Why so serious?", 0.9, 900)
    _seed_episode(creator_id, series_id, 3, "Today we build a fence.", 0.5, 500)
    _seed_episode(creator_id, series_id, 4, "Today we paint a wall.", 0.5, 500)

    res = client.get("/api/experiments/hook-experiment")
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body["hook_types"]) == {"direct", "question", "absurd", "character"}
    assert body["agreement"] is True
    assert {"episode_id", "hook", "hook_type", "sim_watch", "real_views"} <= set(
        body["hooks"][0]
    )

    filtered = client.get(
        "/api/experiments/hook-experiment", params={"creator_id": 999}
    ).json()
    assert filtered["episodes_considered"] == 0

    only_hank = client.get(
        "/api/experiments/hook-experiment", params={"creator_id": creator_id}
    ).json()
    assert only_hank["episodes_considered"] == 4
