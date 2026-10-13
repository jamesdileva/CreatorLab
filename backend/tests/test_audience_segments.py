"""Sprint 11.3 — audience segments: clusters derived from reaction behavior."""
import uuid

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


def _setup(client):
    tag = uuid.uuid4().hex[:8]
    creator = client.post(
        "/api/creators", json={"name": f"Hank {tag}", "slug": f"hank-{tag}"}
    ).json()
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": f"Farm {tag}"}
    ).json()
    for i in range(3):
        ep = client.post(
            f"/api/series/{series['id']}/generate-episode", json={"variant": i}
        ).json()["episode"]
        client.patch(
            f"/api/episodes/{ep['id']}",
            json={"title": f"tractor harvest {i}", "premise": f"tractor harvest chronicles round {i}"},
        )
        ep = client.get(f"/api/episodes/{ep['id']}").json()
        client.post(
            "/api/simulations/run", json={"target_type": "episode", "target_id": ep["id"]}
        )
    return creator


def test_segments_empty(client):
    body = client.get("/api/audience/segments").json()
    assert body["viewer_count"] == 0
    assert body["classified"] == 0
    assert body["segments"] == {}
    assert body["interpretation_allowed"] is False


def test_segments_identifies_clusters(client):
    _setup(client)
    body = client.get("/api/audience/segments").json()

    assert body["classified"] > 0
    assert sum(body["counts"].values()) == body["classified"]
    labels = set(body["segments"])
    assert labels & {"loyalist", "passionate", "replier", "reactor", "lurker", "sampler"}
    for label, members in body["segments"].items():
        assert all(m["segment"] == label for m in members)
        assert all("specialization" in m and "top_creator" in m for m in members)


def test_segments_two_creators_separates_specialists(client):
    tag = uuid.uuid4().hex[:8]
    creators = []
    for name in ("Hank", "Alex"):
        c = client.post(
            "/api/creators", json={"name": f"{name} {tag}", "slug": f"{name.lower()}-{tag}"}
        ).json()
        series = client.post(
            "/api/series", json={"creator_id": c["id"], "name": f"{name} {tag}"}
        ).json()
        for i in range(3):
            ep = client.post(
                f"/api/series/{series['id']}/generate-episode", json={"variant": i}
            ).json()["episode"]
            client.patch(
                f"/api/episodes/{ep['id']}",
                json={"title": f"{name} story {i}", "premise": f"{name} story chronicles round {i}"},
            )
            ep = client.get(f"/api/episodes/{ep['id']}").json()
            client.post(
                "/api/simulations/run", json={"target_type": "episode", "target_id": ep["id"]}
            )
        creators.append(c)

    body = client.get("/api/audience/segments").json()
    assigns = {
        m["top_creator"]
        for members in body["segments"].values()
        for m in members
        if m["top_creator"]
    }
    assert set(f"{c['slug']}" for c in creators) & assigns


def test_segments_route_not_shadowed_by_viewer_id(client):
    _setup(client)
    # literal segments route must not be parsed as /audience/{viewer_id}
    assert client.get("/api/audience/segments").status_code == 200
    assert client.get("/api/audience/99999").status_code == 404
