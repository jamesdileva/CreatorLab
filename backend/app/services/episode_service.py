"""Episode generator — retrieves canon/memory/history, drafts, evaluates, persists.

Never bypasses evaluation: BLOCK drafts are never persisted (guide §19).
"""
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..ai.evaluation import Evaluation, evaluate_draft
from ..ai.prompts import render_episode_prompt
from ..ai.providers import (
    GenerateRequest,
    GenerateResponse,
    LLMProvider,
    PersonaHint,
    get_provider,
)
from ..ai.structured_output import EpisodeDraft, ParseError, parse_episode_draft
from ..models.canon import Canon
from ..models.episode import Episode, EpisodeStatus
from ..models.creator import Creator
from ..models.creator_memory import CreatorMemory
from ..models.scene import Scene
from ..models.series import Series
from ..models.story_thread import StoryThread, ThreadStatus
from .creator_service import retrieve_memories

JSON_SCHEMA = (
    '{"premise": str, "synopsis": str, '
    '"scenes": [{"title": str, "direction": str}], "script": str}'
)


@dataclass
class GenerationResult:
    draft: EpisodeDraft
    evaluation: Evaluation
    episode: Episode | None
    prompt_version: str
    provider: str
    model: str
    canon_used: list[str]
    memories_used: list[str]
    resolved_threads: list[str]


class EpisodeBlockedError(Exception):
    def __init__(self, evaluation: Evaluation) -> None:
        self.evaluation = evaluation
        super().__init__("episode draft blocked by evaluation")


def _next_episode_number(db: Session, series_id: int) -> int:
    return (
        db.query(func.max(Episode.episode_number)).filter(Episode.series_id == series_id).scalar()
        or 0
    ) + 1


def generate_episode(
    db: Session,
    series: Series,
    creator: Creator,
    prompt_version: str | None = None,
    provider_name: str | None = None,
    variant: int = 0,
) -> GenerationResult:
    """Generate + evaluate a draft. Persists unless BLOCKED."""
    version = prompt_version or "episode_prompt_v2"

    canon_rows = (
        db.query(Canon).filter(Canon.series_id == series.id).order_by(Canon.id).all()
    )
    canon = [c.statement for c in canon_rows]
    # universe canon applies to every channel (roadmap 14.1)
    from .universe_service import universe_statements

    universe_facts = universe_statements(db)

    memory_rows = retrieve_memories(db, creator.id)
    memories = [m.content for m in memory_rows]

    history_rows = (
        db.query(Episode)
        .filter(Episode.series_id == series.id)
        .order_by(Episode.episode_number)
        .all()
    )
    previous = [
        f"Ep {e.episode_number} — {e.title}: {e.premise}" for e in history_rows
    ]

    open_threads = [
        t.title
        for t in db.query(StoryThread)
        .filter(StoryThread.series_id == series.id, StoryThread.status == ThreadStatus.OPEN)
        .order_by(StoryThread.id)
        .all()
    ]

    next_number = _next_episode_number(db, series.id)

    system_prompt = render_episode_prompt(
        creator=creator,
        series_name=series.name,
        canon=canon,
        memories=memories,
        previous_episodes=previous,
        open_threads=open_threads,
        next_episode_number=next_number,
        json_schema=JSON_SCHEMA,
        variant=variant,
        universe_facts=universe_facts,
        version=version,
    )

    provider: LLMProvider = get_provider(provider_name)
    response: GenerateResponse = provider.generate(
        GenerateRequest(
            system_prompt=system_prompt,
            user_message="Write the next episode of this series now.",
            persona=PersonaHint(
                name=creator.name,
                interests=creator.interests,
                humor_style=creator.humor_style,
                voice_style=creator.voice_style,
            ),
            memories=memories,
            threads=open_threads,
            universe_canon=universe_facts,
            response_format="json",
            variant=variant,
        )
    )

    try:
        draft = parse_episode_draft(response.text)
    except ParseError as exc:
        raise ParseError(f"{response.model} produced an unparseable episode: {exc}") from exc

    evaluation = evaluate_draft(
        draft,
        canon=canon + universe_facts,
        previous_premises=[e.premise for e in history_rows],
        open_threads=open_threads,
    )

    if evaluation.status == "BLOCK":
        raise EpisodeBlockedError(evaluation)

    episode = _persist(db, series, creator, next_number, draft)
    resolved_threads = _resolve_threads(db, series, episode, open_threads, draft)
    return GenerationResult(
        draft=draft,
        evaluation=evaluation,
        episode=episode,
        prompt_version=version,
        provider=provider.name,
        model=response.model,
        canon_used=canon,
        memories_used=memories,
        resolved_threads=resolved_threads,
    )


def _resolve_threads(
    db: Session,
    series: Series,
    episode: Episode,
    open_thread_titles: list[str],
    draft: EpisodeDraft,
) -> list[str]:
    """Mark threads the episode resolves as RESOLVED (roadmap 2.3).

    Only exact title matches against threads that were open when generation
    started count, so a hallucinated resolution never mutates state.
    """
    claimed = (draft.resolves_thread or "").strip().lower()
    resolved: list[str] = []
    if not claimed or claimed not in {t.strip().lower() for t in open_thread_titles}:
        return resolved
    rows = (
        db.query(StoryThread)
        .filter(
            StoryThread.series_id == series.id,
            StoryThread.status == ThreadStatus.OPEN,
        )
        .all()
    )
    for row in rows:
        if row.title.strip().lower() == claimed:
            row.status = ThreadStatus.RESOLVED
            row.resolved_episode_id = episode.id
            resolved.append(row.title)
    db.commit()
    return resolved


def _episode_title(premise: str) -> str:
    words = premise.split()
    short = " ".join(words[:8]).rstrip(",;:")
    return short or "Untitled episode"


def _persist(
    db: Session, series: Series, creator: Creator, number: int, draft: EpisodeDraft
) -> Episode:
    episode = Episode(
        creator_id=creator.id,
        series_id=series.id,
        episode_number=number,
        title=_episode_title(draft.premise),
        premise=draft.premise,
        synopsis=draft.synopsis,
        script=draft.script,
        status=EpisodeStatus.IDEA,
    )
    db.add(episode)
    db.flush()
    for i, scene in enumerate(draft.scenes, start=1):
        db.add(
            Scene(
                episode_id=episode.id,
                scene_number=i,
                title=scene.title,
                direction=scene.direction,
            )
        )
    db.commit()
    db.refresh(episode)
    return episode
