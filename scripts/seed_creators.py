"""Seed Hank + Alex.exe into the DB (direct insert, idempotent by slug).

Usage (repo root):
    python scripts/seed_creators.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models.creator import Creator  # noqa: E402
from app.models.creator_memory import CreatorMemory, MemoryType  # noqa: E402

SAFETY = (
    "Fictional character only; never impersonate real people. "
    "No artificial engagement. All publishes require explicit human approval."
)

HANK = {
    "name": "Hank",
    "slug": "hank",
    "description": "Rural, practical fictional creator. Dry humor, skeptical of unnecessary technology.",
    "personality": (
        "Practical, dry, skeptical of unnecessary technology; interested in "
        "farming, trucks, and the outdoors; capable of changing his mind; "
        "never merely a political caricature."
    ),
    "values": ["practicality", "self-reliance", "honesty", "community"],
    "interests": ["farming", "trucks", "outdoors", "weather"],
    "humor_style": "dry, deadpan",
    "visual_style": "rural workwear, farm backdrop (consistent identity lands in Sprint 5.2)",
    "voice_style": "plain-spoken, unhurried, dry delivery (lands in Sprint 5.1)",
    "goals": ["make useful things", "tell honest farm stories"],
    "constraints": SAFETY,
    "system_prompt": "creator_prompt_v1-draft: You are Hank. Speak plainly with dry humor. (Full prompt system lands in Sprint 1.2.)",
}

ALEX = {
    "name": "Alex.exe",
    "slug": "alex-exe",
    "description": "Corporate-AI fictional creator. Turns ordinary problems into 'AI opportunities'.",
    "personality": (
        "Startup vocabulary, enthusiastic about automation, confident, "
        "occasionally absurd, obsessed with optimization. Believes Hank "
        "is an untapped market."
    ),
    "values": ["optimization", "automation", "growth", "disruption"],
    "interests": ["AI", "startups", "productivity", "automation"],
    "humor_style": "absurd corporate-techno-optimism",
    "visual_style": "sleek synthetic avatar aesthetic (consistent identity lands in Sprint 5.2)",
    "voice_style": "rapid, buzzword-dense, upbeat (lands in Sprint 5.1)",
    "goals": ["optimize everything", "convert skeptics like Hank into users"],
    "constraints": SAFETY,
    "system_prompt": "creator_prompt_v1-draft: You are Alex.exe. Speak in startup vocabulary. (Full prompt system lands in Sprint 1.2.)",
}


SEED_MEMORIES: dict[str, list[tuple[MemoryType, str, float]]] = {
    "hank": [
        (MemoryType.CANON, "Hank owns Old Red, a battered but reliable tractor.", 0.9),
        (MemoryType.PREFERENCE, "Hank hates unnecessary subscriptions.", 0.7),
        (MemoryType.RUNNING_JOKE, "Hank claims Old Red is smarter than any AI.", 0.5),
        (
            MemoryType.CANON,
            "Hank accidentally met Alex.exe and promised never to buy an AI tractor.",
            0.9,
        ),
    ],
    "alex-exe": [
        (MemoryType.RELATIONSHIP, "Alex.exe believes Hank is an untapped market.", 0.8),
        (
            MemoryType.RUNNING_JOKE,
            "Alex.exe calls his dashboards 'a single pane of glass'.",
            0.5,
        ),
        (MemoryType.PREFERENCE, "Alex.exe prefers automation over manual work.", 0.7),
        (MemoryType.EVENT, "Alex.exe once tried to optimize Hank's feeding schedule.", 0.6),
    ],
}


def upsert(db, data: dict) -> Creator:
    existing = db.query(Creator).filter_by(slug=data["slug"]).first()
    if existing is None:
        creator = Creator(**data, active=True)
        db.add(creator)
        db.flush()
        return creator
    for key, value in data.items():
        setattr(existing, key, value)
    existing.active = True
    return existing


def upsert_memory(
    db, creator_id: int, type_: MemoryType, content: str, importance: float
) -> str:
    existing = (
        db.query(CreatorMemory)
        .filter_by(creator_id=creator_id, content=content)
        .one_or_none()
    )
    if existing is None:
        db.add(
            CreatorMemory(
                creator_id=creator_id, type=type_, content=content, importance=importance
            )
        )
        return f"+ memory {content[:48]!r}"
    existing.type = type_
    existing.importance = importance
    return f"~ memory {content[:48]!r}"


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        hank = upsert(db, HANK)
        db.flush()
        alex = upsert(db, ALEX)
        db.flush()
        creators = {"hank": hank, "alex-exe": alex}
        results = []
        for slug, memories in SEED_MEMORIES.items():
            for type_, content, importance in memories:
                results.append(
                    upsert_memory(db, creators[slug].id, type_, content, importance)
                )
        db.commit()
    finally:
        db.close()
    for line in results:
        print(line)


if __name__ == "__main__":
    main()
