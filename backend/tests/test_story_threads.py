"""Sprint 2.3 — running jokes and story threads across generations.

Roadmap verification: create a thread in Episode 1, resolve it naturally in Episode 4.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.evaluation import evaluate_draft
from app.ai.structured_output import EpisodeDraft, parse_episode_draft
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


THREAD_TITLE = "Hank promised never to buy an AI tractor."


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


def _generate(c, variant):
    return c.post(f"/api/series/{c.series_id}/generate-episode", json={"variant": variant})


def _threads(c):
    return c.get(f"/api/series/{c.series_id}/threads").json()


def _open_threads(c):
    return c.get(f"/api/series/{c.series_id}/threads?status=OPEN").json()


def test_thread_introduced_stays_open_then_resolves_naturally(client):
    # Episode 1
    ep1 = _generate(client, 0).json()["episode"]
    thread = client.post(
        f"/api/series/{client.series_id}/threads",
        json={"title": THREAD_TITLE, "introduced_episode_id": ep1["id"]},
    ).json()
    assert thread["status"] == "OPEN"
    assert thread["introduced_episode_id"] == ep1["id"]
    assert len(_open_threads(client)) == 1

    # Episodes 2 and 3 advance the story but leave the thread open (archetypes 1-2)
    for variant in (1, 2):
        res = _generate(client, variant).json()
        assert res["resolved_threads"] == []
        assert len(_open_threads(client)) == 1

    # Episode 4 (callback archetype) resolves it naturally
    ep4 = _generate(client, 5).json()
    assert ep4["resolved_threads"] == [THREAD_TITLE]

    resolved = _threads(client)[0]
    assert resolved["status"] == "RESOLVED"
    assert resolved["resolved_episode_id"] == ep4["episode"]["id"]
    assert resolved["introduced_episode_id"] == ep1["id"]
    assert _open_threads(client) == []
    assert THREAD_TITLE in ep4["draft"]["script"]


def test_generation_without_open_threads_resolves_nothing(client):
    _generate(client, 0)
    res = _generate(client, 5).json()
    assert res["resolved_threads"] == []


def test_evaluation_flags_hallucinated_thread_resolution():
    draft = EpisodeDraft(
        premise="Hank relents about the bet nobody remembers.",
        synopsis="A strange ending.",
        scenes=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
        script="some script",
    )
    draft.resolves_thread = "a thread that does not exist"
    ev = evaluate_draft(draft, open_threads=[THREAD_TITLE])
    assert any(i.code == "thread_not_found" for i in ev.issues)
    assert ev.status in ("REVIEW", "BLOCK")


def test_evaluation_accepts_real_thread_resolution():
    text = (
        '{"premise":"Hank answers the promise he made long ago.","synopsis":"s",'
        '"scenes":[{"title":"a"},{"title":"b"},{"title":"c"}],'
        '"script":"x","resolves_thread":"%s"}' % THREAD_TITLE
    )
    draft = parse_episode_draft(text)
    assert draft.resolves_thread == THREAD_TITLE
    ev = evaluate_draft(draft, open_threads=[THREAD_TITLE])
    assert not any(i.code == "thread_not_found" for i in ev.issues)


def test_multiple_threads_resolve_only_claimed_one(client):
    ep1 = _generate(client, 0).json()["episode"]
    t1 = client.post(
        f"/api/series/{client.series_id}/threads",
        json={"title": THREAD_TITLE, "introduced_episode_id": ep1["id"]},
    ).json()
    t2 = client.post(
        f"/api/series/{client.series_id}/threads",
        json={"title": "Alex.exe owes Hank a spreadsheet review."},
    ).json()

    _generate(client, 5)
    by_id = {t["id"]: t for t in _threads(client)}
    assert by_id[t1["id"]]["status"] == "RESOLVED"
    assert by_id[t2["id"]]["status"] == "OPEN"
