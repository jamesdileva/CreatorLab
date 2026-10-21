"""Audience service — deterministic viewer population + baseline interest (Sprint 4.1).

Seeding is fully deterministic (no LLM): index i always yields the same viewer
within an audience version, so runs are reproducible (guide §9).
"""
import re

from sqlalchemy.orm import Session

from ..models.viewer import AUDIENCE_VERSION, SyntheticViewer

_DEFAULT_COUNT = 25
_MAX_COUNT = 10000  # Phase 24 ladder tops out at 10,000 viewers

_NAMES = [
    "rowan", "casey", "morgan", "ellis", "devon", "quinn", "reese", "skyler",
    "taylor", "jordan", "avery", "blake", "cameron", "dakota", "emerson",
    "finley", "gray", "harper", "indigo", "jules", "kai", "logan", "marlow",
    "noor", "oakley",
]
_AGES = ["18-24", "25-34", "35-44", "45-54", "55+"]
_REGIONS = ["midwest", "south", "northeast", "west", "rural", "suburban", "urban"]
_INTEREST_POOLS = [
    ["farming", "trucks", "weather"],
    ["AI", "startups", "automation"],
    ["comedy", "memes", "standup"],
    ["cooking", "gardening", "DIY"],
    ["gaming", "streaming", "esports"],
    ["outdoors", "fishing", "camping"],
    ["trucks", "motorsports", "garage"],
    ["productivity", "notion", "habits"],
    ["history", "documentaries", "podcasts"],
    ["music", "concerts", "vinyl"],
    ["farming", "cooking", "markets"],
    ["AI", "gaming", "gadgets"],
    ["weather", "storms", "radio"],
    ["comedy", "improv", "sketches"],
    ["DIY", "woodworking", "tools"],
]
_PERSONALITIES = ["skeptical", "enthusiastic", "laid-back", "analytical", "playful"]
_HUMOR_POOLS = [
    ["deadpan"],
    ["absurdist"],
    ["slapstick", "wholesome"],
    ["dry", "satirical"],
    ["wholesome"],
    ["satirical", "absurdist"],
    ["slapstick"],
    ["dry"],
]
_ATTENTION = [0.3, 0.5, 0.7, 0.9]
_RESPONSE_STYLES = ["lurker", "lurker", "liker", "liker", "commenter", "sharer"]

_STOPWORDS = {
    "the", "and", "his", "her", "that", "with", "from", "this", "have", "has",
    "was", "for", "are", "not", "but", "into", "than", "then", "about",
}


def _words(text: str) -> set[str]:
    return {
        w.lower()
        for w in re.findall(r"[A-Za-z][A-Za-z'-]+", text)
        if len(w) > 3 and w.lower() not in _STOPWORDS
    }


def build_viewer(index: int, version: str = AUDIENCE_VERSION) -> SyntheticViewer:
    """Deterministic profile for seed index (0-based)."""
    return SyntheticViewer(
        handle=f"{_NAMES[index % len(_NAMES)]}_{index + 1:03d}",
        age_bracket=_AGES[index % len(_AGES)],
        region=_REGIONS[(index // 2) % len(_REGIONS)],
        interests=list(_INTEREST_POOLS[index % len(_INTEREST_POOLS)]),
        personality=_PERSONALITIES[index % len(_PERSONALITIES)],
        humor_preferences=list(_HUMOR_POOLS[index % len(_HUMOR_POOLS)]),
        attention_level=_ATTENTION[index % len(_ATTENTION)],
        creator_affinities={},
        response_style=_RESPONSE_STYLES[index % len(_RESPONSE_STYLES)],
        audience_version=version,
        seed_index=index,
    )


def seed_audience(
    db: Session, count: int = _DEFAULT_COUNT, version: str = AUDIENCE_VERSION
) -> list[SyntheticViewer]:
    """Idempotent: returns the existing population if already seeded."""
    if not 1 <= count <= _MAX_COUNT:
        raise ValueError(f"count must be between 1 and {_MAX_COUNT}")
    existing = (
        db.query(SyntheticViewer)
        .filter(SyntheticViewer.audience_version == version)
        .order_by(SyntheticViewer.seed_index)
        .all()
    )
    if len(existing) >= count:
        return existing[:count]
    start = len(existing)
    viewers = [build_viewer(i, version) for i in range(start, count)]
    db.add_all(viewers)
    db.commit()
    for v in viewers:
        db.refresh(v)
    return existing + viewers


def baseline_interest(viewer: SyntheticViewer, text: str, tags: list[str] | None = None) -> float:
    """Deterministic 0..1 interest estimate for one viewer on one content blurb.

    Lightweight precursor to the full reaction model (Sprint 4.2): interest
    overlap dominates, modulated by attention, humor match, and familiarity.
    """
    content_words = _words(text) | _words(" ".join(tags or []))
    interest_words = _words(" ".join(viewer.interests or []))
    humor_words = _words(" ".join(viewer.humor_preferences or []))

    overlap = 0.0
    if interest_words and content_words:
        overlap = len(interest_words & content_words) / len(interest_words | content_words)

    score = 0.15 + 0.6 * overlap
    score += 0.1 * (viewer.attention_level or 0.5)
    if humor_words & content_words:
        score += 0.15
    affinities = viewer.creator_affinities or {}
    if affinities:
        score += 0.1 * max(float(v) for v in affinities.values())
    return round(max(0.0, min(1.0, score)), 3)
