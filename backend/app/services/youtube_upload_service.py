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
MAX_PUBLIC = False  # MVP gate: private only until the verification path exists


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
    """Upload one MP4 as PRIVATE and return the video resource."""
    if privacy.lower() not in ("private", "unlisted"):
        raise PublishGateError("MVP uploads are private/unlisted only")
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
        privacy_status="private",
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
        )
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)[:400]
        db.commit()
        raise
    record.video_id = resource["id"]
    record.status = "uploaded"
    record.upload_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record
