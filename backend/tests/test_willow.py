"""Sprint 12.1 — Willow: distinct humor, interests, visual identity, audience, strategy."""
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


def _seed_three(c):
    db = TestingSession()
    db.add_all(
        [
            Creator(
                name="Hank",
                slug="hank",
                interests=["farming", "trucks", "outdoors", "weather"],
                humor_style="dry, deadpan",
                voice_style="plain-spoken, unhurried, dry delivery",
                active=True,
            ),
            Creator(
                name="Alex.exe",
                slug="alex-exe",
                interests=["AI", "startups", "productivity", "automation"],
                humor_style="absurd corporate-techno-optimism",
                voice_style="rapid, buzzword-dense, upbeat",
                active=True,
            ),
            Creator(
                name="Willow",
                slug="willow",
                interests=[
                    "permaculture", "foraging", "mycology", "herbalism",
                    "off-grid living", "seed saving",
                ],
                humor_style="gentle, earnest nature analogies",
                voice_style="warm, unhurried, earnest, plant metaphors",
                active=True,
            ),
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


def test_interests_disjoint_across_all_three(client):
    ids = _seed_three(client)
    db = TestingSession()
    interests = {
        slug: set(db.get(Creator, cid).interests or [])
        for slug, cid in ids.items()
    }
    db.close()
    assert interests["hank"].isdisjoint(interests["alex-exe"])
    assert interests["hank"].isdisjoint(interests["willow"])
    assert interests["alex-exe"].isdisjoint(interests["willow"])


def test_humor_styles_distinct(client):
    ids = _seed_three(client)
    db = TestingSession()
    humors = [db.get(Creator, cid).humor_style for cid in ids.values()]
    db.close()
    assert len(set(humors)) == 3


def test_willow_identity_defaults(tmp_path, client):
    ids = _seed_three(client)
    ident = _ident_of(ids["willow"])
    assert ident.version == "identity-v1"
    assert ident.display_name == "Willow"
    assert set(ident.accessories) == {"flower"}
    assert set(ident.props) == {"mug"}

    hank = _ident_of(ids["hank"])
    alex = _ident_of(ids["alex-exe"])
    pw = render_portrait(ident, tmp_path / "willow.png")
    ph = render_portrait(hank, tmp_path / "hank.png")
    pa = render_portrait(alex, tmp_path / "alex.png")
    assert _mean_diff(pw, ph) > 0.02
    assert _mean_diff(pw, pa) > 0.02


def test_voices_distinct_across_all_three(client):
    ids = _seed_three(client)
    texts = []
    for slug in ("hank", "alex-exe", "willow"):
        creator = client.get(f"/api/creators/{ids[slug]}").json()
        res = client.post(
            f"/api/creators/{ids[slug]}/generate",
            json={"user_message": "Tell me about your morning routine."},
        )
        assert res.status_code == 200
        texts.append(res.json()["text"])
    assert len(set(texts)) == 3
    assert "Willow" in texts[2] and "permaculture" in texts[2]


def test_willow_memories_retrieved_in_generation(client):
    ids = _seed_three(client)
    client.post(
        f"/api/creators/{ids['willow']}/memories",
        json={
            "type": "RUNNING_JOKE",
            "content": "Willow says the mycelium already invented the internet.",
            "importance": 0.5,
        },
    )
    res = client.post(
        f"/api/creators/{ids['willow']}/generate",
        json={"user_message": "What did you learn this week?"},
    ).json()
    assert "mycelium already invented the internet" in res["text"]
    assert res["memories_used"] == [
        "Willow says the mycelium already invented the internet."
    ]


def test_identity_endpoint_serves_willow(client):
    ids = _seed_three(client)
    body = client.get(f"/api/creators/{ids['willow']}/identity").json()
    assert body["display_name"] == "Willow"
    assert body["version"] == "identity-v1"
