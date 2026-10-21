"""Large-scale simulation — does a bigger audience predict reality better?

Phase 24 ladder: 25 -> 100 -> 500 -> 1,000 -> 10,000 viewers. The same
episodes are simulated at each size (against a frozen pre-study memory window,
so sizes are comparable), then ranked against real-world views.

The answer is measured, not assumed: each size gets pairwise directional
accuracy, Spearman/Kendall correlations, and a "useful" flag. The minimum
useful size is the smallest size clearing both the comparison-count and
accuracy thresholds.
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ..core.metrics import directional_accuracy, kendall_tau, spearman
from ..models.episode import Episode
from ..models.published_video import PublishedVideo
from ..models.simulation import SimulationRun
from ..models.simulation_scale import SCALE_LADDER, SCALE_VERSION, SimulationScaleStudy
from ..models.video_metrics import VideoMetrics
from ..models.viewer import AUDIENCE_VERSION
from .audience_service import _MAX_COUNT
from .simulation_service import RANK_METRICS, run_simulation

DEFAULT_METRIC = "watch_probability"
DEFAULT_MIN_PAIRS = 3  # 3 episodes => 3 pairwise comparisons
DEFAULT_THRESHOLD = 0.6
STUDY_NOTE = (
    "Larger populations are not assumed to be better. Compare directional "
    "accuracy across sizes; below the comparison threshold results are not "
    "interpretable (guide §15)."
)


def _normalize_sizes(sizes: list[int] | None) -> list[int]:
    chosen = sorted(set(sizes or SCALE_LADDER))
    if not chosen:
        raise ValueError("sizes must not be empty")
    for size in chosen:
        if not 1 <= size <= _MAX_COUNT:
            raise ValueError(f"viewer counts must be between 1 and {_MAX_COUNT}")
    return chosen


def _latest_metrics(db: Session) -> dict[int, VideoMetrics]:
    latest: dict[int, VideoMetrics] = {}
    for row in db.query(VideoMetrics).order_by(VideoMetrics.id).all():
        latest[row.published_video_id] = row
    return latest


def episodes_with_real_metrics(
    db: Session,
    creator_id: int | None = None,
    episode_ids: list[int] | None = None,
) -> list[tuple[Episode, int]]:
    """Episodes with >0 real views, plus summed latest views per episode."""
    query = db.query(Episode).order_by(Episode.id)
    if creator_id is not None:
        query = query.filter(Episode.creator_id == creator_id)
    if episode_ids:
        query = query.filter(Episode.id.in_(episode_ids))

    latest = _latest_metrics(db)
    out: list[tuple[Episode, int]] = []
    for episode in query.all():
        videos = (
            db.query(PublishedVideo)
            .filter(PublishedVideo.episode_id == episode.id)
            .all()
        )
        views = sum(latest[v.id].views for v in videos if v.id in latest)
        if views > 0:
            out.append((episode, views))
    return out


def minimum_useful_size(
    results: list[dict], min_pairs: int, threshold: float
) -> int | None:
    sizes = [
        row["viewer_count"]
        for row in results
        if row.get("comparisons", 0) >= min_pairs
        and row.get("directional_accuracy") is not None
        and row["directional_accuracy"] >= threshold
    ]
    return min(sizes) if sizes else None


def _score(result, metric: str) -> float:
    reactions = result.reactions
    if not reactions:
        return 0.0
    return sum(getattr(r, metric) for r in reactions) / len(reactions)


def run_scale_study(
    db: Session,
    *,
    sizes: list[int] | None = None,
    seed: int = 0,
    metric: str = DEFAULT_METRIC,
    creator_id: int | None = None,
    episode_ids: list[int] | None = None,
    min_pairs: int = DEFAULT_MIN_PAIRS,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    if metric not in RANK_METRICS:
        raise ValueError(f"metric must be one of {list(RANK_METRICS)}")
    if min_pairs < 1:
        raise ValueError("min_pairs must be at least 1")
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    chosen_sizes = _normalize_sizes(sizes)

    episodes = episodes_with_real_metrics(
        db, creator_id=creator_id, episode_ids=episode_ids
    )
    if len(episodes) < 2:
        raise ValueError(
            "scale study needs at least two episodes with real view metrics"
        )

    order_ids = [ep.id for ep, _views in episodes]
    real_by_id = {ep.id: views for ep, views in episodes}
    real_order = sorted(order_ids, key=lambda eid: (-real_by_id[eid], eid))

    # Freeze history before the study so every size sees the same past runs.
    pre_study_runs = {row[0] for row in db.query(SimulationRun.id).all()}

    results: list[dict] = []
    for size in chosen_sizes:
        sim_by_id: dict[int, float] = {}
        run_ids: list[int] = []
        for episode_id in order_ids:
            result = run_simulation(
                db,
                "episode",
                episode_id,
                seed=seed,
                viewer_count=size,
                memory_run_ids=pre_study_runs,
            )
            sim_by_id[episode_id] = _score(result, metric)
            run_ids.append(result.run.id)

        sim_order = sorted(order_ids, key=lambda eid: (-sim_by_id[eid], eid))
        pairs = len(order_ids) * (len(order_ids) - 1) // 2
        directional = round(directional_accuracy(sim_order, real_order), 3)
        results.append(
            {
                "viewer_count": size,
                "episodes": len(order_ids),
                "comparisons": pairs,
                "directional_accuracy": directional,
                "spearman": round(
                    spearman([sim_by_id[e] for e in order_ids],
                             [real_by_id[e] for e in order_ids]),
                    3,
                ),
                "kendall_tau": round(
                    kendall_tau([sim_by_id[e] for e in order_ids],
                                [real_by_id[e] for e in order_ids]),
                    3,
                ),
                "top_1_match": sim_order[0] == real_order[0],
                "mean_sim_score": round(sum(sim_by_id.values()) / len(sim_by_id), 4),
                "simulation_run_ids": run_ids,
                "useful": pairs >= min_pairs and directional >= threshold,
            }
        )

    study = SimulationScaleStudy(
        run_uuid=str(uuid4()),
        metric=metric,
        seed=seed,
        sizes=chosen_sizes,
        episode_ids=order_ids,
        creator_id=creator_id,
        min_pairs=min_pairs,
        threshold=threshold,
        results=results,
        min_useful_viewer_count=minimum_useful_size(results, min_pairs, threshold),
        model="stub/deterministic-v1",
        prompt_version=SCALE_VERSION,
        audience_version=AUDIENCE_VERSION,
    )
    db.add(study)
    db.commit()
    db.refresh(study)
    return study_dict(study)


def study_dict(study: SimulationScaleStudy) -> dict:
    return {
        "study_id": study.id,
        "run_uuid": study.run_uuid,
        "metric": study.metric,
        "seed": study.seed,
        "sizes": study.sizes,
        "episode_ids": study.episode_ids,
        "creator_id": study.creator_id,
        "min_pairs": study.min_pairs,
        "threshold": study.threshold,
        "interpretation_allowed": all(
            row["comparisons"] >= study.min_pairs for row in study.results
        ),
        "min_useful_viewer_count": study.min_useful_viewer_count,
        "results": study.results,
        "model": study.model,
        "prompt_version": study.prompt_version,
        "audience_version": study.audience_version,
        "note": STUDY_NOTE,
        "created_at": study.created_at.isoformat() if study.created_at else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def list_studies(db: Session) -> list[SimulationScaleStudy]:
    return db.query(SimulationScaleStudy).order_by(SimulationScaleStudy.id.desc()).all()
