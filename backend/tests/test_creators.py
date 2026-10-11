"""Sprint 1.1 — creator CRUD: create, edit, view, deactivate (Hank + Alex.exe)."""
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


HANK = {
    "name": "Hank",
    "slug": "hank",
    "description": "Rural, practical fictional creator.",
    "personality": "Dry humor, practical, skeptical of unnecessary technology.",
    "interests": ["farming", "trucks", "outdoors"],
    "humor_style": "dry, deadpan",
}

ALEX = {
    "name": "Alex.exe",
    "slug": "alex-exe",
    "description": "Corporate-AI fictional creator.",
    "personality": "Startup vocabulary, automation enthusiast, occasionally absurd.",
    "interests": ["AI", "startups", "automation"],
    "humor_style": "absurd corporate-techno-optimism",
}


@pytest.fixture
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_create_hank_and_alex(client):
    hank = client.post("/api/creators", json=HANK)
    assert hank.status_code == 201, hank.text
    assert hank.json()["slug"] == "hank"
    assert hank.json()["active"] is True

    alex = client.post("/api/creators", json=ALEX)
    assert alex.status_code == 201, alex.text
    assert alex.json()["slug"] == "alex-exe"


def test_duplicate_slug_returns_409(client):
    assert client.post("/api/creators", json=HANK).status_code == 201
    dup = client.post("/api/creators", json=HANK)
    assert dup.status_code == 409


def test_invalid_slug_returns_400(client):
    bad = dict(HANK, slug="Hank!!")
    assert client.post("/api/creators", json=bad).status_code == 400


def test_list_and_get(client):
    hank_id = client.post("/api/creators", json=HANK).json()["id"]
    alex_id = client.post("/api/creators", json=ALEX).json()["id"]

    listing = client.get("/api/creators")
    assert listing.status_code == 200
    assert {c["slug"] for c in listing.json()} == {"hank", "alex-exe"}

    hank = client.get(f"/api/creators/{hank_id}")
    assert hank.status_code == 200
    assert hank.json()["name"] == "Hank"
    assert hank.json()["interests"] == ["farming", "trucks", "outdoors"]

    alex = client.get(f"/api/creators/{alex_id}")
    assert alex.json()["humor_style"] == "absurd corporate-techno-optimism"

    assert client.get("/api/creators/9999").status_code == 404


def test_edit_creator(client):
    hank_id = client.post("/api/creators", json=HANK).json()["id"]
    res = client.patch(
        f"/api/creators/{hank_id}",
        json={"humor_style": "deadpan", "interests": ["farming", "weather"]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["humor_style"] == "deadpan"
    assert body["interests"] == ["farming", "weather"]
    assert body["name"] == "Hank"  # untouched fields intact


def test_update_slug_conflict_returns_409(client):
    client.post("/api/creators", json=HANK)
    alex_id = client.post("/api/creators", json=ALEX).json()["id"]
    res = client.patch(f"/api/creators/{alex_id}", json={"slug": "hank"})
    assert res.status_code == 409


def test_deactivate_and_reactivate(client):
    hank_id = client.post("/api/creators", json=HANK).json()["id"]
    client.post("/api/creators", json=ALEX)

    deactivated = client.delete(f"/api/creators/{hank_id}")
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    # Record stays viewable after deactivation
    assert client.get(f"/api/creators/{hank_id}").json()["active"] is False

    # Default listing hides inactive; opt-out shows them
    assert {c["slug"] for c in client.get("/api/creators").json()} == {"alex-exe"}
    assert {c["slug"] for c in client.get("/api/creators?active_only=false").json()} == {
        "hank",
        "alex-exe",
    }

    # Reactivate via PATCH
    reactivated = client.patch(f"/api/creators/{hank_id}", json={"active": True})
    assert reactivated.json()["active"] is True
    assert {c["slug"] for c in client.get("/api/creators").json()} == {"hank", "alex-exe"}

    assert client.delete("/api/creators/9999").status_code == 404
