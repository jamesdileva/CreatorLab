"""Sprint 20.2 — visual/social agent driving the emulator sandbox."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.structured_output import ParseError, parse_agent_action
from app.core.database import Base, get_db
from app.main import app
from app.services import emulator_service as emu
from app.services import visual_agent

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


# ---------- action parsing ----------


def test_parse_agent_action():
    draft = parse_agent_action('{"action": "OPEN", "target_id": 3, "reasoning": "peek"}')
    assert draft.action == "open"
    assert draft.target_id == 3

    fenced = parse_agent_action('```json\n{"action": "stop"}\n```')
    assert fenced.action == "stop"

    with pytest.raises(ParseError):
        parse_agent_action('{"action": "launch_missiles"}')
    with pytest.raises(ParseError):
        parse_agent_action("not json at all")


# ---------- screen rendering ----------


def test_render_screen_lists_posts_and_ids(client):
    db = _db()
    emu.create_account(db, "creator", "Creator", "creator")
    emu.create_account(db, "viewer", "Viewer", "viewer")
    post = emu.create_post(db, "creator", "the video")
    emu.add_comment(db, post.id, "viewer", "first!")

    screen = visual_agent.render_screen(db, emu.get_account(db, "viewer"), post.id)
    assert f"[post #{post.id}]" in screen
    assert "@creator" in screen
    assert "first!" in screen
    assert f"Open post #{post.id}" in screen
    db.close()


# ---------- agent run ----------


def test_run_agent_full_trajectory_with_stub(client):
    db = _db()
    emu.create_account(db, "creator", "Creator", "creator")
    emu.create_account(db, "viewer", "Viewer", "viewer")
    post = emu.create_post(db, "creator", "watch me")

    session = visual_agent.run_agent(db, "viewer", goal="enjoy the feed", max_steps=8)
    assert session.stopped_reason == "stopped"
    assert session.provider == "stub"
    assert session.model == "stub/deterministic-v1"

    detail = visual_agent.session_detail(db, session.id)
    actions = [a["action"] for a in detail["actions"]]
    assert actions == ["scroll", "open", "watch", "comment", "follow", "stop"]
    assert all("observation" in a for a in detail["actions"])
    assert all(a["status"] == "ok" for a in detail["actions"])

    # side effects really happened in the sandbox
    assert emu.post_detail(db, post.id)["engagement"]["views"] == 1
    assert emu.post_detail(db, post.id)["engagement"]["likes"] == 1
    assert emu.post_detail(db, post.id)["engagement"]["comments"] == 1
    assert emu.profile(db, "viewer")["following"] == 1
    db.close()


def test_run_agent_respects_max_steps(client):
    db = _db()
    emu.create_account(db, "creator", "Creator", "creator")
    emu.create_account(db, "viewer", "Viewer", "viewer")
    emu.create_post(db, "creator", "hi")

    session = visual_agent.run_agent(db, "viewer", max_steps=2)
    assert session.stopped_reason == "max_steps"
    assert session.step_count == 2
    assert len(visual_agent.session_detail(db, session.id)["actions"]) == 2
    db.close()


def test_run_agent_empty_feed_stops_cleanly(client):
    db = _db()
    emu.create_account(db, "viewer", "Viewer", "viewer")
    session = visual_agent.run_agent(db, "viewer", max_steps=8)
    actions = [a["action"] for a in visual_agent.session_detail(db, session.id)["actions"]]
    assert actions[-1] == "stop"
    db.close()


def test_run_agent_unknown_account(client):
    db = _db()
    with pytest.raises(ValueError):
        visual_agent.run_agent(db, "ghost")
    db.close()


# ---------- endpoints ----------


def test_agent_endpoints(client):
    client.post("/api/emulator/accounts", json={"handle": "creator", "kind": "creator"})
    client.post("/api/emulator/accounts", json={"handle": "viewer", "kind": "viewer"})
    client.post("/api/emulator/posts", json={"author": "creator", "caption": "hello"})

    run = client.post(
        "/api/emulator/agent/run",
        json={"account": "viewer", "goal": "explore", "max_steps": 8},
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["stopped_reason"] == "stopped"
    assert body["environment"] == "emulator"
    assert len(body["actions"]) >= 5

    listed = client.get("/api/emulator/agent/sessions").json()
    assert listed and listed[0]["id"] == body["id"]

    detail = client.get(f"/api/emulator/agent/sessions/{body['id']}").json()
    assert detail["actions"][0]["action"] == "scroll"
    assert client.get("/api/emulator/agent/sessions/999").status_code == 404
    assert client.post(
        "/api/emulator/agent/run", json={"account": "ghost"}
    ).status_code == 400
