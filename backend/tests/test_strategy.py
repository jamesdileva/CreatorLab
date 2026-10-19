"""Sprint 22.1 — evidence-backed creator strategy evolution."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.models.episode import Episode, EpisodeStatus
from app.models.published_video import PublishedVideo
from app.models.render import Render
from app.models.scene import Scene
from app.models.series import Series
from app.models.video_metrics import VideoMetrics
from app.services import strategy_evolution as svc

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
    db.commit()
    db.close()
    return out


def _episode(creator_id, series_id, number, premise, scenes, duration, views):
    db = _db()
    episode = Episode(
        creator_id=creator_id, series_id=series_id, episode_number=number,
        title=f"Ep {number}", premise=premise, status=EpisodeStatus.PUBLISHED,
    )
    db.add(episode)
    db.flush()
    for i in range(scenes):
        db.add(
            Scene(
                episode_id=episode.id, scene_number=i + 1, title=f"s{i + 1}",
                direction="",
            )
        )
    render = Render(
        episode_id=episode.id, status="READY", total_duration=duration,
        artifact_dir="test",
    )
    db.add(render)
    db.flush()
    video = PublishedVideo(
        episode_id=episode.id, render_id=render.id, channel_id="chan",
        video_id=f"vid{number}", total_duration=duration,
    )
    db.add(video)
    db.flush()
    db.add(
        VideoMetrics(published_video_id=video.id, video_id=video.video_id, views=views)
    )
    db.commit()
    out = episode.id
    db.close()
    return out


def _rich_corpus():
    """3 strong 'tractor'/'long' episodes + 2 weak 'chickens'/'short' episodes."""
    cid, sid = _seed()
    for n in (1, 2, 3):
        _episode(cid, sid, n, f"Tractor story number {n} in the field",
                 scenes=5, duration=90.0, views=100)
    for n in (4, 5):
        _episode(cid, sid, n, f"Chickens story number {n} at dawn",
                 scenes=1, duration=20.0, views=10)
    return cid, sid


# ---------- evidence + gating ----------


def test_no_evidence_no_proposals(client):
    cid, _ = _seed()
    db = _db()
    assert svc.gather_evidence(db, cid)["topic_mix"] == []
    assert svc.propose_changes(db, cid) == []
    db.close()


def test_evidence_backed_proposals(client):
    cid, _ = _rich_corpus()
    db = _db()
    proposals = svc.propose_changes(db, cid)
    dims = {p.dimension for p in proposals}
    assert {"topic_mix", "episode_structure"} <= dims
    topic = next(p for p in proposals if p.dimension == "topic_mix")
    assert topic.proposed_value == ["tractor"]
    assert topic.evidence_count >= 3
    assert "prior episodes support" in topic.rationale
    # every proposal is grounded in named evidence
    assert all(p.evidence and p.evidence_count >= p.min_evidence for p in proposals)
    db.close()


def test_evidence_threshold_gates_proposal(client):
    cid, sid = _seed()
    # strong 'tractor' bucket exists, but only 2 episodes < MIN_EVIDENCE
    _episode(cid, sid, 1, "Tractor one in the field", 2, 30.0, 100)
    _episode(cid, sid, 2, "Tractor two in the field", 2, 30.0, 100)
    _episode(cid, sid, 3, "Chickens one at dawn", 1, 20.0, 10)
    _episode(cid, sid, 4, "Chickens two at dawn", 1, 20.0, 10)
    db = _db()
    proposals = svc.propose_changes(db, cid)
    assert all(p.dimension != "topic_mix" for p in proposals)

    _episode(cid, sid, 5, "Tractor three in the field", 2, 30.0, 100)
    proposals = svc.propose_changes(db, cid)
    assert any(p.dimension == "topic_mix" for p in proposals)
    db.close()


# ---------- decisions ----------


def test_approve_applies_change(client):
    cid, _ = _rich_corpus()
    db = _db()
    proposal = next(
        p for p in svc.propose_changes(db, cid) if p.dimension == "topic_mix"
    )
    before = svc.get_strategy(db, cid).revision
    decided = svc.decide_proposal(db, proposal.id, True, "looks right")
    assert decided.status == "APPROVED"

    strategy = svc.get_strategy(db, cid)
    assert strategy.topic_mix == ["tractor"]
    assert strategy.revision == before + 1
    with pytest.raises(ValueError):
        svc.decide_proposal(db, proposal.id, True)  # already decided
    db.close()


def test_reject_does_not_apply(client):
    cid, _ = _rich_corpus()
    db = _db()
    proposal = next(
        p for p in svc.propose_changes(db, cid) if p.dimension == "topic_mix"
    )
    svc.decide_proposal(db, proposal.id, False, "not convinced")
    assert svc.get_strategy(db, cid).topic_mix == []
    db.close()


def test_proposals_are_deduped(client):
    cid, _ = _rich_corpus()
    db = _db()
    first = svc.propose_changes(db, cid)
    second = svc.propose_changes(db, cid)
    assert first and second == []  # no duplicate PENDING proposals
    db.close()


# ---------- endpoints ----------


def test_endpoints(client):
    cid, _ = _rich_corpus()

    got = client.get(f"/api/strategy/creators/{cid}")
    assert got.status_code == 200
    assert got.json()["strategy"]["topic_mix"] == []

    made = client.post(f"/api/strategy/creators/{cid}/propose")
    assert made.status_code == 201, made.text
    proposals = made.json()
    assert proposals
    pid = proposals[0]["id"]

    listed = client.get(f"/api/strategy/proposals?creator_id={cid}").json()
    assert len(listed) == len(proposals)

    decided = client.post(
        f"/api/strategy/proposals/{pid}/decide",
        json={"approve": True, "note": "ok"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "APPROVED"

    after = client.get(f"/api/strategy/creators/{cid}").json()
    dim = proposals[0]["dimension"]
    assert after["strategy"][dim] == proposals[0]["proposed_value"]

    assert client.get("/api/strategy/creators/999").status_code == 400
    assert client.post(
        "/api/strategy/proposals/999/decide", json={"approve": True}
    ).status_code == 404
