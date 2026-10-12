"""Sprint 7.2 — private upload: gates, resumable upload mock, record keeping."""
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PIL import Image

from app.core.database import Base, get_db
from app.main import app
from app.models.published_video import PublishedVideo
from app.models.youtube_account import YouTubeAccount
from app.services import youtube_service
from app.services.youtube_upload_service import (
    PublishGateError,
    UploadError,
    publish_episode,
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


def _sine(path, seconds=5.0):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-ar", "44100", "-ac", "1", str(path)],
        capture_output=True, check=True,
    )
    return path


def _upload_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, json={"id": "vid_mock_123"})
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"ok": True},
                headers={"Location": "https://upload.test/upload/session/abc"},
            )
        return httpx.Response(404, json={"error": "not mocked"})

    return httpx.MockTransport(handler)


@pytest.fixture
def client(tmp_path, monkeypatch):
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    monkeypatch.chdir(tmp_path)
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def ready_episode(client, tmp_path, monkeypatch):
    """Approved + rendered episode with a real final.mp4 on disk."""
    monkeypatch.setattr(
        "app.services.video_service.synthesize_speech",
        lambda text, wav_path, **kw: _sine(wav_path, seconds=5.0),
    )
    creator = client.post(
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": "Hank's World"}
    ).json()
    ep = client.post(
        f"/api/series/{series['id']}/generate-episode", json={"variant": 0}
    ).json()["episode"]
    client.post(f"/api/episodes/{ep['id']}/approve", json={})
    render = client.post(f"/api/episodes/{ep['id']}/render", json={}).json()

    # fake an active channel + stored token so the upload can run offline
    db = TestingSession()
    account = YouTubeAccount(
        channel_id="UC_MOCK",
        channel_name="Mock Channel",
        oauth_reference="secrets/youtube_tokens.json",
        status="active",
    )
    db.add(account)
    db.commit()

    token_dir = tmp_path / "secrets"
    token_dir.mkdir(exist_ok=True)
    import json
    import time

    (token_dir / "youtube_tokens.json").write_text(
        json.dumps({"UC_MOCK": {"access_token": "a", "refresh_token": "r",
                                "expires_at": time.time() + 9999, "scope": ""}})
    )
    monkeypatch.setattr(youtube_service, "SECRETS_DIR", token_dir)
    monkeypatch.setattr(youtube_service, "_token_path", lambda: token_dir / "youtube_tokens.json")
    db.close()
    return ep, render


def _mock_http():
    return httpx.Client(transport=_upload_transport(), base_url="https://google.test")


# Roadmap verification: upload privately and record the ids.
def test_publish_records_video_and_ids(ready_episode, monkeypatch):
    ep, render = ready_episode
    db = TestingSession()
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video",
        lambda video_path, title, description, channel_id, **kw: {"id": "vid_mock_123"},
    )
    record = publish_episode(db, ep["id"])
    assert record.channel_id == "UC_MOCK"
    assert record.video_id == "vid_mock_123"
    assert record.privacy_status == "private"
    assert record.status == "uploaded"
    assert record.render_id == render["render_id"]
    assert record.upload_time is not None
    db.close()


def test_publish_endpoint_created(ready_episode, monkeypatch, client):
    ep, render = ready_episode
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video",
        lambda video_path, title, description, channel_id, **kw: {"id": "vid_endpoint"},
    )
    res = client.post(f"/api/youtube/episodes/{ep['id']}/publish", json={})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["video_id"] == "vid_endpoint"
    assert body["status"] == "uploaded"
    assert body["privacy_status"] == "private"

    videos = client.get(f"/api/youtube/episodes/{ep['id']}/videos").json()
    assert [v["video_id"] for v in videos] == ["vid_endpoint"]
    listed = client.get("/api/youtube/videos").json()
    assert len(listed) == 1


def test_publish_requires_ready_episode(client):
    creator = client.post("/api/creators", json={"name": "H", "slug": "h"}).json()
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": "S"}
    ).json()
    ep = client.post(
        f"/api/series/{series['id']}/generate-episode", json={"variant": 0}
    ).json()["episode"]
    db = TestingSession()
    with pytest.raises(PublishGateError, match="approved and rendered"):
        publish_episode(db, ep["id"])
    db.close()

    res = client.post(f"/api/youtube/episodes/{ep['id']}/publish", json={})
    assert res.status_code == 409


def test_publish_requires_channel(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.video_service.synthesize_speech",
        lambda text, wav_path, **kw: _sine(wav_path, seconds=5.0),
    )
    creator = client.post("/api/creators", json={"name": "Hank", "slug": "hank"}).json()
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": "S"}
    ).json()
    ep = client.post(
        f"/api/series/{series['id']}/generate-episode", json={"variant": 0}
    ).json()["episode"]
    client.post(f"/api/episodes/{ep['id']}/approve", json={})
    render = client.post(f"/api/episodes/{ep['id']}/render", json={})
    assert render.status_code == 200, render.text

    res = client.post(f"/api/youtube/episodes/{ep['id']}/publish", json={})
    assert res.status_code == 409
    assert "channel" in res.json()["detail"]


def test_duplicate_publish_rejected(ready_episode, monkeypatch):
    ep, render = ready_episode
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video",
        lambda video_path, title, description, channel_id, **kw: {"id": "vid_dup"},
    )
    db = TestingSession()
    publish_episode(db, ep["id"])
    with pytest.raises(PublishGateError, match="already published"):
        publish_episode(db, ep["id"])
    db.close()


def test_upload_failure_marks_failed(ready_episode, monkeypatch):
    ep, render = ready_episode
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video",
        lambda video_path, title, description, channel_id, **kw: (_ for _ in ()).throw(
            UploadError("boom")
        ),
    )
    db = TestingSession()
    with pytest.raises(UploadError):
        publish_episode(db, ep["id"])
    db.close()
    record = (
        TestingSession()
        .query(PublishedVideo)
        .filter_by(episode_id=ep["id"])
        .first()
    )
    assert record is not None
    assert record.status == "failed"
    assert "boom" in record.error


def test_public_privacy_rejected():
    with pytest.raises(PublishGateError):
        from app.services.youtube_upload_service import upload_private_video

        upload_private_video(
            __import__("pathlib").Path("nonexistent.mp4"),
            title="t",
            channel_id="UC",
            privacy="public",
        )


def test_upload_transport_session_and_put(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake-mp4-bytes")
    http = _mock_http()
    from app.services.youtube_upload_service import start_resumable_session, upload_bytes

    url = start_resumable_session(http, "token", {"snippet": {"title": "t"}, "_size": 14})
    assert url.endswith("/upload/session/abc")
    resource = upload_bytes(http, url, b"fake-mp4-bytes")
    assert resource["id"] == "vid_mock_123"
