"""Episode length experiment — does the simulator pick the preferred length? (16.2).

Content strategy experiment (roadmap 16.2): bucket episodes by their realized
duration, then compare how the synthetic audience (stored simulation watch mean)
and the real audience (latest views) respond to each length.

Duration source: the published video's duration first, then the latest render;
episodes with no measured duration are reported as unknown and skipped.

Honest limitation (recorded in the report): the reaction engine reacts to the
hook text and viewer interest, not to duration directly, and the pipeline
simulates before a render exists — so any length preference here is indirect.
Interpretation is gated (guide §15).
"""
from sqlalchemy.orm import Session

from ..models.episode import Episode
from ..models.published_video import PublishedVideo
from ..models.render import Render
from ..models.simulation import ViewerReaction
from ..models.video_metrics import VideoMetrics
from .review_service import latest_simulation_for
from .simulation_service import aggregate_reactions

# (label, min_inclusive, max_exclusive) — max None = open ended
LENGTH_BUCKETS: tuple[tuple[str, float, float | None], ...] = (
    ("short", 0.0, 30.0),
    ("medium", 30.0, 60.0),
    ("long", 60.0, None),
)

MIN_TOTAL = 4
MIN_PER_TYPE = 2

SIMULATOR_LENGTH_NOTE = (
    "the reaction engine scores hook text + interest only (no duration input); "
    "any length preference is indirect"
)


def length_bucket(seconds: float) -> str:
    for label, low, high in LENGTH_BUCKETS:
        if seconds >= low and (high is None or seconds < high):
            return label
    return LENGTH_BUCKETS[-1][0]


def episode_length(db: Session, episode_id: int) -> tuple[float, str] | None:
    """(seconds, source) from the published video first, then the latest render."""
    published = (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id == episode_id)
        .order_by(PublishedVideo.id.desc())
        .all()
    )
    for video in published:
        if video.total_duration and video.total_duration > 0:
            return round(float(video.total_duration), 2), "published"
    renders = (
        db.query(Render)
        .filter(Render.episode_id == episode_id)
        .order_by(Render.id.desc())
        .all()
    )
    for render in renders:
        if render.total_duration and render.total_duration > 0:
            return round(float(render.total_duration), 2), "render"
    return None


def _sim_watch(db: Session, episode_id: int) -> float | None:
    run = latest_simulation_for(db, episode_id)
    if run is None:
        return None
    reactions = db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
    if not reactions:
        return None
    return aggregate_reactions(reactions)["means"]["watch_probability"]


def _real_views(db: Session, episode_id: int) -> int | None:
    video = (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id == episode_id)
        .order_by(PublishedVideo.id.desc())
        .first()
    )
    if video is None:
        return None
    snap = (
        db.query(VideoMetrics)
        .filter(VideoMetrics.published_video_id == video.id)
        .order_by(VideoMetrics.id.desc())
        .first()
    )
    return snap.views if snap is not None else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def length_experiment_report(db: Session, creator_id: int | None = None) -> dict:
    """Per-length-bucket simulation vs reality comparison across episodes."""
    query = db.query(Episode).order_by(Episode.id)
    if creator_id is not None:
        query = query.filter(Episode.creator_id == creator_id)
    episodes = query.all()

    lengths: list[dict] = []
    grouped: dict[str, dict[str, list]] = {
        label: {"sim": [], "real": []} for label, _, _ in LENGTH_BUCKETS
    }
    unknown = 0
    for episode in episodes:
        measured = episode_length(db, episode.id)
        if measured is None:
            unknown += 1
            continue
        seconds, source = measured
        bucket = length_bucket(seconds)
        sim_watch = _sim_watch(db, episode.id)
        real_views = _real_views(db, episode.id)
        if sim_watch is not None:
            grouped[bucket]["sim"].append(sim_watch)
        if real_views is not None:
            grouped[bucket]["real"].append(real_views)
        lengths.append(
            {
                "episode_id": episode.id,
                "duration_seconds": seconds,
                "source": source,
                "bucket": bucket,
                "sim_watch": sim_watch,
                "real_views": real_views,
            }
        )

    by_bucket: dict[str, dict] = {}
    for label, _, _ in LENGTH_BUCKETS:
        sims = grouped[label]["sim"]
        reals = grouped[label]["real"]
        by_bucket[label] = {
            "episodes": sum(1 for row in lengths if row["bucket"] == label),
            "with_sim": len(sims),
            "with_reality": len(reals),
            "mean_sim_watch": _mean(sims),
            "mean_real_views": _mean([float(v) for v in reals]),
            "sim_sufficient": len(sims) >= MIN_PER_TYPE,
            "reality_sufficient": len(reals) >= MIN_PER_TYPE,
        }

    order = [label for label, _, _ in LENGTH_BUCKETS]

    def preferred(metric: str) -> str | None:
        candidates = [
            (label, by_bucket[label][metric])
            for label in order
            if by_bucket[label][metric] is not None
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda pair: (-pair[1], order.index(pair[0])))
        return candidates[0][0]

    sim_preferred = preferred("mean_sim_watch")
    reality_preferred = preferred("mean_real_views")
    total = sum(
        1 for row in lengths if row["sim_watch"] is not None or row["real_views"] is not None
    )
    interpretation_allowed = total >= MIN_TOTAL
    agreement = (
        sim_preferred == reality_preferred
        if sim_preferred is not None and reality_preferred is not None
        else None
    )

    if not interpretation_allowed:
        verdict = "insufficient data — no interpretation (guide §15)"
    elif agreement is None:
        verdict = "need both simulation and reality samples to compare"
    elif agreement:
        verdict = "simulator agrees with reality on the preferred length"
    else:
        verdict = "simulator and reality disagree on the preferred length"

    return {
        "buckets": order,
        "min_total": MIN_TOTAL,
        "min_per_type": MIN_PER_TYPE,
        "episodes_considered": total,
        "episodes_without_duration": unknown,
        "interpretation_allowed": interpretation_allowed,
        "simulator_note": SIMULATOR_LENGTH_NOTE,
        "lengths": lengths,
        "by_bucket": by_bucket,
        "simulation_preferred": sim_preferred,
        "reality_preferred": reality_preferred,
        "agreement": agreement,
        "verdict": verdict,
    }
