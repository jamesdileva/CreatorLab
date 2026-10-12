"""Analytics collection — periodic snapshots on the metrics ladder (Sprint 8.1).

Cadence (guide §14): 15m / 1h / 6h / 24h / 48h / 7d after the video's
upload_time. The scheduler sweeps videos and snapshots only what's due.
Stats come from the official Data API (videos.list + channels.list);
watch/retention needs the Analytics API and stays nullable until then.
"""
from datetime import datetime, timedelta, timezone

import httpx

from ..integrations.youtube.auth import GoogleOAuthClient, OAuthError
from ..models.published_video import PublishedVideo
from ..models.video_metrics import VideoMetrics
from .youtube_service import access_token_for

# guide §14 offsets after upload_time
METRICS_LADDER = [
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=6),
    timedelta(hours=24),
    timedelta(hours=48),
    timedelta(days=7),
]

VIDEOS_API_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_API_URL = "https://www.googleapis.com/youtube/v3/channels"


class AnalyticsError(OAuthError):
    pass


def _parse_int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def fetch_video_statistics(
    video_id: str,
    channel_id: str,
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
) -> dict:
    """videos.list (statistics) + channels.list (subscriber count)."""
    client = oauth or GoogleOAuthClient()
    token = access_token_for(channel_id, oauth=client)
    transport = http or httpx.Client(timeout=30.0)
    try:
        stats_res = transport.get(
            VIDEOS_API_URL,
            params={"part": "statistics", "id": video_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        stats_res.raise_for_status()
        items = stats_res.json().get("items", [])
        stats = items[0].get("statistics", {}) if items else {}
    except (httpx.HTTPError, IndexError, AttributeError) as exc:
        raise AnalyticsError(f"video statistics lookup failed: {exc}") from exc

    try:
        chan_res = transport.get(
            CHANNELS_API_URL,
            params={"part": "statistics", "id": channel_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        chan_res.raise_for_status()
        chan_items = chan_res.json().get("items", [])
        chan_stats = chan_items[0].get("statistics", {}) if chan_items else {}
    except (httpx.HTTPError, IndexError, AttributeError) as exc:
        raise AnalyticsError(f"channel statistics lookup failed: {exc}") from exc

    return {
        "views": _parse_int(stats.get("viewCount")),
        "likes": _parse_int(stats.get("likeCount")),
        "comments": _parse_int(stats.get("commentCount")),
        "subscriber_count": _parse_int(chan_stats.get("subscriberCount")),
        "raw": {"video": stats, "channel": chan_stats},
    }


def snapshot_video(
    db,
    record_id: int,
    oauth: GoogleOAuthClient | None = None,
    http: httpx.Client | None = None,
) -> VideoMetrics:
    """Fetch + append one snapshot for a published video."""
    from ..models.published_video import PublishedVideo as _PV

    record = db.get(_PV, record_id)
    if record is None:
        raise AnalyticsError("published video not found")
    if not record.video_id:
        raise AnalyticsError("record has no video_id yet")

    stats = fetch_video_statistics(
        record.video_id, record.channel_id, oauth=oauth, http=http
    )
    previous = (
        db.query(VideoMetrics)
        .filter(VideoMetrics.published_video_id == record.id)
        .order_by(VideoMetrics.id.desc())
        .first()
    )
    gained = 0
    if previous is not None:
        gained = max(0, stats["subscriber_count"] - previous.subscriber_count)

    row = VideoMetrics(
        published_video_id=record.id,
        video_id=record.video_id,
        views=stats["views"],
        likes=stats["likes"],
        comments=stats["comments"],
        subscriber_count=stats["subscriber_count"],
        subscribers_gained=gained,
        estimated_minutes_watched=None,  # needs the Analytics API (future)
        raw_json=stats["raw"],
        source="api",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def next_due_offset(
    record: PublishedVideo, snapshots: list[VideoMetrics], now: datetime
) -> timedelta | None:
    """First ladder offset this video has not yet been snapshotted for.

    The Nth snapshot covers ladder[N] (first snapshot = 15m), but only when
    enough time has actually elapsed since upload.
    """
    if record.upload_time is None:
        return None
    upload_time = _as_aware(record.upload_time)
    elapsed = now - upload_time
    if elapsed < timedelta(0):
        return None
    for step in METRICS_LADDER[len(snapshots):]:
        if elapsed >= step:
            return step
    return None


def due_videos(db, now: datetime | None = None) -> list[int]:
    """Published video record ids that have at least one due snapshot."""
    now = now or datetime.now(timezone.utc)
    due: list[int] = []
    for record in db.query(PublishedVideo).filter(PublishedVideo.video_id != "").all():
        snapshots = (
            db.query(VideoMetrics)
            .filter(VideoMetrics.published_video_id == record.id)
            .order_by(VideoMetrics.id)
            .all()
        )
        if next_due_offset(record, snapshots, now) is not None:
            due.append(record.id)
    return due


def collect_due(db, oauth=None, http=None, now: datetime | None = None) -> list[VideoMetrics]:
    """Snapshot every due video. One failure never blocks the rest."""
    now = now or datetime.now(timezone.utc)
    collected: list[VideoMetrics] = []
    for record_id in due_videos(db, now):
        try:
            collected.append(snapshot_video(db, record_id, oauth=oauth, http=http))
        except AnalyticsError:
            continue
    return collected
