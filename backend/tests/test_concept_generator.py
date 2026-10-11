"""Sprint 3.1 — candidate generator: 5-10 substantially different concepts."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.evaluation import evaluate_concepts
from app.ai.structured_output import ConceptItem, ParseError, parse_concepts
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


def _gen(c, topic="AI tractors", count=5):
    return c.post(
        f"/api/series/{c.series_id}/generate-concepts",
        json={"topic": topic, "count": count},
    )


# Roadmap verification: given the same topic, multiple substantially different concepts.
def test_generate_five_distinct_concepts(client):
    res = _gen(client, count=5)
    assert res.status_code == 200, res.text
    body = res.json()
    concepts = body["concepts"]
    assert len(concepts) == 5
    assert [c["index"] for c in concepts] == [1, 2, 3, 4, 5]

    premises = [c["premise"] for c in concepts]
    titles = [c["title"] for c in concepts]
    assert len(set(premises)) == 5
    assert len(set(titles)) == 5
    # different conflicts/angles per concept
    assert len({c["angle"] for c in concepts}) == 5
    assert len({c["hook"] for c in concepts}) == 5
    # topic carried into every concept
    assert all("AI tractors" in c["title"] for c in concepts)
    assert body["evaluation_status"] == "PASS"
    assert body["prompt_version"] == "concepts_prompt_v1"


def test_generate_ten_concepts(client):
    body = _gen(client, count=10).json()
    concepts = body["concepts"]
    assert len(concepts) == 10
    assert len({c["premise"] for c in concepts}) == 10
    assert body["evaluation_status"] == "PASS"


def test_same_topic_reproducible_and_deterministic(client):
    first = _gen(client).json()["concepts"]
    second = _gen(client).json()["concepts"]
    assert [c["premise"] for c in first] == [c["premise"] for c in second]


def test_concepts_persisted_as_set(client):
    created = _gen(client).json()
    set_id = created["set"]["id"]
    assert created["set"]["topic"] == "AI tractors"

    sets = client.get(f"/api/series/{client.series_id}/concept-sets").json()
    assert len(sets) == 1
    assert sets[0]["id"] == set_id

    stored = client.get(f"/api/concept-sets/{set_id}/concepts").json()
    assert [c["index"] for c in stored] == [1, 2, 3, 4, 5]
    assert stored[0]["title"] == created["concepts"][0]["title"]


def test_evaluation_flags_duplicates():
    item = ConceptItem(title="t", premise="same premise text here", hook="h")
    ev = evaluate_concepts([item, item.model_copy()], topic="x")
    assert ev.status == "BLOCK"
    assert any(i.code == "duplicate_concepts" for i in ev.issues)


def test_evaluation_flags_banned():
    item = ConceptItem(
        title="t", premise="we should buy views and impersonate a real person"
    )
    ev = evaluate_concepts([item], topic="x")
    assert ev.status == "BLOCK"
    assert any(i.code == "safety_violation" for i in ev.issues)


def test_parse_rejects_wrong_count():
    text = '```json\n[{"title":"a","premise":"b"}]\n```'
    with pytest.raises(ParseError):
        parse_concepts(text, minimum=3, maximum=10)


def test_topic_not_covered_review():
    items = [
        ConceptItem(title=f"concept {i}", premise=p)
        for i, p in enumerate(
            [
                "Hank rebuilds the barn door after the hailstorm.",
                "A weekend cookout contest with unexpected entrants.",
                "Winter storage habits examined at length.",
            ]
        )
    ]
    ev = evaluate_concepts(items, topic="quantum computing")
    assert ev.status == "REVIEW"
    assert any(i.code == "topic_not_covered" for i in ev.issues)


def test_invalid_count_400(client):
    assert client.post(
        f"/api/series/{client.series_id}/generate-concepts",
        json={"topic": "t", "count": 2},
    ).status_code == 400
    assert client.post(
        f"/api/series/{client.series_id}/generate-concepts",
        json={"topic": "t", "count": 11},
    ).status_code == 400


def test_empty_topic_400(client):
    assert client.post(
        f"/api/series/{client.series_id}/generate-concepts",
        json={"topic": "   ", "count": 5},
    ).status_code == 400


def test_unknown_series_404(client):
    assert client.post(
        "/api/series/9999/generate-concepts",
        json={"topic": "t", "count": 5},
    ).status_code == 404


def test_unknown_prompt_version_400(client):
    assert client.post(
        f"/api/series/{client.series_id}/generate-concepts",
        json={"topic": "t", "count": 5, "prompt_version": "concepts_prompt_v9"},
    ).status_code == 400
