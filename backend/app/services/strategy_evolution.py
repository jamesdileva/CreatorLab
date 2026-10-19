"""Creator strategy evolution (roadmap Sprint 22.1).

Creators can change format mix, topic mix, pacing, episode structure and humor
style — but only on evidence. This service gathers that evidence from existing
experiments/metrics, emits proposals only when the evidence clears a threshold,
and records the change if (and only if) a human approves it.

Constraint (roadmap §22.1): no "the AI thinks this will work". Every proposal's
rationale names the number of prior episodes that support it and the source
report it came from.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.creator_strategy import (
    STRATEGY_VERSION,
    CreatorStrategy,
    StrategyProposal,
)
from .failure_catalog import failure_catalog
from .hook_experiment_service import hook_experiment_report
from .length_experiment_service import length_experiment_report
from .performance_memory import summarize_performance

MIN_EVIDENCE = 3

# Failure-catalog categories that point at a humor-style correction.
_HUMOR_FAILURES = {
    "missed_irony": "lean_irony",
    "misread_niche_humor": "lean_niche_humor",
    "missed_humor": "lean_humor",
    "missed_cringe": "lean_observational",
}


# ---------- current strategy ----------


def get_strategy(db: Session, creator_id: int) -> CreatorStrategy:
    if db.get(Creator, creator_id) is None:
        raise ValueError("creator not found")
    strategy = (
        db.query(CreatorStrategy)
        .filter(CreatorStrategy.creator_id == creator_id)
        .first()
    )
    if strategy is None:
        strategy = CreatorStrategy(creator_id=creator_id)
        db.add(strategy)
        db.commit()
        db.refresh(strategy)
    return strategy


def strategy_dict(strategy: CreatorStrategy) -> dict:
    return {
        "creator_id": strategy.creator_id,
        "topic_mix": strategy.topic_mix or [],
        "format_mix": strategy.format_mix or [],
        "pacing": strategy.pacing,
        "episode_structure": strategy.episode_structure,
        "humor_style": strategy.humor_style,
        "revision": strategy.revision,
        "strategy_version": strategy.strategy_version,
        "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
    }


def proposal_dict(proposal: StrategyProposal) -> dict:
    return {
        "id": proposal.id,
        "creator_id": proposal.creator_id,
        "dimension": proposal.dimension,
        "current_value": proposal.current_value,
        "proposed_value": proposal.proposed_value,
        "rationale": proposal.rationale,
        "evidence": proposal.evidence,
        "evidence_count": proposal.evidence_count,
        "min_evidence": proposal.min_evidence,
        "status": proposal.status,
        "source_version": proposal.source_version,
        "note": proposal.note,
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
    }


# ---------- evidence gathering ----------


def gather_evidence(db: Session, creator_id: int) -> dict[str, list[dict]]:
    """Per-dimension evidence drawn from real performance/experiment reports."""
    if db.get(Creator, creator_id) is None:
        raise ValueError("creator not found")
    evidence: dict[str, list[dict]] = {
        "topic_mix": [],
        "format_mix": [],
        "pacing": [],
        "episode_structure": [],
        "humor_style": [],
    }

    summary = summarize_performance(db, creator_id)
    episodes = summary["episodes"]
    for tag, bucket in summary["topics"].items():
        if bucket["verdict"] != "strong":
            continue
        ids = [r["episode_id"] for r in episodes if r["topic"] == tag]
        evidence["topic_mix"].append(
            {
                "source": "performance_memory",
                "n": bucket["episodes"],
                "ids": ids,
                "value": tag,
                "detail": (
                    f"topic '{tag}' averages {bucket['avg_views']} views "
                    f"({bucket['lift_vs_mean']}x channel mean)"
                ),
            }
        )
    for tag, bucket in summary["structures"].items():
        if bucket["verdict"] != "strong":
            continue
        ids = [r["episode_id"] for r in episodes if r["structure"] == tag]
        evidence["episode_structure"].append(
            {
                "source": "performance_memory",
                "n": bucket["episodes"],
                "ids": ids,
                "value": tag,
                "detail": (
                    f"structure '{tag}' averages {bucket['avg_views']} views "
                    f"({bucket['lift_vs_mean']}x channel mean)"
                ),
            }
        )

    hooks = hook_experiment_report(db, creator_id)
    if hooks["interpretation_allowed"]:
        preferred = hooks["reality_preferred"] or hooks["simulation_preferred"]
        if preferred:
            bucket = hooks["by_type"][preferred]
            ids = [h["episode_id"] for h in hooks["hooks"] if h["hook_type"] == preferred]
            evidence["format_mix"].append(
                {
                    "source": "hook_experiment",
                    "n": bucket["episodes"],
                    "ids": ids,
                    "value": preferred,
                    "detail": (
                        f"hook type '{preferred}' leads "
                        f"(real views {bucket['mean_real_views']}, "
                        f"sim watch {bucket['mean_sim_watch']})"
                    ),
                }
            )

    lengths = length_experiment_report(db, creator_id)
    if lengths["interpretation_allowed"]:
        preferred = lengths["reality_preferred"] or lengths["simulation_preferred"]
        if preferred:
            bucket = lengths["by_bucket"][preferred]
            ids = [r["episode_id"] for r in lengths["lengths"] if r["bucket"] == preferred]
            evidence["pacing"].append(
                {
                    "source": "length_experiment",
                    "n": bucket["episodes"],
                    "ids": ids,
                    "value": preferred,
                    "detail": (
                        f"length '{preferred}' leads "
                        f"(real views {bucket['mean_real_views']})"
                    ),
                }
            )

    catalog = failure_catalog(db, creator_id)
    for category, value in _HUMOR_FAILURES.items():
        entry = catalog["catalog"].get(category)
        if not entry or entry["count"] <= 0:
            continue
        evidence["humor_style"].append(
            {
                "source": "failure_catalog",
                "n": entry["count"],
                "ids": [e["episode_id"] for e in entry["examples"]],
                "value": value,
                "detail": f"{entry['count']} simulator failures in '{category}'",
            }
        )
    return evidence


# ---------- proposal generation ----------


def _current_value(strategy: CreatorStrategy, dimension: str):
    return getattr(strategy, dimension)


def _proposed_value(dimension: str, current, item: dict):
    if dimension in ("topic_mix", "format_mix"):
        current_list = list(current or [])
        if item["value"] in current_list:
            return None
        return sorted({*current_list, item["value"]})
    if current == item["value"]:
        return None
    return item["value"]


def _best_evidence(items: list[dict]) -> dict:
    return sorted(items, key=lambda e: (-e["n"], e["value"]))[0]


def propose_changes(
    db: Session, creator_id: int, min_evidence: int = MIN_EVIDENCE
) -> list[StrategyProposal]:
    strategy = get_strategy(db, creator_id)
    evidence = gather_evidence(db, creator_id)

    existing = {
        (p.dimension, str(p.proposed_value))
        for p in db.query(StrategyProposal)
        .filter(
            StrategyProposal.creator_id == creator_id,
            StrategyProposal.status == "PENDING",
        )
        .all()
    }

    created: list[StrategyProposal] = []
    for dimension, items in evidence.items():
        strong = [e for e in items if e["n"] >= min_evidence]
        if not strong:
            continue
        item = _best_evidence(strong)
        current = _current_value(strategy, dimension)
        proposed = _proposed_value(dimension, current, item)
        if proposed is None:
            continue
        if (dimension, str(proposed)) in existing:
            continue
        total = sum(e["n"] for e in strong)
        rationale = (
            f"{total} prior episodes support changing {dimension} to "
            f"{proposed!r} (evidence: {item['detail']}; source: {item['source']}). "
            "No change is made without evidence and human approval."
        )
        proposal = StrategyProposal(
            creator_id=creator_id,
            dimension=dimension,
            current_value=current,
            proposed_value=proposed,
            rationale=rationale,
            evidence=strong,
            evidence_count=total,
            min_evidence=min_evidence,
            status="PENDING",
            source_version=STRATEGY_VERSION,
        )
        db.add(proposal)
        created.append(proposal)

    db.commit()
    for proposal in created:
        db.refresh(proposal)
    return created


def list_proposals(
    db: Session, creator_id: int | None = None, status: str | None = None
) -> list[StrategyProposal]:
    query = db.query(StrategyProposal)
    if creator_id is not None:
        query = query.filter(StrategyProposal.creator_id == creator_id)
    if status is not None:
        query = query.filter(StrategyProposal.status == status)
    return query.order_by(StrategyProposal.id.desc()).all()


def decide_proposal(
    db: Session, proposal_id: int, approve: bool, note: str = ""
) -> StrategyProposal:
    proposal = db.get(StrategyProposal, proposal_id)
    if proposal is None:
        raise ValueError("proposal not found")
    if proposal.status != "PENDING":
        raise ValueError(f"proposal already {proposal.status}")

    proposal.status = "APPROVED" if approve else "REJECTED"
    proposal.note = note.strip()
    proposal.decided_at = datetime.now(timezone.utc)

    if approve:
        strategy = get_strategy(db, proposal.creator_id)
        setattr(strategy, proposal.dimension, proposal.proposed_value)
        if proposal.dimension in ("topic_mix", "format_mix"):
            setattr(strategy, proposal.dimension, list(proposal.proposed_value))
        strategy.revision += 1
        strategy.strategy_version = STRATEGY_VERSION

    db.commit()
    db.refresh(proposal)
    return proposal
