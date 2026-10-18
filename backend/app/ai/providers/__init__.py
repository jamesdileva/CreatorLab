"""Provider factory — switch models without redesigning the app."""
from ...core.config import settings
from .base import (
    GenerateRequest,
    GenerateResponse,
    LLMProvider,
    PersonaHint,
    ProviderError,
)
from .openai_compatible import OpenAICompatibleProvider
from .stub import StubProvider

__all__ = [
    "GenerateRequest",
    "GenerateResponse",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "PersonaHint",
    "ProviderError",
    "StubProvider",
    "get_provider",
]


def get_provider(name: str | None = None) -> LLMProvider:
    resolved = (name or settings.llm_provider or "stub").lower()
    if resolved == "stub":
        return StubProvider()
    if resolved == "openai":
        return OpenAICompatibleProvider()
    if resolved == "ollama":
        # Ollama exposes an OpenAI-compatible endpoint and ignores the key.
        return OpenAICompatibleProvider(
            api_key=settings.ollama_api_key,
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )
    raise ValueError(f"unknown LLM provider: {resolved}")
