"""Sprint 11.1 — viewer memory: repetition fatigue after repeated exposure."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.audience_service import build_viewer
from app.services.simulation_service import compute_reaction
from app.services.viewer_memory import effective_exposures, fatigue_penalty

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
    creator = c.post("/api/creators", json={"name": f"Hank {tag}", "slug": f"hank-{tag}"}).json()
    series = c.post(
        "/api/series", json={"creator_id": creator["id"], "name": f"Farm {tag}"}
    ).json()
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


def test_five_tractor_episodes_dull_the_sixth(client):
    means = []
    codes = []
    for i in range(6):
        ep = _episode(client, i, TRACTOR_TITLE, f"{TRACTOR_PREMISE} round {i}")
        body = _run(client, ep["id"])
        means.append(body["aggregate"]["means"]["watch_probability"])
        codes.append(body["aggregate"]["reason_counts"])
    assert means[5] < means[0] - 0.05
    assert "repetition_fatigue" in codes[5]
    assert "repetition_fatigue" not in codes[0]


def test_same_episode_rerun_ignores_own_history(client):
    ep = _episode(client, 0, TRACTOR_TITLE, TRACTOR_PREMISE)
    first = _run(client, ep["id"])["aggregate"]["means"]
    second = _run(client, ep["id"])["aggregate"]["means"]
    assert first == second


def test_unrelated_content_has_no_fatigue(client):
    ep1 = _episode(client, 0, TRACTOR_TITLE, TRACTOR_PREMISE)
    _run(client, ep1["id"])
    ep2 = _episode(
        client, 1, "midnight diner jazz", "cryptid crooners play midnight diner jazz mysteries"
    )
    body = _run(client, ep2["id"])
    assert "repetition_fatigue" not in body["aggregate"]["reason_counts"]


def test_concept_runs_stay_memory_free(client):
    gen = client.post(
        f"/api/series/{client.series_id}/generate-concepts",
        json={"topic": "AI tractors", "count": 3},
    ).json()
    ids = [c["id"] for c in gen["concepts"]]
    for concept_id in ids:
        body = client.post(
            "/api/simulations/run",
            json={"target_type": "concept", "target_id": concept_id},
        ).json()
        assert "repetition_fatigue" not in body["aggregate"]["reason_counts"]


def test_fatigue_param_unit():
    viewer = build_viewer(0)
    fresh = compute_reaction(viewer, "tractor time", "tractor harvest chronicles")
    dulled = compute_reaction(viewer, "tractor time", "tractor harvest chronicles", fatigue=0.2)
    assert fresh.watch - dulled.watch == pytest.approx(0.2)
    assert "repetition_fatigue" in dulled.reason_codes
    assert "repetition_fatigue" not in fresh.reason_codes


def test_penalty_math():
    assert fatigue_penalty(0.0) == 0.0
    assert fatigue_penalty(0.75) == 0.0  # free allowance
    assert fatigue_penalty(2.0) > 0.0
    assert fatigue_penalty(999.0) == 0.35  # capped
