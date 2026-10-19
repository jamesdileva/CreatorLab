"""Automated candidate selection service (roadmap Sprint 21.1).

Ranks a candidate pool by: the heuristic concept score (`score`), the synthetic
audience simulation (`simulation`), or a normalized blend (`combined`). Persists
the recommendation with full provenance. Nothing here publishes or approves —
human approval still gates publication.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models.concept import Concept, ConceptSet
from ..models.concept_score import ConceptScore
from ..models.selection import SELECTION_METHODS, CandidateSelection
from ..models.viewer import AUDIENCE_VERSION
from .scoring_service import SCORER_VERSION
from .simulation_service import rank_candidates

_ALLOWED = {
    "concept": {"score", "simulation", "combined"},
    "episode": {"simulation"},
}


@dataclass
class SelectionResult:
    selection: CandidateSelection
    ranked: list[dict]
    selected: list[dict]


def _score_ranking(db: Session, concept_ids: list[int]) -> dict[int, float]:
    rows = (
        db.query(ConceptScore)
        .filter(ConceptScore.concept_id.in_(concept_ids))
        .all()
    )
    scores = {r.concept_id: r.composite for r in rows}
    missing = [cid for cid in concept_ids if cid not in scores]
    if missing:
        raise ValueError(
            f"concepts not scored yet: {missing} (run concept scoring first)"
        )
    return scores


def _simulation_ranking(
    db: Session, candidate_type: str, ids: list[int], metric: str, seed: int
) -> tuple[dict[int, float], int]:
    result = rank_candidates(db, candidate_type, ids, metric=metric, seed=seed)
    scores = {c.candidate_id: c.score for c in result.ranked}
    return scores, result.run.id


def _normalize(scores: dict[int, float]) -> dict[int, float]:
    if not scores:
        return {}
    lo = min(scores.values())
    hi = max(scores.values())
    if hi == lo:
        return {k: 0.5 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _order(scores: dict[int, float]) -> list[int]:
    return sorted(scores, key=lambda cid: (-scores[cid], cid))


def select_candidates(
    db: Session,
    candidate_type: str,
    candidate_ids: list[int],
    method: str = "combined",
    metric: str = "watch_probability",
    count: int = 1,
    seed: int = 0,
    note: str = "",
    series_id: int | None = None,
    concept_set_id: int | None = None,
) -> SelectionResult:
    if candidate_type not in _ALLOWED:
        raise ValueError(f"candidate_type must be one of {sorted(_ALLOWED)}")
    ids = list(dict.fromkeys(candidate_ids))
    if len(ids) < 2:
        raise ValueError("selection needs at least two distinct candidates")
    if method not in SELECTION_METHODS:
        raise ValueError(f"method must be one of {list(SELECTION_METHODS)}")
    if method not in _ALLOWED[candidate_type]:
        raise ValueError(
            f"method '{method}' is not valid for candidate_type '{candidate_type}'"
        )
    if metric not in (
        "watch_probability", "like_probability", "comment_probability",
        "share_probability", "follow_probability",
    ):
        raise ValueError("unknown ranking metric")

    ranking_run_id: int | None = None
    if method == "score":
        scores = _score_ranking(db, ids)
        scorer_version = SCORER_VERSION
    elif method == "simulation":
        scores, ranking_run_id = _simulation_ranking(db, candidate_type, ids, metric, seed)
        scorer_version = ""
    else:  # combined
        score_scores = _score_ranking(db, ids)
        sim_scores, ranking_run_id = _simulation_ranking(db, candidate_type, ids, metric, seed)
        a, b = _normalize(score_scores), _normalize(sim_scores)
        scores = {cid: round(0.5 * a[cid] + 0.5 * b[cid], 4) for cid in ids}
        scorer_version = SCORER_VERSION

    order = _order(scores)
    count = max(1, min(count, len(order)))
    selected = order[:count]

    selection = CandidateSelection(
        candidate_type=candidate_type,
        series_id=series_id,
        concept_set_id=concept_set_id,
        method=method,
        metric=metric if method in ("simulation", "combined") else "",
        count=count,
        selected_ids=selected,
        ranked_ids=order,
        scores={str(cid): round(float(scores[cid]), 4) for cid in order},
        ranking_run_id=ranking_run_id,
        scorer_version=scorer_version,
        audience_version=AUDIENCE_VERSION if ranking_run_id else "",
        seed=seed,
        note=note.strip() or "automated selection; human approval still required to publish",
    )
    db.add(selection)
    db.commit()
    db.refresh(selection)
    return SelectionResult(
        selection=selection,
        ranked=[{"candidate_id": cid, "score": scores[cid]} for cid in order],
        selected=[{"candidate_id": cid, "score": scores[cid]} for cid in selected],
    )


def select_from_concept_set(
    db: Session,
    set_id: int,
    method: str = "combined",
    metric: str = "watch_probability",
    count: int = 1,
    seed: int = 0,
    note: str = "",
) -> SelectionResult:
    concept_set = db.get(ConceptSet, set_id)
    if concept_set is None:
        raise ValueError("concept set not found")
    ids = [
        c.id
        for c in db.query(Concept)
        .filter(Concept.set_id == set_id)
        .order_by(Concept.index)
        .all()
    ]
    if len(ids) < 2:
        raise ValueError("concept set needs at least two concepts")
    return select_candidates(
        db,
        "concept",
        ids,
        method=method,
        metric=metric,
        count=count,
        seed=seed,
        note=note,
        series_id=concept_set.series_id,
        concept_set_id=set_id,
    )


def list_selections(db: Session, limit: int = 50) -> list[CandidateSelection]:
    return (
        db.query(CandidateSelection)
        .order_by(CandidateSelection.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )


def selection_dict(selection: CandidateSelection) -> dict:
    return {
        "id": selection.id,
        "candidate_type": selection.candidate_type,
        "series_id": selection.series_id,
        "concept_set_id": selection.concept_set_id,
        "method": selection.method,
        "metric": selection.metric,
        "count": selection.count,
        "selected_ids": selection.selected_ids,
        "ranked_ids": selection.ranked_ids,
        "scores": selection.scores,
        "ranking_run_id": selection.ranking_run_id,
        "scorer_version": selection.scorer_version,
        "audience_version": selection.audience_version,
        "seed": selection.seed,
        "note": selection.note,
        "requires_human_approval": True,
        "created_at": selection.created_at.isoformat() if selection.created_at else None,
    }
