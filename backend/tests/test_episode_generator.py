"""Sprint 2.2 — episode generator: canon-aware, evaluated, persisted.

Roadmap verification: generate five episodes and confirm they do not
contradict established facts.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.evaluation import Severity, evaluate_draft
from app.ai.structured_output import EpisodeDraft, ParseError, parse_episode_draft
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


CANON = [
    "Hank owns Old Red, a battered but reliable tractor.",
    "Hank hates unnecessary subscriptions.",
]


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
    for statement in CANON:
        c.post(
            f"/api/series/{c.series_id}/canon",
            json={"category": "OBJECT", "statement": statement},
        )
    c.post(
        f"/api/creators/{c.creator_id}/memories",
        json={"type": "CANON", "content": CANON[0], "importance": 0.9},
    )
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _generate(c, variant: int):
    return c.post(
        f"/api/series/{c.series_id}/generate-episode", json={"variant": variant}
    )


def test_parse_episode_draft_fenced_json():
    text = '```json\n{"premise":"p","synopsis":"s","scenes":[{"title":"a"},{"title":"b"},{"title":"c"}],"script":"x"}\n```'
    draft = parse_episode_draft(text)
    assert len(draft.scenes) == 3


def test_parse_episode_draft_rejects_garbage():
    with pytest.raises(ParseError):
        parse_episode_draft("nope, not json at all")


def test_parse_episode_draft_rejects_too_few_scenes():
    text = '{"premise":"p","synopsis":"s","scenes":[{"title":"a"}],"script":"x"}'
    with pytest.raises(ParseError):
        parse_episode_draft(text)


def test_evaluate_blocks_safety_violations():
    draft = EpisodeDraft(
        premise="Hank builds a deepfake to impersonate a real person",
        synopsis="bad",
        scenes=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
        script="buy views and subscribers",
    )
    ev = evaluate_draft(draft, canon=CANON)
    assert ev.status == "BLOCK"
    assert any(i.code == "safety_violation" for i in ev.issues)


def test_evaluate_flags_canon_contradiction():
    draft = EpisodeDraft(
        premise="Hank sold his Old Red tractor and gave up farming entirely.",
        synopsis="A new life without the farm.",
        scenes=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
        script="Hank does not own Old Red anymore.",
    )
    ev = evaluate_draft(draft, canon=CANON)
    assert any(i.code == "canon_contradiction" for i in ev.issues)
    assert ev.status in ("REVIEW", "BLOCK")


def test_evaluate_flags_repetition():
    draft = EpisodeDraft(
        premise="Hank's oldest machine breaks down the morning of an important delivery.",
        synopsis="rehash",
        scenes=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
        script="same stuff again",
    )
    ev = evaluate_draft(
        draft,
        canon=CANON,
        previous_premises=[
            "Hank's oldest machine breaks down the morning of an important delivery."
        ],
    )
    assert any(i.code == "repetition" for i in ev.issues)


def test_evaluate_flags_canon_not_referenced():
    draft = EpisodeDraft(
        premise="Hank builds a weather station from scrap odds and ends.",
        synopsis="No relation to anything established.",
        scenes=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
        script="A standalone story about screws and solder.",
    )
    ev = evaluate_draft(draft, canon=CANON)
    assert any(i.code == "canon_not_referenced" for i in ev.issues)


# Roadmap verification proper: five episodes, no contradictions with established facts.
def test_generate_five_episodes_distinct_and_consistent(client):
    responses = []
    for variant in range(5):
        res = _generate(client, variant)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["evaluation_status"] in ("PASS", "REVIEW")
        assert not any(
            i["code"] == "canon_contradiction" for i in body["issues"]
        ), f"variant {variant} contradicts canon"
        assert not any(i["code"] == "safety_violation" for i in body["issues"])
        assert not any(i["code"] == "repetition" for i in body["issues"])
        assert body["episode"]["status"] == "IDEA"
        responses.append(body["draft"])

    premises = [d["premise"] for d in responses]
    assert len(set(premises)) == 5, "five episodes must be meaningfully different"
    assert all(len(d["scenes"]) >= 3 for d in responses)
    assert CANON[0].split(",")[0] in " ".join(d["script"] for d in responses)


def test_generation_persists_episode_and_scenes(client):
    res = _generate(client, 0)
    episode_id = res.json()["episode"]["id"]

    history = client.get(f"/api/series/{client.series_id}/episodes").json()
    assert [e["episode_number"] for e in history] == [1]
    assert history[0]["script"]
    assert history[0]["status"] == "IDEA"

    scenes = client.get(f"/api/episodes/{episode_id}/scenes").json()
    assert [s["scene_number"] for s in scenes] == [1, 2, 3]

    # next generation continues numbering and sees the previous episode
    second = _generate(client, 1)
    assert second.status_code == 200
    assert second.json()["episode"]["episode_number"] == 2


def test_generation_records_prompt_and_model(client):
    body = _generate(client, 2).json()
    assert body["prompt_version"] == "episode_prompt_v2"
    assert body["model"] == "stub/deterministic-v1"
    assert body["canon_used"] == CANON


def test_generation_unknown_prompt_version_400(client):
    res = client.post(
        f"/api/series/{client.series_id}/generate-episode",
        json={"prompt_version": "episode_prompt_v9"},
    )
    assert res.status_code == 400


def test_generation_unknown_series_404(client):
    res = client.post("/api/series/9999/generate-episode", json={"variant": 0})
    assert res.status_code == 404


def test_generation_ended_series_400(client):
    client.delete(f"/api/series/{client.series_id}")
    assert _generate(client, 0).status_code == 400
