"""Reaction engine + aggregation (Sprint 4.2).

Deterministic scroll-stop model: hook strength and attention decide whether a
viewer stops scrolling; interest decides whether they keep watching; response
style gates like/comment/share; creator affinity gates follow. Every reaction
carries reason codes so the simulator stays inspectable (arch §5.10).
"""
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models.concept import Concept
from ..models.episode import Episode
from ..models.simulation import (
    RANKING_VERSION,
    REACTION_VERSION,
    RankingRun,
    SimulationRun,
    TargetType,
    ViewerReaction,
)
from ..models.viewer import AUDIENCE_VERSION, SyntheticViewer
from .audience_service import _words, baseline_interest, seed_audience

_LIKE_RATE = {"lurker": 0.25, "liker": 0.75, "commenter": 0.60, "sharer": 0.65}
_COMMENT_RATE = {"lurker": 0.05, "liker": 0.05, "commenter": 0.40, "sharer": 0.12}
_SHARE_RATE = {"lurker": 0.02, "liker": 0.03, "commenter": 0.05, "sharer": 0.25}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def hook_strength(hook: str, attention: float) -> float:
    """Short, concrete hooks stop low-attention scrollers; strong hooks score."""
    if not hook:
        return 0.3
    score = 0.6 if len(hook) <= 40 else (0.45 if len(hook) <= 80 else 0.3)
    if hook.endswith("?") or hook.endswith("!"):
        score += 0.15
    if re.search(r"\d", hook):
        score += 0.05
    # low-attention viewers need punchy hooks
    if (attention or 0.5) < 0.5 and len(hook) > 80:
        score -= 0.1
    return _clamp(score)


@dataclass
class Reaction:
    watch: float
    like: float
    comment: float
    share: float
    follow: float
    reason_codes: list[str] = field(default_factory=list)


def compute_reaction(
    viewer: SyntheticViewer,
    title: str,
    premise: str,
    hook: str = "",
    tags: list[str] | None = None,
    fatigue: float = 0.0,
) -> Reaction:
    text = f"{title}. {premise}"
    interest = baseline_interest(viewer, text, tags)
    hook_score = hook_strength(hook, viewer.attention_level or 0.5)

    watch = _clamp(0.25 + 0.45 * hook_score + 0.30 * interest - fatigue)
    style = viewer.response_style or "lurker"
    like = _clamp(watch * _LIKE_RATE.get(style, 0.25))
    comment = _clamp(watch * _COMMENT_RATE.get(style, 0.05))
    share = _clamp(watch * _SHARE_RATE.get(style, 0.02))

    affinities = viewer.creator_affinities or {}
    affinity = max((float(v) for v in affinities.values()), default=0.0)
    follow = _clamp(watch * (0.05 + 0.5 * affinity + 0.2 * interest))

    content_words = _words(text) | _words(hook)
    interest_words = _words(" ".join(viewer.interests or []))
    humor_words = _words(" ".join(viewer.humor_preferences or []))

    codes: list[str] = []
    if interest_words & content_words:
        codes.append("topic_interest")
    if humor_words & content_words:
        codes.append("humor_match")
    if hook_score >= 0.7:
        codes.append("strong_hook")
    if affinity >= 0.5:
        codes.append("creator_affinity")
    if (viewer.attention_level or 0.5) >= 0.7:
        codes.append("high_attention")
    if not codes:
        codes.append("baseline_curiosity")
    if fatigue > 0:
        codes.append("repetition_fatigue")

    return Reaction(
        watch=round(watch, 3),
        like=round(like, 3),
        comment=round(comment, 3),
        share=round(share, 3),
        follow=round(follow, 3),
        reason_codes=codes,
    )


def _resolve_content(db: Session, target_type: str, target_id: int) -> tuple[str, str, str, list[str]]:
    if target_type == TargetType.CONCEPT.value:
        concept = db.get(Concept, target_id)
        if concept is None:
            raise ValueError("concept not found")
        return concept.title, concept.premise, concept.hook, [
            t.strip() for t in (concept.tags or "").split(",") if t.strip()
        ]
    if target_type == TargetType.EPISODE.value:
        episode = db.get(Episode, target_id)
        if episode is None:
            raise ValueError("episode not found")
        return episode.title, episode.premise, episode.synopsis, []
    raise ValueError(f"target_type must be one of {[t.value for t in TargetType]}")


RANK_METRICS = (
    "watch_probability",
    "like_probability",
    "comment_probability",
    "share_probability",
    "follow_probability",
)


