"""Sprint 1.2 — prompt registry: v1 exists, renders all creator fields, versioning enforced."""
import pytest

from app.ai.prompts import (
    get_prompt_versions,
    render_creator_prompt,
)
from app.models.creator import Creator

HANK = Creator(
    name="Hank",
    slug="hank",
    description="Rural, practical fictional creator.",
    personality="Dry humor, practical, skeptical of unnecessary technology.",
    values=["practicality", "honesty"],
    interests=["farming", "trucks", "weather"],
    humor_style="dry, deadpan",
    voice_style="plain-spoken, unhurried",
    goals=["make useful things"],
    constraints="Fictional only. Human approval for all publishes.",
    active=True,
)

ALEX = Creator(
    name="Alex.exe",
    slug="alex-exe",
    description="Corporate-AI fictional creator.",
    personality="Startup vocabulary, automation enthusiast.",
    values=["optimization", "growth"],
    interests=["AI", "productivity", "automation"],
    humor_style="absurd corporate-techno-optimism",
    voice_style="rapid, buzzword-dense",
    goals=["optimize everything"],
    constraints="Fictional only. Human approval for all publishes.",
    active=True,
)


def test_v1_is_registered():
    assert "creator_prompt_v1" in get_prompt_versions()


def test_render_includes_all_creator_fields():
    prompt = render_creator_prompt(HANK, "creator_prompt_v1")
    assert "Hank" in prompt
    assert "Dry humor, practical, skeptical" in prompt
    assert "farming, trucks, weather" in prompt
    assert "dry, deadpan" in prompt
    assert "plain-spoken, unhurried" in prompt
    assert "practicality, honesty" in prompt
    assert "make useful things" in prompt
    assert "Fictional only" in prompt


def test_prompt_requires_roleplay_and_hard_constraints():
    prompt = render_creator_prompt(HANK, "creator_prompt_v1")
    assert "Stay in character" in prompt
    assert "never break character" in prompt.lower() or "never break character" in prompt
    assert "never impersonate real people" in prompt
    assert "Never manufacture engagement" in prompt


def test_prompts_differ_per_creator():
    hank = render_creator_prompt(HANK, "creator_prompt_v1")
    alex = render_creator_prompt(ALEX, "creator_prompt_v1")
    assert hank != alex
    assert "absurd corporate-techno-optimism" in alex and "absurd corporate-techno-optimism" not in hank
    assert "AI, productivity, automation" in alex and "AI, productivity, automation" not in hank


def test_unknown_version_raises():
    with pytest.raises(KeyError):
        render_creator_prompt(HANK, "creator_prompt_v2")


def test_missing_fields_do_not_leave_placeholders():
    bare = Creator(name="Bare", slug="bare", active=True)
    prompt = render_creator_prompt(bare, "creator_prompt_v1")
    for field in ("description", "personality", "interests", "humor_style"):
        assert "{" + field + "}" not in prompt
