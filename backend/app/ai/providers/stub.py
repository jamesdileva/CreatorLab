"""Deterministic offline provider — tests, demos, and voice checks without API keys.

Roleplays from the request's PersonaHint (same creator fields the real
providers read via the system prompt). In "json" mode it emits a valid
episode draft; in "concepts" mode a JSON array of distinct concepts.
"""
import json
import re

from .base import GenerateRequest, GenerateResponse, LLMProvider

TAKES = [
    "Here's my take on that.",
    "Let me put it this way.",
    "Funny you should ask.",
]


CONCEPT_ARCHETYPES = [
    (
        "the mishap",
        "{name} tries the new thing once and it goes sideways immediately.",
        "It broke on the first try.",
        "slapstick failure",
        ["comedy", "failure"],
    ),
    (
        "the bargain",
        "{name} trades something valuable for a shortcut and pays for it later.",
        "What would you trade for an easy day?",
        "cost of convenience",
        ["comedy", "consequence"],
    ),
    (
        "the rival",
        "A snooty outsider challenges {name} at the county fair.",
        "Nobody outdoes the old way. Nobody.",
        "rivalry",
        ["competition", "pride"],
    ),
    (
        "the lesson",
        "{name} teaches a visitor why the old way still works.",
        "Some things cannot be optimized.",
        "mentorship",
        ["wholesome", "teaching"],
    ),
    (
        "the suspicion",
        "{name} is sure something is watching the place. It's the router.",
        "The blinking light knows too much.",
        "mild paranoia",
        ["mystery", "comedy"],
    ),
    (
        "the storm",
        "Weather hits at the worst possible moment and {name} improvises.",
        "The forecast said 'fine'. The forecast lied.",
        "nature vs plan",
        ["tension", "improvisation"],
    ),
    (
        "the promise",
        "{name} finally answers a promise made seasons ago.",
        "The promise comes due.",
        "callback",
        ["continuity", "payoff"],
    ),
    (
        "the audit",
        "A metrics-obsessed visitor tries to rate the unrateable.",
        "What gets measured, gets gamed.",
        "satire",
        ["satire", "work"],
    ),
    (
        "the swap",
        "{name} swaps places with the visitor for one day and learns both sides.",
        "A day in the other boots.",
        "role reversal",
        ["comedy", "insight"],
    ),
    (
        "the return",
        "Someone from an early episode comes back changed.",
        "They said they'd be back.",
        "reunion",
        ["continuity", "change"],
    ),
]


def _concepts_JSON(request: GenerateRequest) -> str:
    name = request.persona.name if request.persona else "Creator"
    topic = request.topic or "an ordinary day"
    count = max(1, min(request.count or 5, len(CONCEPT_ARCHETYPES)))
    items = []
    for i in range(count):
        title, premise, hook, angle, tags = CONCEPT_ARCHETYPES[i]
        items.append(
            {
                "title": f"{topic} — {title}",
                "premise": premise.format(name=name),
                "hook": hook.format(name=name),
                "angle": angle,
                "tags": tags,
            }
        )
    return "```json\n" + json.dumps(items) + "\n```"


