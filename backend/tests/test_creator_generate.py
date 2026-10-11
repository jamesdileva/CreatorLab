"""Sprint 1.2 — POST /api/creators/{id}/generate (provider abstraction, prompt versioning)."""
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
    "interests": ["farming", "trucks"],
    "humor_style": "dry, deadpan",
    "voice_style": "plain-spoken",
}
ALEX = {
    "name": "Alex.exe",
    "slug": "alex-exe",
    "interests": ["AI", "automation"],
    "humor_style": "absurd corporate-techno-optimism",
    "voice_style": "rapid, buzzword-dense",
}


@pytest.fixture
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    c = TestClient(app)
    hank = c.post("/api/creators", json=HANK).json()
    alex = c.post("/api/creators", json=ALEX).json()
    c.hank_id = hank["id"]  # type: ignore[attr-defined]
    c.alex_id = alex["id"]  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_generate_uses_versioned_prompt(client):
    res = client.post(
        f"/api/creators/{client.hank_id}/generate",
        json={"user_message": "What do you think about automated tractors?"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["prompt_version"] == "creator_prompt_v1"
    assert body["provider"] == "stub"
    assert body["model"] == "stub/deterministic-v1"
    assert body["text"]


def test_hank_and_alex_voices_differ(client):
    text = "What do you think about automated tractors?"
    hank = client.post(f"/api/creators/{client.hank_id}/generate", json={"user_message": text}).json()
    alex = client.post(f"/api/creators/{client.alex_id}/generate", json={"user_message": text}).json()
    assert hank["text"] != alex["text"]
    assert "Hank" in hank["text"] and "dry, deadpan" in hank["text"]
    assert "Alex.exe" in alex["text"] and "rapid, buzzword-dense" in alex["text"]


def test_generate_unknown_creator_404(client):
    res = client.post("/api/creators/9999/generate", json={"user_message": "hello"})
    assert res.status_code == 404


def test_generate_empty_message_400(client):
    res = client.post(f"/api/creators/{client.hank_id}/generate", json={"user_message": "   "})
    assert res.status_code == 400


def test_generate_unknown_prompt_version_400(client):
    res = client.post(
        f"/api/creators/{client.hank_id}/generate",
        json={"user_message": "hello", "prompt_version": "creator_prompt_v9"},
    )
    assert res.status_code == 400
    assert "creator_prompt_v9" in res.json()["detail"]


def test_prompt_versions_endpoint(client):
    res = client.get("/api/creators/prompts/versions")
    assert res.status_code == 200
    assert "creator_prompt_v1" in res.json()
