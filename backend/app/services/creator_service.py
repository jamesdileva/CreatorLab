"""Creator service — prompt assembly + memory retrieval + provider call. Keeps API thin."""
from sqlalchemy.orm import Session

from ..ai.prompts import render_creator_prompt
from ..ai.providers import (
    GenerateRequest,
    GenerateResponse,
    LLMProvider,
    PersonaHint,
    get_provider,
)
from ..models.creator import Creator
from ..models.creator_memory import CreatorMemory
from ..core.config import settings

MAX_MEMORIES = 10  # bound prompt size; scale later with evidence (guide §27)

MEMORY_HEADER = "\n\n## Canon and established facts (from memory)"


def retrieve_memories(db: Session, creator_id: int) -> list[CreatorMemory]:
    """Most important, newest first — pin memory_used for reproducibility."""
    return (
        db.query(CreatorMemory)
        .filter(CreatorMemory.creator_id == creator_id)
        .order_by(
            CreatorMemory.importance.desc(),
            CreatorMemory.created_at.desc(),
            CreatorMemory.id.desc(),
        )
        .limit(MAX_MEMORIES)
        .all()
    )


def build_system_prompt(creator: Creator, version: str, memories: list[CreatorMemory]) -> str:
    """Render the frozen prompt template, then append per-call memory context.

    Templates stay versioned and unmodified (guide §26); memory is injected
    per call so the same stored fact can be replayed for reproducibility.
    """
    system_prompt = render_creator_prompt(creator, version)
    if memories:
        bullets = "\n".join(f"- [{m.type.value}] {m.content}" for m in memories)
        system_prompt += f"{MEMORY_HEADER}\n{bullets}"
    return system_prompt


def generate_creator_response(
    db: Session,
    creator: Creator,
    user_message: str,
    prompt_version: str | None = None,
    provider_name: str | None = None,
    use_memory: bool = True,
) -> tuple[GenerateResponse, str, str, list[str]]:
    """Return (provider_response, prompt_version, provider_name, memories_used).

    Versioning is explicit and recorded in the response so every generation
    is attributable to an exact prompt/model pair.
    """
    version = prompt_version or settings.creator_prompt_version
    memories = retrieve_memories(db, creator.id) if use_memory else []
    system_prompt = build_system_prompt(creator, version, memories)
    provider: LLMProvider = get_provider(provider_name)
    response = provider.generate(
        GenerateRequest(
            system_prompt=system_prompt,
            user_message=user_message,
            persona=PersonaHint(
                name=creator.name,
                interests=creator.interests,
                humor_style=creator.humor_style,
                voice_style=creator.voice_style,
            ),
            memories=[m.content for m in memories],
        )
    )
    return response, version, provider.name, [m.content for m in memories]
