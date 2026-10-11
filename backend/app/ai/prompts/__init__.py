"""Prompt registry — versioned, never silently edit a production prompt.

A new prompt version is a NEW file (creator_prompt_v2.md) + registry entry,
so experiments can always reference the exact prompt used (implementation-guide §26).
"""
from pathlib import Path

from ...models.creator import Creator

PROMPT_DIR = Path(__file__).parent
PROMPT_VERSIONS: dict[str, str] = {"creator_prompt_v1": "creator_prompt_v1.md"}


def _load(template_name: str) -> str:
    path = PROMPT_DIR / template_name
    if not path.is_file():
        raise FileNotFoundError(f"prompt template not found: {template_name}")
    return path.read_text(encoding="utf-8")


def get_prompt_versions() -> list[str]:
    return sorted(PROMPT_VERSIONS)


def render_creator_prompt(creator: Creator, version: str = "creator_prompt_v1") -> str:
    if version not in PROMPT_VERSIONS:
        raise KeyError(f"unknown prompt version: {version}")
    def _join(items) -> str:
        return ", ".join(items or []) or "(none)"

    values = {
        "name": creator.name,
        "description": creator.description or "(none)",
        "personality": creator.personality or "(none)",
        "values": _join(creator.values),
        "interests": _join(creator.interests),
        "humor_style": creator.humor_style or "(none)",
        "voice_style": creator.voice_style or "(none)",
        "goals": _join(creator.goals),
        "constraints": creator.constraints
        or "Fictional character only; all publishes require explicit human approval.",
    }
    template = _load(PROMPT_VERSIONS[version])
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template
