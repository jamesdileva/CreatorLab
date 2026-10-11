"""Structured output parsing — episodes must be inspectable JSON (architecture §10)."""
import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SceneDraft(BaseModel):
    title: str
    direction: str = ""


class EpisodeDraft(BaseModel):
    premise: str = Field(min_length=1)
    synopsis: str = Field(min_length=1)
    scenes: list[SceneDraft] = Field(min_length=3, max_length=6)
    script: str = Field(min_length=1)
    resolves_thread: str | None = None  # exact title of an open thread this episode resolves


class ParseError(ValueError):
    """Raised when provider output is not a valid EpisodeDraft JSON."""


_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL | re.IGNORECASE)
_BRACES = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Any:
    match = _FENCE.search(text)
    candidate = match.group(1) if match else None
    if candidate is None:
        brace = _BRACES.search(text)
        candidate = brace.group(0) if brace else text
    return json.loads(candidate)


def parse_episode_draft(text: str) -> EpisodeDraft:
    try:
        data = _extract_json(text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ParseError(f"output is not valid JSON: {exc}") from exc
    try:
        return EpisodeDraft.model_validate(data)
    except Exception as exc:  # pydantic ValidationError and friends
        raise ParseError(f"episode draft failed validation: {exc}") from exc
