"""Sprint 3.2 — concept scoring + comparison against human judgment."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.metrics import (
    directional_accuracy,
    kendall_tau,
    spearman,
    top_k_agreement,
)
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
        "/api/creators",
        json={
            "name": "Hank",
            "slug": "hank",
            "interests": ["farming", "trucks"],
            "humor_style": "dry, deadpan",
        },
    ).json()["id"]
    c.series_id = c.post(  # type: ignore[attr-defined]
        "/api/series", json={"creator_id": c.creator_id, "name": "Hank's World"}
    ).json()["id"]
    c.post(
        f"/api/series/{c.series_id}/canon",
        json={"category": "OBJECT", "statement": "Hank owns an Old Red tractor."},
    )
    res = c.post(
        f"/api/series/{c.series_id}/generate-concepts",
        json={"topic": "AI tractors", "count": 5},
    )
    c.set_id = res.json()["set"]["id"]  # type: ignore[attr-defined]
    c.concept_ids = [cc["id"] for cc in res.json()["concepts"]]  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_metrics_known_values():
    # perfect agreement
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert kendall_tau([1, 2, 3], [10, 20, 30]) == 1.0
    assert spearman([1, 2, 3], [30, 20, 10]) == pytest.approx(-1.0)
    assert kendall_tau([1, 2, 3], [30, 20, 10]) == -1.0
    # one inversion out of three pairs
    assert directional_accuracy([1, 2, 3], [1, 3, 2]) == pytest.approx(2 / 3)
    assert directional_accuracy([1, 2, 3], [3, 2, 1]) == 0.0
    assert top_k_agreement([1, 2, 3], [1, 2, 3], 2) == 1.0
    # top-2s {1,2} vs {3,2} share item 2
    assert top_k_agreement([1, 2, 3], [3, 2, 1], 2) == 0.5


def test_score_set_returns_all_six_dimensions_ranked(client):
    body = client.post(f"/api/concept-sets/{client.set_id}/score").json()
    assert len(body["ranked"]) == 5
    assert body["scorer_version"] == "heuristic-v1"

    dims = {
        "hook",
        "character_fit",
        "novelty",
        "story_potential",
        "audience_relevance",
        "episode_continuity",
    }
    for item in body["ranked"]:
        assert set(item["scores"].keys()) == dims
        assert 0.0 <= item["composite"] <= 1.0
    ranks = [item["rank"] for item in body["ranked"]]
    assert ranks == [1, 2, 3, 4, 5]
    composites = [item["composite"] for item in body["ranked"]]
    assert composites == sorted(composites, reverse=True)


def test_scores_persisted_and_idempotent(client):
    first = client.post(f"/api/concept-sets/{client.set_id}/score").json()
    second = client.post(f"/api/concept-sets/{client.set_id}/score").json()

    stored = client.get(f"/api/concept-sets/{client.set_id}/scores").json()
    assert len(stored) == 5
    assert [s["rank"] for s in stored] == [1, 2, 3, 4, 5]

    a = {r["concept"]["id"]: r["composite"] for r in first["ranked"]}
    b = {r["concept"]["id"]: r["composite"] for r in second["ranked"]}
    assert a == b  # deterministic + upsert, no duplicate rows


def test_human_ranking_requires_exact_set(client):
    missing = client.concept_ids[:-1]
    bad = client.post(
        f"/api/concept-sets/{client.set_id}/human-ranking", json={"order": missing}
    )
    assert bad.status_code == 400
    bad_dup = client.post(
        f"/api/concept-sets/{client.set_id}/human-ranking",
        json={"order": client.concept_ids + [client.concept_ids[0]]},
    )
    assert bad_dup.status_code == 400


def test_comparison_after_scoring_and_human_ranking(client):
    client.post(f"/api/concept-sets/{client.set_id}/score")
    # human deliberately reverses system's expected ranking
    body = client.post(f"/api/concept-sets/{client.set_id}/score").json()
    system_order = [r["concept"]["id"] for r in body["ranked"]]
    human_order = list(reversed(system_order))

    ranking = client.post(
        f"/api/concept-sets/{client.set_id}/human-ranking",
        json={"order": human_order, "note": "test: reversed"},
    )
    assert ranking.status_code == 201

    comparison = client.get(f"/api/concept-sets/{client.set_id}/comparison").json()
    assert comparison["system_order"] == system_order
    assert comparison["human_order"] == human_order
    assert comparison["sample_size"] == 5
    # reversed ranking of 5 items: spearman = -1, kendall = -1, directional = 0
    assert comparison["correlation"]["spearman"] == -1.0
    assert comparison["correlation"]["kendall_tau"] == -1.0
    assert comparison["agreement"]["directional_accuracy"] == 0.0
    assert comparison["agreement"]["top_1_match"] is False


def test_comparison_identical_ranking(client):
    body = client.post(f"/api/concept-sets/{client.set_id}/score").json()
    order = [r["concept"]["id"] for r in body["ranked"]]
    client.post(f"/api/concept-sets/{client.set_id}/human-ranking", json={"order": order})
    comparison = client.get(f"/api/concept-sets/{client.set_id}/comparison").json()
    assert comparison["correlation"]["spearman"] == 1.0
    assert comparison["correlation"]["kendall_tau"] == 1.0
    assert comparison["agreement"]["top_1_match"] is True
    assert comparison["agreement"]["top_3_overlap"] == 1.0


def test_comparison_before_data_409(client):
    assert client.get(f"/api/concept-sets/{client.set_id}/comparison").status_code == 409


def test_unknown_concept_set_404(client):
    assert client.post("/api/concept-sets/9999/score").status_code == 404
    assert client.get("/api/concept-sets/9999/scores").status_code == 404
    assert client.get("/api/concept-sets/9999/comparison").status_code == 404
    assert (
        client.post(
            "/api/concept-sets/9999/human-ranking", json={"order": [1]}
        ).status_code
        == 404
    )


def test_rank_ordering_matches_dimensions(client):
    """The concept with the strongest overall profile should rank first."""
    body = client.post(f"/api/concept-sets/{client.set_id}/score").json()
    top = body["ranked"][0]
    assert top["rank"] == 1
    # composite equals the weighted mean of its dimension scores
    weights = {
        "hook": 0.20,
        "character_fit": 0.20,
        "novelty": 0.20,
        "story_potential": 0.15,
        "audience_relevance": 0.15,
        "episode_continuity": 0.10,
    }
    expected = round(sum(top["scores"][k] * w for k, w in weights.items()), 3)
    assert top["composite"] == expected
