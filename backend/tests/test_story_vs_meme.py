"""Sprint 16.3 — story vs meme: serialized vs one-off content on real behavior."""
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
from app.models.video_metrics import VideoMetrics
from app.services.story_vs_meme_service import (
    format_for_series_size,
    story_vs_meme_report,
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
    db.commit()
    creator_id = creator.id
    db.close()
    return creator_id


def _seed_series_ep(creator_id, with_run, views, subs_gained, snap_count=1):
    """One series with `with_run` episodes; publish + metrics on the last one."""
    db = _db()
    series = Series(creator_id=creator_id, name=f"Series {views}-{subs_gained}-{with_run}")
    db.add(series)
    db.flush()
    for _ in range(with_run):
        episode = Episode(
            creator_id=creator_id,
            series_id=series.id,
            episode_number=episode_count(db, series.id) + 1,
            title=f"ep {series.id}",
        )
        db.add(episode)
        db.commit()
        db.refresh(episode)
    video = PublishedVideo(
        episode_id=episode.id,
        render_id=1,
        channel_id="UC_MOCK",
        video_id=f"vid-{episode.id}",
    )
    db.add(video)
    db.flush()
    for i in range(snap_count):
        db.add(
            VideoMetrics(
                published_video_id=video.id,
                video_id=video.video_id,
                views=views,
                subscriber_count=100,
                subscribers_gained=subs_gained,
            )
        )
    db.commit()
    episode_id = episode.id
    db.close()
    return episode_id


def episode_count(db, series_id):
    return db.query(Episode).filter(Episode.series_id == series_id).count()


def _views_gained(db, ep_id):
    row = next(e for e in story_vs_meme_report(db)["episodes"] if e["episode_id"] == ep_id)
    return row


# ---------- classification ----------


def test_format_for_series_size():
    assert format_for_series_size(1) == "meme"
    assert format_for_series_size(2) == "story"
    assert format_for_series_size(7) == "story"


# ---------- report ----------


def test_story_wins_subscriber_conversion(client):
    creator_id = _seed_world()
    # two story episodes, two meme one-offs
    _seed_series_ep(creator_id, 2, 1000, 20)
    _seed_series_ep(creator_id, 3, 1000, 25)
    _seed_series_ep(creator_id, 1, 1000, 10)
    _seed_series_ep(creator_id, 1, 1000, 8)

    report = story_vs_meme_report(_db())
    assert report["by_format"]["story"]["episodes"] == 2
    assert report["by_format"]["meme"]["episodes"] == 2
    assert report["by_format"]["story"]["subscriber_conversion"] == pytest.approx(45 / 2000, abs=1e-3)
    assert report["by_format"]["meme"]["subscriber_conversion"] == pytest.approx(18 / 2000, abs=1e-3)
    assert report["higher_subscriber_conversion"] == "story"
    assert report["interpretation_allowed"] is True
    assert "story" in report["verdict"]


def test_meme_wins_when_conversion_higher(client):
    creator_id = _seed_world()
    _seed_series_ep(creator_id, 2, 1000, 5)
    _seed_series_ep(creator_id, 3, 1000, 6)
    _seed_series_ep(creator_id, 1, 1000, 30)
    _seed_series_ep(creator_id, 1, 1000, 40)

    report = story_vs_meme_report(_db())
    assert report["higher_subscriber_conversion"] == "meme"
    assert report["verdict"].startswith("meme")


def test_report_gated_below_min_total(client):
    creator_id = _seed_world()
    _seed_series_ep(creator_id, 2, 1000, 20)

    report = story_vs_meme_report(_db())
    assert report["episodes_considered"] == 1
    assert report["interpretation_allowed"] is False
    assert report["verdict"].startswith("insufficient data")


def test_report_records_episode_rows_and_skips(client):
    creator_id = _seed_world()
    _seed_series_ep(creator_id, 2, 500, 10)
    db = _db()
    db.add(Episode(creator_id=creator_id, series_id=9, episode_number=1, title="orphan"))
    db.commit()
    db.close()

    report = story_vs_meme_report(_db())
    row = report["episodes"][0]
    assert {"episode_id", "series_id", "format", "series_size", "views",
            "subscribers_gained", "subscriber_conversion"} <= set(row)
    assert row["format"] == "story"  # series holds 2 episodes
    assert report["episodes_skipped"] == 2  # orphan + the un-published first episode


def test_endpoint(client):
    creator_id = _seed_world()
    _seed_series_ep(creator_id, 2, 1000, 20)
    _seed_series_ep(creator_id, 1, 1000, 10)
    _seed_series_ep(creator_id, 2, 1000, 22)
    _seed_series_ep(creator_id, 1, 1000, 9)

    res = client.get("/api/experiments/story-vs-meme")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["formats"] == ["story", "meme"]
    assert body["series_story_min"] == 2
    assert "higher_subscriber_conversion" in body
    assert set(body["by_format"]) == {"story", "meme"}

    filtered = client.get(
        "/api/experiments/story-vs-meme", params={"creator_id": 999}
    ).json()
    assert filtered["episodes_considered"] == 0
