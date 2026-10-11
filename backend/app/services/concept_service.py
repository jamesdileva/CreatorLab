"""Concept generation — pool of candidate episode concepts (roadmap Sprint 3.1)."""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..ai.evaluation import Evaluation, evaluate_concepts
from ..ai.prompts import render_concepts_prompt
from ..ai.providers import (
    GenerateRequest,
    GenerateResponse,
    LLMProvider,
    PersonaHint,
    get_provider,
)
from ..ai.structured_output import ConceptItem, ParseError, parse_concepts
from ..models.canon import Canon
from ..models.concept import Concept, ConceptSet
from ..models.creator import Creator
from ..models.series import Series
from ..models.series import SeriesStatus
from ..models.story_thread import StoryThread, ThreadStatus
from .creator_service import retrieve_memories

CONCEPTS_SCHEMA = (
    '[{"title": str, "premise": str, "hook": str, "angle": str, '
    '"tags": [str]}]'
)
MIN_CONCEPTS = 3
MAX_CONCEPTS = 10


@dataclass
class ConceptGeneration:
    set: ConceptSet
    concepts: list[Concept]
    evaluation: Evaluation
    prompt_version: str
    provider: str
    model: str


class ConceptsBlockedError(Exception):
    def __init__(self, evaluation: Evaluation) -> None:
        self.evaluation = evaluation
        super().__init__("concepts blocked by evaluation")


def generate_concepts(
    db: Session,
    series: Series,
    creator: Creator,
    topic: str,
    count: int = 5,
    prompt_version: str | None = None,
    provider_name: str | None = None,
) -> ConceptGeneration:
    if not MIN_CONCEPTS <= count <= MAX_CONCEPTS:
        raise ValueError(f"count must be between {MIN_CONCEPTS} and {MAX_CONCEPTS}")
    if series.status != SeriesStatus.ACTIVE:
        raise ValueError("series is ended; no new concepts")

    version = prompt_version or "concepts_prompt_v1"
    canon = [
        c.statement
        for c in db.query(Canon).filter(Canon.series_id == series.id).order_by(Canon.id).all()
    ]
    memories = [m.content for m in retrieve_memories(db, creator.id)]
    open_threads = [
        t.title
        for t in db.query(StoryThread)
        .filter(StoryThread.series_id == series.id, StoryThread.status == ThreadStatus.OPEN)
        .order_by(StoryThread.id)
        .all()
    ]

    system_prompt = render_concepts_prompt(
        creator=creator,
        series_name=series.name,
        canon=canon,
        memories=memories,
        open_threads=open_threads,
        topic=topic,
        count=count,
        json_schema=CONCEPTS_SCHEMA,
        version=version,
    )

    provider: LLMProvider = get_provider(provider_name)
    response: GenerateResponse = provider.generate(
        GenerateRequest(
            system_prompt=system_prompt,
            user_message=f"Brainstorm {count} concepts about: {topic}",
            persona=PersonaHint(
                name=creator.name,
                interests=creator.interests,
                humor_style=creator.humor_style,
                voice_style=creator.voice_style,
            ),
            response_format="concepts",
            count=count,
            topic=topic,
        )
    )

    try:
        items: list[ConceptItem] = parse_concepts(response.text, MIN_CONCEPTS, MAX_CONCEPTS)
    except ParseError as exc:
        raise ParseError(f"{response.model} produced an unparseable concept set: {exc}") from exc

    evaluation = evaluate_concepts(items, topic=topic)
    if evaluation.status == "BLOCK":
        raise ConceptsBlockedError(evaluation)

    concept_set = ConceptSet(
        creator_id=creator.id,
        series_id=series.id,
        topic=topic,
        prompt_version=version,
        provider=provider.name,
        model=response.model,
    )
    db.add(concept_set)
    db.flush()

    concepts: list[Concept] = []
    for i, item in enumerate(items, start=1):
        concept = Concept(
            set_id=concept_set.id,
            index=i,
            title=item.title,
            premise=item.premise,
            hook=item.hook,
            angle=item.angle,
            tags=", ".join(item.tags),
        )
        db.add(concept)
        concepts.append(concept)
    db.commit()
    db.refresh(concept_set)

    return ConceptGeneration(
        set=concept_set,
        concepts=concepts,
        evaluation=evaluation,
        prompt_version=version,
        provider=provider.name,
        model=response.model,
    )
