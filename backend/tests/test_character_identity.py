"""Sprint 5.2 — character visual identity: consistent + distinct portraits."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PIL import Image, ImageChops

from app.core.database import Base, get_db
from app.main import app
from app.services.character_service import (
    IDENTITY_VERSION,
    identity_for_creator,
    identity_snapshot,
    render_identity_card,
    render_portrait,
    validate_palette,
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


def _creator(c, name, slug):
    return c.post("/api/creators", json={"name": name, "slug": slug}).json()


def _mean_diff(a: Path, b: Path) -> float:
    """Mean per-pixel channel difference in 0..1 (0 = identical)."""
    from PIL import ImageChops, ImageStat

    with Image.open(a).convert("RGB") as ia, Image.open(b).convert("RGB") as ib:
        stat = ImageStat.Stat(ImageChops.difference(ia, ib))
    return sum(stat.mean) / len(stat.mean) / 255


def _identity(client, slug="hank", name="Hank"):
    creator = _creator(client, name, slug)
    ident = client.get(f"/api/creators/{creator['id']}/identity").json()
    return creator, ident


def test_get_default_identity_for_known_creator(client):
    creator, ident = _identity(client)
    assert ident["version"] == IDENTITY_VERSION
    assert ident["display_name"] == "Hank"
    assert id(ident)  # sanity
    assert set(ident["palette"]) >= {"bg_top", "skin", "shirt", "accent"}
    assert "cap" in ident["accessories"]


def test_identity_is_one_per_creator(client):
    creator, first = _identity(client)
    again = client.get(f"/api/creators/{creator['id']}/identity")
    assert again.json()["id"] == first["id"]


def test_palette_validation(client):
    creator, _ = _identity(client)
    res = client.patch(
        f"/api/creators/{creator['id']}/identity",
        json={"palette": {"skin": "not-a-color"}},
    )
    assert res.status_code == 400
    ok = client.patch(
        f"/api/creators/{creator['id']}/identity",
        json={"palette": {"accent": "#ff0000"}},
    )
    assert ok.status_code == 200
    assert ok.json()["palette"]["accent"] == "#ff0000"


def test_accessory_update(client):
    creator, _ = _identity(client)
    res = client.patch(
        f"/api/creators/{creator['id']}/identity",
        json={"accessories": ["cap", "scarf"], "display_name": "Old Hank"},
    )
    assert res.status_code == 200
    assert res.json()["accessories"] == ["cap", "scarf"]
    assert res.json()["display_name"] == "Old Hank"

    bad = client.patch(
        f"/api/creators/{creator['id']}/identity", json={"display_name": "   "}
    )
    assert bad.status_code == 400


def test_identity_unknown_creator_404(client):
    assert client.get("/api/creators/9999/identity").status_code == 404


def test_render_portrait_is_deterministic_and_distinct(tmp_path, client):
    creator, _ = _identity(client, "hank", "Hank")
    alex, _ = _identity(client, "alex-exe", "Alex.exe")

    def ident_of(creator_id):
        db = TestingSession()
        creator_obj = db.get(
            __import__("app.models", fromlist=["Creator"]).Creator, creator_id
        )
        obj = identity_for_creator(db, creator_obj)
        db.expunge_all()
        return obj

    hank = ident_of(creator["id"])
    alex_ident = ident_of(alex["id"])

    # same identity, same portrait
    p1 = render_portrait(hank, tmp_path / "hank1.png")
    p2 = render_portrait(hank, tmp_path / "hank2.png")
    assert p1.is_file() and p2.is_file()
    assert _mean_diff(p1, p2) == 0.0

    # cross-creator portraits differ substantially
    pa = render_portrait(alex_ident, tmp_path / "alex.png")
    assert _mean_diff(p1, pa) > 0.02


# Roadmap verification: five Hank scenes render recognizably the same character.
def test_five_scenes_consistent_character(tmp_path, client):
    creator, _ = _identity(client, "hank", "Hank")
    from app.models import Creator

    db = TestingSession()
    identity = identity_for_creator(db, db.get(Creator, creator["id"]))
    db.expunge_all()

    scenes = [
        ("Hank sees advertisement", "wide shot of the barn"),
        ("Hank becomes suspicious", "close-up"),
        ("Alex.exe explains features", "side by side"),
        ("Tractor behaves unexpectedly", "fields"),
        ("Hank's reaction", "final beat"),
    ]
    paths = []
    for i, (title, direction) in enumerate(scenes):
        path = tmp_path / f"scene_{i}.png"
        render_identity_card(identity, title, direction, path)
        assert path.is_file()
        with Image.open(path) as img:
            assert img.size == (1080, 1920)
        paths.append(path)

    # pairwise portrait-region consistency: compare top half (character bust)
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            a = paths[i].with_name(paths[i].stem + f"_a{i}.png")
            b = paths[j].with_name(paths[j].stem + f"_b{j}.png")
            with Image.open(paths[i]) as im, Image.open(paths[j]) as im2:
                im.crop((0, 200, 1080, 900)).save(a)
                im2.crop((0, 200, 1080, 900)).save(b)
            # character region identical across scenes (text lives outside the crop)
            assert _mean_diff(a, b) == 0.0


def test_identity_snapshot_records_palette(client):
    creator, _ = _identity(client)
    from app.models import Creator

    db = TestingSession()
    identity = identity_for_creator(db, db.get(Creator, creator["id"]))
    snap = identity_snapshot(identity)
    db.expunge_all()
    assert snap["version"] == IDENTITY_VERSION
    assert "palette" in snap and "accessories" in snap


def test_episode_render_uses_identity(tmp_path, monkeypatch, client):
    import subprocess

    from app.services import video_service

    monkeypatch.setattr(
        video_service,
        "synthesize_speech",
        lambda text, wav_path, **kw: (
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                 "-ar", "44100", "-ac", "1", str(wav_path)],
                capture_output=True, check=True,
            )
            or wav_path
        ),
    )
    creator = _creator(client, "Hank", "hank")
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": "Hank's World"}
    ).json()
    episode = client.post(
        f"/api/series/{series['id']}/generate-episode", json={"variant": 0}
    ).json()["episode"]

    res = client.post(f"/api/episodes/{episode['id']}/render", json={})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "READY"

    detail = client.get(f"/api/episodes/{episode['id']}").json()
    assert detail["status"] == "READY"
