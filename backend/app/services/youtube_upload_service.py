"""Private video upload — official YouTube Data API only (Sprint 7.2).

MVP publishes PRIVATE only (architecture §17): human approval lands first
(episode must be rendered from an approved script), and public publishing
waits for Sprint 7.4's verification path. Resumable uploads via an injectable
HTTP client so the flow is testable without credentials.
"""
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..integrations.youtube.auth import GoogleOAuthClient, OAuthError
from ..models.episode import Episode, EpisodeStatus
from ..models.published_video import PublishedVideo
from ..models.render import Render
from ..models.youtube_account import YouTubeAccount
from .youtube_service import access_token_for

UPLOAD_SESSION_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
VIDEOS_API_URL = "https://www.googleapis.com/youtube/v3/videos"
THUMBNAILS_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
MAX_PUBLIC = False  # MVP gate: private only until the verification path exists

# YouTube uploadStatus -> our record status (roadmap §7.3)
_UPLOAD_STATUS_MAP = {
    "uploaded": "uploaded",
    "processed": "processed",
    "processed with failures": "processed_with_warnings",
    "failed": "failed",
    "rejected": "rejected",
}


class UploadError(OAuthError):
    pass


class PublishGateError(UploadError):
    pass


def _client(oauth: GoogleOAuthClient | None) -> GoogleOAuthClient:
    return oauth or GoogleOAuthClient()


def start_resumable_session(
    http: httpx.Client,
    access_token: str,
    metadata: dict,
) -> str:
    """Step 1 of the resumable protocol: open the upload session."""
    try:
        res = http.post(
            UPLOAD_SESSION_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(metadata["_size"]),
            },
            json={k: v for k, v in metadata.items() if not k.startswith("_")},
        )
        res.raise_for_status()
        location = res.headers.get("Location")
    except httpx.HTTPError as exc:
        raise UploadError(f"could not start upload session: {exc}") from exc
    if not location:
        raise UploadError("upload session response missing Location header")
    return location


def upload_bytes(http: httpx.Client, session_url: str, data: bytes) -> dict:
    """Step 2: PUT the media to the session URL."""
    try:
        res = http.put(
            session_url,
            content=data,
            headers={"Content-Type": "video/mp4", "Content-Length": str(len(data))},
        )
        res.raise_for_status()
        return res.json()
    except httpx.HTTPError as exc:
        raise UploadError(f"upload PUT failed: {exc}") from exc


def upload_private_video(
    video_path: Path,
    title: str,
    description: str = "",
    channel_id: str = "",
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
    privacy: str = "private",
) -> dict:
    """Upload one MP4 with the requested privacy and return the video resource."""
    privacy = (privacy or "private").lower()
    if privacy not in ("private", "unlisted", "public"):
        raise PublishGateError("unknown privacy status")
    if privacy == "public":
        raise PublishGateError("public publishing needs audit approval (roadmap 7.4)")
    if not video_path.is_file():
        raise UploadError(f"video file not found: {video_path}")
    if not channel_id:
        raise UploadError("channel_id is required for upload")

    client = _client(oauth)
    data = video_path.read_bytes()
    token = access_token_for(channel_id, oauth=client)
    transport_client = http or httpx.Client(timeout=300.0)

    metadata = {
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": privacy.lower()},
        "_size": len(data),
    }
    session = start_resumable_session(transport_client, token, metadata)
    resource = upload_bytes(transport_client, session, data)
    if "id" not in resource:
        raise UploadError("upload response missing video id")
    return resource


