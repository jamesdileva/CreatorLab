"""Story vs meme experiment — does serialized storytelling beat one-off jokes? (16.3).

Content strategy experiment (roadmap 16.3). Research question: does persistent
storytelling produce stronger subscriber / returning-viewer behavior than
disposable content?

Format is classified by serialization: an episode is part of a STORY when its
series holds two or more episodes (an ongoing narrative) and a MEME when its
series is a single one-off. Each format is then compared on real audience
behavior:

- views (reach),
- subscribers_gained (subscription behavior),
- subscriber_conversion = subscribers_gained / views (the practical proxy for a
  returning/subscribing audience).

Honest limitation (recorded in the report): true returning-viewer/retention
metrics need the YouTube Analytics API and remain unavailable (guide §14), so
subscriber conversion is a proxy only. Interpretation is gated (guide §15).
"""
from sqlalchemy.orm import Session

from ..models.episode import Episode
from ..models.published_video import PublishedVideo
from ..models.series import Series
from ..models.video_metrics import VideoMetrics

FORMATS = ("story", "meme")
SERIES_STORY_MIN = 2  # a series with this many episodes counts as storytelling

MIN_TOTAL = 4
MIN_PER_FORMAT = 2

ANALYTICS_NOTE = (
    "returning-viewer/retention metrics need the YouTube Analytics API (not yet "
    "available, guide §14); subscriber_conversion is a proxy"
)


def format_for_series_size(episode_count: int) -> str:
    """A serialized series is a story; a one-off series is a meme."""
    return "story" if episode_count >= SERIES_STORY_MIN else "meme"


def _episode_behavior(db: Session, episode_id: int) -> tuple[int, int] | None:
    """(views, subscribers_gained) from the latest published video, or None."""
    video = (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id == episode_id)
        .order_by(PublishedVideo.id.desc())
        .first()
    )
    if video is None:
        return None
    snapshots = (
        db.query(VideoMetrics)
        .filter(VideoMetrics.published_video_id == video.id)
        .order_by(VideoMetrics.id)
        .all()
    )
    if not snapshots:
        return None
    views = snapshots[-1].views
    gained = sum(max(0, s.subscribers_gained or 0) for s in snapshots)
    return views, gained


def _conversion(subs: int, views: int) -> float | None:
    return round(subs / views, 4) if views else None


def story_vs_meme_report(db: Session, creator_id: int | None = None) -> dict:
    """Compare story vs meme formats on real subscriber/returning behavior."""
    query = db.query(Episode).order_by(Episode.id)
    if creator_id is not None:
        query = query.filter(Episode.creator_id == creator_id)
    episodes = query.all()

    rows: list[dict] = []
    by_format: dict[str, dict] = {
        f: {"views": 0, "subs": 0, "episodes": 0} for f in FORMATS
    }
    skipped = 0
    for episode in episodes:
        series = db.get(Series, episode.series_id)
        if series is None:
            skipped += 1
            continue
        series_size = (
            db.query(Episode).filter(Episode.series_id == episode.series_id).count()
        )
        fmt = format_for_series_size(series_size)
        behavior = _episode_behavior(db, episode.id)
        if behavior is None:
            skipped += 1
            continue
        views, gained = behavior
        by_format[fmt]["views"] += views
        by_format[fmt]["subs"] += gained
        by_format[fmt]["episodes"] += 1
        rows.append(
            {
                "episode_id": episode.id,
                "series_id": episode.series_id,
                "format": fmt,
                "series_size": series_size,
                "views": views,
                "subscribers_gained": gained,
                "subscriber_conversion": _conversion(gained, views),
            }
        )

    summary: dict[str, dict] = {}
    for fmt in FORMATS:
        agg = by_format[fmt]
        n = agg["episodes"]
        summary[fmt] = {
            "episodes": n,
            "total_views": agg["views"],
            "total_subscribers_gained": agg["subs"],
            "mean_views": round(agg["views"] / n, 1) if n else None,
            "mean_subscribers_gained": round(agg["subs"] / n, 2) if n else None,
            "subscriber_conversion": _conversion(agg["subs"], agg["views"]),
            "sufficient": n >= MIN_PER_FORMAT,
        }

    total = len(rows)
    interpretation_allowed = total >= MIN_TOTAL

    higher: str | None = None
    if interpretation_allowed:
        candidates = [
            (fmt, summary[fmt]["subscriber_conversion"])
            for fmt in FORMATS
            if summary[fmt]["subscriber_conversion"] is not None
        ]
        if candidates:
            candidates.sort(key=lambda pair: (-pair[1], FORMATS.index(pair[0])))
            # only a real winner if it is strictly better than the other
            if len(candidates) == 1 or candidates[0][1] > candidates[1][1]:
                higher = candidates[0][0]

    if not interpretation_allowed:
        verdict = "insufficient data — no interpretation (guide §15)"
    elif higher is None:
        verdict = "subscriber conversion is tied — no clear winner yet"
    else:
        verdict = f"{higher} content shows higher subscriber conversion"

    return {
        "formats": list(FORMATS),
        "series_story_min": SERIES_STORY_MIN,
        "min_total": MIN_TOTAL,
        "min_per_format": MIN_PER_FORMAT,
        "episodes_considered": total,
        "episodes_skipped": skipped,
        "interpretation_allowed": interpretation_allowed,
        "analytics_note": ANALYTICS_NOTE,
        "episodes": rows,
        "by_format": summary,
        "higher_subscriber_conversion": higher,
        "verdict": verdict,
    }
