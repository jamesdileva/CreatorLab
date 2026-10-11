"""Sprint 5.1 — video renderer: cards, captions, FFmpeg assembly, episode render."""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services import video_service
from app.services.video_service import (
    MAX_DURATION,
    MIN_DURATION,
    VideoError,
    make_scene_card,
    probe_duration,
    render_episode_video,
    render_short,
    write_srt,
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
def client(tmp_path, monkeypatch):
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    media = tmp_path / "media"
    monkeypatch.chdir(tmp_path)
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _sine_wav(path, seconds=5.0):
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ar", "44100", "-ac", "1", str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


def test_scene_card_dimensions(tmp_path):
    png = tmp_path / "card.png"
    make_scene_card("Hank sees advertisement", "wide shot of the barn", png, 0, 3)
    assert png.is_file()
    from PIL import Image

    with Image.open(png) as img:
        assert img.size == (1080, 1920)


def test_srt_format(tmp_path):
    srt = write_srt([(0.4, 2.5, "hello"), (2.5, 4.0, "world")], tmp_path / "c.srt")
    text = srt.read_text()
    assert "00:00:00,400 --> 00:00:02,500" in text
    assert "hello" in text and "world" in text


def test_probe_duration(tmp_path):
    wav = _sine_wav(tmp_path / "tone.wav", seconds=2.0)
    assert probe_duration(wav) == pytest.approx(2.0, abs=0.1)


def test_render_short_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(
        video_service,
        "synthesize_speech",
        lambda text, wav_path, **kw: _sine_wav(wav_path, seconds=5.0),
    )
    out = tmp_path / "short"
    manifest = render_short(
        [
            {"title": "The breakdown", "text": "Hank finds Old Red dead at dawn."},
            {"title": "The repair", "text": "Hank fixes it with baling wire."},
            {"title": "The delivery", "text": "Old Red makes it, barely."},
        ],
        out,
    )
    final = out / "final.mp4"
    assert final.is_file()
    assert MIN_DURATION <= manifest["total_duration"] <= MAX_DURATION
    assert probe_duration(final) == pytest.approx(manifest["total_duration"], abs=0.5)
    assert (out / "captions.srt").is_file()
    assert (out / "manifest.json").is_file()
    assert len(list(out.glob("scene_*.wav"))) == 3
    assert len(list(out.glob("scene_*.png"))) == 3


def test_render_short_rejects_too_long(tmp_path, monkeypatch):
    monkeypatch.setattr(
        video_service,
        "synthesize_speech",
        lambda text, wav_path, **kw: _sine_wav(wav_path, seconds=20.0),
    )
    with pytest.raises(VideoError, match="exceeds"):
        render_short(
            [{"title": f"s{i}", "text": "x"} for i in range(3)],
            tmp_path / "toolong",
        )


def test_render_short_rejects_empty(tmp_path):
    with pytest.raises(VideoError):
        render_short([], tmp_path / "empty")


def test_render_episode_video_marks_ready(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        video_service,
        "synthesize_speech",
        lambda text, wav_path, **kw: _sine_wav(wav_path, seconds=5.0),
    )
    creator = client.post("/api/creators", json={"name": "Hank", "slug": "hank"}).json()
    series = client.post(
        "/api/series", json={"creator_id": creator["id"], "name": "Hank's World"}
    ).json()
    episode = client.post(
        f"/api/series/{series['id']}/generate-episode", json={"variant": 0}
    ).json()["episode"]

    res = client.post(f"/api/episodes/{episode['id']}/render", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "READY"
    assert MIN_DURATION <= body["total_duration"] <= MAX_DURATION
    assert body["video_url"].endswith("final.mp4")

    detail = client.get(f"/api/episodes/{episode['id']}").json()
    assert detail["status"] == "READY"

    manifest = json.loads(
        (tmp_path / "media" / "generated" / f"episode_{episode['id']}")
        .glob("*/manifest.json")
        .__next__()
        .read_text()
    )
    assert manifest["episode_id"] == episode["id"]


def test_render_unknown_episode_404(client):
    assert client.post("/api/episodes/9999/render", json={}).status_code == 404


def test_tts_smoke(tmp_path):
    try:
        wav = video_service.synthesize_speech(
            "Hank here. Old Red is smarter than any AI.", tmp_path / "tts.wav"
        )
    except VideoError as exc:
        pytest.skip(f"no TTS engine in this environment: {exc}")
    assert probe_duration(wav) > 1.0