@dataclass
class RunResult:
    run: SimulationRun
    aggregate: dict
    reactions: list[ViewerReaction]


@dataclass
class RankedCandidate:
    candidate_id: int
    score: float
    run_id: int


@dataclass
class RankingResult:
    run: RankingRun
    ranked: list[RankedCandidate]


def rank_candidates(
    db: Session,
    candidate_type: str,
    candidate_ids: list[int],
    metric: str = "watch_probability",
    seed: int = 0,
) -> RankingResult:
    """Run every candidate through the same audience, then order by metric.

    Deterministic: reruns with the same inputs produce the same ranking, with
    candidate id as the tiebreak so the order is always total.
    """
    if candidate_type not in {t.value for t in TargetType}:
        raise ValueError(f"candidate_type must be one of {[t.value for t in TargetType]}")
    if metric not in RANK_METRICS:
        raise ValueError(f"metric must be one of {list(RANK_METRICS)}")
    if len(candidate_ids) < 2:
        raise ValueError("ranking needs at least two candidates")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate_ids must be unique")

    scored: list[RankedCandidate] = []
    for candidate_id in candidate_ids:
        result = run_simulation(db, candidate_type, candidate_id, seed=seed)
        score = result.aggregate["means"][metric]
        scored.append(RankedCandidate(candidate_id=candidate_id, score=score, run_id=result.run.id))

    scored.sort(key=lambda c: (-c.score, c.candidate_id))

    first_run = db.get(SimulationRun, scored[0].run_id)
    run = RankingRun(
        candidate_type=candidate_type,
        candidate_ids=list(candidate_ids),
        metric=metric,
        ranking=[c.candidate_id for c in scored],
        simulation_run_ids=[c.run_id for c in scored],
        model="stub/deterministic-v1",
        prompt_version=RANKING_VERSION,
        audience_version=AUDIENCE_VERSION,
        viewer_count=first_run.viewer_count if first_run else 0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return RankingResult(run=run, ranked=scored)


def aggregate_reactions(reactions: list[ViewerReaction]) -> dict:
    n = len(reactions)
    if n == 0:
        raise ValueError("no reactions to aggregate")
    means = {
        key: round(sum(getattr(r, key) for r in reactions) / n, 3)
        for key in (
            "watch_probability",
            "like_probability",
            "comment_probability",
            "share_probability",
            "follow_probability",
        )
    }
    code_counts: dict[str, int] = {}
    for r in reactions:
        for code in r.reason_codes or []:
            code_counts[code] = code_counts.get(code, 0) + 1
    buckets = {"low": 0, "mid": 0, "high": 0}
    for r in reactions:
        w = r.watch_probability
        buckets["low" if w < 0.3 else ("mid" if w < 0.6 else "high")] += 1
    return {"viewer_count": n, "means": means, "reason_counts": code_counts, "watch_buckets": buckets}


def run_simulation(
    db: Session, target_type: str, target_id: int, seed: int = 0
) -> RunResult:
    from .viewer_memory import effective_exposures, fatigue_penalty

    title, premise, hook, tags = _resolve_content(db, target_type, target_id)
    viewers = seed_audience(db)
    memoryful = target_type == TargetType.EPISODE.value
    content_words = (
        _words(f"{title}. {premise}") | _words(hook) | _words(" ".join(tags))
        if memoryful
        else set()
    )

    run = SimulationRun(
        target_type=target_type,
        target_id=target_id,
        model="stub/deterministic-v1",
        prompt_version=REACTION_VERSION,
        audience_version=AUDIENCE_VERSION,
        seed=seed,
        viewer_count=len(viewers),
    )
    db.add(run)
    db.flush()

    reactions: list[ViewerReaction] = []
    for viewer in viewers:
        fatigue = fatigue_penalty(
            effective_exposures(db, viewer.id, content_words, target_type, target_id)
        )
        reaction = compute_reaction(viewer, title, premise, hook, tags, fatigue=fatigue)
        row = ViewerReaction(
            run_id=run.id,
            viewer_id=viewer.id,
            watch_probability=reaction.watch,
            like_probability=reaction.like,
            comment_probability=reaction.comment,
            share_probability=reaction.share,
            follow_probability=reaction.follow,
            reason_codes=reaction.reason_codes,
        )
        db.add(row)
        reactions.append(row)
    db.commit()
    for row in reactions:
        db.refresh(row)
    db.refresh(run)
    return RunResult(run=run, aggregate=aggregate_reactions(reactions), reactions=reactions)