def publish_episode(
    db,
    episode_id: int,
    video_path: Path | None = None,
    channel_id: str | None = None,
    privacy: str = "private",
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
) -> PublishedVideo:
    """Publish an approved, rendered episode as a private YouTube video."""
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise PublishGateError("episode not found")
    if episode.status != EpisodeStatus.READY:
        raise PublishGateError(
            "episode must be approved and rendered (READY) before publishing"
        )

    privacy = (privacy or "private").lower()
    if privacy == "public":
        from .publish_policy import policy as _publication_policy

        info = _publication_policy(db)
        if not info["public_automated_uploads_allowed"]:
            raise PublishGateError(
                "public publishing blocked: " + "; ".join(info["blockers"])
            )
    elif privacy not in ("private", "unlisted"):
        raise PublishGateError("unknown privacy status")

    render = (
        db.query(Render)
        .filter(Render.episode_id == episode_id, Render.status == "READY")
        .order_by(Render.id.desc())
        .first()
    )
    if render is None:
        raise PublishGateError("episode has no READY render to publish")

    if video_path is None:
        video_path = Path(render.artifact_dir) / "final.mp4"
    if not video_path.is_file():
        raise UploadError(f"render artifact missing: {video_path}")

    account = None
    if channel_id:
        account = (
            db.query(YouTubeAccount)
            .filter_by(channel_id=channel_id, status="active")
            .one_or_none()
        )
        if account is None:
            raise PublishGateError(f"no active connected channel: {channel_id}")
    else:
        account = db.query(YouTubeAccount).filter_by(status="active").first()
        if account is None:
            raise PublishGateError("no connected YouTube channel — connect one first")

    existing = (
        db.query(PublishedVideo)
        .filter_by(render_id=render.id, channel_id=account.channel_id)
        .first()
    )
    if existing is not None:
        raise PublishGateError("this render is already published")

    description = (
        f"{episode.premise}\n\nEpisode {episode.episode_number}. "
        "Fictional AI-generated content."
    )
    record = PublishedVideo(
        episode_id=episode.id,
        render_id=render.id,
        channel_id=account.channel_id,
        video_id="",
        title=episode.title,
        description=description,
        privacy_status=privacy,
        status="uploading",
        video_size_bytes=video_path.stat().st_size,
        total_duration=render.total_duration,
    )
    db.add(record)
    db.commit()
    try:
        resource = upload_private_video(
            video_path,
            title=episode.title,
            description=description,
            channel_id=account.channel_id,
            oauth=oauth,
            http=http,
            privacy=privacy,
        )
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)[:400]
        db.commit()
        raise
    record.video_id = resource["id"]
    record.status = "uploaded"
    record.youtube_status = "uploaded"
    record.upload_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record


# ---------- Lifecycle (Sprint 7.3) ----------


