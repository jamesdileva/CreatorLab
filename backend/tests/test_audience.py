"""Sprint 4.1 — synthetic audience: 25 heterogeneous viewers, differing reactions."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.audience_service import baseline_interest, build_viewer

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


def test_seed_25_viewers(client):
    res = client.post("/api/audience/seed", json={"count": 25})
    assert res.status_code == 201, res.text
    viewers = res.json()
    assert len(viewers) == 25
    assert all(v["audience_version"] == "audience-v1" for v in viewers)
    assert [v["seed_index"] for v in viewers] == list(range(25))


def test_seed_idempotent_and_deterministic(client):
    first = client.post("/api/audience/seed", json={"count": 25}).json()
    second = client.post("/api/audience/seed", json={"count": 25}).json()
    assert [v["handle"] for v in first] == [v["handle"] for v in second]
    assert len(second) == 25  # no duplicate population


def test_population_heterogeneous(client):
    viewers = client.post("/api/audience/seed", json={"count": 25}).json()
    assert len({tuple(v["interests"]) for v in viewers}) >= 10
    assert len({v["personality"] for v in viewers}) >= 3
    assert len({v["response_style"] for v in viewers}) >= 3
    assert len({tuple(v["humor_preferences"]) for v in viewers}) >= 3


def test_get_viewer_and_404(client):
    vid = client.post("/api/audience/seed", json={"count": 1}).json()[0]["id"]
    assert client.get(f"/api/audience/{vid}").status_code == 200
    assert client.get("/api/audience/9999").status_code == 404


def test_invalid_count_400(client):
    assert client.post("/api/audience/seed", json={"count": 0}).status_code == 400
    assert client.post("/api/audience/seed", json={"count": 10001}).status_code == 400


# Roadmap verification: two viewers given identical content produce different reactions.
def test_two_viewers_differ_on_identical_content(client):
    client.post("/api/audience/seed", json={"count": 25})
    viewers = client.get("/api/audience").json()
    text = "Hank's Old Red tractor breaks down the morning of an important delivery."
    tags = ["farming", "comedy"]

    interests = [
        client.post(
            f"/api/audience/{v['id']}/preview", json={"text": text, "tags": tags}
        ).json()["interest"]
        for v in viewers
    ]
    assert len(set(interests)) >= 2, "audience must be heterogeneous, not one generic judge"


def test_interest_tracks_topic_match(client):
    v1 = build_viewer(0)  # farming/trucks interests
    farm = baseline_interest(v1, "Old Red tractor breaks down in the field", ["farming"])
    alien = baseline_interest(v1, "quantum computing keynote with free stickers", ["tech"])
    assert farm > alien


def test_affinity_increases_interest(client):
    v = build_viewer(0)
    before = baseline_interest(v, "a new episode just dropped", [])
    v.creator_affinities = {"hank": 1.0}
    after = baseline_interest(v, "a new episode just dropped", [])
    assert after > before


def test_affinity_endpoint(client):
    vid = client.post("/api/audience/seed", json={"count": 1}).json()[0]["id"]
    res = client.patch(
        f"/api/audience/{vid}/affinity",
        json={"creator_slug": "hank", "familiarity": 0.8},
    )
    assert res.status_code == 200
    assert res.json()["creator_affinities"] == {"hank": 0.8}

    bad = client.patch(
        f"/api/audience/{vid}/affinity",
        json={"creator_slug": "hank", "familiarity": 1.5},
    )
    assert bad.status_code == 400
    assert client.patch("/api/audience/9999/affinity", json={"creator_slug": "x", "familiarity": 0.5}).status_code == 404
