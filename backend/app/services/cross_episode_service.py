"""Cross-creator episode generation (roadmap Sprint 13.2).

A crossover episode is generated for a HOST series with 2+ nominated creators:
the host provides the story universe (series, canon, threads, history), each
creator contributes identity/memory, and the relationship between participants
shapes the interaction.

Cross-creator storytelling is fictional continuity only — accounts never interact
to manufacture engagement (architecture §4/§20).
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..ai.evaluation import Evaluation, evaluate_draft
from ..ai.prompts import render_cross_episode_prompt
from ..ai.providers import (
    GenerateRequest,
    GenerateResponse,
    LLMProvider,
    PersonaHint,
    get_provider,
)
from ..ai.structured_output import (
    CrossEpisodeDraft,
    EpisodeDraft,
    ParseError,
    parse_episode_draft,
    parse_cross_episode_draft,
)
from ..models.canon import Canon
from ..models.creator import Creator
from ..models.episode import Episode, EpisodeStatus
from ..models.relationship import CreatorRelationship, DIMENSIONS
from ..models.scene import Scene
from ..models.series import Series, SeriesStatus
from ..models.story_thread import StoryThread, ThreadStatus
from .creator_service import retrieve_memories

CROSS_SCHEMA = (
    '{"participants": [str], "premise": str, "synopsis": str, '
    '"scenes": [{"title": str, "direction": str}], "script": str}'
)


class CrossEpisodeError(ValueError):
    pass


@dataclass
class CrossGeneration:
    draft: CrossEpisodeDraft
    evaluation: Evaluation
    episode: Episode
    prompt_version: str
    provider: str
    model: str
    cast_used: list[str]


def _creator_or_400(db: Session, creator_id: int) -> Creator:
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise CrossEpisodeError(f"creator {creator_id} not found")
    return creator


def _relationship_between(
    db: Session, a_id: int, b_id: int
) -> CreatorRelationship | None:
    lo, hi = (a_id, b_id) if a_id < b_id else (b_id, a_id)
    return (
        db.query(CreatorRelationship)
        .filter_by(creator_a_id=lo, creator_b_id=hi)
        .one_or_none()
    )


def generate_cross_episode(
    db: Session,
    series_id: int,
    participant_ids: list[int],
    prompt_version: str | None = None,
    provider_name: str | None = None,
    variant: int = 0,
) -> CrossGeneration:
    unique_ids: list[int] = []
    for cid in participant_ids:
        wrong_type = not isinstance(cid, int) or isinstance(cid, bool)
        if wrong_type:
            raise CrossEpisodeError("participant ids must be integers")
        if cid not in unique_ids:
            unique_ids.append(cid)
    if len(unique_ids) < 2:
        raise CrossEpisodeError("cross-creator episodes need at least two creators")
    if len(unique_ids) > 3:
        raise CrossEpisodeError("at most three participants per episode")

    series = db.get(Series, series_id)
    if series is None:
        raise CrossEpisodeError("series not found")

    series = db.get(Series, series_id)
    if series is None:
        raise CrossEpisodeError("series not found")
    if series.status != SeriesStatus.ACTIVE:
        raise CrossEpisodeError("series is ended; no new episodes")

    participants = [_creator_or_400(db, cid) for cid in unique_ids]
    host = db.get(Creator, series.creator_id)
    if host is None or not host.active:
        raise CrossEpisodeError("series creator is missing or inactive")

    if not any(c.id == host.id for c in participants):
        raise CrossEpisodeError("host series creator must be a participant")

    version = prompt_version or "cross_episode_prompt_v1"

    canon = [
        c.statement
        for c in db.query(Canon).filter(Canon.series_id == series.id).order_by(Canon.id).all()
    ]
    memories: list[str] = []
    for creator in participants:
        name = creator.name
        for row in retrieve_memories(db, creator.id):
            memories.append(f"{name}: {row.content}")
    threads = [
        t.title
        for t in db.query(StoryThread)
        .filter(StoryThread.series_id == series.id, StoryThread.status == ThreadStatus.OPEN)
        .order_by(StoryThread.id)
        .all()
    ]
    history = [
        f"Ep {e.episode_number} — {e.title}: {e.premise}"
        for e in db.query(Episode)
        .filter(Episode.series_id == series.id)
        .order_by(Episode.episode_number)
        .all()
    ]
    relationships: list[str] = []
    for i in range(len(participants)):
        for j in range(i + 1, len(participants)):
            rel = _relationship_between(db, participants[i].id, participants[j].id)
            if rel is None:
                relationships.append(
                    f"{participants[i].name} and {participants[j].name} have no "
                    "established relationship yet — introduce them cautiously."
                )
                continue
            profile = ", ".join(
                f"{dim} {getattr(rel, dim):.2f}" for dim in DIMENSIONS
            )
            note = f" — {rel.note}" if rel.note else ""
            relationships.append(
                f"{participants[i].name} and {participants[j].name} ({profile}){note}"
            )

    cast = [
        f"{c.name} ({c.personality or 'unknown personality'}; humor: "
        f"{c.humor_style or 'unknown'})"
        for c in participants
    ]
    system_prompt = render_cross_episode_prompt(
        cast=cast,
        series_name=series.name,
        canon=canon,
        memories=memories,
        relationships=relationships,
        open_threads=threads,
        previous_episodes=history,
        json_schema=CROSS_SCHEMA,
        version=version,
    )

    provider: LLMProvider = get_provider(provider_name)
    response: GenerateResponse = provider.generate(
        GenerateRequest(
            system_prompt=system_prompt,
            user_message="Write the crossover episode now.",
            persona=PersonaHint(name=host.name),
            memories=memories,
            response_format="cross_episode",
            variant=variant,
        )
    )

    try:
        draft = parse_cross_episode_draft(response.text)
    except ParseError as exc:
        raise ParseError(
            f"{response.model} produced an unparseable crossover: {exc}"
        ) from exc

    known_names = {c.name.lower() for c in participants}
    evaluation = evaluate_cross_draft(draft, participants, canon, history)

    next_number = (
        db.query(func_max(Episode.episode_number))
        .filter(Episode.series_id == series.id)
        .scalar()
        or 0
    ) + 1
    episode = Episode(
        creator_id=host.id,
        series_id=series.id,
        episode_number=next_number,
        title=_cross_title(draft),
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

    return CrossGeneration(
        draft=draft,
        evaluation=evaluation,
        episode=episode,
        prompt_version=version,
        provider=provider.name,
        model=response.model,
        cast_used=[c.name for c in participants],
    )


def _cross_title(draft: CrossEpisodeDraft) -> str:
    words = draft.premise.split()
    return " ".join(words[:8]).rstrip(",;:") or "Crossover episode"


def func_max(column):  # small indirection keeps imports tidy
    from sqlalchemy import func

    return func.max(column)


def evaluate_cross_draft(
    draft: CrossEpisodeDraft,
    participants: list[Creator],
    canon: list[str],
    previous_premises: list[str] | None = None,
) -> Evaluation:
    """Safety + coherence gates specific to cross-creator drafts."""
    solo = EpisodeDraft(
        premise=draft.premise,
        synopsis=draft.synopsis,
        scenes=draft.scenes,
        script=draft.script,
    )
    evaluation = evaluate_draft(
        solo, canon=canon, previous_premises=previous_premises or []
    )
    from ..ai.evaluation import Issue, Severity

    known = {c.name.lower() for c in participants}
    claimed = [p.strip().lower() for p in draft.participants if p.strip()]
    if not claimed:
        evaluation.issues.append(
            Issue("no_participants", Severity.BLOCK, "draft lists no participants")
        )
    else:
        for name in claimed:
            if name not in known:
                evaluation.issues.append(
                    Issue(
                        "unknown_participant",
                        Severity.BLOCK,
                        f"draft introduces {name!r}, who was not part of the request",
                    )
                )
        missing = [c.name for c in participants if c.name.lower() not in claimed]
        if missing:
            evaluation.issues.append(
                Issue(
                    "missing_participant",
                    Severity.REVIEW,
                    f"participants not featured in the draft: {missing}",
                )
            )
        # every participant must actually speak in the script
        silent = [
            c.name
            for c in participants
            if c.name.lower() not in draft.script.lower()
        ]
        if silent:
            evaluation.issues.append(
                Issue(
                    "silent_participant",
                    Severity.REVIEW,
                    f"participants with no lines: {silent}",
                )
            )
    return evaluation
