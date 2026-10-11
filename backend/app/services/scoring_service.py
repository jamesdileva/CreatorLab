"""Deterministic heuristic concept scorer (roadmap Sprint 3.2).

Cheap tier (guide §27): scores the six roadmap dimensions from text features and
series context. This is the baseline scorer (scorer_version=heuristic-v1); a
prompt-based scorer can be added later behind the same interface.
"""
import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..core.metrics import (
    directional_accuracy,
    kendall_tau,
    spearman,
    top_k_agreement,
)
from ..models.canon import Canon
from ..models.concept import Concept, ConceptSet
from ..models.concept_score import ConceptScore, HumanRanking
from ..models.creator import Creator
from ..models.episode import Episode
from ..models.story_thread import StoryThread, ThreadStatus

SCORER_VERSION = "heuristic-v1"

WEIGHTS = {
    "hook": 0.20,
    "character_fit": 0.20,
    "novelty": 0.20,
    "story_potential": 0.15,
    "audience_relevance": 0.15,
    "episode_continuity": 0.10,
}

_STOPWORDS = {
    "the", "and", "his", "her", "that", "with", "from", "this", "have", "has",
    "was", "for", "are", "not", "but", "into", "than", "then", "them", "they",
}


def _words(text: str) -> set[str]:
    return {
        w.lower()
        for w in re.findall(r"[A-Za-z][A-Za-z'-]+", text)
        if len(w) > 3 and w.lower() not in _STOPWORDS
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class ConceptScoreData:
    concept: Concept
    scores: dict[str, float]
    composite: float
    rank: int


def _score_dimensions(
    concept: Concept,
    creator: Creator,
    topic: str,
    canon_keywords: set[str],
    thread_keywords: set[str],
    previous_word_sets: list[set[str]],
) -> dict[str, float]:
    premise_words = _words(concept.premise)
    text_words = _words(" ".join([concept.title, concept.premise, concept.hook, concept.angle]))

    # hook: tight, concrete hooks win
    hook = concept.hook or ""
    hook_score = 0.4
    if hook:
        if len(hook) <= 40:
            hook_score = 0.9
        elif len(hook) <= 70:
            hook_score = 0.7
        if hook.endswith("?") or hook.endswith("!"):
            hook_score = min(1.0, hook_score + 0.1)

    # character fit: overlap with creator interests + humor vocabulary
    interest_words = _words(" ".join(creator.interests or []))
    humor_words = _words(creator.humor_style or "")
    fit = 0.0
    if interest_words:
        fit = 0.8 * len(premise_words & interest_words) / max(1, len(interest_words))
    if humor_words and premise_words & humor_words:
        fit += 0.2
    character_fit = _clamp(fit)

    # novelty: distance from previous episode premises
    novelty = 0.8 if not previous_word_sets else max(
        1 - _jaccard(premise_words, prev) for prev in previous_word_sets
    )

    # story potential: premise length in a workable band + layered sentences
    length = len(concept.premise)
    length_score = 1.0 if 60 <= length <= 220 else (0.5 if 30 <= length <= 320 else 0.3)
    sentences = len([s for s in re.split(r"[.!?]+", concept.premise) if s.strip()])
    story_potential = _clamp(length_score + (0.1 if sentences >= 2 else 0.0))

    # audience relevance: topic coverage + canon overlap
    topic_words = _words(topic)
    relevance = 0.0
    if topic_words:
        relevance += 0.5 * len(text_words & topic_words) / max(1, len(topic_words))
    if canon_keywords:
        relevance += 0.5 * len(text_words & canon_keywords) / max(1, len(canon_keywords))
    audience_relevance = _clamp(relevance)

    # episode continuity: threads carried forward + canon echo
    continuity = 0.0
    if thread_keywords:
        continuity += 0.6 * len(text_words & thread_keywords) / max(1, len(thread_keywords))
    if canon_keywords:
        continuity += 0.4 * len(text_words & canon_keywords) / max(1, len(canon_keywords))
    episode_continuity = _clamp(continuity)

    return {
        "hook": round(hook_score, 3),
        "character_fit": round(character_fit, 3),
        "novelty": round(novelty, 3),
        "story_potential": round(story_potential, 3),
        "audience_relevance": round(audience_relevance, 3),
        "episode_continuity": round(episode_continuity, 3),
    }


def _composite(scores: dict[str, float]) -> float:
    return round(sum(scores[k] * w for k, w in WEIGHTS.items()), 3)


def score_concept_set(
    db: Session, concept_set: ConceptSet, creator: Creator
) -> list[ConceptScoreData]:
    concepts = (
        db.query(Concept).filter(Concept.set_id == concept_set.id).order_by(Concept.index).all()
    )
    if not concepts:
        raise ValueError("concept set is empty")

    canon_keywords = set()
    for c in db.query(Canon).filter(Canon.series_id == concept_set.series_id).all():
        canon_keywords |= _words(c.statement)

    thread_keywords = set()
    for t in (
        db.query(StoryThread)
        .filter(
            StoryThread.series_id == concept_set.series_id,
            StoryThread.status == ThreadStatus.OPEN,
        )
        .all()
    ):
        thread_keywords |= _words(t.title)

    previous_word_sets = [
        _words(e.premise)
        for e in (
            db.query(Episode)
            .filter(Episode.series_id == concept_set.series_id)
            .all()
        )
        if e.premise
    ]

    scored: list[tuple[Concept, dict[str, float], float]] = []
    for concept in concepts:
        scores = _score_dimensions(
            concept,
            creator,
            concept_set.topic,
            canon_keywords,
            thread_keywords,
            previous_word_sets,
        )
        scored.append((concept, scores, _composite(scores)))

    scored.sort(key=lambda t: (-t[2], t[0].index))

    existing = {
        s.concept_id: s
        for s in db.query(ConceptScore)
        .filter(ConceptScore.set_id == concept_set.id)
        .all()
    }
    results: list[ConceptScoreData] = []
    for rank, (concept, scores, composite) in enumerate(scored, start=1):
        score = existing.get(concept.id)
        if score is None:
            score = ConceptScore(concept_id=concept.id, set_id=concept_set.id, rank=rank)
            db.add(score)
        score.rank = rank
        score.hook_score = scores["hook"]
        score.character_fit_score = scores["character_fit"]
        score.novelty_score = scores["novelty"]
        score.story_potential_score = scores["story_potential"]
        score.audience_relevance_score = scores["audience_relevance"]
        score.episode_continuity_score = scores["episode_continuity"]
        score.composite = composite
        score.scorer_version = SCORER_VERSION
        results.append(
            ConceptScoreData(concept=concept, scores=scores, composite=composite, rank=rank)
        )
    db.commit()
    return results


def record_human_ranking(
    db: Session, concept_set: ConceptSet, order: list[int], note: str = ""
) -> HumanRanking:
    concepts = (
        db.query(Concept).filter(Concept.set_id == concept_set.id).all()
    )
    valid = {c.id for c in concepts}
    if not order or len(order) != len(valid) or set(order) != valid:
        raise ValueError(
            "order must list every concept id of this set exactly once"
        )
    ranking = HumanRanking(
        set_id=concept_set.id,
        order=json.dumps(order),
        note=note,
    )
    db.add(ranking)
    db.commit()
    db.refresh(ranking)
    return ranking


def compare_with_human(db: Session, concept_set: ConceptSet) -> dict | None:
    """Compare the latest human ranking against the system ranking."""
    human = (
        db.query(HumanRanking)
        .filter(HumanRanking.set_id == concept_set.id)
        .order_by(HumanRanking.id.desc())
        .first()
    )
    scores = (
        db.query(ConceptScore)
        .filter(ConceptScore.set_id == concept_set.id)
        .order_by(ConceptScore.rank)
        .all()
    )
    if human is None or not scores:
        return None

    human_order = json.loads(human.order)
    system_order = [s.concept_id for s in scores]

    # position (lower = better) per concept id, for correlation math
    human_pos = {cid: i for i, cid in enumerate(human_order)}
    system_pos = {cid: i for i, cid in enumerate(system_order)}
    ids = system_order
    system_vals = [system_pos[c] for c in ids]
    human_vals = [human_pos[c] for c in ids]

    top_system = system_order[0]
    top_human = human_order[0]

    return {
        "system_order": system_order,
        "human_order": human_order,
        "agreement": {
            "top_1_match": top_system == top_human,
            "top_3_overlap": round(top_k_agreement(system_order, human_order, 3), 3),
            "directional_accuracy": round(
                directional_accuracy(system_order, human_order), 3
            ),
        },
        "correlation": {
            "spearman": round(spearman(system_vals, human_vals), 3),
            "kendall_tau": round(kendall_tau(system_vals, human_vals), 3),
        },
        "system_top": top_system,
        "human_top": top_human,
        "sample_size": len(ids),
    }
