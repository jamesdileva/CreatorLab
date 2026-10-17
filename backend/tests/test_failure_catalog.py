"""Sprint 17.2 — simulation failure catalog: categorize where the sim is wrong."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.models.episode import Episode
from app.models.experiment import ContentExperiment
from app.models.published_video import PublishedVideo
from app.models.series import Series
from app.models.simulation import SimulationRun, ViewerReaction
from app.services.failure_catalog import classify_failure, failure_catalog

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


def _words(text):
    return set(__import__("re").findall(r"[a-z][a-z'-]+", text.lower()))


# ---------- classifier (pure) ----------


def test_classify_failure_rules():
    over = "over"
    under = "under"
    none = set()
    # over, absurd hook → controversy
    assert classify_failure(over, none, "absurd", None, none) == "overestimated_controversy"
    # over, controversy marker
    assert classify_failure(over, _words("the drama"), "direct", None, none) == (
        "overestimated_controversy"
    )
    # over, long → pacing
    assert classify_failure(over, none, "direct", "long", none) == "misread_pacing"
    # over, plain → reach
    assert classify_failure(over, none, "direct", "short", none) == "overestimated_reach"
    # under variants
    assert classify_failure(under, _words("so ironic"), "direct", None, none) == "missed_irony"
    assert classify_failure(under, _words("very awkward"), "direct", None, none) == "missed_cringe"
    assert classify_failure(under, _words("a niche trope"), "direct", None, none) == "misread_niche_humor"
    assert classify_failure(under, _words("a funny bit"), "direct", None, none) == "missed_humor"
    assert classify_failure(
        under, none, "direct", None, {"creator_affinity"}
    ) == "underestimated_character_attachment"
    assert classify_failure(under, none, "direct", "long", none) == "misread_pacing"
    assert classify_failure(under, none, "direct", "short", none) == "underestimated_reach"


def test_humor_matched_is_not_a_miss():
    # humor marker present but the sim DID flag humor_match → not missed_humor
    assert classify_failure(
        "under", _words("a funny bit"), "direct", None, {"humor_match"}
    ) == "underestimated_reach"


# ---------- fixtures ----------


def _seed():
    db = _db()
    creator = Creator(name="Hank", slug="hank")
    db.add(creator)
    db.flush()
    series = Series(creator_id=creator.id, name="Hank's World")
    db.add(series)
    db.commit()
    cid, sid = creator.id, series.id
    db.close()
    return cid, sid


def _episode(creator_id, series_id, n, synopsis, duration=None, reasons=None, delta=None):
    db = _db()
    ep = Episode(
        creator_id=creator_id,
        series_id=series_id,
        episode_number=n,
        title=f"Ep {n}",
        synopsis=synopsis,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)

    if reasons is not None:
        run = SimulationRun(target_type="episode", target_id=ep.id)
        db.add(run)
        db.flush()
        db.add(
            ViewerReaction(
                run_id=run.id,
                viewer_id=1,
                watch_probability=0.5,
                like_probability=0.4,
                comment_probability=0.1,
                share_probability=0.1,
                follow_probability=0.1,
                reason_codes=list(reasons),
            )
        )
    if duration is not None:
        video = PublishedVideo(
            episode_id=ep.id,
            render_id=1,
            channel_id="UC_MOCK",
            video_id=f"vid-{ep.id}",
            total_duration=duration,
        )
        db.add(video)
    if delta is not None:
        db.add(
            ContentExperiment(
                creator_id=creator_id,
                episode_id=ep.id,
                reality_gap={"rank_deltas": {str(ep.id): delta}, "sample_size": 2},
            )
        )
    db.commit()
    ep_id = ep.id
    db.close()
    return ep_id


# ---------- catalog ----------


def test_catalog_groups_and_ranks(client):
    cid, sid = _seed()
    _episode(cid, sid, 1, "The tractor is possessed.", delta=-3)
    _episode(cid, sid, 2, "Oh how ironic the harvest was.", delta=2)
    _episode(cid, sid, 3, "It just got awkward.", delta=1)
    _episode(cid, sid, 4, "The barn stood in the morning light.", delta=2)

    report = failure_catalog(_db())
    assert report["failures_considered"] == 4
    assert report["interpretation_allowed"] is True
    assert report["catalog"]["overestimated_controversy"]["count"] == 1
    assert report["catalog"]["missed_irony"]["count"] == 1
    assert report["catalog"]["missed_cringe"]["count"] == 1
    assert report["catalog"]["underestimated_reach"]["count"] == 1
    counts = [w["count"] for w in report["weakness_rank"]]
    assert counts == sorted(counts, reverse=True)
    assert report["verdict"].startswith("most common simulator weakness")


def test_catalog_uses_reason_codes_and_length(client):
    cid, sid = _seed()
    _episode(cid, sid, 1, "The barn in the morning light.", delta=1,
             reasons={"creator_affinity"})
    _episode(cid, sid, 2, "A quiet day on the farm.", delta=2, duration=120.0)

    report = failure_catalog(_db())
    assert report["catalog"]["underestimated_character_attachment"]["count"] == 1
    assert report["catalog"]["misread_pacing"]["count"] == 1
    pacing = [f for f in report["failures"] if f["category"] == "misread_pacing"][0]
    assert pacing["length_bucket"] == "long"


def test_catalog_gated_below_min(client):
    cid, sid = _seed()
    _episode(cid, sid, 1, "Oh how ironic.", delta=2)
    report = failure_catalog(_db())
    assert report["failures_considered"] == 1
    assert report["interpretation_allowed"] is False
    assert report["verdict"].startswith("insufficient data")


def test_catalog_ignores_zero_delta_and_other_creator(client):
    cid, sid = _seed()
    _episode(cid, sid, 1, "Oh how ironic.", delta=0)
    report = failure_catalog(_db())
    assert report["failures_considered"] == 0
    assert report["weakness_rank"] == []
    assert report["verdict"].startswith("insufficient data")
    assert failure_catalog(_db(), creator_id=999)["failures_considered"] == 0


def test_endpoint(client):
    cid, sid = _seed()
    _episode(cid, sid, 1, "The tractor is possessed.", delta=-3)
    _episode(cid, sid, 2, "Oh how ironic.", delta=2)
    _episode(cid, sid, 3, "It just got awkward.", delta=1)

    res = client.get("/api/experiments/failure-catalog")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["categories"][0] == "missed_irony"
    assert body["interpretation_allowed"] is True
    assert {"experiment_id", "episode_id", "direction", "rank_delta",
            "category"} <= set(body["failures"][0])

    filtered = client.get(
        "/api/experiments/failure-catalog", params={"creator_id": 999}
    ).json()
    assert filtered["failures_considered"] == 0
