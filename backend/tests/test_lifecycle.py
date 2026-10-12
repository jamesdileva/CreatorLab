"""Sprint 7.3 â€” lifecycle: status refresh, retry recovery, metadata, thumbnails."""
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.published_video import PublishedVideo
from app.models.youtube_account import YouTubeAccount
from app.services import youtube_service
from app.services.youtube_upload_service import (
    PublishGateError,
    UploadError,
    extract_thumbnail,
    publish_episode,
    refresh_published_status,
    retry_publish,
    set_video_thumbnail,
    update_video_metadata,
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


def _upload_ok():
    return lambda video_path, title, description, channel_id, **kw: {"id": "vid_ok"}


def _upload_fail():
    def boom(video_path, title, description, channel_id, **kw):
        raise UploadError("simulated upload failure")

    return boom


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
def channel_with_token(client, tmp_path):
    import time

    db = TestingSession()
    db.add(
        YouTubeAccount(
            channel_id="UC_MOCK",
            channel_name="Mock Channel",
            oauth_reference="secrets/youtube_tokens.json",
            status="active",
        )
    )
    db.commit()
    secrets = tmp_path / "secrets"
    secrets.mkdir(exist_ok=True)
    import json

    (secrets / "youtube_tokens.json").write_text(
        json.dumps(
            {"UC_MOCK": {"access_token": "a", "refresh_token": "r",
                         "expires_at": time.time() + 9999, "scope": ""}}
        )
    )
    import app.services.youtube_service as yts

    monkeypatch_target = secrets / "youtube_tokens.json"
    monkeypatch_attr = yts
    monkeypatch_attr._token_path = lambda: monkeypatch_target
    db.close()


@pytest.fixture
def ready_episode(client, monkeypatch):
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
    return ep, render


def _http_for_status(upload_status: str, privacy: str = "private"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "status": {
                            "uploadStatus": upload_status,
                            "privacyStatus": privacy,
                            "failureReason": "transcode_error",
                        }
                    }
                ]
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


# Roadmap verification: upload multiple videos and recover from a failure.
def test_status_mapping(client, monkeypatch, ready_episode, channel_with_token):
    ep, _ = ready_episode
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", _upload_ok()
    )
    db = TestingSession()
    record = publish_episode(db, ep["id"])
    db.close()

    db = TestingSession()
    monkeypatch.setattr(
        "app.services.youtube_upload_service.fetch_video_status",
        lambda channel_id, video_id, **kw: {
            "upload_status": "processed",
            "privacy_status": "private",
            "processing_status": "succeeded",
            "failure_reason": "",
            "rejection_reason": "",
        },
    )
    refreshed = refresh_published_status(db, record.id)
    assert refreshed.status == "processed"
    assert refreshed.youtube_status == "processed"
    db.close()


def test_refresh_marks_failed(client, monkeypatch, ready_episode, channel_with_token):
    ep, _ = ready_episode
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", _upload_ok()
    )
    db = TestingSession()
    record = publish_episode(db, ep["id"])
    db.close()

    db = TestingSession()
    monkeypatch.setattr(
        "app.services.youtube_upload_service.fetch_video_status",
        lambda channel_id, video_id, **kw: {
            "upload_status": "failed",
            "privacy_status": "private",
            "processing_status": "failed",
            "failure_reason": "transcode_error",
            "rejection_reason": "",
        },
    )
    refreshed = refresh_published_status(db, record.id)
    assert refreshed.status == "failed"
    assert "transcode_error" in refreshed.error
    db.close()


def test_retry_recovers_from_failure(client, monkeypatch, ready_episode, channel_with_token):
    ep, _ = ready_episode
    db = TestingSession()
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", _upload_fail()
    )
    with pytest.raises(UploadError):
        publish_episode(db, ep["id"])
    record = db.query(PublishedVideo).filter_by(episode_id=ep["id"]).first()
    assert record.status == "failed"

    # retry fails once (still flaky), then succeeds
    calls = {"n": 0}

    def flaky(video_path, title, description, channel_id, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise UploadError("still flaky")
        return {"id": "vid_recovered"}

    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", flaky
    )
    with pytest.raises(UploadError):
        retry_publish(db, record.id)
    assert record.attempts == 1

    retried = retry_publish(db, record.id)
    assert retried.status == "uploaded"
    assert retried.video_id == "vid_recovered"
    assert retried.attempts == 2
    assert retried.error == ""
    db.close()


