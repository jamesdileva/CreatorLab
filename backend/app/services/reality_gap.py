"""Reality gap — simulator rankings vs real rankings (roadmap Sprint 9.1).

The first question is always relative prediction (architecture §5.3):
did the simulator rank episode A above episode B, and did reality agree?
Absolute forecasting comes later (Phase 15).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..core.metrics import (
    directional_accuracy,
    kendall_tau,
    spearman,
    top_k_agreement,
)
from ..models.episode import Episode
from ..models.experiment import ContentExperiment
from ..models.published_video import PublishedVideo
from ..models.video_metrics import VideoMetrics
from .experiment_service import _latest_series_scores, full_lifecycle


def sim_order_for_series(db: Session, series_id: int) -> list[int]:
    """Episode ids ordered by latest simulated watch mean (best first)."""
    return [eid for eid, _ in _latest_series_scores(db, series_id)]


def _latest_snapshots(db: Session) -> dict[int, VideoMetrics]:
    """Latest metrics row per published video record id."""
    latest: dict[int, VideoMetrics] = {}
    for row in db.query(VideoMetrics).order_by(VideoMetrics.id).all():
        latest[row.published_video_id] = row
    return latest


def real_order_for_series(db: Session, series_id: int) -> list[int]:
    """Episode ids ordered by latest real views (best first, likes break ties)."""
    episodes = (
        db.query(Episode).filter(Episode.series_id == series_id).order_by(Episode.id).all()
    )
    latest = _latest_snapshots(db)
    scored: list[tuple[int, int, int]] = []
    for episode in episodes:
        videos = (
            db.query(PublishedVideo)
            .filter(PublishedVideo.episode_id == episode.id)
            .all()
        )
        best = None
        for video in videos:
            row = latest.get(video.id)
            if row is None:
                continue
            key = (row.views, row.likes)
            if best is None or key > best:
                best = key
        if best is not None:
            scored.append((episode.id, best[0], best[1]))
    scored.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return [eid for eid, _, _ in scored]


def compare_rankings(sim_order: list, real_order: list) -> dict:
    """Compare two best-first orders over the same candidates."""
    sim_ids = set(sim_order)
    real_ids = set(real_order)
    common = [x for x in sim_order if x in real_ids]
    real_sub = [x for x in real_order if x in sim_ids]

    pos_sim = {item: i for i, item in enumerate(sim_order)}
    pos_real = {item: i for i, item in enumerate(real_sub)}
    keys = sorted(common, key=lambda x: (str(type(x)), x))
    sim_vals = [pos_sim[k] for k in keys]
    real_vals = [pos_real[k] for k in keys]

    disagreements: list[dict] = []
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            x, y = common[i], common[j]
            sim_first = pos_sim[x] < pos_sim[y]
            real_first = pos_real[x] < pos_real[y]
            if sim_first != real_first:
                disagreements.append(
                    {
                        "earlier_in_sim": x if sim_first else y,
                        "later_in_sim": y if sim_first else x,
                        "sim_order": f"{x} > {y}" if sim_first else f"{y} > {x}",
                        "real_order": f"{x} > {y}" if real_first else f"{y} > {x}",
                    }
                )

    n = len(common)
    if n < 2:
        correlation = {"spearman": None, "kendall_tau": None}
        agreement = {
            "top_1_match": (common[0] == real_sub[0]) if n == 1 else None,
            "top_k_overlap": None,
            "directional_accuracy": None,
        }
    else:
        correlation = {
            "spearman": round(spearman(sim_vals, real_vals), 3),
            "kendall_tau": round(kendall_tau(sim_vals, real_vals), 3),
        }
        agreement = {
            "top_1_match": common[0] == real_sub[0],
            "top_k_overlap": round(top_k_agreement(common, real_sub, min(3, n)), 3),
            "directional_accuracy": round(directional_accuracy(common, real_sub), 3),
        }

    return {
        "sim_order": list(sim_order),
        "real_order": list(real_order),
        "common_ids": common,
        "sample_size": n,
        "correlation": correlation,
        "agreement": agreement,
        "disagreements": disagreements,
        "rank_deltas": {
            str(item): pos_sim[item] - pos_real[item] for item in common
        },
    }


def compute_reality_gap(db: Session, experiment: ContentExperiment) -> dict:
    """Compare sim vs real for the experiment's series; persist on the row."""
    from .experiment_service import write_notebook_record

    episode = db.get(Episode, experiment.episode_id)
    if episode is None:
        raise ValueError("episode not found")
    sim_order = sim_order_for_series(db, episode.series_id)
    real_order = real_order_for_series(db, episode.series_id)
    if len(set(sim_order) & set(real_order)) < 1:
        raise ValueError("no episode has both a simulation and real metrics yet")

    gap = compare_rankings(sim_order, real_order)
    gap["computed_at"] = datetime.now(timezone.utc).isoformat()
    gap["experiment_id"] = experiment.id
    experiment.reality_gap = gap
    db.commit()
    db.refresh(experiment)
    write_notebook_record(db, experiment)
    return gap


def gap_summary(db: Session, experiment: ContentExperiment) -> dict | None:
    if experiment.reality_gap:
        return dict(experiment.reality_gap)
    return None
