"""Sprint 4.3 — candidate ranking: which candidate should we test first?"""
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
    c = TestClient(app)
    c.creator_id = c.post(  # type: ignore[attr-defined]
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()["id"]
    c.series_id = c.post(  # type: ignore[attr-defined]
        "/api/series", json={"creator_id": c.creator_id, "name": "Hank's World"}
    ).json()["id"]
    gen = c.post(
        f"/api/series/{c.series_id}/generate-concepts",
        json={"topic": "AI tractors", "count": 5},
    ).json()
    c.concept_ids = [cc["id"] for cc in gen["concepts"]]  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _rank(c, ids, metric="watch_probability"):
    return c.post(
        "/api/simulations/rank",
        json={"candidate_type": "concept", "candidate_ids": ids, "metric": metric},
    )


# Roadmap verification: produce an ordered ranking over several candidates.
def test_rank_four_candidates_ordered(client):
    ids = client.concept_ids[:4]
    res = _rank(client, ids)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["run"]["metric"] == "watch_probability"
    assert body["run"]["audience_version"] == "audience-v1"
    assert body["run"]["viewer_count"] == 25
    assert body["run"]["prompt_version"] == "ranking-v1"

    ranked = body["ranked"]
    assert len(ranked) == 4
    assert {r["candidate_id"] for r in ranked} == set(ids)
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)  # A > C > B > D style order
    assert body["run"]["ranking"] == [r["candidate_id"] for r in ranked]
    assert body["run"]["candidate_ids"] == ids


def test_ranking_deterministic_rerun(client):
    ids = client.concept_ids[:4]
    first = _rank(client, ids).json()
    second = _rank(client, ids).json()
    assert first["run"]["ranking"] == second["run"]["ranking"]
    assert [r["score"] for r in first["ranked"]] == [r["score"] for r in second["ranked"]]


def test_ranking_links_simulation_runs(client):
    ids = client.concept_ids[:4]
    body = _rank(client, ids).json()
    assert len(body["run"]["simulation_run_ids"]) == 4
    for run_id in body["run"]["simulation_run_ids"]:
        reactions = client.get(f"/api/simulations/{run_id}/reactions").json()
        assert len(reactions) == 25


def test_ranking_persisted_and_retrievable(client):
    ids = client.concept_ids[:4]
    created = _rank(client, ids).json()

    rankings = client.get("/api/simulations/rankings").json()
    assert any(r["id"] == created["run"]["id"] for r in rankings)

    detail = client.get(f"/api/simulations/rankings/{created['run']['id']}").json()
    assert detail["run"]["ranking"] == created["run"]["ranking"]
    assert len(detail["ranked"]) == 4


def test_alternate_metric(client):
    ids = client.concept_ids[:4]
    res = _rank(client, ids, metric="like_probability")
    assert res.status_code == 200 or res.status_code == 201
    assert res.json()["run"]["metric"] == "like_probability"


def test_episode_ranking(client):
    ep_ids = []
    for variant in range(3):
        res = client.post(
            f"/api/series/{client.series_id}/generate-episode", json={"variant": variant}
        )
        ep_ids.append(res.json()["episode"]["id"])
    res = client.post(
        "/api/simulations/rank",
        json={"candidate_type": "episode", "candidate_ids": ep_ids},
    )
    assert res.status_code == 201
    assert len(res.json()["ranked"]) == 3


def test_rank_validation(client):
    ids = client.concept_ids[:4]
    assert _rank(client, ids[:1]).status_code == 400  # needs >= 2
    assert _rank(client, ids + ids[:1]).status_code == 400  # unique
    bad_metric = client.post(
        "/api/simulations/rank",
        json={"candidate_type": "concept", "candidate_ids": ids, "metric": "viral_probability"},
    )
    assert bad_metric.status_code == 400
    bad_type = client.post(
        "/api/simulations/rank",
        json={"candidate_type": "video", "candidate_ids": ids},
    )
    assert bad_type.status_code == 400
    missing = client.post(
        "/api/simulations/rank",
        json={"candidate_type": "concept", "candidate_ids": ids + [9999]},
    )
    assert missing.status_code == 400
    assert client.get("/api/simulations/rankings/9999").status_code == 404
