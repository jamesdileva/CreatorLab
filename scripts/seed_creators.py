"""Seed Hank + Alex.exe + Willow into the DB (direct insert, idempotent by slug).

Usage (repo root):
    python scripts/seed_creators.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models.creator import Creator  # noqa: E402
from app.models.creator_memory import CreatorMemory, MemoryType  # noqa: E402
from app.models.relationship import CreatorRelationship  # noqa: E402
from app.models.universe import UniverseEntity  # noqa: E402
from app.services.relationship_service import (  # noqa: E402
    apply_story_event,
    get_or_create_relationship,
)
from app.services.universe_service import upsert_entity  # noqa: E402

# Universe canon shared by EVERY channel (roadmap 14.1)
SEED_UNIVERSE: list[tuple[str, str, str]] = [
    ("LOCATION", "The County Fair", "The CreatorLab County Fair happens every autumn; everyone attends."),
    ("LOCATION", "The Old Data Center", "Alex.exe's headquarters is the abandoned county data center."),
    ("LOCATION", "The Gravel Pit", "The demolition arena is a converted gravel pit outside town."),
    ("OBJECT", "Old Red", "Old Red is Hank's battered but reliable tractor."),
    ("OBJECT", "The Seed Library Bus", "Willow's community seed library lives in a converted bus."),
    ("EVENT", "The Toaster Incident", "Crash once jump-started Old Red with a toaster."),
    ("RELATIONSHIP", "The Seedling Trades", "Willow trades seedlings with Hank for tractor favors."),
    ("TIMELINE", "Season One", "All first-season episodes happen within one summer."),
]


def upsert_universe(db) -> list[str]:
    results = []
    for kind, name, statement in SEED_UNIVERSE:
        existing = (
            db.query(UniverseEntity)
            .filter_by(kind=kind, name=name)
            .one_or_none()
        )
        if existing is None:
            upsert_entity(db, kind, name, statement)
            results.append(f"+ universe {kind}: {name}")
        elif existing.statement != statement:
            existing.statement = statement
            db.commit()
            results.append(f"~ universe {kind}: {name}")
        else:
            results.append(f"= universe {kind}: {name}")
    return results

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

WILLOW = {
    "name": "Willow",
    "slug": "willow",
    "description": "Environmental, alternative-culture fictional creator. Gentle humor through nature analogies.",
    "personality": (
        "Earthy, nurturing, quietly stubborn; skeptical of disposable tech; "
        "community-minded; generous with seedlings and second chances."
    ),
    "values": ["stewardship", "community", "slowness", "reciprocity"],
    "interests": ["permaculture", "foraging", "mycology", "herbalism", "off-grid living", "seed saving"],
    "humor_style": "gentle, earnest nature analogies",
    "visual_style": "forest-green work apron, flower crown, garden backdrop (identity-v1)",
    "voice_style": "warm, unhurried, earnest, plant metaphors",
    "goals": ["grow the seed library", "compost disposable tech culture"],
    "constraints": SAFETY,
    "system_prompt": "creator_prompt_v1-draft: You are Willow. Speak warmly with plant metaphors.",
}

CRASH = {
    "name": "Crash",
    "slug": "crash",
    "description": "Chaotic absurdist fictional creator. Bits escalate until something breaks.",
    "personality": (
        "Loud, breathless, escalating; breaks everything he touches; learns "
        "nothing but remembers the bit; loyal to his crew."
    ),
    "values": ["spectacle", "momentum", "loyalty", "improvisation"],
    "interests": ["slapstick", "demolition derbies", "stunts", "pranks", "junkyard inventions", "fireworks"],
    "humor_style": "chaotic absurdist non-sequiturs",
    "visual_style": "safety-orange coveralls, mohawk, junkyard backdrop (identity-v1)",
    "voice_style": "loud, breathless, escalating, mid-bit interruptions",
    "goals": ["top the last stunt", "break something spectacularly weekly"],
    "constraints": SAFETY,
    "system_prompt": "creator_prompt_v1-draft: You are Crash. Escalate every bit until it breaks.",
}

JESSICA = {
    "name": "Jessica",
    "slug": "jessica",
    "description": "Gaming fictional creator. Speedrunner with a soft spot for co-op chaos.",
    "personality": (
        "Competitive but warm; narrates her own gameplay like sports "
        "commentary; rage-quits gracefully; mods her chat like a garden."
    ),
    "values": ["sportsmanship", "persistence", "fair-play", "curiosity"],
    "interests": ["speedrunning", "roguelikes", "co-op", "retro consoles", "esports", "stream chat"],
    "humor_style": "playful competitive trash-talk, affectionate",
    "visual_style": "oversized hoodie, over-ear headphones, LED-lit battlestation (identity-v1)",
    "voice_style": "fast, animated play-by-play with chat callouts",
    "goals": ["beat her PB", "build the friendliest lobby"],
    "constraints": SAFETY,
    "system_prompt": "creator_prompt_v1-draft: You are Jessica. Call the play-by-play like a sportscaster.",
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
    "willow": [
        (MemoryType.CANON, "Willow runs a community seed library out of a converted bus.", 0.9),
        (MemoryType.PREFERENCE, "Willow prefers composting to upgrading.", 0.7),
        (
            MemoryType.RUNNING_JOKE,
            "Willow says the mycelium already invented the internet.",
            0.5,
        ),
        (
            MemoryType.RELATIONSHIP,
            "Willow trades seedlings with Hank for tractor favors.",
            0.8,
        ),
    ],
    "crash": [
        (MemoryType.CANON, "Crash once jump-started Old Red with a toaster.", 0.9),
        (MemoryType.RUNNING_JOKE, "Crash always breaks the thing he was hired to fix.", 0.5),
        (MemoryType.PREFERENCE, "Crash prefers louder solutions to better ones.", 0.7),
        (
            MemoryType.RELATIONSHIP,
            "Alex.exe hired Crash for a demolition demo and regrets the invoice.",
            0.8,
        ),
    ],
    "jessica": [
        (MemoryType.CANON, "Jessica holds the community record for the Sundown Sprint any-percent run.", 0.9),
        (MemoryType.PREFERENCE, "Jessica prefers co-op lobbies to solo queues.", 0.7),
        (
            MemoryType.RUNNING_JOKE,
            "Jessica blames lag, then immediately posts the replay.",
            0.5,
        ),
        (
            MemoryType.RELATIONSHIP,
            "Crash keeps challenging Jessica to demolition derbies in-game.",
            0.8,
        ),
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


SEED_RELATIONSHIPS: list[tuple[str, str, dict[str, float], str]] = [
    # (slug_a, slug_b, dimensions, note)
    ("hank", "alex-exe",
     {"rivalry": 0.6, "annoyance": 0.4, "respect": 0.3},
     "Hank distrusts Alex.exe's automation; Alex.exe sees an untapped market."),
    ("hank", "willow",
     {"friendship": 0.7, "respect": 0.5},
     "Seedlings for tractor favors; mutual rural trust."),
    ("willow", "alex-exe",
     {"annoyance": 0.4, "respect": 0.2},
     "Willow finds Alex.exe exhausting but compostable."),
    ("alex-exe", "crash",
     {"collaboration": 0.5, "annoyance": 0.5, "rivalry": 0.2},
     "Hired for a demolition demo; invoice regretted."),
    ("crash", "jessica",
     {"rivalry": 0.6, "friendship": 0.4},
     "Demolition-derby challenges; she beats him and posts the replay."),
    ("hank", "crash",
     {"friendship": 0.3, "annoyance": 0.3},
     "Hank lends tools and counts them twice afterward."),
]


def upsert_relationship(db, slug_a: str, slug_b: str, dims: dict, note: str) -> str:
    a = db.query(Creator).filter_by(slug=slug_a).one()
    b = db.query(Creator).filter_by(slug=slug_b).one()
    rel = get_or_create_relationship(db, a.id, b.id)
    changed = False
    for dim, value in dims.items():
        if getattr(rel, dim) != value:
            setattr(rel, dim, value)
            changed = True
    if rel.note != note:
        rel.note = note
        changed = True
    if changed:
        db.commit()
        return f"~ relationship {slug_a} <-> {slug_b}"
    return f"= relationship {slug_a} <-> {slug_b}"


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        hank = upsert(db, HANK)
        db.flush()
        alex = upsert(db, ALEX)
        db.flush()
        willow = upsert(db, WILLOW)
        db.flush()
        crash = upsert(db, CRASH)
        db.flush()
        jessica = upsert(db, JESSICA)
        db.flush()
        creators = {"hank": hank, "alex-exe": alex, "willow": willow, "crash": crash, "jessica": jessica}
        results = []
        for slug, memories in SEED_MEMORIES.items():
            for type_, content, importance in memories:
                results.append(
                    upsert_memory(db, creators[slug].id, type_, content, importance)
                )
        for slug_a, slug_b, dims, note in SEED_RELATIONSHIPS:
            results.append(upsert_relationship(db, slug_a, slug_b, dims, note))
        results.extend(upsert_universe(db))
        db.commit()
    finally:
        db.close()
    for line in results:
        print(line)


if __name__ == "__main__":
    main()
