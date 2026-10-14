"""Sprint 12.2 — Crash: chaotic absurdist comedic style, distinct from all three."""
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


FOUR = {
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
}


def _seed_four(client):
    db = TestingSession()
    db.add_all(
        [
            Creator(
                name=spec["name"], slug=slug, interests=spec["interests"],
                humor_style=spec["humor_style"], voice_style=spec["voice_style"],
                active=True,
            )
            for slug, spec in FOUR.items()
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


def test_interests_disjoint_across_all_four(client):
    ids = _seed_four(client)
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


def test_four_distinct_humor_styles(client):
    ids = _seed_four(client)
    db = TestingSession()
    humors = [db.get(Creator, cid).humor_style for cid in ids.values()]
    db.close()
    assert len(set(humors)) == 4
    assert "chaotic absurdist" in [h for h in humors if "Crash" in h or "chaotic" in h][0]


def test_crash_identity_defaults_and_visuals(tmp_path, client):
    assert set(DEFAULT_IDENTITIES["crash"]["accessories"]) == {"mohawk"}
    assert set(DEFAULT_IDENTITIES["crash"]["props"]) == {"hammer"}

    ids = _seed_four(client)
    portraits = {}
    for slug, cid in ids.items():
        portraits[slug] = render_portrait(
            _ident_of(cid), tmp_path / f"{slug}.png"
        )
    crash = portraits.pop("crash")
    assert _ident_of(ids["crash"]).display_name == "Crash"
    for slug, other in portraits.items():
        assert _mean_diff(crash, other) > 0.02, slug


def test_voices_distinct_across_all_four(client):
    ids = _seed_four(client)
    texts = []
    for slug in ("hank", "alex-exe", "willow", "crash"):
        res = client.post(
            f"/api/creators/{ids[slug]}/generate",
            json={"user_message": "What did you break this week?"},
        )
        assert res.status_code == 200
        texts.append(res.json()["text"])
    assert len(set(texts)) == 4
    assert "Crash" in texts[3] and "demolition" in texts[3]


def test_crash_memories_retrieved_in_generation(client):
    ids = _seed_four(client)
    client.post(
        f"/api/creators/{ids['crash']}/memories",
        json={
            "type": "RUNNING_JOKE",
            "content": "Crash always breaks the thing he was hired to fix.",
            "importance": 0.5,
        },
    )
    res = client.post(
        f"/api/creators/{ids['crash']}/generate",
        json={"user_message": "How did the demo go?"},
    ).json()
    assert "Crash always breaks the thing he was hired to fix." in res["text"]
    assert res["memories_used"] == [
        "Crash always breaks the thing he was hired to fix."
    ]
