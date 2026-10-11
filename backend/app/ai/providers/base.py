"""LLM provider abstraction — never hard-code one model (architecture §7)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PersonaHint:
    """Identity cues for test-double providers.

    Real providers ignore this (they read the system prompt).
    The stub uses it to roleplay deterministically offline.
    """

    name: str = ""
    interests: list[str] = field(default_factory=list)
    humor_style: str = ""
    voice_style: str = ""


@dataclass
class GenerateRequest:
    system_prompt: str
    user_message: str
    persona: PersonaHint | None = None
    memories: list[str] = field(default_factory=list)
    response_format: str = "text"  # "text" | "json"
    variant: int = 0  # deterministic archetype selection
    temperature: float = 0.7
    max_tokens: int = 300
    seed: int | None = None


@dataclass
class GenerateResponse:
    text: str
    model: str


class ProviderError(RuntimeError):
    """Raised when a provider call fails (network, auth, malformed response)."""


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, request: GenerateRequest) -> GenerateResponse:
        raise NotImplementedError