def _episode_JSON(request: GenerateRequest) -> str:
    name = request.persona.name if request.persona else "Creator"
    canon = request.memories[0] if request.memories else (
        "Old traditions on the farm are worth keeping."
    )
    archetypes = [
        {
            "premise": (
                f"{name}'s oldest machine breaks down the morning of an "
                "important delivery, and there is no time to fix it properly."
            ),
            "synopsis": (
                f"{name} improvises a repair, learns why the machine matters, "
                "and delivers anyway."
            ),
            "scenes": [
                ("The breakdown", f"{name} finds the machine dead at dawn."),
                ("The improvised repair", f"{name} fixes it with what is at hand."),
                ("The delivery", "The machine makes it, barely."),
            ],
        },
        {
            "premise": (
                f"{name} tries a subscription tool to save time and ends up "
                "fighting the pricing screen more than the work."
            ),
            "synopsis": (
                f"{name} cancels the subscription, keeps one feature, and "
                "swears off trials for a week."
            ),
            "scenes": [
                ("The trial", f"{name} signs up with one click."),
                ("The pricing screen", "Four tiers, none of them quite right."),
                ("The cancel", f"{name} keeps one feature and leaves."),
            ],
        },
        {
            "premise": (
                f"{name} is audited by a metrics-obsessed visitor who "
                "promises to optimize everything on the place."
            ),
            "synopsis": (
                f"{name} plays along, games the metrics once, and the "
                "visitor learns a lesson about things that resist measuring."
            ),
            "scenes": [
                ("The audit", "The visitor arrives with a clipboard and a dashboard."),
                ("Gaming the metrics", f"{name} shows the visitor a suspiciously good number."),
                ("The lesson", "Some things on the place do not fit a spreadsheet."),
            ],
        },
        {
            "premise": (
                f"{name} bets against a new forecasting gadget using nothing "
                "but instinct, and instinct is only half right."
            ),
            "synopsis": (
                f"{name} wins the argument in front of witnesses and quietly "
                "checks the gadget again that night."
            ),
            "scenes": [
                ("The bet", f"{name} says the gadget has it wrong."),
                ("The storm that half-comes", "Rain, but not the rain promised."),
                ("The quiet check", f"{name} tests the gadget alone, grudgingly impressed."),
            ],
        },
        {
            "premise": (
                f"{name} enters the county fair contest with the old machine "
                "against a glossy automated competitor."
            ),
            "synopsis": (
                f"{name} wins by a hair, shares the prize, and the glossy "
                "competitor malfunctions in front of everyone."
            ),
            "scenes": [
                ("The rivals", "The glossy competitor hums beside the old machine."),
                ("The contest", "Both machines run; the margin is a hair."),
                ("The prize", f"{name} shares it, and the competitor breaks down."),
            ],
        },
        {
            # callback archetype — resolves the first open thread (deterministic)
            "callback": True,
            "premise": (
                "The promise everyone remembers finally comes due, and the answer "
                "is not what the crowd expects."
            ),
            "synopsis": (
                "An old promise is revisited, a choice is made in front of "
                "witnesses, and the story moves forward."
            ),
            "scenes": [
                ("The promise resurfaces", "Someone brings up the old promise."),
                ("The choice", "The decision is made, plainly, in front of everyone."),
                ("The aftermath", "Things are different now, and better for it."),
            ],
        },
    ]
    archetype = archetypes[request.variant % len(archetypes)]
    scenes = [
        {"title": title, "direction": direction}
        for title, direction in archetype["scenes"]
    ]
    thread_echo = ""
    resolves_thread = None
    if archetype.get("callback") and request.threads:
        resolves_thread = request.threads[0]
        thread_echo = f"\n{name}: About that promise — {resolves_thread}. Here's where I stand."
    script_lines = [
        f"EPISODE {request.variant + 1} — {name.upper()}",
        "INT. THE PLACE — DAY",
        f"{name}: {archetype['premise']}",
        f"NARRATION: {archetype['synopsis']}",
        f"{name}: And just so it's on record: {canon}",
    ]
    if thread_echo:
        script_lines.append(thread_echo.strip())
    if request.universe_canon:
        script_lines.append(f"{name}: Universe fact: {request.universe_canon[0]}")
    script_lines.append("END.")
    draft = {
        "premise": archetype["premise"],
        "synopsis": archetype["synopsis"],
        "scenes": scenes,
        "script": "\n".join(script_lines),
        "resolves_thread": resolves_thread,
    }
    return "```json\n" + json.dumps(draft) + "\n```"


