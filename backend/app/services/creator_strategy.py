"""Creator strategy observations (roadmap Sprint 10.2).

Builds differentiated, evidence-backed strategies from distilled performance
summaries (Sprint 10.1): per-creator strengths/weaknesses plus shared
cross-creator patterns ("Both: ..."). Every observation carries its sample
count; shared patterns require at least two creators with sufficient data.
Read-only: unlike distillation, this writes no memories (that is 10.1).
"""
from sqlalchemy.orm import Session

from ..models.creator import Creator
from .performance_memory import MIN_EPISODES, summarize_performance

MIN_CREATORS = 2  # shared patterns need at least this many sufficient creators


def _creator_observations(slug: str, name: str, summary: dict) -> list[dict]:
    observations: list[dict] = []
    for kind in ("topics", "structures"):
        for tag, bucket in summary[kind].items():
            if bucket["verdict"] not in ("strong", "weak"):
                continue
            verb = "performs strongly" if bucket["verdict"] == "strong" else "underperforms"
            observations.append(
                {
                    "scope": "creator",
                    "creator": slug,
                    "kind": kind[:-1],
                    "tag": tag,
                    "verdict": bucket["verdict"],
                    "episodes": bucket["episodes"],
                    "lift": bucket["lift_vs_mean"],
                    "text": (
                        f"{name}: {kind[:-1]} '{tag}' {verb} "
                        f"({bucket['episodes']} episodes, lift {bucket['lift_vs_mean']})."
                    ),
                }
            )
    return observations


def build_strategy(db: Session, min_episodes: int = MIN_EPISODES) -> dict:
    per_creator: dict[str, dict] = {}
    for creator in db.query(Creator).order_by(Creator.id).all():
        summary = summarize_performance(db, creator.id)
        if summary["episodes_with_metrics"] < min_episodes:
            continue
        per_creator[creator.slug] = {
            "creator_id": creator.id,
            "name": creator.name,
            "episodes_with_metrics": summary["episodes_with_metrics"],
            "overall_avg_views": summary["overall_avg_views"],
            "observations": _creator_observations(creator.slug, creator.name, summary),
        }

    # Shared patterns: same (kind, tag, verdict) strong/weak in >=2 creators.
    index: dict[tuple[str, str, str], list[tuple[str, dict]]] = {}
    for slug, entry in per_creator.items():
        seen: set[tuple[str, str, str]] = set()
        for obs in entry["observations"]:
            key = (obs["kind"], obs["tag"], obs["verdict"])
            if key in seen:
                continue
            seen.add(key)
            index.setdefault(key, []).append((slug, obs))
    shared: list[dict] = []
    for (kind, tag, verdict), holders in sorted(index.items()):
        if len(holders) < MIN_CREATORS:
            continue
        episodes = sum(obs["episodes"] for _, obs in holders)
        who = "Both" if len(holders) == 2 else f"{len(holders)} creators"
        verb = "performs strongly" if verdict == "strong" else "underperforms"
        shared.append(
            {
                "scope": "shared",
                "creators": sorted(s for s, _ in holders),
                "kind": kind,
                "tag": tag,
                "verdict": verdict,
                "episodes": episodes,
                "text": (
                    f"{who}: {kind} '{tag}' {verb} "
                    f"({len(holders)} creators, {episodes} episodes)."
                ),
            }
        )

    return {
        "min_episodes": min_episodes,
        "sufficient_creators": len(per_creator),
        "per_creator": per_creator,
        "shared": shared,
        "interpretation_allowed": len(per_creator) >= MIN_CREATORS,
    }
