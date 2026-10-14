"""Prompt registry — versioned, never silently edit a production prompt.

A new prompt version is a NEW file (creator_prompt_v2.md) + registry entry,
so experiments can always reference the exact prompt used (implementation-guide §26).
"""
from pathlib import Path

from ...models.creator import Creator

PROMPT_DIR = Path(__file__).parent
PROMPT_VERSIONS: dict[str, str] = {
    "creator_prompt_v1": "creator_prompt_v1.md",
    "episode_prompt_v1": "episode_prompt_v1.md",
    "concepts_prompt_v1": "concepts_prompt_v1.md",
    "cross_episode_prompt_v1": "cross_episode_prompt_v1.md",
}


def _load(template_name: str) -> str:
    path = PROMPT_DIR / template_name
    if not path.is_file():
        raise FileNotFoundError(f"prompt template not found: {template_name}")
    return path.read_text(encoding="utf-8")


def get_prompt_versions() -> list[str]:
    return sorted(PROMPT_VERSIONS)


def _render(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def _join(items) -> str:
    return ", ".join(items or []) or "(none)"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none yet)"


def render_creator_prompt(creator: Creator, version: str = "creator_prompt_v1") -> str:
    if version not in PROMPT_VERSIONS:
        raise KeyError(f"unknown prompt version: {version}")
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
    return _render(_load(PROMPT_VERSIONS[version]), values)


def render_concepts_prompt(
    creator: Creator,
    series_name: str,
    canon: list[str],
    memories: list[str],
    open_threads: list[str],
    topic: str,
    count: int,
    json_schema: str,
    version: str = "concepts_prompt_v1",
) -> str:
    if version not in PROMPT_VERSIONS:
        raise KeyError(f"unknown prompt version: {version}")
    values = {
        "creator_name": creator.name,
        "personality": creator.personality or "(none)",
        "interests": _join(creator.interests),
        "humor_style": creator.humor_style or "(none)",
        "voice_style": creator.voice_style or "(none)",
        "series_name": series_name,
        "canon_facts": _bullets(canon),
        "memories": _bullets(memories),
        "open_threads": _bullets(open_threads),
        "topic": topic,
        "count": str(count),
        "json_schema": json_schema,
    }
    return _render(_load(PROMPT_VERSIONS[version]), values)


def render_episode_prompt(
    creator: Creator,
    series_name: str,
    canon: list[str],
    memories: list[str],
    previous_episodes: list[str],
    open_threads: list[str],
    next_episode_number: int,
    json_schema: str,
    variant: int = 0,
    version: str = "episode_prompt_v1",
) -> str:
    if version not in PROMPT_VERSIONS:
        raise KeyError(f"unknown prompt version: {version}")
    values = {
        "creator_name": creator.name,
        "personality": creator.personality or "(none)",
        "interests": _join(creator.interests),
        "humor_style": creator.humor_style or "(none)",
        "voice_style": creator.voice_style or "(none)",
        "series_name": series_name,
        "canon_facts": _bullets(canon),
        "memories": _bullets(memories),
        "previous_episodes": _bullets(previous_episodes),
        "open_threads": _bullets(open_threads),
        "next_episode_number": str(next_episode_number),
        "variant": str(variant),
        "json_schema": json_schema,
    }
    return _render(_load(PROMPT_VERSIONS[version]), values)

def render_cross_episode_prompt(
    cast: list[str],
    series_name: str,
    canon: list[str],
    memories: list[str],
    relationships: list[str],
    open_threads: list[str],
    previous_episodes: list[str],
    json_schema: str,
    version: str = "cross_episode_prompt_v1",
) -> str:
    if version not in PROMPT_VERSIONS:
        raise KeyError(f"unknown prompt version: {version}")
    values = {
        "series_name": series_name,
        "cast": "\n".join(f"- {member}" for member in cast),
        "canon": _bullets(canon),
        "memories": _bullets(memories),
        "relationships": _bullets(relationships),
        "open_threads": _bullets(open_threads),
        "previous_episodes": _bullets(previous_episodes),
        "json_schema": json_schema,
    }
    return _render(_load(PROMPT_VERSIONS[version]), values)
