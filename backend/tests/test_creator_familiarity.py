"""Sprint 11.2 — creator familiarity: stranger → familiar → favorite."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.audience_service import build_viewer
from app.services.creator_familiarity import (
    FAMILIAR_MIN,
    FAVORITE_MIN,
    strength_for,
    tier_for,
)
from app.services.simulation_service import compute_reaction

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
    tag = uuid.uuid4().hex[:8]
    c = TestClient(app)
    c.slug_tag = tag  # type: ignore[attr-defined]
    creator = c.post("/api/creators", json={"name": f"Hank {tag}", "slug": f"hank-{tag}"}).json()
    series = c.post(
        "/api/series", json={"creator_id": creator["id"], "name": f"Farm {tag}"}
    ).json()
    c.creator_id = creator["id"]  # type: ignore[attr-defined]
    c.series_id = series["id"]  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _episode(client, variant, title, premise):
    ep = client.post(
        f"/api/series/{client.series_id}/generate-episode", json={"variant": variant}
    ).json()["episode"]
    client.patch(f"/api/episodes/{ep['id']}", json={"title": title, "premise": premise})
    return client.get(f"/api/episodes/{ep['id']}").json()


def _run(client, episode_id):
    return client.post(
        "/api/simulations/run", json={"target_type": "episode", "target_id": episode_id}
    ).json()


TRACTOR_TITLE = "tractor harvest chronicles"
TRACTOR_PREMISE = "tractor harvest chronicles continue with familiar machines and stubborn engines"


def test_tier_boundaries():
    assert tier_for(0.0) == "unknown"
    assert tier_for(FAMILIAR_MIN - 0.1) == "unknown"
    assert tier_for(FAMILIAR_MIN + 0.5) == "familiar"
    assert tier_for(FAVORITE_MIN - 0.1) == "familiar"
    assert tier_for(FAVORITE_MIN + 0.5) == "favorite"


def test_familiarity_increases_follow():
    viewer = build_viewer(0)
    stranger = compute_reaction(viewer, TRACTOR_TITLE, TRACTOR_PREMISE).follow
    familiar = compute_reaction(
        viewer, TRACTOR_TITLE, TRACTOR_PREMISE, familiarity=("familiar", 0.4)
    ).follow
    favorite = compute_reaction(
        viewer, TRACTOR_TITLE, TRACTOR_PREMISE, familiarity=("favorite", 0.75)
    ).follow
    assert stranger < familiar < favorite
    assert "familiar_creator" not in compute_reaction(
        viewer, TRACTOR_TITLE, TRACTOR_PREMISE
    ).reason_codes


def test_familiar_viewer_follows_more_after_seen_episodes(client):
    for i in range(4):
        ep = _episode(client, i, TRACTOR_TITLE, f"{TRACTOR_PREMISE} round {i}")
        _run(client, ep["id"])

    tiers = client.get(f"/api/creators/{client.creator_id}/familiarity")
    assert tiers.status_code == 200, tiers.text
    body = tiers.json()
    assert body["tiers"]["familiar"] + body["tiers"]["favorite"] > 0
    assert body["viewer_count"] > 0


def test_same_episode_rerun_ignores_familiarity_from_itself(client):
    ep = _episode(client, 0, TRACTOR_TITLE, TRACTOR_PREMISE)
    first = _run(client, ep["id"])["aggregate"]["means"]
    second = _run(client, ep["id"])["aggregate"]["means"]
    assert first == second


def test_strength_monotonic():
    assert strength_for(0.0) == 0.0
    assert strength_for(FAMILIAR_MIN) == 0.0
    assert strength_for((FAMILIAR_MIN + FAVORITE_MIN) / 2) > 0.0
    assert strength_for(FAVORITE_MIN + 5) == 0.75
    values = [strength_for(x / 10) for x in range(0, 60)]
    assert values == sorted(values)
