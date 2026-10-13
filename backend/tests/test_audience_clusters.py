"""Sprint 11.3 — behavior clusters (deterministic k-means over reaction signals)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.simulation import SimulationRun, ViewerReaction
from app.services.audience_segments import cluster_viewers

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


def _row(viewer_id, watch, follow, engage):
    return {
        "viewer_id": viewer_id,
        "watch": watch,
        "follow": follow,
        "engagement": engage,
        "comment_share": 0.2,
        "runs": 1,
    }


def test_clusters_are_deterministic():
    rows = [
        _row(1, 0.8, 0.5, 0.3),
        _row(2, 0.75, 0.45, 0.28),
        _row(3, 0.5, 0.2, 0.15),
        _row(4, 0.45, 0.18, 0.12),
        _row(5, 0.1, 0.05, 0.05),
        _row(6, 0.12, 0.06, 0.04),
    ]
    first = cluster_viewers(rows)
    second = cluster_viewers(list(reversed(rows)))
    assert first["assignments"] == list(reversed(second["assignments"])) or first["centroids"] == second["centroids"]
    assert first["k"] == 3
    assert len(first["assignments"]) == 6
    assert set(first["assignments"]) <= {0, 1, 2}


def test_clusters_separate_behavioral_groups():
    rows = [
        _row(1, 0.9, 0.6, 0.4),
        _row(2, 0.85, 0.55, 0.38),
        _row(3, 0.7, 0.6, 0.35),
        _row(4, 0.4, 0.1, 0.1),
        _row(5, 0.35, 0.12, 0.08),
        _row(6, 0.05, 0.02, 0.02),
        _row(7, 0.08, 0.03, 0.03),
        _row(8, 0.42, 0.11, 0.09),
    ]
    result = cluster_viewers(rows)
    # the three deep viewers land together, the three skimmers land together
    deep = {result["assignments"][i] for i in range(3)}
    skim = {result["assignments"][i] for i in (5, 6)}
    assert len(deep) == 1
    assert len(skim) == 1
    assert deep != skim


def test_clusters_handle_empty_and_tiny():
    assert cluster_viewers([])["assignments"] == []
    single = cluster_viewers([_row(1, 0.5, 0.2, 0.1)])
    assert single["k"] == 1
    assert single["assignments"] == [0]


def test_endpoint_includes_clusters(client):
    creator = client.post(
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": "S"}
    ).json()
    ep = client.post(
        f"/api/series/{series['id']}/generate-episode", json={"variant": 0}
    ).json()["episode"]
    client.post("/api/audience/seed", json={"count": 25})
    client.post("/api/simulations/run", json={"target_type": "episode", "target_id": ep["id"]})

    body = client.get("/api/audience/segments").json()
    assert body["classified"] == 25
    assert body["clusters"]["k"] == 3
    assert len(body["clusters"]["centroids"]) == 3
    assert set(body["clusters"]["labels"]) <= {
        "deep-fans",
        "steady-watchers",
        "casual-engagers",
        "skimmers",
    }
    # every classified viewer sits in exactly one cluster member list
    total = sum(body["clusters"]["counts"].values())
    assert total == 25
    # specialization + top creator reach the payload (roadmap: Hank fans etc.)
    sample = next(iter(body["segments"].values()))[0]
    assert "specialization" in sample
    assert sample["top_creator"] == "hank"
