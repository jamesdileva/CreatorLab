"""Deterministic offline provider — tests, demos, and voice checks without API keys.

Roleplays from the request's PersonaHint (same creator fields the real
providers read via the system prompt). In "json" mode it emits a valid
episode draft so the parsing/evaluation pipeline is fully exercised offline.
"""
import json

from .base import GenerateRequest, GenerateResponse, LLMProvider

TAKES = [
    "Here's my take on that.",
    "Let me put it this way.",
    "Funny you should ask.",
]


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
    ]
    archetype = archetypes[request.variant % len(archetypes)]
    scenes = [
        {"title": title, "direction": direction}
        for title, direction in archetype["scenes"]
    ]
    script_lines = [
        f"EPISODE {request.variant + 1} — {name.upper()}",
        f"INT. THE PLACE — DAY",
        f"{name}: {archetype['premise']}",
        f"NARRATION: {archetype['synopsis']}",
        f"{name}: And just so it's on record: {canon}",
        "END.",
    ]
    draft = {
        "premise": archetype["premise"],
        "synopsis": archetype["synopsis"],
        "scenes": scenes,
        "script": "\n".join(script_lines),
    }
    return "```json\n" + json.dumps(draft) + "\n```"


class StubProvider(LLMProvider):
    name = "stub"

    def generate(self, request: GenerateRequest) -> GenerateResponse:
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
