"""Creator service — prompt assembly + provider call. Keeps API thin."""
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
from ..core.config import settings


def generate_creator_response(
    db: Session,
    creator: Creator,
    user_message: str,
    prompt_version: str | None = None,
    provider_name: str | None = None,
) -> tuple[GenerateResponse, str, str]:
    """Return (provider_response, prompt_version, provider_name).

    Versioning is explicit and recorded in the response so every generation
    is attributable to an exact prompt/model pair.
    """
    version = prompt_version or settings.creator_prompt_version
    system_prompt = render_creator_prompt(creator, version)
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
        )
    )
    return response, version, provider.name
