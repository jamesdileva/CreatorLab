"""Artificial creator competition — organic-only leaderboard (roadmap Phase 23).

Creators compete on five dimensions derived *only* from real, official
real-world metrics (`VideoMetrics` snapshots):

- growth                — net subscribers gained across published videos
- subscriber_conversion — gained subscribers / views
- retention             — minutes watched / possible minutes (when reported)
- audience_loyalty      — (likes + comments) / views
- episode_performance   — mean views per published video

No artificial engagement: this service never reads the emulator/simulation and
never fabricates likes, views, comments, or subscribers. Interpretation is gated
(guide §15) and the sample size is always reported.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.episode import Episode
from ..models.published_video import PublishedVideo
from ..models.video_metrics import VideoMetrics

COMPETITION_VERSION = "competition-v1"
DIMENSIONS = (
    "growth",
    "subscriber_conversion",
    "retention",
    "audience_loyalty",
    "episode_performance",
)
DIMENSION_LABELS = {
    "growth": "subscriber growth",
    "subscriber_conversion": "subscriber conversion",
    "retention": "retention",
    "audience_loyalty": "audience loyalty (engagement rate)",
    "episode_performance": "episode performance (mean views)",
}
MIN_EPISODES = 2  # published videos with metrics needed to compete
NOTE = (
    "Ranked only on organic real-world metrics from official API snapshots — "
    "never artificial engagement. Do not over-interpret small samples."
)


@dataclass
class CreatorMetrics:
    creator_id: int
    slug: str
    name: str
    videos_with_metrics: int = 0
    total_views: int = 0
    total_likes: int = 0
    total_comments: int = 0
    subscribers_gained: int = 0
    growth: int = 0
    subscriber_conversion: float | None = None
    retention: float | None = None
    audience_loyalty: float | None = None
    episode_performance: float | None = None
    video_ids: list[int] = field(default_factory=list)

    def dimensions(self) -> dict:
        return {
            "growth": self.growth,
            "subscriber_conversion": self.subscriber_conversion,
            "retention": self.retention,
            "audience_loyalty": self.audience_loyalty,
            "episode_performance": self.episode_performance,
        }

    def to_dict(self) -> dict:
        return {
            "creator_id": self.creator_id,
            "slug": self.slug,
            "name": self.name,
            "videos_with_metrics": self.videos_with_metrics,
            "total_views": self.total_views,
            "total_likes": self.total_likes,
            "total_comments": self.total_comments,
            "subscribers_gained": self.subscribers_gained,
            "dimensions": self.dimensions(),
            "video_ids": self.video_ids,
        }


def _latest_metrics(db: Session) -> dict[int, VideoMetrics]:
    """Latest snapshot per published video (append-only table)."""
    latest: dict[int, VideoMetrics] = {}
    for row in db.query(VideoMetrics).order_by(VideoMetrics.id).all():
        latest[row.published_video_id] = row
    return latest


def _ratio(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def creator_metrics(db: Session, creator_id: int) -> CreatorMetrics:
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise ValueError("creator not found")

    episode_ids = [
        e.id for e in db.query(Episode).filter(Episode.creator_id == creator_id).all()
    ]
    videos = (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id.in_(episode_ids))
        .order_by(PublishedVideo.id)
        .all()
        if episode_ids
        else []
    )
    latest = _latest_metrics(db)

    out = CreatorMetrics(creator_id=creator.id, slug=creator.slug, name=creator.name)
    retentions: list[float] = []
    for video in videos:
        metrics = latest.get(video.id)
        if metrics is None:
            continue
        out.videos_with_metrics += 1
        out.video_ids.append(video.id)
        out.total_views += metrics.views
        out.total_likes += metrics.likes
        out.total_comments += metrics.comments
        out.subscribers_gained += metrics.subscribers_gained

        if (
            metrics.estimated_minutes_watched is not None
            and metrics.views > 0
            and video.total_duration > 0
        ):
            possible_minutes = metrics.views * (video.total_duration / 60.0)
            retentions.append(metrics.estimated_minutes_watched / possible_minutes)

    out.growth = out.subscribers_gained
    out.subscriber_conversion = _ratio(out.subscribers_gained, out.total_views)
    out.audience_loyalty = _ratio(
        out.total_likes + out.total_comments, out.total_views
    )
    out.episode_performance = (
        round(out.total_views / out.videos_with_metrics, 1)
        if out.videos_with_metrics
        else None
    )
    out.retention = (
        round(sum(retentions) / len(retentions), 4) if retentions else None
    )
    return out


def _rank(values: dict[int, float | None]) -> dict[int, int]:
    """Rank 1..N, higher is better; ties resolved by creator id for determinism."""
    ranked = sorted(
        ((cid, value) for cid, value in values.items() if value is not None),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return {cid: position for position, (cid, _value) in enumerate(ranked, start=1)}


def build_leaderboard(db: Session, min_episodes: int = MIN_EPISODES) -> dict:
    rows: list[CreatorMetrics] = []
    for creator in db.query(Creator).order_by(Creator.id).all():
        rows.append(creator_metrics(db, creator.id))

    eligible = [
        row
        for row in rows
        if row.videos_with_metrics >= min_episodes and row.total_views > 0
    ]
    eligible_ids = {row.creator_id for row in eligible}

    ranks: dict[str, dict[int, int]] = {
        dimension: _rank({row.creator_id: row.dimensions()[dimension] for row in eligible})
        for dimension in DIMENSIONS
    }

    overall: dict[int, dict] = {}
    for row in eligible:
        dimension_ranks = {
            dimension: ranks[dimension].get(row.creator_id)
            for dimension in DIMENSIONS
            if ranks[dimension].get(row.creator_id) is not None
        }
        composite = (
            round(sum(dimension_ranks.values()) / len(dimension_ranks), 3)
            if dimension_ranks
            else None
        )
        overall[row.creator_id] = {
            "dimension_ranks": dimension_ranks,
            "composite_rank": composite,
            "dimension_coverage": len(dimension_ranks),
        }

    ordered = sorted(
        eligible,
        key=lambda row: (
            overall[row.creator_id]["composite_rank"]
            if overall[row.creator_id]["composite_rank"] is not None
            else float("inf"),
            -overall[row.creator_id]["dimension_coverage"],
            -row.total_views,
            row.creator_id,
        ),
    )
    overall_position = {
        row.creator_id: position for position, row in enumerate(ordered, start=1)
    }

    creators = []
    for row in rows:
        entry = row.to_dict()
        entry["eligible"] = row.creator_id in eligible_ids
        entry["ranks"] = ranks_dimension_view(ranks, row.creator_id)
        entry["composite_rank"] = overall.get(row.creator_id, {}).get("composite_rank")
        entry["dimension_coverage"] = overall.get(row.creator_id, {}).get(
            "dimension_coverage", 0
        )
        entry["overall_rank"] = overall_position.get(row.creator_id)
        creators.append(entry)

    creators.sort(
        key=lambda c: (
            c["overall_rank"] is None,
            c["overall_rank"] or 0,
            c["creator_id"],
        )
    )

    return {
        "competition_version": COMPETITION_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_episodes": min_episodes,
        "dimensions": list(DIMENSIONS),
        "dimension_labels": DIMENSION_LABELS,
        "interpretation_allowed": len(eligible) >= 2,
        "eligible_creators": len(eligible),
        "leader": ordered[0].slug if ordered else None,
        "creators": creators,
        "note": NOTE,
    }


def ranks_dimension_view(
    ranks: dict[str, dict[int, int]], creator_id: int
) -> dict[str, int | None]:
    return {
        dimension: ranks[dimension].get(creator_id) for dimension in DIMENSIONS
    }


def creator_standing(db: Session, creator_id: int, min_episodes: int = MIN_EPISODES) -> dict:
    board = build_leaderboard(db, min_episodes=min_episodes)
    for entry in board["creators"]:
        if entry["creator_id"] == creator_id:
            return entry
    raise ValueError("creator not found")
