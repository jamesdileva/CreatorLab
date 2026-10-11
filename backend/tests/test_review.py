"""Sprint 6.1 — human review queue: risks, payload, approve/reject/edit."""
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app

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
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _episode(c, variant=0):
    return c.post(
        f"/api/series/{c.series_id}/generate-episode", json={"variant": variant}
    ).json()["episode"]


def test_queue_lists_pending_episodes(client):
    ep = _episode(client)
    queue = client.get("/api/review-queue").json()
    assert [q["id"] for q in queue] == [ep["id"]]
    assert queue[0]["status"] == "IDEA"

    # approved episodes leave the queue
    client.post(f"/api/episodes/{ep['id']}/approve", json={})
    assert client.get("/api/review-queue").json() == []


def test_review_payload_has_script_scenes_metadata(client):
    ep = _episode(client)
    body = client.get(f"/api/review-queue/{ep['id']}").json()

    assert body["episode"]["script"]
    assert body["episode"]["premise"]
    assert body["creator"]["name"] == "Hank"
    assert body["series"]["name"] == "Hank's World"
    assert len(body["scenes"]) == 3
    assert body["metadata"]["scene_count"] == 3
    assert body["metadata"]["word_count"] > 0
    assert body["metadata"]["status"] == "IDEA"
    assert body["simulation"] is None
    assert body["latest_render"] is None


def test_review_payload_includes_simulation(client):
    ep = _episode(client)
    client.post("/api/simulations/run", json={"target_type": "episode", "target_id": ep["id"]})
    body = client.get(f"/api/review-queue/{ep['id']}").json()
    assert body["simulation"] is not None
    assert body["simulation"]["aggregate"]["viewer_count"] == 25
    assert "watch_probability" in body["simulation"]["aggregate"]["means"]


def test_risks_include_synthetic_disclosure(client):
    ep = _episode(client)
    body = client.get(f"/api/review-queue/{ep['id']}").json()
    codes = {r["code"] for r in body["risks"]}
    assert "synthetic_media_disclosure" in codes
    assert body["risk_status"] == "REVIEW"


def test_real_person_reference_blocks(client):
    ep = _episode(client)
    client.patch(
        f"/api/episodes/{ep['id']}",
        json={"script": "Guest appearance by Elon Musk on the farm."},
    )
    body = client.get(f"/api/review-queue/{ep['id']}").json()
    codes = {r["code"] for r in body["risks"]}
    assert "real_person_reference" in codes
    assert body["risk_status"] == "BLOCK"


def test_copyright_dependency_blocks(client):
    ep = _episode(client)
    client.patch(
        f"/api/episodes/{ep['id']}",
        json={"premise": "Hank watches the new Marvel movie on the tractor screen."},
    )
    body = client.get(f"/api/review-queue/{ep['id']}").json()
    assert {r["code"] for r in body["risks"]} >= {"copyright_dependency"}
    assert body["risk_status"] == "BLOCK"


def test_repetition_review_for_duplicate_premise(client):
    first = _episode(client, 0)
    second = _episode(client, 0)  # same archetype premise
    client.patch(
        f"/api/episodes/{second['id']}",
        json={"premise": first["premise"]},
    )
    body = client.get(f"/api/review-queue/{second['id']}").json()
    assert "repetition" in {r["code"] for r in body["risks"]}


# Roadmap verification: approve, reject, and edit from the queue.
def test_approve_reject_edit_from_queue(client):
    ep = _episode(client)

    # edit
    edited = client.patch(
        f"/api/episodes/{ep['id']}",
        json={"script": "Hank: Old Red, we need to talk.\nNARRATION: It's about the subscription."},
    )
    assert edited.status_code == 200
    assert "subscription" in edited.json()["script"]
    assert "subscription" in client.get(f"/api/review-queue/{ep['id']}").json()["episode"]["script"]

    # reject -> back to REVIEW, stays in queue
    assert client.post(f"/api/episodes/{ep['id']}/reject", json={}).json()["status"] == "REVIEW"
    assert client.get(f"/api/episodes/{ep['id']}").json()["status"] == "REVIEW"
    assert [q["id"] for q in client.get("/api/review-queue").json()] == [ep["id"]]

    # approve -> leaves queue
    assert client.post(f"/api/episodes/{ep['id']}/approve", json={}).json()["status"] == "APPROVED"
    assert client.get("/api/review-queue").json() == []
    assert client.get(f"/api/episodes/{ep['id']}").json()["status"] == "APPROVED"


def test_review_payload_unknown_episode_404(client):
    assert client.get("/api/review-queue/9999").status_code == 404


def test_review_payload_includes_render(client, tmp_path, monkeypatch):
    import subprocess

    from app.services import video_service

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        video_service,
        "synthesize_speech",
        lambda text, wav_path, **kw: _sine(wav_path),
    )
    ep = _episode(client)
    client.post(f"/api/episodes/{ep['id']}/approve", json={})
    render = client.post(f"/api/episodes/{ep['id']}/render", json={})
    assert render.status_code == 200, render.text
    render_id = render.json()["render_id"]

    body = client.get(f"/api/review-queue/{ep['id']}").json()
    assert body["latest_render"] is not None
    assert body["latest_render"]["render_id"] == render_id
    assert body["latest_render"]["video_url"] == f"/media/generated/episode_{ep['id']}/render_{render_id}/final.mp4"
    # rendered episodes leave the pending queue (they are READY)
    assert client.get("/api/review-queue").json() == []


def _sine(path, seconds=5.0):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-ar", "44100", "-ac", "1", str(path)],
        capture_output=True, check=True,
    )
    return path
