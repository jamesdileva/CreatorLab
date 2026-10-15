"""Sprint 14.2 — audience lore: recurring reactions identified + promoted to canon."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.lore_service import distill_lore, promote_lore

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
    hank = client.post(
        "/api/creators", json={"name": "Hank", "slug": "hank"}
    ).json()
    series = client.post(
        "/api/series", json={"creator_id": hank["id"], "name": "Hank's World"}
    ).json()
    return hank, series


def _episode(client, series_id, variant, patch_premise=None):
    ep = client.post(
        f"/api/series/{series_id}/generate-episode", json={"variant": variant}
    ).json()["episode"]
    if patch_premise:
        client.patch(f"/api/episodes/{ep['id']}", json={"premise": patch_premise})
        ep = client.get(f"/api/episodes/{ep['id']}").json()
    return ep


def _sim(client, episode_id, watch):
    """Run a simulation then pin the reactions to a fixed watch probability."""
    res = client.post(
        "/api/simulations/run", json={"target_type": "episode", "target_id": episode_id}
    )
    assert res.status_code == 201, res.text
    run_id = res.json()["run"]["id"]
    db = TestingSession()
    from app.models.simulation import ViewerReaction

    db.query(ViewerReaction).filter(ViewerReaction.run_id == run_id).update(
        {"watch_probability": watch}
    )
    db.commit()
    db.close()


# Roadmap verification: the system identifies recurring audience themes.
def test_distill_finds_recurring_theme(client):
    _setup(client)
    # three episodes whose premises share the "old red tractor" phrase
    for i, premise in enumerate(
        [
            "Old Red tractor breaks down before the market run.",
            "Old Red tractor wins the county fair parade.",
            "Old Red tractor gets a suspicious software update.",
        ]
    ):
        ep = _episode(client, client.get("/api/series").json()[0]["id"], i, premise)
        _sim(client, ep["id"], watch=0.7)

    db = TestingSession()
    lore = distill_lore(db)
    db.close()
    themes = {l.theme for l in lore}
    assert "red tractor" in themes or "old tractor" in themes or "tractor breaks" in themes
    picked = [l for l in lore if "tractor" in l.theme][0]
    assert picked.mention_count >= 2
    assert picked.status == "recurring"
    assert picked.avg_watch == pytest.approx(0.7)


def test_single_episode_theme_stays_emerging(client):
    hank, series = _setup(client)
    ep = _episode(client, series["id"], 0, "Rainbow tractor catches the morning bus.")
    _sim(client, ep["id"], watch=0.9)

    db = TestingSession()
    lore = distill_lore(db)
    db.close()
    for entry in lore:
        assert entry.mention_count == 1
        assert entry.status == "emerging"


def test_low_watch_episodes_do_not_create_themes(client):
    hank, series = _setup(client)
    # one watched episode and two ignored ones sharing a different phrase
    watched = _episode(client, series["id"], 0, "Old Red tractor wins the parade.")
    _sim(client, watched["id"], watch=0.8)
    for i in (1, 2):
        ignored = _episode(client, series["id"], i, "Boring spreadsheet bores the barn.")
        _sim(client, ignored["id"], watch=0.05)

    db = TestingSession()
    lore = distill_lore(db)
    db.close()
    themes = {l.theme for l in lore}
    assert any("tractor" in t for t in themes)
    assert not any("spreadsheet" in t or "bores" in t for t in themes)


def test_distill_endpoint_and_listing(client):
    hank, series = _setup(client)
    for i, premise in enumerate(
        ["Old Red tractor stalls.", "Old Red tractor parades."]
    ):
        ep = _episode(client, series["id"], i, premise)
        _sim(client, ep["id"], watch=0.8)

    res = client.post("/api/audience-lore/distill", json={})
    assert res.status_code == 200, res.text
    listed = client.get("/api/audience-lore").json()
    assert any(l["status"] == "recurring" for l in listed)


def test_promote_writes_series_canon(client):
    hank, series = _setup(client)
    for i, premise in enumerate(
        ["Old Red tractor stalls at dawn.", "Old Red tractor parades at noon."]
    ):
        ep = _episode(client, series["id"], i, premise)
        _sim(client, ep["id"], watch=0.8)

    db = TestingSession()
    distilled = distill_lore(db)
    theme = next(l for l in distilled if l.mention_count >= 2)
    canon = promote_lore(db, theme.id)
    db.close()

    assert canon.category.value == "RUNNING_JOKE"
    assert theme.theme in canon.statement
    assert canon.series_id == series["id"]

    # promotion is idempotent
    db = TestingSession()
    again = promote_lore(db, theme.id)
    db.close()
    assert again.id == canon.id

    promoted = client.get("/api/audience-lore").json()
    entry = next(l for l in promoted if l["id"] == theme.id)
    assert entry["status"] == "promoted"
    assert entry["promoted_canon_id"] == canon.id


def test_promote_requires_recurring(client):
    hank, series = _setup(client)
    ep = _episode(client, series["id"], 0, "Lonely tractor misses the parade.")
    _sim(client, ep["id"], watch=0.85)

    db = TestingSession()
    lore = distill_lore(db)
    theme = lore[0]
    with pytest.raises(ValueError, match="still emerging"):
        promote_lore(db, theme.id)
    db.close()


def test_promote_unknown_404(client):
    assert client.post("/api/audience-lore/9999/promote", json={}).status_code == 404


def test_distill_without_runs_is_empty(client):
    _setup(client)
    assert client.post("/api/audience-lore/distill", json={}).json() == []
