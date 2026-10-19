"""Sprint 21.1 — automated candidate selection from the simulated pool."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.concept import Concept, ConceptSet
from app.models.concept_score import ConceptScore
from app.models.creator import Creator
from app.models.episode import Episode, EpisodeStatus
from app.models.series import Series
from app.services import selection_service as svc
from app.services.scoring_service import score_concept_set

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


def _db():
    return TestingSession()


_PREMISES = [
    "Hank buys an AI tractor that refuses to start until someone compliments it.",
    "Hank races his neighbor's drone across the fields at dawn and loses badly.",
    "Hank teaches the old machine to tell jokes about how things used to be done.",
]


def _seed_set():
    db = _db()
    creator = Creator(
        name="Hank", slug="hank", interests=["AI tractors", "farming"],
        humor_style="dry", personality="stubborn but kind",
    )
    db.add(creator)
    db.flush()
    series = Series(creator_id=creator.id, name="Hank's World")
    db.add(series)
    db.flush()
    cs = ConceptSet(creator_id=creator.id, series_id=series.id, topic="AI tractors")
    db.add(cs)
    db.flush()
    concepts = []
    for i, premise in enumerate(_PREMISES, start=1):
        c = Concept(
            set_id=cs.id, index=i, title=f"concept {i}", premise=premise,
            hook="Why though?", angle="comedy", tags="comedy",
        )
        db.add(c)
        concepts.append(c)
    db.commit()
    ids = [c.id for c in concepts]
    out = (creator.id, series.id, cs.id, ids)
    db.close()
    return out


def _score(set_id):
    db = _db()
    cs = db.get(ConceptSet, set_id)
    creator = db.get(Creator, cs.creator_id)
    score_concept_set(db, cs, creator)
    db.close()


# ---------- methods ----------


def test_select_by_simulation(client):
    _, _, set_id, ids = _seed_set()
    db = _db()
    result = svc.select_candidates(db, "concept", ids, method="simulation", count=1)

    assert result.selection.method == "simulation"
    assert result.selection.ranking_run_id is not None
    assert result.selection.audience_version
    assert len(result.selected) == 1
    assert len(result.ranked) == 3
    assert result.selection.selected_ids == [result.selected[0]["candidate_id"]]
    assert result.selection.scores
    assert "human approval" in result.selection.note
    assert len(svc.list_selections(db)) == 1
    db.close()


def test_select_by_score_requires_scoring(client):
    _, _, set_id, ids = _seed_set()
    db = _db()
    with pytest.raises(ValueError):
        svc.select_candidates(db, "concept", ids, method="score")
    db.close()

    _score(set_id)
    db = _db()
    top = (
        db.query(ConceptScore)
        .filter(ConceptScore.set_id == set_id)
        .order_by(ConceptScore.rank)
        .first()
    )
    result = svc.select_candidates(db, "concept", ids, method="score", count=2)
    assert result.selection.scorer_version
    assert result.selected[0]["candidate_id"] == top.concept_id
    assert len(result.selected) == 2
    db.close()


def test_combined_method(client):
    _, _, set_id, ids = _seed_set()
    _score(set_id)
    db = _db()
    result = svc.select_candidates(db, "concept", ids, method="combined", count=1)
    assert result.selection.method == "combined"
    assert result.selection.ranking_run_id is not None
    assert result.selection.scorer_version
    assert 0.0 <= result.selected[0]["score"] <= 1.0
    db.close()


def test_select_from_concept_set(client):
    _, series_id, set_id, ids = _seed_set()
    _score(set_id)
    db = _db()
    result = svc.select_from_concept_set(db, set_id, method="combined")
    assert result.selection.series_id == series_id
    assert result.selection.concept_set_id == set_id
    assert set(result.selection.selected_ids) <= set(ids)
    db.close()


# ---------- validation ----------


def test_validation(client):
    _, _, set_id, ids = _seed_set()
    db = _db()
    with pytest.raises(ValueError):
        svc.select_candidates(db, "widget", ids)
    with pytest.raises(ValueError):
        svc.select_candidates(db, "concept", ids[:1])
    with pytest.raises(ValueError):
        svc.select_candidates(db, "concept", ids, method="vibes")
    with pytest.raises(ValueError):
        svc.select_candidates(db, "episode", ids, method="score")
    with pytest.raises(ValueError):
        svc.select_candidates(db, "concept", ids, method="simulation", metric="nonsense")
    db.close()


# ---------- episode pool + no side effects ----------


def test_episode_simulation_selection_is_safe(client):
    cid, sid, _, _ = _seed_set()
    db = _db()
    eps = []
    for i in (1, 2):
        ep = Episode(
            creator_id=cid, series_id=sid, episode_number=i,
            title=f"Ep {i}", premise=f"premise {i}", status=EpisodeStatus.IDEA,
        )
        db.add(ep)
        eps.append(ep)
    db.commit()
    ep_ids = [e.id for e in eps]
    db.close()

    db = _db()
    result = svc.select_candidates(db, "episode", ep_ids, method="simulation", count=1)
    assert result.selection.candidate_type == "episode"
    assert len(result.selected) == 1
    # selection must not approve/publish anything
    for ep_id in ep_ids:
        assert db.get(Episode, ep_id).status == EpisodeStatus.IDEA
    db.close()


# ---------- endpoints ----------


def test_endpoints(client):
    _, _, set_id, ids = _seed_set()
    _score(set_id)

    created = client.post(
        "/api/selections",
        json={"candidate_type": "concept", "candidate_ids": ids, "method": "combined"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["requires_human_approval"] is True
    assert body["selected"] and body["ranked"]

    from_set = client.post(
        "/api/selections/from-concept-set",
        json={"set_id": set_id, "method": "simulation", "count": 2},
    )
    assert from_set.status_code == 201, from_set.text
    assert from_set.json()["concept_set_id"] == set_id

    listed = client.get("/api/selections").json()
    assert len(listed) == 2

    detail = client.get(f"/api/selections/{body['id']}").json()
    assert detail["id"] == body["id"]
    assert client.get("/api/selections/999").status_code == 404
    assert client.post(
        "/api/selections",
        json={"candidate_type": "nope", "candidate_ids": ids},
    ).status_code == 400
