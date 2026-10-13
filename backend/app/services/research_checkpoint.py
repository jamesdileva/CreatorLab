"""First research checkpoint (roadmap Sprint 9.3).

Question: does the synthetic audience rank episodes better than random
selection? Compares the Sprint 9.2 dashboard's simulator numbers against
random baselines, both analytic (directional 0.5, correlations 0.0, top-1 1/n)
and empirical: a seeded random selector shuffling the simulated order and
scored on the same pairwise comparisons.

Human-panel comparison is reported as unavailable: no human ranking data
exists in the system yet (roadmap defers human judges to Sprint 17.1), so
the checkpoint answers simulator-vs-random only and says so explicitly.

Guide §15 rule applies: no interpretation below MIN_SAMPLES comparisons.
"""
import random
from datetime import datetime

from sqlalchemy.orm import Session

from ..core.metrics import directional_accuracy
from ..models.experiment import ContentExperiment
from .reality_gap_dashboard import MIN_SAMPLES, build_dashboard

MARGIN = 0.15  # directional must clear 0.5 by this to claim A or C

OUTCOME_INSUFFICIENT = "insufficient_data"
OUTCOME_A = "A_beats_random"
OUTCOME_B = "B_similar_to_random"
OUTCOME_C = "C_worse_than_random"

HUMAN_NOTE = "no human panel data yet (roadmap Sprint 17.1: human judges)"

RANDOM_TRIALS = 200
RANDOM_SEED = 20261012

VERDICT_TEXT = {
    OUTCOME_INSUFFICIENT: (
        f"Not enough comparisons to judge (need >= {MIN_SAMPLES}). "
        "Collect more experiments before interpreting."
    ),
    OUTCOME_A: (
        "Outcome A: the synthetic audience clearly beats random selection. "
        "Continue improving the simulator."
    ),
    OUTCOME_B: (
        "Outcome B: the synthetic audience performs similarly to random. "
        "Investigate the audience model design."
    ),
    OUTCOME_C: (
        "Outcome C: the synthetic audience performs worse than random. "
        "This is still valuable: reconsider behavioral modeling (architecture §12)."
    ),
}


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


def empirical_random_selector(
    orders: list[tuple[list, list]],
    trials: int = RANDOM_TRIALS,
    seed: int = RANDOM_SEED,
) -> dict:
    """Shuffle each simulated order and score it against the real order.

    `orders` is a list of (sim_order, real_order) pairs. The random selector
    keeps the same candidates but discards the simulator's information; its
    directional accuracy is the average over trials. Deterministic per seed.
    """
    if not orders:
        return {"trials": 0, "directional_accuracy": None, "top_1_hit_rate": None}
    rng = random.Random(seed)
    hits = top1_hits = scored = 0
    for _ in range(trials):
        trial_score = 0.0
        trial_top1 = 0
        counted = 0
        for sim_order, real_order in orders:
            common = [x for x in sim_order if x in set(real_order)]
            if len(common) < 2:
                continue
            shuffled = common[:]
            rng.shuffle(shuffled)
            trial_score += directional_accuracy(shuffled, real_order)
            counted += 1
            if shuffled[0] == real_order[0]:
                trial_top1 += 1
        if counted:
            hits += trial_score / counted
            top1_hits += trial_top1 / counted
            scored += 1
    if not scored:
        return {"trials": scored, "directional_accuracy": None, "top_1_hit_rate": None}
    return {
        "trials": scored,
        "seed": seed,
        "directional_accuracy": round(hits / scored, 3),
        "top_1_hit_rate": round(top1_hits / scored, 3),
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
    orders: list[tuple[list, list]] = []
    for experiment in (
        db.query(ContentExperiment)
        .filter(ContentExperiment.reality_gap.isnot(None))
        .order_by(ContentExperiment.id)
        .all()
    ):
        gap = experiment.reality_gap or {}
        n = gap.get("sample_size")
        if isinstance(n, int) and n > 0:
            sample_sizes.append(n)
        sim_order = gap.get("sim_order") or []
        real_order = gap.get("real_order") or []
        if len(sim_order) >= 2 and len(real_order) >= 2:
            orders.append((sim_order, real_order))

    random = random_baselines(sample_sizes)
    empirical = empirical_random_selector(orders)
    verdict = compare_to_random(sim["directional_accuracy"], sim["comparisons"], min_samples)

    reference = (
        empirical["directional_accuracy"]
        if empirical["directional_accuracy"] is not None
        else random["directional_accuracy"]
    )

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
        "random_selector": empirical,
        "deltas": {
            "directional": _delta(sim["directional_accuracy"], reference),
            "spearman": _delta(sim["spearman"], random["spearman"]),
            "kendall_tau": _delta(sim["kendall_tau"], random["kendall_tau"]),
            "top_1": _delta(
                sim["top_1_hit_rate"],
                empirical["top_1_hit_rate"]
                if empirical["top_1_hit_rate"] is not None
                else random["top_1_hit_rate"],
            ),
        },
        "human_baseline": None,
        "human_note": HUMAN_NOTE,
        "verdict": verdict,
        "verdict_text": VERDICT_TEXT[verdict],
        "interpretation_allowed": verdict != OUTCOME_INSUFFICIENT,
    }
