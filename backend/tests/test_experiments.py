"""Sprint 8.2 — experiment record: one row + notebook for the whole lifecycle."""
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
def client(tmp_path, monkeypatch):
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    monkeypatch.chdir(tmp_path)
    c = TestClient(app)
    c.creator_id = c.post(  # type: ignore[attr-defined]
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()["id"]
    c.series_id = c.post(  # type: ignore[attr-defined]
        "/api/series", json={"creator_id": c.creator_id, "name": "Hank's World"}
    ).json()["id"]
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _episode(c, variant=0):
    return c.post(
        f"/api/series/{c.series_id}/generate-episode", json={"variant": variant}
    ).json()["episode"]


# Roadmap verification: open one experiment and see the complete lifecycle.
def test_full_lifecycle_payload(client):
    ep1 = _episode(client, 0)
    ep2 = _episode(client, 1)
    for ep in (ep1, ep2):
        client.post(
            "/api/simulations/run",
            json={"target_type": "episode", "target_id": ep["id"]},
        )

    from pathlib import Path

    exp = client.post(
        "/api/experiments",
        json={"episode_id": ep1["id"], "hypothesis": "Hank episodes beat random", "variant": "A"},
    )
    assert exp.status_code == 201, exp.text
    exp_id = exp.json()["id"]

    body = client.get(f"/api/experiments/{exp_id}").json()
    assert body["experiment"]["hypothesis"] == "Hank episodes beat random"
    assert body["experiment"]["variant"] == "A"
    assert body["creator"]["name"] == "Hank"
    assert body["series"]["name"] == "Hank's World"
    assert body["episode"]["title"] == ep1["title"]
    assert body["simulation"] is not None
    assert body["simulation"]["aggregate"]["viewer_count"] == 25
    # relative rank among the two simmed episodes in the series
    assert body["experiment"]["simulation_rank"] in (1, 2)
    assert body["experiment"]["simulation_score"] is not None
    assert body["render"] is None
    assert body["published_video"] is None
    assert body["metrics"] == []
    assert body["experiment"]["reality_gap"] is None


def test_experiment_without_simulation_has_null_links(client):
    ep = _episode(client)
    exp = client.post("/api/experiments", json={"episode_id": ep["id"]}).json()
    assert exp["simulation_run_id"] is None
    assert exp["simulation_score"] is None
    assert exp["simulation_rank"] is None
    assert exp["published_video_id"] is None
    assert exp["real_metrics"] is None

    body = client.get(f"/api/experiments/{exp['id']}").json()
    assert body["simulation"] is None
    assert body["metrics"] == []


def test_notebook_record_written(client, tmp_path):
    ep = _episode(client)
    exp = client.post("/api/experiments", json={"episode_id": ep["id"]}).json()
    from pathlib import Path

    path = Path("docs/experiments") / f"EXPERIMENT-{exp['id']:04d}.md"
    assert path.is_file()
    text = path.read_text()
    assert text.startswith(f"# EXPERIMENT-{exp['id']:04d}")
    assert "Creator: Hank" in text
    assert "Reality gap" in text


def test_notebook_records_links_and_conclusions(client, tmp_path):
    from pathlib import Path

    ep = _episode(client)
    client.post("/api/simulations/run", json={"target_type": "episode", "target_id": ep["id"]})
    exp = client.post(
        "/api/experiments", json={"episode_id": ep["id"], "hypothesis": "h"}
    ).json()
    assert exp["simulation_run_id"] is not None

    conclusions = "Simulator correctly identified the tractor hook."
    res = client.patch(f"/api/experiments/{exp['id']}/conclusions", json={"conclusions": conclusions})
    assert res.status_code == 200
    assert res.json()["conclusions"] == conclusions

    text = (Path("docs/experiments") / f"EXPERIMENT-{exp['id']:04d}.md").read_text()
    assert conclusions in text


def test_experiment_list_filters(client):
    ep1 = _episode(client, 0)
    ep2 = _episode(client, 1)
    e1 = client.post("/api/experiments", json={"episode_id": ep1["id"]}).json()
    client.post("/api/experiments", json={"episode_id": ep2["id"]})

    assert len(client.get("/api/experiments").json()) == 2
    assert [e["id"] for e in client.get(f"/api/experiments?episode_id={ep1['id']}").json()] == [e1["id"]]
    assert len(client.get(f"/api/experiments?creator_id={client.creator_id}").json()) == 2


def test_experiment_unknown_episode_404(client):
    assert client.post("/api/experiments", json={"episode_id": 9999}).status_code == 404
    assert client.get("/api/experiments/9999").status_code == 404
    assert client.patch("/api/experiments/9999/conclusions", json={"conclusions": "x"}).status_code == 404


def test_refresh_relinks_video_and_metrics(client, tmp_path, monkeypatch):
    from datetime import datetime

    from app.models.published_video import PublishedVideo

    ep = _episode(client)
    exp = client.post("/api/experiments", json={"episode_id": ep["id"]}).json()
    assert exp["published_video_id"] is None

    # video + metrics land after the experiment was bound
    db = TestingSession()
    db.add(
        PublishedVideo(
            episode_id=ep["id"], render_id=1, channel_id="UC_X", video_id="vid_x",
            title="t", status="uploaded", upload_time=datetime.now(),
        )
    )
    db.commit()
    db.close()

    refreshed = client.post(f"/api/experiments/{exp['id']}/refresh").json()
    assert refreshed["published_video_id"] is not None
    body = client.get(f"/api/experiments/{exp['id']}").json()
    assert body["published_video"]["video_id"] == "vid_x"