def _cross_episode_JSON(request: GenerateRequest) -> str:
    """Deterministic crossover draft; the cast comes from the prompt's list."""
    participants = _prompt_participants(request.system_prompt)
    universe = request.universe_canon[0] if request.universe_canon else None
    premise = (
        f"{participants[0]} has a problem nobody should solve alone, and "
        f"{participants[1]} insists on helping their way."
    )
    synopsis = (
        f"A shared problem forces {participants[0]} and {participants[1]} to "
        "negotiate one plan; the plan half-works, and together they finish it."
    )
    scenes = [
        ("The problem", f"{participants[0]} explains what broke."),
        ("The negotiation", f"{participants[1]} proposes an ambitious fix."),
        ("The breakdown", "The ambitious fix makes it worse."),
        ("The finish", "They combine approaches and succeed."),
    ]
    script_lines = [
        f"CROSSOVER — {' AND '.join(participants)}",
        "INT. THE PLACE — DAY",
    ]
    for title, direction in scenes:
        script_lines.append(f"* {title} — {direction}")
    for name in participants:
        script_lines.append(f"{name}: We're only doing this my way.")
    if universe:
        script_lines.append(f"NARRATION: Universe fact: {universe}")
    script_lines.append("END.")
    draft = {
        "participants": participants,
        "premise": premise,
        "synopsis": synopsis,
        "scenes": [{"title": t, "direction": d} for t, d in scenes],
        "script": "\n".join(script_lines),
    }
    return "```json\n" + json.dumps(draft) + "\n```"


def _prompt_participants(system_prompt: str) -> list[str]:
    """Read the cast section out of the rendered cross prompt."""
    names: list[str] = []
    in_cast = False
    for line in system_prompt.splitlines():
        stripped = line.strip()
        if stripped == "## Cast":
            in_cast = True
            continue
        if in_cast:
            if stripped.startswith("## "):
                break
            if stripped.startswith("- "):
                candidate = stripped[2:].split(" (")[0].strip()
                if candidate and candidate.lower() not in {"none yet", "(none)"}:
                    names.append(candidate)
    return names or ["Hank", "Alex.exe"]


def _agent_action_JSON(request: GenerateRequest) -> str:
    """Deterministic agent trajectory for the emulator (roadmap Sprint 20.2).

    Reads a post id (`#<id>`) and an author handle (`@name`) from the rendered
    screen in the user message, then walks a fixed scripted sequence by step.
    """
    screen = request.user_message
    feed_match = re.search(r"#(\d+)\]\s*@([a-z0-9_.-]+)", screen)
    if feed_match:
        post_id = int(feed_match.group(1))
        author = feed_match.group(2)
    else:
        post = re.search(r"#(\d+)", screen)
        handle = re.search(r"@([a-z0-9_.-]+)", screen)
        post_id = int(post.group(1)) if post else None
        author = handle.group(1) if handle else None

    step = request.variant % 6
    if post_id is None:
        action = {"action": "scroll", "reasoning": "loading the feed"}
        if step >= 4:
            action = {"action": "stop", "reasoning": "nothing to engage with"}
    elif step == 0:
        action = {"action": "scroll", "reasoning": "scanning the feed"}
    elif step == 1:
        action = {"action": "open", "target_id": post_id, "reasoning": "opening the top post"}
    elif step == 2:
        action = {
            "action": "watch",
            "target_id": post_id,
            "watch_seconds": 9,
            "liked": True,
            "reasoning": "watching and liking the post",
        }
    elif step == 3:
        action = {
            "action": "comment",
            "target_id": post_id,
            "body": "Nice one.",
            "reasoning": "leaving a short comment after watching",
        }
    elif step == 4 and author:
        action = {"action": "follow", "handle": author, "reasoning": "following the creator"}
    else:
        action = {"action": "stop", "reasoning": "goal met"}
    return "```json\n" + json.dumps(action) + "\n```"


class StubProvider(LLMProvider):
    name = "stub"

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        if request.response_format == "agent_action":
            return GenerateResponse(
                text=_agent_action_JSON(request), model="stub/deterministic-v1"
            )
        if request.response_format == "cross_episode":
            return GenerateResponse(
                text=_cross_episode_JSON(request), model="stub/deterministic-v1"
            )
        if request.response_format == "concepts":
            return GenerateResponse(
                text=_concepts_JSON(request), model="stub/deterministic-v1"
            )
        if request.response_format == "json":
            return GenerateResponse(text=_episode_JSON(request), model="stub/deterministic-v1")
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
        if request.memories:
            recall = "; ".join(request.memories)
            text += f" And here's what I remember about my own story: {recall}."
        return GenerateResponse(text=text, model="stub/deterministic-v1")
