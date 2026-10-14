"""Sprint 13.2 — cross-creator episodes: coherent multi-creator A-stories."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.cross_episode_service import (
    CrossEpisodeError,
    generate_cross_episode,
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


def _two_creators(client):
    hank = client.post(
        "/api/creators",
        json={"name": "Hank", "slug": "hank", "humor_style": "dry, deadpan"},
    ).json()
    alex = client.post(
        "/api/creators",
        json={"name": "Alex.exe", "slug": "alex-exe",
              "humor_style": "absurd corporate-techno-optimism"},
    ).json()
    return hank, alex


def _series(client, creator_id):
    return client.post(
        "/api/series", json={"creator_id": creator_id, "name": "Hank's World"}
    ).json()


# Roadmap verification: a coherent cross-character episode.
def test_generate_cross_episode_endpoint(client):
    hank, alex = _two_creators(client)
    series = _series(client, hank["id"])
    # relationship exists so the cast dynamics show up in the draft context
    client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": alex["id"]},
    )

    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": [hank["id"], alex["id"]]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    episode = body["episode"]
    assert episode["creator_id"] == hank["id"]
    assert episode["episode_number"] == 1
    assert episode["status"] == "IDEA"

    draft = body["draft"]
    assert set(p.lower() for p in draft["participants"]) == {"hank", "alex.exe"}
    assert len(draft["scenes"]) >= 3
    assert "Hank" in draft["script"] and "Alex.exe" in draft["script"]
    assert body["evaluation_status"] in ("PASS", "REVIEW")
    assert body["prompt_version"] == "cross_episode_prompt_v1"
    assert body["cast_used"] == ["Hank", "Alex.exe"]
    assert "Alex.exe" in draft["premise"]

    # episode persists with scenes, then renders like any other episode
    detail = client.get(f"/api/episodes/{episode['id']}").json()
    assert detail["premise"] == draft["premise"]
    scenes = client.get(f"/api/episodes/{episode['id']}/scenes").json()
    assert [s["scene_number"] for s in scenes] == [1, 2, 3, 4]


def test_cross_episode_uses_both_voices(client):
    hank, alex = _two_creators(client)
    series = _series(client, hank["id"])
    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": [hank["id"], alex["id"]]},
    ).json()
    script = res["draft"]["script"]
    # A coherent A-story: problem -> negotiation -> breakdown -> finish
    for beat in ("The problem", "The negotiation", "The breakdown", "The finish"):
        assert beat in script or any(beat in s["title"] for s in res["draft"]["scenes"])


def test_duplicate_participants_collapse(client):
    hank, alex = _two_creators(client)
    series = _series(client, hank["id"])
    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": [hank["id"], alex["id"], hank["id"]]},
    )
    assert res.status_code == 200
    assert res.json()["cast_used"] == ["Hank", "Alex.exe"]


def test_single_participant_400(client):
    hank, _ = _two_creators(client)
    series = _series(client, hank["id"])
    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": [hank["id"]]},
    )
    assert res.status_code == 400


def test_host_creator_required(client):
    hank, alex = _two_creators(client)
    series = _series(client, hank["id"])
    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": [alex["id"], 9999]},
    )
    assert res.status_code == 400


def test_unknown_participant_404(client):
    hank, alex = _two_creators(client)
    series = _series(client, hank["id"])
    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": [hank["id"], alex["id"], 9999]},
    )
    assert res.status_code == 400


def test_ended_series_400(client):
    hank, alex = _two_creators(client)
    series = _series(client, hank["id"])
    client.delete(f"/api/series/{series['id']}")
    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": [hank["id"], alex["id"]]},
    )
    assert res.status_code == 400


def test_service_rejects_empty_cast():
    """A single participant is rejected before any DB access."""
    with pytest.raises(CrossEpisodeError, match="at least two"):
        generate_cross_episode(None, 1, [1])
def test_three_participants_coherent(client):
    ids = []
    for name, slug in (("Hank", "hank"), ("Alex.exe", "alex-exe"), ("Crash", "crash")):
        ids.append(
            client.post("/api/creators", json={"name": name, "slug": slug}).json()["id"]
        )
    series = _series(client, ids[0])
    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": ids},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["cast_used"] == ["Hank", "Alex.exe", "Crash"]
    for name in ("Hank", "Alex.exe", "Crash"):
        assert name in body["draft"]["script"]


def test_evaluation_flags_silent_participant(client):
    """Evaluation, not the generator, is what rejects a draft that drops a voice."""
    from app.ai.structured_output import CrossEpisodeDraft

    from app.services.cross_episode_service import evaluate_cross_draft

    hank, alex = _two_creators(client)
    db = TestingSession()
    from app.models import Creator

    cast = [db.get(Creator, hank["id"]), db.get(Creator, alex["id"])]
    db.close()

    draft = CrossEpisodeDraft(
        participants=["Hank"],
        premise="Hank fixes the fence alone.",
        synopsis="Solo episode.",
        scenes=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
        script="Hank: all mine.",
    )
    ev = evaluate_cross_draft(draft, cast, canon=[])
    codes = {i.code for i in ev.issues}
    assert "missing_participant" in codes
    assert "silent_participant" in codes


def test_evaluation_blocks_unknown_participant(client):
    from app.ai.structured_output import CrossEpisodeDraft

    from app.services.cross_episode_service import evaluate_cross_draft

    hank, alex = _two_creators(client)
    db = TestingSession()
    from app.models import Creator

    cast = [db.get(Creator, hank["id"]), db.get(Creator, alex["id"])]
    db.close()

    draft = CrossEpisodeDraft(
        participants=["Hank", "Alex.exe", "Injected Person"],
        premise="Hank and Alex.exe meet an unbidden guest.",
        synopsis="Crossover with a stranger.",
        scenes=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
        script="Hank: who are you? Alex.exe: unknown node.",
    )
    ev = evaluate_cross_draft(draft, cast, canon=[])
    assert ev.status == "BLOCK"
    assert any(i.code == "unknown_participant" for i in ev.issues)