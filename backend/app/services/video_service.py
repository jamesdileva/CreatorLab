"""Simple video renderer — first real video artifacts (roadmap Sprint 5.1).

Storytelling first, not photorealism: title cards + offline TTS voice +
SRT captions + FFmpeg Ken Burns assembly into a 9:16 Short. Every
intermediate artifact is kept for debugging (guide §11).

Character visuals land in Sprint 5.2; this renderer uses stylized cards.
"""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from ..models.episode import Episode, EpisodeStatus
from ..models.scene import Scene

WIDTH, HEIGHT, FPS = 1080, 1920, 30
MIN_DURATION = 15.0  # Shorts verification window: 15-45s
MAX_DURATION = 45.0
SCENE_LEAD = 0.4  # silence before narration starts
SCENE_TAIL = 0.4  # hold after narration ends
FONT_PATH = r"C:\Windows\Fonts\arial.ttf"


class VideoError(RuntimeError):
    """Raised when rendering fails (TTS, FFmpeg, or duration bounds)."""


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise VideoError("ffmpeg not found on PATH")
    return exe


def _ffprobe() -> str:
    exe = shutil.which("ffprobe")
    if exe is None:
        raise VideoError("ffprobe not found on PATH")
    return exe


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def synthesize_speech(
    text: str, wav_path: Path, rate: int = 175, voice_id: str | None = None
) -> Path:
    """Offline TTS (SAPI on Windows). Raises VideoError when no engine works."""
    try:
        import pyttsx3
    except ImportError as exc:
        raise VideoError("pyttsx3 is not installed") from exc
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        if voice_id:
            engine.setProperty("voice", voice_id)
        engine.save_to_file(text, str(wav_path))
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        raise VideoError(f"TTS synthesis failed: {exc}") from exc
    if not wav_path.is_file() or wav_path.stat().st_size == 0:
        raise VideoError("TTS produced no audio file")
    return wav_path


def make_scene_card(
    title: str,
    subtitle: str,
    png_path: Path,
    index: int = 0,
    total: int = 1,
    series_name: str = "",
) -> Path:
    """Stylized 9:16 title card (character art lands in Sprint 5.2)."""
    hue_shift = (index * 37) % 60
    top = (24 + hue_shift // 3, 32, 54)
    bottom = (12, 16, 30)
    img = Image.new("RGB", (WIDTH, HEIGHT), top)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        draw.line(
            [(0, y), (WIDTH, y)],
            fill=tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3)),
        )
    draw.rectangle([60, 760, WIDTH - 60, 770], fill=(255, 200, 80))
    _wrapped(draw, title or f"Scene {index + 1}", 920, 820, _font(84))
    _wrapped(draw, subtitle, 920, 1150, _font(44))
    footer = f"{series_name}  ·  scene {index + 1}/{total}" if series_name else f"scene {index + 1}/{total}"
    draw.text((90, HEIGHT - 220), footer, font=_font(36), fill=(200, 200, 200))
    img.save(png_path)
    return png_path


