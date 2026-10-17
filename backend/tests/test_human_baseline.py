"""Sprint 17.1 — human judges: synthetic vs human panel vs real audience."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.models.episode import Episode
from app.models.human_panel import HumanPanelRanking
from app.models.published_video import PublishedVideo
from app.models.series import Series
from app.models.simulation import SimulationRun, ViewerReaction
from app.models.video_metrics import VideoMetrics
from app.services.human_baseline import (
    MIN_CANDIDATES,
    PanelError,
    judge_comparison,
    record_panel_ranking,
)

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


def _seed_world(n=3):
    db = _db()
    creator = Creator(name="Hank", slug="hank")
    db.add(creator)
    db.flush()
    series = Series(creator_id=creator.id, name="Hank's World")
    db.add(series)
    db.flush()
    ids = []
    for i in range(n):
        episode = Episode(
            creator_id=creator.id,
            series_id=series.id,
            episode_number=i + 1,
            title=f"Ep {i + 1}",
        )
        db.add(episode)
        db.commit()
        db.refresh(episode)
        ids.append(episode.id)
    db.close()
    return ids


def _seed_scores(episode_id, sim_watch=None, real_views=None):
    db = _db()
    if sim_watch is not None:
        run = SimulationRun(target_type="episode", target_id=episode_id)
        db.add(run)
        db.flush()
        db.add(
            ViewerReaction(
                run_id=run.id,
                viewer_id=1,
                watch_probability=sim_watch,
                like_probability=0.5,
                comment_probability=0.1,
                share_probability=0.1,
                follow_probability=0.1,
            )
        )
    if real_views is not None:
        video = PublishedVideo(
            episode_id=episode_id,
            render_id=1,
            channel_id="UC_MOCK",
            video_id=f"vid-{episode_id}",
        )
        db.add(video)
        db.flush()
        db.add(
            VideoMetrics(
                published_video_id=video.id,
                video_id=video.video_id,
                views=real_views,
            )
        )
    db.commit()
    db.close()


# ---------- panel recording ----------


def test_record_rejects_bad_orders(client):
    with pytest.raises(PanelError):
        record_panel_ranking(_db(), "concept", [1, 2])
    with pytest.raises(PanelError):
        record_panel_ranking(_db(), "episode", [1])  # too short
    ids = _seed_world(2)
    with pytest.raises(PanelError):
        record_panel_ranking(_db(), "episode", ids + [999])  # unknown id
    with pytest.raises(PanelError):
        record_panel_ranking(_db(), "episode", [ids[0], ids[0]])  # duplicates


def test_record_persists_ranking(client):
    ids = _seed_world(2)
    row = record_panel_ranking(_db(), "episode", list(reversed(ids)), note="panel A")
    assert row.order == list(reversed(ids))
    assert row.note == "panel A"


# ---------- comparison ----------


def test_full_agreement_on_identical_judgments(client):
    ids = _seed_world(MIN_CANDIDATES)
    # sim rank = ids order (ascending watch), human rank same, views same
    for i, cid in enumerate(ids):
        _seed_scores(cid, sim_watch=0.1 * (i + 1), real_views=100 * (i + 1))
    record_panel_ranking(_db(), "episode", list(reversed(ids)))  # best = highest id

    report = judge_comparison(_db())
    assert report["candidates"] == MIN_CANDIDATES
    assert report["interpretation_allowed"] is True
    for pair in ("synthetic_vs_human", "synthetic_vs_reality", "human_vs_reality"):
        assert report["pairs"][pair]["directional_accuracy"] == 1.0
        assert report["pairs"][pair]["top_1_match"] is True
        assert report["pairs"][pair]["spearman"] == pytest.approx(1.0, abs=1e-3)
    assert "resembles human judgment and the real audience" in report["verdict"]


def test_simulator_diverges_from_human_and_reality(client):
    ids = _seed_world(MIN_CANDIDATES)
    for i, cid in enumerate(ids):
        # sim prefers low ids; humans and reality prefer high ids
        _seed_scores(cid, sim_watch=1.0 - 0.1 * i, real_views=100 * i)
    record_panel_ranking(_db(), "episode", list(reversed(ids)))

    report = judge_comparison(_db())
    sim_human = report["pairs"]["synthetic_vs_human"]
    assert sim_human["top_1_match"] is False
    assert sim_human["directional_accuracy"] < 0.6
    assert "neither human judgment" in report["verdict"]


def test_candidates_missing_a_judge_are_excluded(client):
    ids = _seed_world(3)
    _seed_scores(ids[0], sim_watch=0.9, real_views=100)
    _seed_scores(ids[1], sim_watch=0.5)  # no reality
    _seed_scores(ids[2], real_views=300)  # no simulation
    record_panel_ranking(_db(), "episode", [ids[0], ids[2]])

    report = judge_comparison(_db())
    assert report["candidates"] == 1
    assert report["pairs"] == {}
    marked = {r["episode_id"]: r["judged_by_all_three"] for r in report["candidates_scored"]}
    assert marked[ids[0]] is True
    assert marked[ids[1]] is False
    assert marked[ids[2]] is False
    assert report["verdict"].startswith("insufficient data")


def test_series_filter(client):
    ids = _seed_world(MIN_CANDIDATES)
    for cid in ids:
        _seed_scores(cid, sim_watch=0.5, real_views=100)
    record_panel_ranking(_db(), "episode", list(reversed(ids)))

    assert judge_comparison(_db(), series_id=1)["candidates"] == MIN_CANDIDATES
    assert judge_comparison(_db(), series_id=999)["candidates"] == 0


def test_endpoint_flow(client):
    ids = _seed_world(MIN_CANDIDATES)
    for i, cid in enumerate(ids):
        _seed_scores(cid, sim_watch=0.1 * (i + 1), real_views=100 * (i + 1))

    res = client.post(
        "/api/experiments/human-panel",
        json={"candidate_type": "episode", "order": list(reversed(ids)), "note": "panel"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["order"] == list(reversed(ids))

    bad = client.post(
        "/api/experiments/human-panel",
        json={"candidate_type": "episode", "order": [1]},
    )
    assert bad.status_code == 400

    report = client.get("/api/experiments/judge-comparison").json()
    assert report["candidates"] == MIN_CANDIDATES
    assert report["min_candidates"] == MIN_CANDIDATES
    assert set(report["pairs"]) == {
        "synthetic_vs_human",
        "synthetic_vs_reality",
        "human_vs_reality",
    }
    assert report["orders"]["synthetic"] == list(reversed(ids))
