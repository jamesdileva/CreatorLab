"""Deterministic offline provider — tests, demos, and voice checks without API keys.

Roleplays from the request's PersonaHint (same creator fields the real
providers read via the system prompt), so voice differentiation is exercised
end-to-end even without an LLM call.
"""
from .base import GenerateRequest, GenerateResponse, LLMProvider

TAKES = [
    "Here's my take on that.",
    "Let me put it this way.",
    "Funny you should ask.",
]


class StubProvider(LLMProvider):
    name = "stub"

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        persona = request.persona
        name = (persona.name if persona else "") or "Creator"
        interests = (persona.interests if persona else []) or ["whatever's in front of me"]
        humor = (persona.humor_style if persona else "") or "straightforward"
        voice = (persona.voice_style if persona else "") or "plain"
        if len(interests) == 1:
            topics = interests[0]
        else:
            topics = f"{interests[0]} and {interests[1]}"
        take = TAKES[sum(ord(c) for c in name + request.user_message) % len(TAKES)]
        text = (
            f"{name} here. {take} Talking {topics}: {request.user_message.strip()} "
            f"— that's my honest read, delivered {voice} with {humor} humor."
        )
        return GenerateResponse(text=text, model="stub/deterministic-v1")
