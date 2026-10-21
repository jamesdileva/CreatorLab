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
    familiarity: tuple[str, float] | None = None,
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
    # learned familiarity fills the gap when no explicit affinity is set
    if affinity == 0.0 and familiarity is not None:
        affinity = familiarity[1]
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
        if familiarity is not None and affinity == familiarity[1]:
            codes.append("familiar_creator")
        else:
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
    db: Session,
    target_type: str,
    target_id: int,
    seed: int = 0,
    viewer_count: int | None = None,
    memory_run_ids: set[int] | list[int] | None = None,
) -> RunResult:
    """Run one target through the audience.

    `viewer_count` grows the deterministic population (superset: seed indexes
    are stable), and `memory_run_ids` freezes the past runs used for memory so
    scale studies compare sizes against the same pre-study history.
    """
    title, premise, hook, tags = _resolve_content(db, target_type, target_id)
    viewers = (
        seed_audience(db)
        if viewer_count is None
        else seed_audience(db, count=viewer_count)
    )
    memoryful = target_type == TargetType.EPISODE.value
    content_words = (
        _words(f"{title}. {premise}") | _words(hook) | _words(" ".join(tags))
        if memoryful
        else set()
    )
    creator_id: int | None = None
    if memoryful:
        episode = db.get(Episode, target_id)
        creator_id = episode.creator_id if episode is not None else None

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

    fatigue_by_viewer, familiarity_by_viewer = _memory_context(
        db,
        viewers,
        target_type,
        target_id,
        creator_id,
        content_words,
        memory_run_ids,
    )

    reactions: list[ViewerReaction] = []
    for viewer in viewers:
        reaction = compute_reaction(
            viewer,
            title,
            premise,
            hook,
            tags,
            fatigue=fatigue_by_viewer.get(viewer.id, 0.0),
            familiarity=familiarity_by_viewer.get(viewer.id),
        )
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


def _memory_context(
    db: Session,
    viewers: list,
    target_type: str,
    target_id: int,
    creator_id: int | None,
    content_words: set[str],
    memory_run_ids: set[int] | list[int] | None,
) -> tuple[dict[int, float], dict[int, tuple[str, float] | None]]:
    """Batched equivalent of per-viewer fatigue + familiarity lookups.

    Mirrors `viewer_memory.effective_exposures` and
    `creator_familiarity.familiarity_for` exactly, but resolves past runs once
    instead of per viewer. `memory_run_ids` restricts the history window.
    """
    from .creator_familiarity import strength_for, tier_for
    from .viewer_memory import (
        FATIGUE_CAP,
        FATIGUE_FREE,
        FATIGUE_SLOPE,
        MIN_SHARED_WORDS,
        content_words_for_run,
    )

    if not content_words and creator_id is None:
        return {}, {}

    run_query = db.query(SimulationRun).order_by(SimulationRun.id)
    if memory_run_ids is not None:
        allowed = set(memory_run_ids)
        run_query = run_query.filter(SimulationRun.id.in_(allowed)) if allowed else None
    runs = [] if run_query is None else run_query.all()
    past_runs = [
        r
        for r in runs
        if not (r.target_type == target_type and r.target_id == target_id)
    ]

    past_words = {r.id: content_words_for_run(db, r) for r in past_runs}
    watched: dict[int, dict[int, float]] = {}
    if past_runs:
        rows = (
            db.query(ViewerReaction)
            .filter(ViewerReaction.run_id.in_([r.id for r in past_runs]))
            .all()
        )
        for row in rows:
            watched.setdefault(row.viewer_id, {})[row.run_id] = row.watch_probability

    creator_episode_ids: set[int] = set()
    if creator_id is not None:
        creator_episode_ids = {
            e.id for e in db.query(Episode).filter(Episode.creator_id == creator_id)
        }

    exposure_by_viewer: dict[int, float] = {}
    for run in past_runs:
        if run.target_type != TargetType.EPISODE.value:
            continue
        if run.target_id not in creator_episode_ids:
            continue
        for viewer_id, viewer_watch in watched.items():
            exposure_by_viewer[viewer_id] = (
                exposure_by_viewer.get(viewer_id, 0.0)
                + viewer_watch.get(run.id, 0.0)
            )

    fatigue_by_viewer: dict[int, float] = {}
    familiarity_by_viewer: dict[int, tuple[str, float] | None] = {}
    for viewer in viewers:
        viewer_watch = watched.get(viewer.id, {})
        total = 0.0
        for run_id, words in past_words.items():
            shared = content_words & words
            if len(shared) >= MIN_SHARED_WORDS:
                total += viewer_watch.get(run_id, 0.0) * (len(shared) / len(content_words))
        total = round(total, 3)
        fatigue_by_viewer[viewer.id] = round(
            min(FATIGUE_CAP, FATIGUE_SLOPE * max(0.0, total - FATIGUE_FREE)), 3
        )
        if creator_id is not None:
            exposure = round(exposure_by_viewer.get(viewer.id, 0.0), 3)
            familiarity_by_viewer[viewer.id] = (tier_for(exposure), strength_for(exposure))

    return fatigue_by_viewer, familiarity_by_viewer
