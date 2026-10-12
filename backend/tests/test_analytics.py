"""Sprint 8.1 — analytics: ladder logic, append-only snapshots, sweep behavior."""
import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.published_video import PublishedVideo
from app.models.video_metrics import VideoMetrics
from app.models.youtube_account import YouTubeAccount
from app.services.analytics_service import (
    METRICS_LADDER,
    collect_due,
    due_videos,
    fetch_video_statistics,
    next_due_offset,
    snapshot_video,
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
def client(tmp_path, monkeypatch):
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    monkeypatch.chdir(tmp_path)
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _write_tokens(tmp_path):
    """Token file every stats-fetching test needs (order-independent)."""
    secrets = tmp_path / "secrets"
    secrets.mkdir(exist_ok=True)
    (secrets / "youtube_tokens.json").write_text(
        json.dumps(
            {"UC_MOCK": {"access_token": "a", "refresh_token": "r",
                         "expires_at": time.time() + 9999, "scope": ""}}
        )
    )
    import app.services.youtube_service as yts

    yts._token_path = lambda: secrets / "youtube_tokens.json"


@pytest.fixture
def tokens(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_tokens(tmp_path)


def _stats_transport(views=100, likes=10, comments=2, subs=50):
    def handler(request: httpx.Request) -> httpx.Response:
        if "channels" in request.url.path:
            return httpx.Response(
                200, json={"items": [{"statistics": {"subscriberCount": str(subs)}}]}
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "statistics": {
                            "viewCount": str(views),
                            "likeCount": str(likes),
                            "commentCount": str(comments),
                        }
                    }
                ]
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def published(client, tmp_path):
    db = TestingSession()
    db.add(
        YouTubeAccount(
            channel_id="UC_MOCK",
            channel_name="Mock Channel",
            oauth_reference="secrets/youtube_tokens.json",
            status="active",
        )
    )
    record = PublishedVideo(
        episode_id=1,
        render_id=1,
        channel_id="UC_MOCK",
        video_id="vid_analytics",
        title="t",
        privacy_status="private",
        status="uploaded",
        upload_time=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    db.add(record)
    db.commit()
    secrets = tmp_path / "secrets"
    secrets.mkdir(exist_ok=True)
    (secrets / "youtube_tokens.json").write_text(
        json.dumps(
            {"UC_MOCK": {"access_token": "a", "refresh_token": "r",
                         "expires_at": time.time() + 9999, "scope": ""}}
        )
    )
    import app.services.youtube_service as yts

    yts._token_path = lambda: secrets / "youtube_tokens.json"
    record_id = record.id
    db.close()
    return record_id


def test_fetch_statistics_parses_counts(tokens):
    stats = fetch_video_statistics("vid", "UC_MOCK", http=_stats_transport(views=123))
    assert stats["views"] == 123
    assert stats["subscriber_count"] == 50


def test_ladder_shape():
    assert [s.total_seconds() for s in METRICS_LADDER] == [
        900, 3600, 21600, 86400, 172800, 604800
    ]


def test_next_due_offset_needs_15m_first():
    db = TestingSession()
    record = PublishedVideo(
        episode_id=1, render_id=1, channel_id="UC", video_id="v",
        upload_time=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    assert next_due_offset(record, [], datetime.now(timezone.utc)) == METRICS_LADDER[0]


def test_nothing_due_before_15m():
    record = PublishedVideo(
        episode_id=1, render_id=1, channel_id="UC", video_id="v",
        upload_time=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    assert next_due_offset(record, [], datetime.now(timezone.utc)) is None


def test_taken_offset_skipped():
    record = PublishedVideo(
        episode_id=1, render_id=1, channel_id="UC", video_id="v",
        upload_time=datetime.now(timezone.utc) - timedelta(minutes=70),
    )
    row = VideoMetrics(
        published_video_id=1, video_id="v", views=1,
        captured_at=datetime.now(timezone.utc) - timedelta(minutes=54),
    )
    assert next_due_offset(record, [row], datetime.now(timezone.utc)) == METRICS_LADDER[1]


def test_snapshot_append_only_with_subscriber_delta(published):
    db = TestingSession()
    first = snapshot_video(
        db, published, http=_stats_transport(views=100, subs=50)
    )
    assert first.views == 100 and first.subscribers_gained == 0

    second = snapshot_video(
        db, published, http=_stats_transport(views=150, subs=53)
    )
    assert second.views == 150 and second.subscribers_gained == 3

    history = (
        db.query(VideoMetrics)
        .filter(VideoMetrics.published_video_id == published)
        .order_by(VideoMetrics.id)
        .all()
    )
    assert [h.views for h in history] == [100, 150]
    db.close()


def test_due_videos_lists_only_due(published):
    db = TestingSession()
    assert db.query(VideoMetrics).count() == 0
    assert due_videos(db) == [published]  # 20m old -> 15m due
    db.close()


def test_collect_due_sweeps(client, published):
    db = TestingSession()
    collected = collect_due(db, http=_stats_transport(views=7))
    assert len(collected) == 1
    assert collected[0].views == 7
    # snapshot counts toward the ladder: nothing further is due yet
    assert collect_due(db, http=_stats_transport(views=8)) == []
    db.close()


def test_snapshot_failure_does_not_block_sweep(published):
    db = TestingSession()

    def bad_transport():
        def handler(request):
            return httpx.Response(500, json={"error": "boom"})

        return httpx.Client(transport=httpx.MockTransport(handler))

    assert collect_due(db, http=bad_transport()) == []
    assert db.query(VideoMetrics).count() == 0
    db.close()


def test_snapshot_endpoint(client, published):
    import app.services.analytics_service as svc

    http = _stats_transport(views=42)
    original = svc.fetch_video_statistics
    svc.fetch_video_statistics = lambda *a, **k: original(
        *a, **{**k, "http": http}
    )
    try:
        res = client.post(f"/api/youtube/published/{published}/snapshot")
        assert res.status_code == 201, res.text
        assert res.json()["views"] == 42
    finally:
        svc.fetch_video_statistics = original


def test_metrics_history_endpoint(client, published):
    db = TestingSession()
    for views in (10, 20):
        snapshot_video(db, published, http=_stats_transport(views=views))
    db.close()

    history = client.get(f"/api/youtube/published/{published}/metrics").json()
    assert [h["views"] for h in history] == [10, 20]
    assert client.get("/api/youtube/published/9999/metrics").status_code == 404


def test_due_endpoint(client, published):
    assert published in client.get("/api/youtube/analytics/due").json()