def _wrapped(
    draw: ImageDraw.ImageDraw, text: str, width: int, y: int, font, fill=(245, 245, 245)
) -> None:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    for i, ln in enumerate(lines[:8]):
        draw.text((90, y + i * 105), ln, font=font, fill=fill)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [_ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise VideoError(f"ffprobe failed on {path.name}: {out.stderr.strip()}")
    try:
        return float(out.stdout.strip())
    except ValueError as exc:
        raise VideoError(f"ffprobe returned no duration for {path.name}") from exc


def _srt_timestamp(seconds: float) -> str:
    ms = int(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list[tuple[float, float, str]], path: Path) -> Path:
    lines = []
    for i, (start, end, text) in enumerate(segments, start=1):
        lines.append(f"{i}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run_ffmpeg(args: list[str], label: str) -> None:
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0:
        raise VideoError(f"ffmpeg {label} failed: {out.stderr.strip()[-800:]}")


def _scene_clip(card: Path, wav: Path, duration: float, out_path: Path) -> None:
    frames = max(1, int(duration * FPS))
    vf = (
        "[0:v]scale=2160:3840,"
        f"zoompan=z='min(1+0.0012*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}[v]"
    )
    _run_ffmpeg(
        [
            _ffmpeg(), "-y",
            "-i", str(card),
            "-i", str(wav),
            "-filter_complex", vf,
            "-map", "[v]", "-map", "1:a",
            "-af", "apad",
            "-t", f"{duration:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "1",
            str(out_path),
        ],
        f"scene clip {out_path.name}",
    )


def _concat(clips: list[Path], list_path: Path, out_path: Path) -> None:
    list_path.write_text(
        "".join(f"file '{c.resolve().as_posix()}'\n" for c in clips), encoding="utf-8"
    )
    _run_ffmpeg(
        [_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
         "-i", str(list_path), "-c", "copy", str(out_path)],
        "concat",
    )


def _burn_subtitles(video_in: Path, srt: Path, out_path: Path) -> None:
    srt_escaped = srt.as_posix().replace(":", r"\:")
    style = (
        "FontName=Arial,FontSize=22,PrimaryColour=&HFFFFFF,"
        "OutlineColour=&H80000000,BorderStyle=1,Outline=2,MarginV=140"
    )
    _run_ffmpeg(
        [
            _ffmpeg(), "-y", "-i", str(video_in),
            "-vf", f"subtitles='{srt_escaped}':force_style='{style}'",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(out_path),
        ],
        "subtitle burn-in",
    )


def render_short(
    scenes: list[dict],
    out_dir: Path,
    voice_id: str | None = None,
    rate: int = 175,
    series_name: str = "",
) -> dict:
    """Render scenes [{title, text}] into a 15-45s Short. Returns the manifest."""
    if not scenes:
        raise VideoError("no scenes to render")
    out_dir.mkdir(parents=True, exist_ok=True)

    planned: list[dict] = []
    for i, scene in enumerate(scenes):
        text = (scene.get("text") or "").strip()
        if not text:
            raise VideoError(f"scene {i + 1} has no narration text")
        wav = out_dir / f"scene_{i + 1:02d}.wav"
        synthesize_speech(text, wav, rate=rate, voice_id=voice_id)
        audio_dur = probe_duration(wav)
        card = out_dir / f"scene_{i + 1:02d}.png"
        make_scene_card(
            scene.get("title") or f"Scene {i + 1}",
            text[:120],
            card,
            index=i,
            total=len(scenes),
            series_name=series_name,
        )
        planned.append(
            {"title": scene.get("title") or f"Scene {i + 1}", "text": text,
             "wav": wav, "card": card, "duration": audio_dur + SCENE_LEAD + SCENE_TAIL}
        )

    total = sum(s["duration"] for s in planned)
    if total < MIN_DURATION:
        planned[-1]["duration"] += MIN_DURATION - total
        total = MIN_DURATION
    if total > MAX_DURATION:
        raise VideoError(
            f"planned duration {total:.1f}s exceeds {MAX_DURATION:.0f}s limit; "
            "shorten the script"
        )

    clips: list[Path] = []
    segments: list[tuple[float, float, str]] = []
    cursor = 0.0
    for i, scene in enumerate(planned):
        clip = out_dir / f"clip_{i + 1:02d}.mp4"
        _scene_clip(scene["card"], scene["wav"], scene["duration"], clip)
        clips.append(clip)
        segments.append((cursor + SCENE_LEAD, cursor + scene["duration"] - SCENE_TAIL, scene["text"]))
        cursor += scene["duration"]

    joined = out_dir / "joined.mp4"
    _concat(clips, out_dir / "concat.txt", joined)
    srt = write_srt(segments, out_dir / "captions.srt")
    final = out_dir / "final.mp4"
    _burn_subtitles(joined, srt, final)
    final_duration = probe_duration(final)

    manifest = {
        "version": "short-renderer-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "voice_id": voice_id,
        "rate": rate,
        "total_duration": round(final_duration, 2),
        "scenes": [
            {
                "title": s["title"],
                "text": s["text"],
                "wav": s["wav"].name,
                "card": s["card"].name,
                "duration": round(s["duration"], 2),
            }
            for s in planned
        ],
        "captions": srt.name,
        "video": final.name,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def render_episode_video(
    db: Session,
    episode_id: int,
    voice_id: str | None = None,
    rate: int = 175,
    base_dir: Path | str = "media/generated",
) -> dict:
    """Full pipeline for one episode: scenes -> audio/cards/captions -> Short."""
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise VideoError("episode not found")
    rows = (
        db.query(Scene)
        .filter(Scene.episode_id == episode_id)
        .order_by(Scene.scene_number)
        .all()
    )
    if rows:
        scenes = [
            {"title": r.title or f"Scene {r.scene_number}", "text": r.direction or episode.premise}
            for r in rows
        ]
        # narration prefers the scene direction; fall back to episode script chunks
        if episode.script.strip():
            chunks = [c.strip() for c in episode.script.split("\n") if c.strip()]
            for i, scene in enumerate(scenes):
                if i < len(chunks):
                    scene["text"] = chunks[i]
    else:
        text = episode.script.strip() or episode.premise.strip()
        if not text:
            raise VideoError("episode has no scenes and no script/premise to narrate")
        scenes = [{"title": episode.title, "text": text}]

    episode.status = EpisodeStatus.RENDERING
    db.commit()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(base_dir) / f"episode_{episode_id}" / stamp
    try:
        manifest = render_short(
            scenes, out_dir, voice_id=voice_id, rate=rate,
            series_name=f"episode {episode.episode_number}",
        )
    except Exception:
        episode.status = EpisodeStatus.REVIEW
        db.commit()
        raise
    manifest["episode_id"] = episode_id
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    episode.status = EpisodeStatus.READY
    db.commit()
    return manifest
