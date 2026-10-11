"""Sprint 5.3 — end-to-end episode pipeline: approval gate + recorded artifacts."""
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services import video_service

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
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _sine(path, seconds=5.0):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-ar", "44100", "-ac", "1", str(path)],
        capture_output=True, check=True,
    )
    return path


@pytest.fixture
def episode(client, monkeypatch):
    monkeypatch.setattr(
        video_service,
        "synthesize_speech",
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
    return ep


# Roadmap verification: generate an entire Short from a single approved episode.
def test_full_pipeline_from_approved_episode(client, episode):
    assert episode["status"] == "IDEA"

    approval = client.post(f"/api/episodes/{episode['id']}/approve", json={})
    assert approval.status_code == 200
    assert approval.json()["status"] == "APPROVED"

    render = client.post(f"/api/episodes/{episode['id']}/render", json={})
    assert render.status_code == 200, render.text
    body = render.json()
    assert body["status"] == "READY"
    assert body["video_url"].endswith("final.mp4")
    assert body["scene_count"] == 3
    assert 15.0 <= body["total_duration"] <= 45.0

    detail = client.get(f"/api/episodes/{episode['id']}").json()
    assert detail["status"] == "READY"


def test_render_requires_approval(client, episode):
    """Nothing renders before the human approves (§5.6)."""
    res = client.post(f"/api/episodes/{episode['id']}/render", json={})
    assert res.status_code == 422
    assert "approved" in res.json()["detail"]

    assert client.get(f"/api/episodes/{episode['id']}/renders").json() == []
    assert client.get(f"/api/episodes/{episode['id']}").json()["status"] == "IDEA"


def test_approve_then_reject(client, episode):
    assert client.post(f"/api/episodes/{episode['id']}/approve", json={}).json()["status"] == "APPROVED"
    assert client.post(f"/api/episodes/{episode['id']}/reject", json={}).json()["status"] == "REVIEW"
    # rejected episodes cannot render again until re-approved
    assert client.post(f"/api/episodes/{episode['id']}/render", json={}).status_code == 422


def test_cannot_approve_published(client, episode):
    client.patch(f"/api/episodes/{episode['id']}", json={"status": "PUBLISHED"})
    assert client.post(f"/api/episodes/{episode['id']}/approve", json={}).status_code == 400
    assert client.post(f"/api/episodes/{episode['id']}/reject", json={}).status_code == 400


def test_render_records_artifacts(client, episode):
    client.post(f"/api/episodes/{episode['id']}/approve", json={})
    render = client.post(f"/api/episodes/{episode['id']}/render", json={}).json()

    detail = client.get(f"/api/renders/{render['render_id']}").json()
    assert detail["render"]["status"] == "READY"
    kinds = {a["kind"] for a in detail["assets"]}
    assert kinds == {"card", "voice", "captions", "video", "manifest"}
    # 3 cards + 3 voices
    assert len([a for a in detail["assets"] if a["kind"] == "card"]) == 3
    assert len([a for a in detail["assets"] if a["kind"] == "voice"]) == 3
    video_asset = [a for a in detail["assets"] if a["kind"] == "video"][0]
    assert video_asset["duration"] == render["total_duration"]
    assert detail["render"]["card_version"] in ("card-v1", "identity-v1")


def test_renders_listed_and_404s(client, episode):
    client.post(f"/api/episodes/{episode['id']}/approve", json={})
    client.post(f"/api/episodes/{episode['id']}/render", json={})
    renders = client.get(f"/api/episodes/{episode['id']}/renders").json()
    assert len(renders) == 1
    assert renders[0]["status"] == "READY"

    assert client.get("/api/renders/9999").status_code == 404
    assert client.get("/api/episodes/9999/renders").status_code == 404


def test_failed_render_is_recorded(client, episode, monkeypatch):
    monkeypatch.setattr(
        video_service,
        "synthesize_speech",
        lambda text, wav_path, **kw: (_ for _ in ()).throw(
            video_service.VideoError("TTS exploded")
        ),
    )
    client.post(f"/api/episodes/{episode['id']}/approve", json={})
    res = client.post(f"/api/episodes/{episode['id']}/render", json={})
    assert res.status_code in (502, 422)

    renders = client.get(f"/api/episodes/{episode['id']}/renders").json()
    assert len(renders) == 1
    assert renders[0]["status"] == "FAILED"
    assert "TTS exploded" in renders[0]["error"]

    detail = client.get(f"/api/episodes/{episode['id']}").json()
    assert detail["status"] == "REVIEW"
