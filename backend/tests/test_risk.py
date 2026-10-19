"""Sprint 21.2 — risk-based approval classification + fast lane."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.models.episode import Episode, EpisodeStatus
from app.models.risk import RiskAssessment
from app.models.series import Series
from app.models.simulation import SimulationRun, ViewerReaction
from app.services.risk_service import classify_episode
from app.services.simulation_service import seed_audience

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


def _seed():
    db = _db()
    creator = Creator(name="Hank", slug="hank", interests=["farming"], humor_style="dry")
    db.add(creator)
    db.flush()
    series = Series(creator_id=creator.id, name="Hank's World")
    db.add(series)
    db.flush()
    out = (creator.id, series.id)
    db.close()
    return out


def _episode(creator_id, series_id, number, title, premise="", script=""):
    db = _db()
    ep = Episode(
        creator_id=creator_id, series_id=series_id, episode_number=number,
        title=title, premise=premise, script=script, status=EpisodeStatus.REVIEW,
    )
    db.add(ep)
    db.commit()
    out = ep.id
    db.close()
    return out


def _sim(episode_id, watch=0.8, codes=()):
    db = _db()
    viewer = seed_audience(db)[0]
    run = SimulationRun(
        target_type="episode", target_id=episode_id, viewer_count=1, seed=0
    )
    db.add(run)
    db.flush()
    db.add(
        ViewerReaction(
            run_id=run.id, viewer_id=viewer.id, watch_probability=watch,
            like_probability=0.5, comment_probability=0.2, share_probability=0.1,
            follow_probability=0.1, reason_codes=list(codes),
        )
    )
    db.commit()
    db.close()


def _verdict(episode_id):
    db = _db()
    v = classify_episode(db, db.get(Episode, episode_id))
    db.close()
    return v


# ---------- classification ----------


def test_low_risk_uses_fast_lane(client):
    cid, sid = _seed()
    eid = _episode(cid, sid, 1, "Fixing the wheel",
                   "Hank oils a squeaky wheel before the harvest.",
                   script="He oils it and walks home happy.")
    _sim(eid, watch=0.8)

    verdict = _verdict(eid)
    assert verdict.level == "LOW"
    assert verdict.fast_lane is True

    risk = client.get(f"/api/episodes/{eid}/risk").json()
    assert risk["level"] == "LOW" and risk["fast_lane"] is True

    resp = client.post(f"/api/episodes/{eid}/fast-approve")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"

    db = _db()
    assert db.query(RiskAssessment).filter_by(episode_id=eid).count() == 1
    assert db.get(Episode, eid).status == EpisodeStatus.APPROVED
    db.close()


def test_medium_without_simulation_blocks_fast_lane(client):
    cid, sid = _seed()
    eid = _episode(cid, sid, 1, "Planting day", "Hank plants corn at dawn.")
    assert _verdict(eid).level == "MEDIUM"
    assert client.post(f"/api/episodes/{eid}/fast-approve").status_code == 422


def test_high_sensitive_topic(client):
    cid, sid = _seed()
    eid = _episode(cid, sid, 1, "The debate",
                   "Hank argues about the local election results with his neighbour.")
    _sim(eid, watch=0.9)
    verdict = _verdict(eid)
    assert verdict.level == "HIGH"
    assert client.post(f"/api/episodes/{eid}/fast-approve").status_code == 422


def test_high_from_simulation_flags(client):
    cid, sid = _seed()
    eid = _episode(cid, sid, 1, "Barn rumble", "Hank argues with the barn cat.")
    _sim(eid, watch=0.9, codes=["controversy"])
    verdict = _verdict(eid)
    assert verdict.level == "HIGH"
    assert any("simulation flags" in r for r in verdict.reasons)


def test_hard_block_is_high(client):
    cid, sid = _seed()
    eid = _episode(cid, sid, 1, "Fake", "Hank makes a deepfake of his neighbour.")
    assert _verdict(eid).level == "HIGH"


# ---------- queue + endpoints ----------


def test_risk_queue_literal_route_and_order(client):
    cid, sid = _seed()
    high = _episode(cid, sid, 1, "Vote", "Hank discusses the election over coffee.")
    low = _episode(cid, sid, 2, "Oil can", "Hank oils the combine before harvest.")
    _sim(low, watch=0.8)
    med = _episode(cid, sid, 3, "Morning", "Hank feeds the chickens early.")

    rows = client.get("/api/review-queue/risk")
    assert rows.status_code == 200, rows.text  # literal route not swallowed by /{id}
    data = rows.json()
    assert {r["episode_id"] for r in data} == {high, low, med}
    assert data[0]["level"] == "HIGH"
    assert data[0]["episode_id"] == high

    # detail route still works
    assert client.get(f"/api/review-queue/{low}").status_code == 200


def test_fast_lane_batch_approves_only_low(client):
    cid, sid = _seed()
    low1 = _episode(cid, sid, 1, "Oil", "Hank oils the gate at sunrise.")
    low2 = _episode(cid, sid, 2, "Feed", "Hank feeds the goats and laughs.")
    med = _episode(cid, sid, 3, "Wood", "Hank stacks firewood for winter.")
    _sim(low1, watch=0.8)
    _sim(low2, watch=0.7)

    out = client.post("/api/review-queue/fast-lane").json()
    assert set(out["approved"]) == {low1, low2}
    assert out["skipped"] == [med]
    assert out["classifier_version"]

    db = _db()
    assert db.get(Episode, low1).status == EpisodeStatus.APPROVED
    assert db.get(Episode, low2).status == EpisodeStatus.APPROVED
    assert db.get(Episode, med).status == EpisodeStatus.REVIEW
    db.close()


def test_risk_404(client):
    assert client.get("/api/episodes/999/risk").status_code == 404
