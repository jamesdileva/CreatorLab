"""Reality-gap dashboard aggregation (roadmap Sprint 9.2).

Aggregates per-experiment gaps into overall + per-creator / per-topic /
per-format simulator accuracy. Guide §15: do not interpret these numbers
until there are enough experiments, so every bucket carries its sample count
and a sufficiency flag (default: >= 5 comparisons).
"""
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.episode import Episode
from ..models.experiment import ContentExperiment

MIN_SAMPLES = 5  # guide §15: no interpretation below this


@dataclass
class GapStats:
    comparisons: int = 0
    directional_sum: float = 0.0
    spearman_sum: float = 0.0
    kendall_sum: float = 0.0
    spearman_count: int = 0
    top1_hits: int = 0
    disagreements: int = 0
    sufficient: bool = False

    def to_dict(self) -> dict:
        n = self.comparisons
        return {
            "comparisons": n,
            "directional_accuracy": round(self.directional_sum / n, 3) if n else None,
            "spearman": round(self.spearman_sum / self.spearman_count, 3)
            if self.spearman_count
            else None,
            "kendall_tau": round(self.kendall_sum / self.spearman_count, 3)
            if self.spearman_count
            else None,
            "top_1_hit_rate": round(self.top1_hits / n, 3) if n else None,
            "disagreements": self.disagreements,
            "sample_sufficient": self.sufficient and n > 0,
        }


def _bucket() -> GapStats:
    return GapStats()


def _record(stats: GapStats, gap: dict) -> None:
    """Fold one experiment's gap into a bucket."""
    agreement = gap.get("agreement") or {}
    directional = agreement.get("directional_accuracy")
    correlations = gap.get("correlation") or {}
    spearman = correlations.get("spearman")
    kendall = correlations.get("kendall_tau")
    if directional is not None:
        stats.comparisons += 1
        stats.directional_sum += directional
        stats.disagreements += len(gap.get("disagreements") or [])
        top1 = agreement.get("top_1_match")
        if top1 is True:
            stats.top1_hits += 1
    if spearman is not None:
        stats.spearman_count += 1
        stats.spearman_sum += spearman
        if kendall is not None:
            stats.kendall_sum += kendall


def _topic_of(episode: Episode) -> str:
    """Cheap topic tag: first meaningful word of the premise (>5 chars)."""
    import re

    for word in re.findall(r"[A-Za-z][A-Za-z'-]+", episode.premise or ""):
        if len(word) > 5:
            return word.lower()
    return "unknown"


def _format_of(gap: dict) -> str:
    """Format bucket heuristic: multi-scene disagreement shape."""
    n = gap.get("sample_size") or 0
    return "episodic" if n >= 3 else "standalone"


def build_dashboard(db: Session, min_samples: int = MIN_SAMPLES) -> dict:
    experiments = (
        db.query(ContentExperiment)
        .filter(ContentExperiment.reality_gap.isnot(None))
        .order_by(ContentExperiment.id)
        .all()
    )
    overall = _bucket()
    per_creator: dict[str, GapStats] = {}
    per_topic: dict[str, GapStats] = {}
    per_format: dict[str, GapStats] = {}

    for experiment in experiments:
        gap = experiment.reality_gap or {}
        _record(overall, gap)

        episode = db.get(Episode, experiment.episode_id)
        if episode is None:
            continue
        creator = db.get(Creator, episode.creator_id)
        if creator is not None:
            per_creator.setdefault(creator.slug, _bucket())
            _record(per_creator[creator.slug], gap)

        per_topic.setdefault(_topic_of(episode), _bucket())
        _record(per_topic[_topic_of(episode)], gap)

        fmt = _format_of(gap)
        per_format.setdefault(fmt, _bucket())
        _record(per_format[fmt], gap)

    for stats in [overall, *per_creator.values(), *per_topic.values(), *per_format.values()]:
        stats.sufficient = stats.comparisons >= min_samples

    scored = [e for e in experiments if e.reality_gap]
    return {
        "generated_at": datetime.now().isoformat(),
        "min_samples": min_samples,
        "experiments_scored": len(scored),
        "overall": overall.to_dict(),
        "per_creator": {k: v.to_dict() for k, v in sorted(per_creator.items())},
        "per_topic": {k: v.to_dict() for k, v in sorted(per_topic.items())},
        "per_format": {k: v.to_dict() for k, v in sorted(per_format.items())},
        "interpretation_allowed": overall.comparisons >= min_samples,
    }
