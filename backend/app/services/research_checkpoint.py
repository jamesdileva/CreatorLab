"""First research checkpoint (roadmap Sprint 9.3).

Question: does the synthetic audience rank episodes better than random
selection? Compares the Sprint 9.2 dashboard's overall simulator numbers
against random baselines (directional 0.5, correlations 0.0, top-1 1/n).

Human-panel comparison is reported as unavailable: no human ranking data
exists in the system yet (roadmap defers human judges to Sprint 17.1), so
the checkpoint answers simulator-vs-random only and says so explicitly.

Guide §15 rule applies: no interpretation below MIN_SAMPLES comparisons.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models.experiment import ContentExperiment
from .reality_gap_dashboard import MIN_SAMPLES, build_dashboard

MARGIN = 0.15  # directional must clear 0.5 by this to claim A or C

OUTCOME_INSUFFICIENT = "insufficient_data"
OUTCOME_A = "A_beats_random"
OUTCOME_B = "B_similar_to_random"
OUTCOME_C = "C_worse_than_random"

HUMAN_NOTE = "no human panel data yet (roadmap Sprint 17.1: human judges)"


def random_baselines(sample_sizes: list[int]) -> dict:
    """Expected random-selection performance for the observed sample sizes."""
    sizes = [n for n in sample_sizes if n and n > 0]
    expected_top1 = round(sum(1.0 / n for n in sizes) / len(sizes), 3) if sizes else None
    return {
        "directional_accuracy": 0.5,
        "spearman": 0.0,
        "kendall_tau": 0.0,
        "top_1_hit_rate": expected_top1,
    }


def compare_to_random(
    directional: float | None,
    comparisons: int,
    min_samples: int = MIN_SAMPLES,
) -> str:
    """Map the headline directional number to a roadmap outcome."""
    if comparisons < min_samples or directional is None:
        return OUTCOME_INSUFFICIENT
    if directional >= 0.5 + MARGIN:
        return OUTCOME_A
    if directional <= 0.5 - MARGIN:
        return OUTCOME_C
    return OUTCOME_B


def build_checkpoint(db: Session, min_samples: int = MIN_SAMPLES) -> dict:
    dashboard = build_dashboard(db, min_samples=min_samples)
    sim = dashboard["overall"]

    sample_sizes: list[int] = []
    for experiment in (
        db.query(ContentExperiment)
        .filter(ContentExperiment.reality_gap.isnot(None))
        .order_by(ContentExperiment.id)
        .all()
    ):
        n = (experiment.reality_gap or {}).get("sample_size")
        if isinstance(n, int) and n > 0:
            sample_sizes.append(n)

    random = random_baselines(sample_sizes)
    verdict = compare_to_random(sim["directional_accuracy"], sim["comparisons"], min_samples)

    def _delta(value: float | None, base: float | None) -> float | None:
        if value is None or base is None:
            return None
        return round(value - base, 3)

    return {
        "generated_at": datetime.now().isoformat(),
        "min_samples": min_samples,
        "experiments_scored": dashboard["experiments_scored"],
        "simulator": sim,
        "random_baseline": random,
        "deltas": {
            "directional": _delta(sim["directional_accuracy"], random["directional_accuracy"]),
            "spearman": _delta(sim["spearman"], random["spearman"]),
            "kendall_tau": _delta(sim["kendall_tau"], random["kendall_tau"]),
            "top_1": _delta(sim["top_1_hit_rate"], random["top_1_hit_rate"]),
        },
        "human_baseline": None,
        "human_note": HUMAN_NOTE,
        "verdict": verdict,
        "interpretation_allowed": verdict != OUTCOME_INSUFFICIENT,
    }
