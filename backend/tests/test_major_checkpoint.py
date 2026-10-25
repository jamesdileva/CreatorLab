"""Phase 25 — major research checkpoint (simulator vs random vs humans)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.models.episode import Episode, EpisodeStatus
from app.models.experiment import ContentExperiment
from app.models.human_panel import HumanPanelRanking
from app.models.published_video import PublishedVideo
from app.models.render import Render
from app.models.series import Series
from app.models.simulation import SimulationRun, ViewerReaction
from app.models.video_metrics import VideoMetrics
from app.services import major_checkpoint as svc
from app.services.audience_service import seed_audience

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


def _universe(name="Hank", slug="hank", count=5):
    db = _db()
    creator = Creator(name=name, slug=slug)
    db.add(creator)
    db.flush()
    series = Series(creator_id=creator.id, name=f"{name}'s World")
    db.add(series)
    db.flush()
    ids = []
    for number in range(1, count + 1):
        episode = Episode(
            creator_id=creator.id, series_id=series.id, episode_number=number,
            title=f"Episode {number}",
            premise=f"Tractor repair story number {number} with tools",
            status=EpisodeStatus.PUBLISHED,
        )
        db.add(episode)
        db.flush()
        ids.append(episode.id)
    db.commit()
    out = (creator.id, series.id, ids)
    db.close()
    return out


def _gap(directional=0.8, sample_size=5):
    return {
        "agreement": {
            "directional_accuracy": directional,
            "top_1_match": directional >= 0.5,
        },
        "correlation": {
            "spearman": round(directional - 0.5, 3),
            "kendall_tau": round(directional - 0.5, 3),
        },
        "disagreements": [],
        "sample_size": sample_size,
        "sim_order": [],
        "real_order": [],
    }


def _experiments(cid, episode_ids, directional=0.8, sample_size=5):
    db = _db()
    for eid in episode_ids:
        db.add(
            ContentExperiment(
                creator_id=cid, episode_id=eid, hypothesis="test",
                reality_gap=_gap(directional, sample_size),
            )
        )
    db.commit()
    db.close()


def test_strong_evidence_continue(client):
    cid, _sid, ids = _universe()
    _experiments(cid, ids, directional=0.8)

    db = _db()
    result = svc.build_checkpoint(db)
    db.close()

    assert result["experiments_scored"] == 5
    assert result["overall"]["comparisons"] == 5
    assert result["overall"]["directional_accuracy"] == 0.8
    assert result["overall"]["sim_vs_random_delta"] == 0.3
    assert result["overall"]["sample_sufficient"] is True
    assert result["outcome"] == "strong"
    assert result["recommendation"] == "continue"
    assert "continue" in result["outcome_text"].lower()
    assert set(result["buckets"]) == {
        "creator", "topic", "format", "episode_type", "platform"
    }
    assert result["buckets"]["creator"]["hank"]["comparisons"] == 5
    assert result["classification_counts"]["strong"] >= 1


def test_weak_evidence_pivots(client):
    cid, _sid, ids = _universe()
    _experiments(cid, ids, directional=0.2)

    db = _db()
    result = svc.build_checkpoint(db)
    db.close()

    assert result["outcome"] == "weak"
    assert result["recommendation"] == "pivot"
    assert "pivot" in result["outcome_text"].lower()


def test_insufficient_below_sample_gate(client):
    cid, _sid, ids = _universe()
    _experiments(cid, ids[:2], directional=0.9)

    db = _db()
    result = svc.build_checkpoint(db)
    db.close()

    assert result["overall"]["comparisons"] == 2
    assert result["overall"]["sample_sufficient"] is False
    assert result["outcome"] == "insufficient"
    assert result["recommendation"] == "collect_more_data"


def test_human_panel_comparison(client):
    cid, _sid, ids = _universe()
    db = _db()
    viewer = seed_audience(db, count=1)[0]
    for index, eid in enumerate(ids):
        run = SimulationRun(
            target_type="episode", target_id=eid, viewer_count=1, seed=0
        )
        db.add(run)
        db.flush()
        db.add(
            ViewerReaction(
                run_id=run.id, viewer_id=viewer.id,
                watch_probability=0.9 - 0.1 * index, like_probability=0.3,
                comment_probability=0.1, share_probability=0.05,
                follow_probability=0.1, reason_codes=[],
            )
        )
        render = Render(episode_id=eid, status="READY", total_duration=45.0)
        db.add(render)
        db.flush()
        video = PublishedVideo(
            episode_id=eid, render_id=render.id, channel_id="chan",
            video_id=f"v{eid}", total_duration=45.0,
        )
        db.add(video)
        db.flush()
        db.add(
            VideoMetrics(
                published_video_id=video.id, video_id=video.video_id,
                views=500 - 50 * index, likes=10, comments=1,
                subscriber_count=10, subscribers_gained=1,
            )
        )
    db.add(
        HumanPanelRanking(candidate_type="episode", order=list(ids), note="panel")
    )
    db.commit()
    db.close()
    _experiments(cid, ids, directional=0.8)

    db = _db()
    result = svc.build_checkpoint(db)
    db.close()

    assert result["human_available"] is True
    assert result["panel_rankings_recorded"] > 0
    human = result["overall"]["human"]
    assert human is not None
    assert human["candidates"] == 5
    assert human["sim_vs_human"]["directional_accuracy"] == 1.0
    assert human["human_vs_reality"]["directional_accuracy"] == 1.0
    assert result["outcome"] == "strong"


def test_classify_respects_human_mismatch():
    assert svc.classify(5, 0.8, 0.5) == "mixed"
    assert svc.classify(5, 0.8, 0.7) == "strong"
    assert svc.classify(5, 0.8, 0.3) == "weak"
    assert svc.classify(2, 0.9, None) == "insufficient"


def test_checkpoint_endpoints(client):
    cid, _sid, ids = _universe()
    _experiments(cid, ids, directional=0.8)

    preview = client.get("/api/checkpoint/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["outcome"] == "strong"

    created = client.post("/api/checkpoint", json={})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["recommendation"] == "continue"
    assert body["results"]["overall"]["directional_accuracy"] == 0.8

    listing = client.get("/api/checkpoint")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    detail = client.get(f"/api/checkpoint/{body['checkpoint_id']}")
    assert detail.status_code == 200
    assert detail.json()["run_uuid"] == body["run_uuid"]
    assert client.get("/api/checkpoint/999").status_code == 404
