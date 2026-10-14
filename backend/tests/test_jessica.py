"""Sprint 12.3 — Jessica: gaming creator; all five operate independently."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageStat, ImageChops
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models import Creator
from app.services.character_service import (
    DEFAULT_IDENTITIES,
    identity_for_creator,
    render_portrait,
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


FIVE = {
    "hank": {
        "name": "Hank",
        "interests": ["farming", "trucks", "outdoors", "weather"],
        "humor_style": "dry, deadpan",
        "voice_style": "plain-spoken, unhurried, dry delivery",
    },
    "alex-exe": {
        "name": "Alex.exe",
        "interests": ["AI", "startups", "productivity", "automation"],
        "humor_style": "absurd corporate-techno-optimism",
        "voice_style": "rapid, buzzword-dense, upbeat",
    },
    "willow": {
        "name": "Willow",
        "interests": [
            "permaculture", "foraging", "mycology", "herbalism",
            "off-grid living", "seed saving",
        ],
        "humor_style": "gentle, earnest nature analogies",
        "voice_style": "warm, unhurried, earnest, plant metaphors",
    },
    "crash": {
        "name": "Crash",
        "interests": ["slapstick", "demolition derbies", "stunts", "pranks",
                      "junkyard inventions", "fireworks"],
        "humor_style": "chaotic absurdist non-sequiturs",
        "voice_style": "loud, breathless, escalating, mid-bit interruptions",
    },
    "jessica": {
        "name": "Jessica",
        "interests": ["speedrunning", "roguelikes", "co-op", "retro consoles",
                      "esports", "stream chat"],
        "humor_style": "playful competitive trash-talk, affectionate",
        "voice_style": "fast, animated play-by-play with chat callouts",
    },
}


def _seed_five(client):
    db = TestingSession()
    db.add_all(
        [
            Creator(
                name=spec["name"], slug=slug, interests=spec["interests"],
                humor_style=spec["humor_style"], voice_style=spec["voice_style"],
                active=True,
            )
            for slug, spec in FIVE.items()
        ]
    )
    db.commit()
    ids = {c.slug: c.id for c in db.query(Creator).all()}
    db.close()
    return ids


def _mean_diff(a: Path, b: Path) -> float:
    with Image.open(a).convert("RGB") as ia, Image.open(b).convert("RGB") as ib:
        stat = ImageStat.Stat(ImageChops.difference(ia, ib))
    return sum(stat.mean) / len(stat.mean) / 255


def _ident_of(creator_id: int):
    db = TestingSession()
    ident = identity_for_creator(db, db.get(Creator, creator_id))
    db.expunge_all()
    return ident


def test_interests_disjoint_across_all_five(client):
    ids = _seed_five(client)
    db = TestingSession()
    interests = {
        slug: set(db.get(Creator, cid).interests or [])
        for slug, cid in ids.items()
    }
    db.close()
    slugs = list(interests)
    for i in range(len(slugs)):
        for j in range(i + 1, len(slugs)):
            assert interests[slugs[i]].isdisjoint(interests[slugs[j]]), (
                slugs[i], slugs[j]
            )


def test_five_distinct_humor_styles(client):
    ids = _seed_five(client)
    db = TestingSession()
    humors = [db.get(Creator, cid).humor_style for cid in ids.values()]
    db.close()
    assert len(set(humors)) == 5


def test_jessica_identity_defaults_and_visuals(tmp_path, client):
    assert set(DEFAULT_IDENTITIES["jessica"]["accessories"]) == {"headphones"}
    assert set(DEFAULT_IDENTITIES["jessica"]["props"]) == {"controller"}

    ids = _seed_five(client)
    portraits = {
        slug: render_portrait(_ident_of(cid), tmp_path / f"{slug}.png")
        for slug, cid in ids.items()
    }
    assert _ident_of(ids["jessica"]).display_name == "Jessica"
    jessica = portraits.pop("jessica")
    for slug, other in portraits.items():
        assert _mean_diff(jessica, other) > 0.02, slug


def test_voices_distinct_across_all_five(client):
    ids = _seed_five(client)
    texts = []
    for slug in ("hank", "alex-exe", "willow", "crash", "jessica"):
        res = client.post(
            f"/api/creators/{ids[slug]}/generate",
            json={"user_message": "What are you playing this weekend?"},
        )
        assert res.status_code == 200
        texts.append(res.json()["text"])
    assert len(set(texts)) == 5
    assert "Jessica" in texts[4] and "speedrunning" in texts[4]


def test_jessica_memories_retrieved_in_generation(client):
    ids = _seed_five(client)
    client.post(
        f"/api/creators/{ids['jessica']}/memories",
        json={
            "type": "RUNNING_JOKE",
            "content": "Jessica blames lag, then immediately posts the replay.",
            "importance": 0.5,
        },
    )
    res = client.post(
        f"/api/creators/{ids['jessica']}/generate",
        json={"user_message": "How did the run go?"},
    ).json()
    assert "Jessica blames lag, then immediately posts the replay." in res["text"]
    assert res["memories_used"] == [
        "Jessica blames lag, then immediately posts the replay."
    ]


def test_all_five_operate_independently(client):
    """Each creator keeps isolated memories, voices, series, and episodes."""
    ids = _seed_five(client)
    for slug, cid in ids.items():
        client.post(
            f"/api/creators/{cid}/memories",
            json={"type": "CANON", "content": f"{slug} private fact.", "importance": 0.9},
        )
        series = client.post(
            "/api/series", json={"creator_id": cid, "name": f"{slug} show"}
        ).json()
        ep = client.post(
            f"/api/series/{series['id']}/generate-episode", json={"variant": 0}
        ).json()["episode"]
        assert ep["creator_id"] == cid

    for slug, cid in ids.items():
        res = client.post(
            f"/api/creators/{cid}/generate",
            json={"user_message": "Remind me of something only you know."},
        ).json()
        assert res["memories_used"] == [f"{slug} private fact."], slug

    listing = client.get("/api/creators").json()
    assert {c["slug"] for c in listing} == set(FIVE)
