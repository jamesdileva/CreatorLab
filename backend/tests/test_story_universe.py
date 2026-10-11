"""Sprint 2.1 — story universe: series, episodes, scenes, threads, canon."""
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
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    c = TestClient(app)
    c.hank_id = c.post("/api/creators", json={"name": "Hank", "slug": "hank"}).json()["id"]  # type: ignore[attr-defined]
    c.alex_id = c.post(  # type: ignore[attr-defined]
        "/api/creators", json={"name": "Alex.exe", "slug": "alex-exe"}
    ).json()["id"]
    c.series_id = c.post(  # type: ignore[attr-defined]
        "/api/series", json={"creator_id": c.hank_id, "name": "Hank's World"}
    ).json()["id"]
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _ep(c, n, title, premise=""):
    return c.post(
        f"/api/series/{c.series_id}/episodes",
        json={"title": title, "premise": premise},
    )


# Roadmap verification: create a series with three episodes and retrieve its history.
def test_series_with_three_episodes_history(client):
    r = _ep(client, 1, "Hank discovers AI", "Hank discovers AI.")
    assert r.status_code == 201
    r = _ep(client, 2, "Hank buys an AI tractor", "Hank buys an AI tractor.")
    r = _ep(client, 3, "Hank asks Alex.exe for help", "Hank asks Alex.exe for help.")

    history = client.get(f"/api/series/{client.series_id}/episodes")
    assert history.status_code == 200
    body = history.json()
    assert [e["episode_number"] for e in body] == [1, 2, 3]
    assert [e["title"] for e in body] == [
        "Hank discovers AI",
        "Hank buys an AI tractor",
        "Hank asks Alex.exe for help",
    ]
    assert all(e["status"] == "IDEA" for e in body)
    assert all(e["series_id"] == client.series_id for e in body)
    assert all(e["creator_id"] == client.hank_id for e in body)


def test_episode_numbers_auto_increment(client):
    first = _ep(client, 1, "one").json()
    second = _ep(client, 2, "two").json()
    assert (first["episode_number"], second["episode_number"]) == (1, 2)


def test_explicit_duplicate_episode_number_409(client):
    assert _ep(client, 1, "one").status_code == 201
    dup = client.post(
        f"/api/series/{client.series_id}/episodes",
        json={"title": "dup", "episode_number": 1},
    )
    assert dup.status_code == 409


def test_series_requires_existing_creator(client):
    res = client.post(
        "/api/series", json={"creator_id": 9999, "name": "Nobody's show"}
    )
    assert res.status_code == 404


def test_list_series_filtered_by_creator(client):
    client.post(
        "/api/series", json={"creator_id": client.alex_id, "name": "Alex Optimizes"}
    )
    hank = client.get(f"/api/series?creator_id={client.hank_id}").json()
    assert [s["name"] for s in hank] == ["Hank's World"]


def test_episode_status_lifecycle_and_validation(client):
    episode_id = _ep(client, 1, "ep").json()["id"]
    advanced = client.patch(
        f"/api/episodes/{episode_id}", json={"status": "REVIEW", "synopsis": "s"}
    )
    assert advanced.json()["status"] == "REVIEW"
    assert advanced.json()["synopsis"] == "s"

    bad = client.patch(f"/api/episodes/{episode_id}", json={"status": "TRENDING"})
    assert bad.status_code == 400
    assert "IDEA" in bad.json()["detail"]

    archived = client.delete(f"/api/episodes/{episode_id}")
    assert archived.json()["status"] == "ARCHIVED"
    # archived record stays viewable (history preserved)
    assert client.get(f"/api/episodes/{episode_id}").json()["status"] == "ARCHIVED"


def test_end_series(client):
    ended = client.delete(f"/api/series/{client.series_id}")
    assert ended.json()["status"] == "ENDED"


