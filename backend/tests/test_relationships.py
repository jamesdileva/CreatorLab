"""Sprint 13.1 — relationship graph: social continuity via story events."""
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
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _two(client):
    hank = client.post("/api/creators", json={"name": "Hank", "slug": "hank"}).json()
    alex = client.post(
        "/api/creators", json={"name": "Alex.exe", "slug": "alex-exe"}
    ).json()
    return hank, alex


def test_create_relationship_pair(client):
    hank, alex = _two(client)
    res = client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": alex["id"]},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["creator_a_id"] == min(hank["id"], alex["id"])
    assert body["creator_b_id"] == max(hank["id"], alex["id"])
    assert body["friendship"] == 0.0

    # reversed order returns the same pair (idempotent)
    again = client.post(
        "/api/creators/relationships",
        json={"creator_a_id": alex["id"], "creator_b_id": hank["id"]},
    )
    assert again.status_code == 201
    assert again.json()["id"] == body["id"]


def test_self_relationship_400_and_unknown_creator_404(client):
    hank, _ = _two(client)
    assert client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": hank["id"]},
    ).status_code == 400
    assert client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": 9999},
    ).status_code == 404


def test_list_per_creator(client):
    hank, alex = _two(client)
    rel = client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": alex["id"]},
    ).json()
    for cid in (hank["id"], alex["id"]):
        listing = client.get(f"/api/creators/{cid}/relationships").json()
        assert [r["id"] for r in listing] == [rel["id"]]
    assert client.get("/api/creators/9999/relationships").status_code != 200


# Roadmap verification: creator relationship changes after story events.
def test_story_event_changes_relationship(client):
    hank, alex = _two(client)
    rel = client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": alex["id"]},
    ).json()

    before = {k: rel[k] for k in
              ("friendship", "rivalry", "respect", "annoyance", "collaboration")}
    _ = before  # replaced below once a rivalry exists

    # give them a rivalry first (delta floors at 0 otherwise)
    client.post(
        f"/api/creators/relationships/{rel['id']}/events",
        json={"event_type": "rivalry_match", "note": "County fair showdown."},
    )
    rivalrous = client.get(
        f"/api/creators/{hank['id']}/relationships"
    ).json()[0]
    assert rivalrous["rivalry"] > 0.0
    before = {k: rivalrous[k] for k in
              ("friendship", "rivalry", "respect", "annoyance", "collaboration")}

    res = client.post(
        f"/api/creators/relationships/{rel['id']}/events",
        json={"event_type": "collaboration_success",
              "note": "Fixed Old Red together."},
    )
    assert res.status_code == 201, res.text
    after = res.json()["relationship"]
    assert after["friendship"] > before["friendship"]
    assert after["collaboration"] > before["collaboration"]
    assert after["rivalry"] < before["rivalry"]

    event = res.json()["event"]
    assert event["event_type"] == "collaboration_success"
    assert event["note"] == "Fixed Old Red together."

    # history accumulates across events
    client.post(
        f"/api/creators/relationships/{rel['id']}/events",
        json={"event_type": "prank", "note": "Crash rigged the barn door."},
    )
    history = client.get(
        f"/api/creators/relationships/{rel['id']}/events"
    ).json()
    assert [e["event_type"] for e in history] == [
        "rivalry_match", "collaboration_success", "prank",
    ]
    final = client.get(f"/api/creators/{hank['id']}/relationships").json()[0]
    assert final["annoyance"] > after["annoyance"]
    assert final["friendship"] < after["friendship"]


def test_dimensions_clamp_at_bounds(client):
    hank, alex = _two(client)
    rel = client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": alex["id"]},
    ).json()
    for _ in range(10):
        rel = client.post(
            f"/api/creators/relationships/{rel['id']}/events",
            json={"event_type": "rivalry_match"},
        ).json()["relationship"]
    assert rel["rivalry"] == 1.0
    for _ in range(10):
        rel = client.post(
            f"/api/creators/relationships/{rel['id']}/events",
            json={"event_type": "reconciliation"},
        ).json()["relationship"]
    assert rel["annoyance"] == 0.0
    assert rel["friendship"] <= 1.0


def test_unknown_event_type_400_and_missing_relationship_404(client):
    hank, alex = _two(client)
    rel = client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": alex["id"]},
    ).json()
    assert client.post(
        f"/api/creators/relationships/{rel['id']}/events",
        json={"event_type": "alien_invasion"},
    ).status_code == 400
    assert client.post(
        "/api/creators/relationships/9999/events",
        json={"event_type": "prank"},
    ).status_code == 404
    assert client.get("/api/creators/relationships/9999/events").status_code == 404
    assert client.patch(
        "/api/creators/relationships/9999", json={"note": "x"}
    ).status_code == 404


def test_note_update(client):
    hank, alex = _two(client)
    rel = client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": alex["id"]},
    ).json()
    updated = client.patch(
        f"/api/creators/relationships/{rel['id']}",
        json={"note": "Frenemies since the AI tractor incident."},
    ).json()
    assert updated["note"] == "Frenemies since the AI tractor incident."
