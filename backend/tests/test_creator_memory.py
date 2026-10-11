"""Sprint 1.3 — creator memory: CRUD + generation retrieves stored facts."""
from fastapi.testclient import TestClient
import pytest
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


HANK = {
    "name": "Hank",
    "slug": "hank",
    "interests": ["farming", "trucks"],
    "humor_style": "dry, deadpan",
}


@pytest.fixture
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    c = TestClient(app)
    c.hank_id = c.post("/api/creators", json=HANK).json()["id"]  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_memory_types_available():
    assert sorted(t.value for t in __import__("app.models.creator_memory", fromlist=["MemoryType"]).MemoryType) == [
        "AUDIENCE_DISCOVERY",
        "CANON",
        "CONTENT_LESSON",
        "EVENT",
        "PREFERENCE",
        "RELATIONSHIP",
        "RUNNING_JOKE",
    ]


def test_create_and_list_memory(client):
    res = client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "CANON", "content": "Hank owns Old Red, a battered tractor."},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["type"] == "CANON"
    assert body["importance"] == 0.5

    listing = client.get(f"/api/creators/{client.hank_id}/memories")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["content"] == "Hank owns Old Red, a battered tractor."


def test_memories_sorted_by_importance(client):
    client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "EVENT", "content": "minor detail", "importance": 0.1},
    )
    client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "CANON", "content": "canon fact", "importance": 0.9},
    )
    contents = [m["content"] for m in client.get(f"/api/creators/{client.hank_id}/memories").json()]
    assert contents[:2] == ["canon fact", "minor detail"]


def test_type_filter(client):
    client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "CANON", "content": "canon fact"},
    )
    client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "RUNNING_JOKE", "content": "the bit"},
    )
    canon = client.get(f"/api/creators/{client.hank_id}/memories?type=canon").json()
    assert [m["content"] for m in canon] == ["canon fact"]


def test_invalid_type_400(client):
    res = client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "PROPAGANDA", "content": "nope"},
    )
    assert res.status_code == 400
    assert "CANON" in res.json()["detail"]


def test_empty_content_400(client):
    res = client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "CANON", "content": "   "},
    )
    assert res.status_code == 400


def test_out_of_range_importance_400(client):
    res = client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "CANON", "content": "x", "importance": 1.5},
    )
    assert res.status_code == 400


def test_unknown_creator_404(client):
    assert client.get("/api/creators/9999/memories").status_code == 404
    assert (
        client.post(
            "/api/creators/9999/memories", json={"type": "CANON", "content": "x"}
        ).status_code
        == 404
    )
    assert client.delete("/api/creators/9999/memories/1").status_code == 404


def test_delete_memory(client):
    memory_id = client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "CANON", "content": "canon fact"},
    ).json()["id"]
    assert client.delete(f"/api/creators/{client.hank_id}/memories/{memory_id}").status_code == 204
    assert client.get(f"/api/creators/{client.hank_id}/memories").json() == []


def test_delete_other_creators_memory_404(client):
    other_id = client.post(
        "/api/creators", json={"name": "Alex.exe", "slug": "alex-exe"}
    ).json()["id"]
    memory_id = client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "CANON", "content": "canon fact"},
    ).json()["id"]
    assert client.delete(f"/api/creators/{other_id}/memories/{memory_id}").status_code == 404


# Roadmap verification: generate → store a fact → generate again → second uses the fact.
def test_generation_uses_stored_fact_two_pass(client):
    first = client.post(
        f"/api/creators/{client.hank_id}/generate",
        json={"user_message": "Tell me about your tractor."},
    )
    assert first.status_code == 200
    assert first.json()["memories_used"] == []
    assert "Old Red" not in first.json()["text"]

    fact = "Hank's tractor Old Red only starts when Hank compliments the radio."
    client.post(
        f"/api/creators/{client.hank_id}/memories",
        json={"type": "CANON", "content": fact, "importance": 0.9},
    )

    second = client.post(
        f"/api/creators/{client.hank_id}/generate",
        json={"user_message": "Tell me about your tractor."},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["memories_used"] == [fact]
    assert "Old Red" in body["text"]
    assert body["prompt_version"] == "creator_prompt_v1"


def test_first_generation_has_no_memory_context(client):
    res = client.post(
        f"/api/creators/{client.hank_id}/generate",
        json={"user_message": "Hello."},
    )
    assert res.status_code == 200
    assert res.json()["memories_used"] == []
