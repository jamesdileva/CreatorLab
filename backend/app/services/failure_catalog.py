"""Simulation failure catalog — categorize where the simulator is wrong (17.2).

Phase 17 experiment. The reality gap already records, per episode, how far the
simulator's rank was from reality (`rank_deltas`: pos_sim − pos_real, 0 = best).
This service turns those failures into a catalog of weaknesses.

Direction: a negative delta means the simulator ranked the episode BETTER than
reality did (overestimated); a positive delta means it ranked it WORSE
(underestimated).

Category is a documented heuristic over available structured signals — the
episode's hook type (hook_experiment_service), its length bucket
(length_experiment_service), text markers, and the simulation's own reason codes.
Every row keeps its evidence so the classification is auditable; categories are
expected to be refined as more experiments land. Interpretation is gated
(guide §15).
"""
import re

from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.episode import Episode
from ..models.experiment import ContentExperiment
from ..models.simulation import ViewerReaction
from .hook_experiment_service import classify_hook, episode_hook
from .length_experiment_service import episode_length, length_bucket
from .review_service import latest_simulation_for
from .simulation_service import aggregate_reactions

FAILURE_CATEGORIES = (
    "missed_irony",
    "missed_cringe",
    "missed_humor",
    "misread_niche_humor",
    "overestimated_controversy",
    "underestimated_character_attachment",
    "misread_pacing",
    "overestimated_reach",
    "underestimated_reach",
)

MIN_FAILURES = 3

# explicit marker vocabularies (word-boundary matched against episode text)
_MARKERS = {
    "irony": {"ironic", "irony", "sarcasm", "sarcastic", "satire", "satirical", "parody"},
    "cringe": {"cringe", "cringey", "awkward", "embarrassing", "secondhand"},
    "niche": {"niche", "insider", "subculture", "obscure", "trope", "deep-cut"},
    "controversy": {"controversy", "controversial", "outrage", "drama", "banned",
                    "cancel", "heated", "debate"},
    "humor": {"funny", "joke", "humor", "comedy", "comic", "prank", "gag",
              "ridiculous"},
}
_AFFINITY_CODES = {"creator_affinity", "familiar_creator"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z'-]+", (text or "").lower()))


def _creator_names(db: Session) -> tuple[str, ...]:
    names: list[str] = []
    for creator in db.query(Creator).order_by(Creator.id).all():
        full = (creator.name or "").strip()
        if not full:
            continue
        names.append(full)
        first = re.split(r"\s+", full)[0]
        if first and first != full:
            names.append(first)
    return tuple(names)


def _reason_codes(db: Session, episode_id: int) -> set[str]:
    run = latest_simulation_for(db, episode_id)
    if run is None:
        return set()
    reactions = db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
    if not reactions:
        return set()
    return set(aggregate_reactions(reactions)["reason_counts"].keys())


def classify_failure(
    direction: str,
    text_words: set[str],
    hook_type: str,
    length: str | None,
    reasons: set[str],
) -> str:
    """Map a failed episode's signals to a documented failure category."""
    if direction == "over":
        if hook_type == "absurd" or (text_words & _MARKERS["controversy"]):
            return "overestimated_controversy"
        if length == "long":
            return "misread_pacing"
        return "overestimated_reach"

    # direction == "under"
    if text_words & _MARKERS["irony"]:
        return "missed_irony"
    if text_words & _MARKERS["cringe"]:
        return "missed_cringe"
    if text_words & _MARKERS["niche"]:
        return "misread_niche_humor"
    if (text_words & _MARKERS["humor"]) and "humor_match" not in reasons:
        return "missed_humor"
    if reasons & _AFFINITY_CODES:
        return "underestimated_character_attachment"
    if length == "long":
        return "misread_pacing"
    return "underestimated_reach"


def failure_catalog(db: Session, creator_id: int | None = None) -> dict:
    """Aggregate simulator failures from stored reality gaps into a catalog."""
    names = _creator_names(db)
    query = db.query(ContentExperiment).filter(ContentExperiment.reality_gap.isnot(None))
    if creator_id is not None:
        query = query.filter(ContentExperiment.creator_id == creator_id)
    experiments = query.order_by(ContentExperiment.id).all()

    failures: list[dict] = []
    for experiment in experiments:
        gap = experiment.reality_gap or {}
        deltas = gap.get("rank_deltas") or {}
        for raw_id, delta in deltas.items():
            if not delta:
                continue
            episode_id = int(raw_id)
            episode = db.get(Episode, episode_id)
            if episode is None or episode.creator_id != experiment.creator_id:
                continue
            direction = "under" if delta > 0 else "over"
            hook_type = classify_hook(episode_hook(episode), names)
            measured = episode_length(db, episode_id)
            length = length_bucket(measured[0]) if measured else None
            reasons = _reason_codes(db, episode_id)
            category = classify_failure(
                direction,
                _words(f"{episode.title}. {episode.premise}. {episode.synopsis}"),
                hook_type,
                length,
                reasons,
            )
            failures.append(
                {
                    "experiment_id": experiment.id,
                    "episode_id": episode_id,
                    "direction": direction,
                    "rank_delta": delta,
                    "magnitude": abs(delta),
                    "category": category,
                    "hook_type": hook_type,
                    "length_bucket": length,
                    "reason_codes": sorted(reasons),
                }
            )

    catalog: dict[str, dict] = {
        cat: {"count": 0, "over": 0, "under": 0, "examples": []}
        for cat in FAILURE_CATEGORIES
    }
    for failure in failures:
        entry = catalog[failure["category"]]
        entry["count"] += 1
        entry[failure["direction"]] += 1
        if len(entry["examples"]) < 3:
            entry["examples"].append(
                {
                    "experiment_id": failure["experiment_id"],
                    "episode_id": failure["episode_id"],
                    "rank_delta": failure["rank_delta"],
                }
            )

    total = len(failures)
    interpretation_allowed = total >= MIN_FAILURES
    weakness_rank = [
        {"category": cat, "count": data["count"]}
        for cat, data in sorted(
            catalog.items(), key=lambda kv: (-kv[1]["count"], FAILURE_CATEGORIES.index(kv[0]))
        )
        if data["count"] > 0
    ]

    if not interpretation_allowed:
        verdict = "insufficient data — no interpretation (guide §15)"
    elif weakness_rank:
        top = weakness_rank[0]["category"]
        verdict = f"most common simulator weakness: {top} ({weakness_rank[0]['count']} cases)"
    else:
        verdict = "no failures recorded — simulator matches reality so far"

    return {
        "categories": list(FAILURE_CATEGORIES),
        "min_failures": MIN_FAILURES,
        "failures_considered": total,
        "interpretation_allowed": interpretation_allowed,
        "failures": failures,
        "catalog": catalog,
        "weakness_rank": weakness_rank,
        "verdict": verdict,
    }