def fetch_video_status(
    channel_id: str,
    video_id: str,
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
) -> dict:
    """videos.list part=status: uploadStatus, privacy, processing details."""
    client = _client(oauth)
    token = access_token_for(channel_id, oauth=client)
    transport = http or httpx.Client(timeout=30.0)
    try:
        res = transport.get(
            VIDEOS_API_URL,
            params={"part": "status", "id": video_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        res.raise_for_status()
        items = res.json().get("items", [])
    except httpx.HTTPError as exc:
        raise UploadError(f"status lookup failed: {exc}") from exc
    if not items:
        raise UploadError(f"video {video_id} not found on channel {channel_id}")
    item = items[0]
    status = item.get("status", {})
    processing = item.get("processingDetails", {})
    return {
        "upload_status": status.get("uploadStatus", ""),
        "privacy_status": status.get("privacyStatus", ""),
        "processing_status": processing.get("processingStatus", ""),
        "failure_reason": status.get("failureReason", ""),
        "rejection_reason": status.get("rejectionReason", ""),
    }


def _record_for(db, record_id: int) -> PublishedVideo:
    record = db.get(PublishedVideo, record_id)
    if record is None:
        raise PublishGateError("published video not found")
    return record


def refresh_published_status(
    db,
    record_id: int,
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
) -> PublishedVideo:
    """Pull processing/publication state from YouTube into our record."""
    record = _record_for(db, record_id)
    if not record.video_id:
        raise PublishGateError("record has no video_id yet")
    info = fetch_video_status(
        record.channel_id, record.video_id, oauth=oauth, http=http
    )
    mapped = _UPLOAD_STATUS_MAP.get(info["upload_status"].lower(), info["upload_status"])
    record.youtube_status = info["upload_status"] or record.youtube_status
    record.privacy_status = info["privacy_status"] or record.privacy_status
    if mapped and mapped != "failed":
        record.status = mapped
    elif mapped == "failed":
        record.status = "failed"
        record.error = info["failure_reason"] or info["rejection_reason"] or "upload failed"
    db.commit()
    db.refresh(record)
    return record


def retry_publish(
    db,
    record_id: int,
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
) -> PublishedVideo:
    """Re-attempt the upload for a failed publish (roadmap §7.3 retries)."""
    record = _record_for(db, record_id)
    if record.status not in ("failed", "uploading", "rejected"):
        raise PublishGateError(f"cannot retry a record in status {record.status!r}")
    render = db.get(Render, record.render_id)
    if render is None or render.status != "READY":
        raise PublishGateError("the underlying render is not READY")
    video_path = Path(render.artifact_dir) / "final.mp4"
    if not video_path.is_file():
        raise UploadError(f"render artifact missing: {video_path}")

    record.attempts += 1
    record.status = "uploading"
    db.commit()
    try:
        resource = upload_private_video(
            video_path,
            title=record.title,
            description=record.description,
            channel_id=record.channel_id,
            oauth=oauth,
            http=http,
        )
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)[:400]
        db.commit()
        raise
    record.video_id = resource["id"]
    record.status = "uploaded"
    record.youtube_status = "uploaded"
    record.error = ""
    record.upload_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record


def update_video_metadata(
    db,
    record_id: int,
    title: str | None = None,
    description: str | None = None,
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
) -> PublishedVideo:
    """videos.update for title/description (privacy stays private in MVP)."""
    record = _record_for(db, record_id)
    if not record.video_id:
        raise PublishGateError("record has no video_id yet")
    client = _client(oauth)
    token = access_token_for(record.channel_id, oauth=client)
    transport = http or httpx.Client(timeout=30.0)
    payload: dict = {"id": record.video_id}
    if title is not None:
        payload.setdefault("snippet", {})["title"] = title
    if description is not None:
        payload.setdefault("snippet", {})["description"] = description
    if "snippet" not in payload:
        raise PublishGateError("nothing to update")
    try:
        res = transport.put(
            f"{VIDEOS_API_URL}",
            params={"part": "snippet"},
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise UploadError(f"metadata update failed: {exc}") from exc
    if title is not None:
        record.title = title
    if description is not None:
        record.description = description
    db.commit()
    db.refresh(record)
    return record


def extract_thumbnail(video_path: Path, out_path: Path) -> Path:
    """Grab a representative frame with FFmpeg (offline, deterministic)."""
    import shutil
    import subprocess

    if not video_path.is_file():
        raise UploadError(f"video file not found: {video_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        raise UploadError("ffprobe failed for thumbnail extraction")
    try:
        duration = float(probe.stdout.strip() or 0)
    except ValueError:
        duration = 0.0
    midpoint = max(0.0, duration / 2)
    out = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{midpoint:.2f}", "-i", str(video_path),
         "-frames:v", "1", str(out_path)],
        capture_output=True,
    )
    if out.returncode != 0 or not out_path.is_file():
        raise UploadError(f"thumbnail frame extraction failed: {out.stderr[-200:]}")
    return out_path


def set_video_thumbnail(
    db,
    record_id: int,
    thumbnail_path: Path | None = None,
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
) -> PublishedVideo:
    """thumbnails.set for a connected video (extracts a frame if none given)."""
    record = _record_for(db, record_id)
    if not record.video_id:
        raise PublishGateError("record has no video_id yet")
    if thumbnail_path is None:
        render = db.get(Render, record.render_id) if record.render_id else None
        if render is None:
            raise PublishGateError("record has no render to derive a thumbnail from")
        video = Path(render.artifact_dir) / "final.mp4"
        thumbnail_path = Path(render.artifact_dir) / "thumbnail.jpg"
        extract_thumbnail(video, thumbnail_path)
    if not thumbnail_path.is_file():
        raise UploadError(f"thumbnail file missing: {thumbnail_path}")

    client = _client(oauth)
    token = access_token_for(record.channel_id, oauth=client)
    transport = http or httpx.Client(timeout=60.0)
    try:
        res = transport.post(
            THUMBNAILS_URL,
            params={"videoId": record.video_id},
            headers={"Authorization": f"Bearer {token}"},
            content=thumbnail_path.read_bytes(),
        )
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise UploadError(f"thumbnail upload failed: {exc}") from exc
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record
