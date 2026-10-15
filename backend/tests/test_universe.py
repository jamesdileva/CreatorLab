"""Sprint 14.1 — universe canon: shared facts keep channels consistent."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.universe import UniverseEntity

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


def _universe(client, kind, name, statement):
    return client.post(
        "/api/universe", json={"kind": kind, "name": name, "statement": statement}
    )


def _creator(client, slug):
    return client.post(
        "/api/creators", json={"name": slug.title(), "slug": slug}
    ).json()


def _series(client, creator_id, name):
    return client.post(
        "/api/series", json={"creator_id": creator_id, "name": name}
    ).json()


# Roadmap verification: episodes across different channels remain consistent.
def test_universe_crud(client):
    created = _universe(
        client, "LOCATION", "The County Fair",
        "The CreatorLab County Fair happens every autumn.",
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["kind"] == "LOCATION"

    listing = client.get("/api/universe").json()
    assert [e["name"] for e in listing] == ["The County Fair"]

    assert client.delete(f"/api/universe/{body['id']}").status_code == 204
    assert client.get("/api/universe").json() == []
    assert client.delete("/api/universe/9999").status_code == 404


def test_universe_validation(client):
    assert _universe(client, "PLANET", "X", "y").status_code == 400
    assert _universe(client, "LOCATION", "", "y").status_code == 400
    assert _universe(client, "LOCATION", "X", "   ").status_code == 400


def test_two_channels_episodes_respect_shared_canon(client):
    """Hank's and Alex.exe's episodes both echo the shared universe fact."""
    hank = _creator(client, "hank")
    alex = _creator(client, "alex-exe")
    _universe(
        client, "OBJECT", "The Town Bell",
        "The town bell rings exactly at noon every day.",
    )

    hank_series = _series(client, hank["id"], "Hank's World")
    alex_series = _series(client, alex["id"], "Alex Optimizes")

    hank_ep = client.post(
        f"/api/series/{hank_series['id']}/generate-episode", json={"variant": 0}
    )
    alex_ep = client.post(
        f"/api/series/{alex_series['id']}/generate-episode", json={"variant": 0}
    )
    for res in (hank_ep, alex_ep):
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["episode"]["status"] == "IDEA"
        # shared universe fact is echoed, so both channels stay consistent
        assert "town bell rings exactly at noon" in body["draft"]["script"]
        # universe canon is never contradicted on either channel
        assert not any(i["code"] == "canon_contradiction" for i in body["issues"])


def test_prompt_versions_expose_v2_and_keep_v1(client):
    versions = client.get("/api/creators/prompts/versions").json()
    assert "episode_prompt_v1" in versions
    assert "episode_prompt_v2" in versions


def test_v1_prompt_renders_unchanged(client):
    from app.ai.prompts import render_episode_prompt
    from app.models.creator import Creator

    db = TestingSession()
    creator = Creator(name="Hank", slug="hank", active=True)
    db.add(creator)
    db.commit()
    db.refresh(creator)

    v1 = render_episode_prompt(
        creator=creator,
        series_name="Hank's World",
        canon=["Old Red is a tractor."],
        memories=[],
        previous_episodes=[],
        open_threads=[],
        next_episode_number=1,
        json_schema="{}",
        version="episode_prompt_v1",
    )
    db.close()
    assert "Old Red is a tractor." in v1
    assert "Universe facts" not in v1  # v1 stays frozen (guide §26)

    v2 = render_episode_prompt(
        creator=creator,
        series_name="Hank's World",
        canon=["Old Red is a tractor."],
        memories=[],
        previous_episodes=[],
        open_threads=[],
        next_episode_number=1,
        json_schema="{}",
        version="episode_prompt_v2",
        universe_facts=["The town bell rings at noon."],
    )
    assert "Universe facts" in v2
    assert "The town bell rings at noon." in v2


def test_cross_episode_includes_universe_canon(client):
    hank = _creator(client, "hank")
    alex = _creator(client, "alex-exe")
    _universe(client, "EVENT", "The Toaster Incident", "Crash jump-started Old Red with a toaster.")
    series = _series(client, hank["id"], "Hank's World")
    client.post(
        "/api/creators/relationships",
        json={"creator_a_id": hank["id"], "creator_b_id": alex["id"]},
    )
    res = client.post(
        f"/api/series/{series['id']}/generate-cross-episode",
        json={"participant_ids": [hank["id"], alex["id"]]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "toaster" in body["draft"]["script"].lower()
    assert body["evaluation_status"] in ("PASS", "REVIEW")


def test_seed_defines_shared_universe():
    """The universe seed carries the shared facts for every channel."""
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "seed_creators.py"
    spec = importlib.util.spec_from_file_location("seed_creators_check", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    kinds = {kind for kind, _, _ in module.SEED_UNIVERSE}
    names = {name for _, name, _ in module.SEED_UNIVERSE}
    assert {"LOCATION", "OBJECT", "EVENT", "RELATIONSHIP", "TIMELINE"} <= kinds
    assert {"The County Fair", "Old Red", "The Seed Library Bus", "Season One"} <= names
    assert len(module.SEED_UNIVERSE) >= 6