def test_retry_only_for_failures(client, monkeypatch, ready_episode, channel_with_token):
    ep, _ = ready_episode
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", _upload_ok()
    )
    db = TestingSession()
    record = publish_episode(db, ep["id"])
    with pytest.raises(PublishGateError, match="cannot retry"):
        retry_publish(db, record.id)
    db.close()


def test_metadata_update(client, monkeypatch, ready_episode, channel_with_token):
    ep, _ = ready_episode
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", _upload_ok()
    )
    db = TestingSession()
    record = publish_episode(db, ep["id"])

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.json() if hasattr(request, "json") else None
        return httpx.Response(200, json={"ok": True})

    from pathlib import Path
    record = _update_with_mock(record, db, handler)
    assert record.title == "New Title"
    db.close()


def _update_with_mock(record, db, handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return update_video_metadata(
        db, record.id, title="New Title", description="New desc", http=http
    )


def test_thumbnail_endpoint(client, monkeypatch, ready_episode, channel_with_token):
    ep, _ = ready_episode
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", _upload_ok()
    )
    db = TestingSession()
    record = publish_episode(db, ep["id"])

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["len"] = len(request.content)
        return httpx.Response(200, json={"ok": True})

    from pathlib import Path

    video = Path(record.artifact_dir if hasattr(record, "artifact_dir") else ".") / "final.mp4"
    from app.models.render import Render

    render = db.get(Render, record.render_id)
    thumb = extract_thumbnail(Path(render.artifact_dir) / "final.mp4",
                              Path(render.artifact_dir) / "thumb.jpg")
    assert thumb.is_file()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    set_video_thumbnail(db, record.id, thumbnail_path=thumb, http=http)
    assert seen.get("len", 0) > 0
    db.close()


def test_status_and_retry_endpoints(client, monkeypatch, ready_episode, channel_with_token):
    ep, _ = ready_episode
    db = TestingSession()
    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", _upload_fail()
    )
    with pytest.raises(UploadError):
        publish_episode(db, ep["id"])
    db.close()
    record_id = (
        TestingSession()
        .query(PublishedVideo)
        .filter_by(episode_id=ep["id"])
        .first()
        .id
    )

    # endpoint-level retry
    calls = {"n": 0}

    def flaky(video_path, title, description, channel_id, **kw):
        calls["n"] += 1
        return {"id": "vid_api_recovered"}

    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", flaky
    )
    res = client.post(f"/api/youtube/videos/{record_id}/retry")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "uploaded"
    assert body["attempts"] == 1

    listed = client.get("/api/youtube/videos").json()
    assert listed[0]["attempts"] == 1
    assert listed[0]["youtube_status"] == "uploaded"


def test_lifecycle_generate_publish_multiple(client, monkeypatch, channel_with_token):
    """Roadmap: upload multiple videos and recover from at least one failure."""
    import app.services.video_service as vs

    monkeypatch.setattr(
        vs, "synthesize_speech", lambda text, wav_path, **kw: _sine(wav_path, 5.0)
    )
    creator = client.post(
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()["id"]
    series = client.post(
        "/api/series", json={"creator_id": creator, "name": "Hanks World 73"}
    ).json()["id"]

    episodes = []
    for variant in (0, 1, 2):
        ep = client.post(
            f"/api/series/{series}/generate-episode", json={"variant": variant}
        ).json()["episode"]
        client.post(f"/api/episodes/{ep['id']}/approve", json={})
        client.post(f"/api/episodes/{ep['id']}/render", json={})
        episodes.append(ep)

    calls = {"n": 0}

    def flaky(video_path, title, description, channel_id, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise UploadError("transient upload failure")
        return {"id": f"vid_{calls['n']}"}

    monkeypatch.setattr(
        "app.services.youtube_upload_service.upload_private_video", flaky
    )

    db = TestingSession()
    records = []
    for ep in episodes:
        try:
            records.append(publish_episode(db, ep["id"]))
        except UploadError:
            records.append(
                db.query(PublishedVideo).filter_by(episode_id=ep["id"]).first()
            )

    assert [r.status for r in records] == ["uploaded", "failed", "uploaded"]

    recovered = retry_publish(db, records[1].id)
    assert recovered.status == "uploaded"
    assert recovered.video_id == "vid_4"
    assert recovered.attempts == 1
    db.close()