def test_scenes_ordered(client):
    episode_id = _ep(client, 1, "ep").json()["id"]
    for title, direction in [
        ("Hank sees advertisement", "wide shot of the barn"),
        ("Hank becomes suspicious", "close-up"),
    ]:
        res = client.post(
            f"/api/episodes/{episode_id}/scenes",
            json={"title": title, "direction": direction},
        )
        assert res.status_code == 201
        assert res.json()["scene_number"] in (1, 2)
    scenes = client.get(f"/api/episodes/{episode_id}/scenes").json()
    assert [s["scene_number"] for s in scenes] == [1, 2]
    assert [s["title"] for s in scenes] == ["Hank sees advertisement", "Hank becomes suspicious"]

    dup = client.post(
        f"/api/episodes/{episode_id}/scenes",
        json={"title": "dup", "scene_number": 1},
    )
    assert dup.status_code == 409

    scene_id = scenes[0]["id"]
    assert client.delete(f"/api/scenes/{scene_id}").status_code == 204
    assert len(client.get(f"/api/episodes/{episode_id}/scenes").json()) == 1


def test_story_thread_lifecycle(client):
    ep1 = _ep(client, 1, "one").json()
    ep2 = _ep(client, 2, "two").json()

    thread = client.post(
        f"/api/series/{client.series_id}/threads",
        json={
            "title": "Hank promised never to buy an AI tractor",
            "introduced_episode_id": ep1["id"],
        },
    )
    assert thread.status_code == 201
    assert thread.json()["status"] == "OPEN"

    assert len(client.get(f"/api/series/{client.series_id}/threads?status=OPEN").json()) == 1

    resolved = client.patch(
        f"/api/threads/{thread.json()['id']}",
        json={"status": "RESOLVED", "resolved_episode_id": ep2["id"]},
    )
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_episode_id"] == ep2["id"]
    assert client.get(f"/api/series/{client.series_id}/threads?status=RESOLVED").json()

    # resolving without an episode is rejected
    t2 = client.post(
        f"/api/series/{client.series_id}/threads", json={"title": "new thread"}
    ).json()
    bad = client.patch(f"/api/threads/{t2['id']}", json={"status": "RESOLVED"})
    assert bad.status_code == 400

    # cross-series resolution rejected
    other_series = client.post(
        "/api/series", json={"creator_id": client.alex_id, "name": "other"}
    ).json()
    other_ep = client.post(
        f"/api/series/{other_series['id']}/episodes", json={"title": "other ep"}
    ).json()
    bad_link = client.patch(
        f"/api/threads/{t2['id']}",
        json={"resolved_episode_id": other_ep["id"]},
    )
    assert bad_link.status_code == 400

    assert client.delete(f"/api/threads/{t2['id']}").status_code == 204


def test_canon_crud(client):
    made = client.post(
        f"/api/series/{client.series_id}/canon",
        json={"category": "OBJECT", "statement": "Hank owns Old Red tractor."},
    )
    assert made.status_code == 201
    made2 = client.post(
        f"/api/series/{client.series_id}/canon",
        json={"category": "RUNNING_JOKE", "statement": "Old Red is smarter than AI."},
    )
    assert made2.status_code == 201

    canon = client.get(f"/api/series/{client.series_id}/canon").json()
    assert [c["category"] for c in canon] == ["OBJECT", "RUNNING_JOKE"]

    bad = client.post(
        f"/api/series/{client.series_id}/canon",
        json={"category": "GOSSIP", "statement": "x"},
    )
    assert bad.status_code == 400

    assert client.delete(f"/api/canon/{made.json()['id']}").status_code == 204
    assert len(client.get(f"/api/series/{client.series_id}/canon").json()) == 1


def test_unknown_resources_404(client):
    assert client.get("/api/series/9999").status_code == 404
    assert client.get("/api/series/9999/episodes").status_code == 404
    assert client.get("/api/episodes/9999").status_code == 404
    assert client.get("/api/episodes/9999/scenes").status_code == 404
    assert client.patch("/api/episodes/9999", json={"status": "REVIEW"}).status_code == 404
    assert client.delete("/api/episodes/9999").status_code == 404
    assert client.get("/api/threads/9999").status_code != 200
    assert client.delete("/api/canon/9999").status_code == 404
