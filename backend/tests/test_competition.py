"""Phase 23 — organic-only creator competition leaderboard."""
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
from app.services import competition_service as svc

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


def _video(cid, sid, number, *, views, likes=0, comments=0, subs=0,
           duration=60.0, minutes=None):
    db = _db()
    episode = Episode(
        creator_id=cid, series_id=sid, episode_number=number,
        title=f"Ep {number}", status=EpisodeStatus.PUBLISHED,
    )
    db.add(episode)
    db.flush()
    render = Render(episode_id=episode.id, status="READY", total_duration=duration)
    db.add(render)
    db.flush()
    video = PublishedVideo(
        episode_id=episode.id, render_id=render.id, channel_id="chan",
        video_id=f"v{cid}-{number}", total_duration=duration,
    )
    db.add(video)
    db.flush()
    db.add(
        VideoMetrics(
            published_video_id=video.id, video_id=video.video_id, views=views,
            likes=likes, comments=comments, subscriber_count=subs,
            subscribers_gained=subs, estimated_minutes_watched=minutes,
        )
    )
    db.commit()
    out = video.id
    db.close()
    return out


def _snapshot(published_id, *, views, likes=0, comments=0, subs=0, minutes=None):
    db = _db()
    video = db.get(PublishedVideo, published_id)
    db.add(
        VideoMetrics(
            published_video_id=published_id, video_id=video.video_id, views=views,
            likes=likes, comments=comments, subscriber_count=subs,
            subscribers_gained=subs, estimated_minutes_watched=minutes,
        )
    )
    db.commit()
    db.close()


# ---------- metrics ----------


def test_creator_metrics(client):
    cid, sid = _seed()
    _video(cid, sid, 1, views=100, likes=10, comments=5, subs=2, minutes=30)
    _video(cid, sid, 2, views=300, likes=30, comments=15, subs=8, minutes=60)

    db = _db()
    m = svc.creator_metrics(db, cid)
    db.close()

    assert m.videos_with_metrics == 2
    assert m.total_views == 400
    assert m.growth == 10
    assert m.subscriber_conversion == 0.025
    assert m.audience_loyalty == 0.15
    assert m.episode_performance == 200.0
    assert m.retention == 0.25


def test_latest_snapshot_wins(client):
    cid, sid = _seed()
    pid = _video(cid, sid, 1, views=100, subs=2)
    _video(cid, sid, 2, views=300, subs=8)
    _snapshot(pid, views=500, subs=50)

    db = _db()
    m = svc.creator_metrics(db, cid)
    db.close()

    assert m.total_views == 800
    assert m.growth == 58


def test_retention_missing_is_null(client):
    cid, sid = _seed()
    _video(cid, sid, 1, views=100)
    _video(cid, sid, 2, views=100)
    db = _db()
    m = svc.creator_metrics(db, cid)
    db.close()
    assert m.retention is None


# ---------- leaderboard ----------


def test_leaderboard_ranks_organic_best_first(client):
    hank, hsid = _seed("Hank", "hank")
    alex, asid = _seed("Alex", "alex-exe")
    _video(hank, hsid, 1, views=100, likes=10, comments=5, subs=10)
    _video(hank, hsid, 2, views=100, likes=10, comments=5, subs=10)
    _video(alex, asid, 1, views=50, likes=1, comments=0, subs=1)
    _video(alex, asid, 2, views=50, likes=1, comments=0, subs=1)

    db = _db()
    board = svc.build_leaderboard(db)
    db.close()

    assert board["interpretation_allowed"] is True
    assert board["eligible_creators"] == 2
    assert board["leader"] == "hank"
    hank_row = next(c for c in board["creators"] if c["slug"] == "hank")
    alex_row = next(c for c in board["creators"] if c["slug"] == "alex-exe")
    assert hank_row["overall_rank"] == 1
    assert alex_row["overall_rank"] == 2
    assert hank_row["composite_rank"] < alex_row["composite_rank"]
    # retention wasn't reported: four dimensions carry ranks
    assert hank_row["dimension_coverage"] == 4
    assert hank_row["ranks"]["retention"] is None


def test_ineligible_creator_excluded(client):
    hank, hsid = _seed("Hank", "hank")
    _video(hank, hsid, 1, views=100, subs=5)

    db = _db()
    board = svc.build_leaderboard(db)
    db.close()

    row = board["creators"][0]
    assert row["eligible"] is False
    assert row["overall_rank"] is None
    assert board["eligible_creators"] == 0
    assert board["interpretation_allowed"] is False
    assert board["leader"] is None


# ---------- endpoints ----------


def test_endpoints(client):
    hank, hsid = _seed("Hank", "hank")
    alex, asid = _seed("Alex", "alex-exe")
    _video(hank, hsid, 1, views=100, likes=5, comments=1, subs=10)
    _video(hank, hsid, 2, views=100, likes=5, comments=1, subs=10)
    _video(alex, asid, 1, views=20, subs=1)
    _video(alex, asid, 2, views=20, subs=1)

    board = client.get("/api/competition/leaderboard")
    assert board.status_code == 200, board.text
    assert board.json()["leader"] == "hank"
    assert "never artificial engagement" in board.json()["note"].lower()

    standing = client.get(f"/api/competition/creators/{hank}")
    assert standing.status_code == 200
    assert standing.json()["overall_rank"] == 1

    assert client.get("/api/competition/creators/999").status_code == 404
