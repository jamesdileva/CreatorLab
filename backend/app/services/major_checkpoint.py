"""Major research checkpoint (roadmap Phase 25).

Question: is the simulated audience actually useful? Compares the simulator
against two baselines — random selection and human judges — overall and across
creators, topics, formats, episode types, and platforms.

Evidence is classified per bucket (strong / mixed / weak / insufficient) and
rolled into one project direction: continue, use selectively, or pivot toward
the fictional-creator ecosystem. No interpretation below the sample gate
(guide §15); human comparison also needs enough common panel candidates.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ..core.metrics import directional_accuracy, kendall_tau, spearman
from ..models.checkpoint import CHECKPOINT_VERSION, MajorCheckpoint
from ..models.creator import Creator
from ..models.episode import Episode
from ..models.experiment import ContentExperiment
from ..models.human_panel import HumanPanelRanking
from ..models.published_video import PublishedVideo
from ..models.series import Series
from ..models.simulation import ViewerReaction
from ..models.video_metrics import VideoMetrics
from .reality_gap_dashboard import MIN_SAMPLES
from .review_service import latest_simulation_for
from .simulation_service import aggregate_reactions

MARGIN = 0.15  # directional must clear 0.5 by this much
HUMAN_RESEMBLANCE = 0.6  # sim resembles humans at/above this
HUMAN_WEAK = 0.45  # sim clearly anti-correlates with humans below this
MIN_HUMAN_CANDIDATES = 5
BUCKETS = ("creator", "topic", "format", "episode_type", "platform")

STRONG = "strong"
MIXED = "mixed"
WEAK = "weak"
INSUFFICIENT = "insufficient"

OUTCOME_TEXT = {
    STRONG: "Strong evidence: continue toward a mature Creator Reality Lab.",
    MIXED: "Mixed evidence: use the simulator selectively, where it has shown lift.",
    WEAK: (
        "Weak evidence: pivot toward an AI fictional creator ecosystem / "
        "episodic storytelling laboratory rather than predictive simulation."
    ),
    INSUFFICIENT: (
        "Insufficient data: collect more experiments before making a direction call."
    ),
}

RECOMMENDATION = {
    STRONG: "continue",
    MIXED: "selective",
    WEAK: "pivot",
    INSUFFICIENT: "collect_more_data",
}


@dataclass
class BucketStats:
    comparisons: int = 0
    directional_sum: float = 0.0
    spearman_sum: float = 0.0
    spearman_count: int = 0
    top1_hits: int = 0

    def add_gap(self, gap: dict) -> None:
        agreement = gap.get("agreement") or {}
        directional = agreement.get("directional_accuracy")
        if directional is not None:
            self.comparisons += 1
            self.directional_sum += directional
            if agreement.get("top_1_match") is True:
                self.top1_hits += 1
        correlation = gap.get("correlation") or {}
        value = correlation.get("spearman")
        if value is not None:
            self.spearman_count += 1
            self.spearman_sum += value


def _topic_of(episode: Episode) -> str:
    import re

    for word in re.findall(r"[A-Za-z][A-Za-z'-]+", episode.premise or ""):
        if len(word) > 5:
            return word.lower()
    return "unknown"


def _episode_info(db: Session, episode: Episode) -> dict[str, str]:
    creator = db.get(Creator, episode.creator_id)
    series = db.get(Series, episode.series_id)
    videos = (
        db.query(PublishedVideo).filter(PublishedVideo.episode_id == episode.id).all()
    )
    duration = max((v.total_duration or 0) for v in videos) if videos else 0
    if duration and duration <= 60:
        fmt = "short"
    elif duration > 60:
        fmt = "long"
    else:
        fmt = "unknown"
    episodes_in_series = (
        db.query(Episode).filter(Episode.series_id == episode.series_id).count()
    )
    return {
        "creator": creator.slug if creator else "unknown",
        "topic": _topic_of(episode),
        "format": fmt,
        "episode_type": "episodic" if episodes_in_series > 1 else "standalone",
        "platform": "youtube" if videos else "none",
    }


def _directional_row(order_a: list[int], order_b: list[int]) -> dict:
    values_a = [float(i) for i in range(len(order_a))]
    pos_b = {cid: i for i, cid in enumerate(order_b)}
    values_b = [float(pos_b[cid]) for cid in order_a]
    return {
        "top_1_match": order_a[0] == order_b[0],
        "directional_accuracy": round(directional_accuracy(order_a, order_b), 3),
        "spearman": round(spearman(values_a, values_b), 3),
        "kendall_tau": round(kendall_tau(values_a, values_b), 3),
        "candidates": len(order_a),
    }


def _real_views(db: Session, episode_id: int) -> int | None:
    videos = (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id == episode_id)
        .order_by(PublishedVideo.id)
        .all()
    )
    latest: dict[int, VideoMetrics] = {}
    for row in db.query(VideoMetrics).order_by(VideoMetrics.id).all():
        latest[row.published_video_id] = row
    views = sum(latest[v.id].views for v in videos if v.id in latest)
    return views if videos else None


def _sim_scores(db: Session, episode_ids: list[int]) -> dict[int, float]:
    scores: dict[int, float] = {}
    for episode_id in episode_ids:
        run = latest_simulation_for(db, episode_id)
        if run is None:
            continue
        reactions = (
            db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
        )
        if reactions:
            scores[episode_id] = aggregate_reactions(reactions)["means"][
                "watch_probability"
            ]
    return scores


def _human_bucket(
    ids: list[int], panel_order: list[int], sim: dict[int, float], real: dict[int, int]
) -> dict | None:
    candidates = [
        cid for cid in ids if cid in sim and cid in real and cid in set(panel_order)
    ]
    if len(candidates) < 2:
        return None
    sim_order = sorted(candidates, key=lambda cid: (-sim[cid], cid))
    human_order = [cid for cid in panel_order if cid in set(candidates)]
    real_order = sorted(candidates, key=lambda cid: (-real[cid], cid))
    return {
        "candidates": len(candidates),
        "sim_vs_human": _directional_row(sim_order, human_order),
        "human_vs_reality": _directional_row(human_order, real_order),
    }


def classify(
    comparisons: int,
    directional: float | None,
    human_directional: float | None,
    min_samples: int = MIN_SAMPLES,
) -> str:
    if comparisons < min_samples or directional is None:
        return INSUFFICIENT
    if directional >= 0.5 + MARGIN and (
        human_directional is None or human_directional >= HUMAN_RESEMBLANCE
    ):
        return STRONG
    if directional <= 0.5 - MARGIN or (
        human_directional is not None and human_directional <= HUMAN_WEAK
    ):
        return WEAK
    return MIXED


def _row(stats: BucketStats, human: dict | None, min_samples: int) -> dict:
    directional = (
        round(stats.directional_sum / stats.comparisons, 3)
        if stats.comparisons
        else None
    )
    human_directional = None
    if human and human["candidates"] >= MIN_HUMAN_CANDIDATES:
        human_directional = human["sim_vs_human"]["directional_accuracy"]
    return {
        "comparisons": stats.comparisons,
        "directional_accuracy": directional,
        "spearman": round(stats.spearman_sum / stats.spearman_count, 3)
        if stats.spearman_count
        else None,
        "top_1_hit_rate": round(stats.top1_hits / stats.comparisons, 3)
        if stats.comparisons
        else None,
        "sample_sufficient": stats.comparisons >= min_samples,
        "sim_vs_random_delta": round(directional - 0.5, 3)
        if directional is not None
        else None,
        "human": human,
        "human_directional_used": human_directional,
        "classification": classify(
            stats.comparisons, directional, human_directional, min_samples
        ),
    }


def build_checkpoint(db: Session, min_samples: int = MIN_SAMPLES) -> dict:
    experiments = (
        db.query(ContentExperiment)
        .filter(ContentExperiment.reality_gap.isnot(None))
        .order_by(ContentExperiment.id)
        .all()
    )

    overall = BucketStats()
    buckets: dict[str, dict[str, BucketStats]] = {name: {} for name in BUCKETS}
    info_cache: dict[int, dict[str, str] | None] = {}

    for experiment in experiments:
        gap = experiment.reality_gap or {}
        overall.add_gap(gap)
        episode = db.get(Episode, experiment.episode_id)
        if episode is None:
            continue
        if episode.id not in info_cache:
            info_cache[episode.id] = _episode_info(db, episode)
        info = info_cache[episode.id]
        for name in BUCKETS:
            key = info[name]
            buckets[name].setdefault(key, BucketStats()).add_gap(gap)

    panel = (
        db.query(HumanPanelRanking)
        .filter(HumanPanelRanking.candidate_type == "episode")
        .order_by(HumanPanelRanking.id.desc())
        .first()
    )
    panel_order = list(panel.order) if panel else []
    human_by_bucket: dict[str, dict[str, dict | None]] = {
        name: {} for name in BUCKETS
    }
    overall_human = None
    if panel_order:
        for episode_id in panel_order:
            if episode_id not in info_cache:
                episode = db.get(Episode, episode_id)
                if episode is not None:
                    info_cache[episode_id] = _episode_info(db, episode)
        scored_ids = [eid for eid in panel_order if eid in info_cache]
        sim = _sim_scores(db, scored_ids)
        real = {
            eid: views
            for eid in scored_ids
            if (views := _real_views(db, eid)) is not None
        }
        overall_human = _human_bucket(panel_order, panel_order, sim, real)
        for name in BUCKETS:
            groups: dict[str, list[int]] = {}
            for eid in scored_ids:
                groups.setdefault(info_cache[eid][name], []).append(eid)
            for key, ids in groups.items():
                human_by_bucket[name][key] = _human_bucket(
                    ids, panel_order, sim, real
                )

    rows = {
        name: {
            key: _row(stats, human_by_bucket[name].get(key), min_samples)
            for key, stats in buckets[name].items()
        }
        for name in BUCKETS
    }

    classification_counts = {STRONG: 0, MIXED: 0, WEAK: 0, INSUFFICIENT: 0}
    for dimension in rows.values():
        for row in dimension.values():
            classification_counts[row["classification"]] += 1

    overall_row = _row(overall, overall_human, min_samples)
    outcome = overall_row["classification"]
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_samples": min_samples,
        "experiments_scored": len(experiments),
        "human_available": bool(panel_order),
        "panel_rankings_recorded": panel.id if panel else 0,
        "human_note": (
            f"latest human panel ranking #{panel.id}; comparison needs >= "
            f"{MIN_HUMAN_CANDIDATES} common candidates"
            if panel
            else "no human panel data yet (roadmap Sprint 17.1)"
        ),
        "overall": overall_row,
        "buckets": rows,
        "classification_counts": classification_counts,
        "outcome": outcome,
        "recommendation": RECOMMENDATION[outcome],
        "outcome_text": OUTCOME_TEXT[outcome],
    }


def snapshot_checkpoint(db: Session, min_samples: int = MIN_SAMPLES) -> dict:
    results = build_checkpoint(db, min_samples=min_samples)
    row = MajorCheckpoint(
        run_uuid=str(uuid4()),
        min_samples=min_samples,
        experiments_scored=results["experiments_scored"],
        panel_rankings_recorded=results["panel_rankings_recorded"],
        outcome=results["outcome"],
        recommendation=results["recommendation"],
        results=results,
        prompt_version=CHECKPOINT_VERSION,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return checkpoint_dict(row)


def checkpoint_dict(row: MajorCheckpoint) -> dict:
    return {
        "checkpoint_id": row.id,
        "run_uuid": row.run_uuid,
        "outcome": row.outcome,
        "recommendation": row.recommendation,
        "experiments_scored": row.experiments_scored,
        "panel_rankings_recorded": row.panel_rankings_recorded,
        "min_samples": row.min_samples,
        "prompt_version": row.prompt_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "results": row.results,
    }


def list_checkpoints(db: Session) -> list[MajorCheckpoint]:
    return db.query(MajorCheckpoint).order_by(MajorCheckpoint.id.desc()).all()
