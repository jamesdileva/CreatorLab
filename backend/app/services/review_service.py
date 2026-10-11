"""Human review queue + risk screening (roadmap Sprint 6.1, guide §19).

The review screen is the gate between generated content and the outside world:
nothing progresses without explicit human approval (architecture §5.6).
Risks are deterministic keyword/pattern screens — cheap and inspectable.
"""
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models.concept import Concept
from ..models.creator import Creator
from ..models.episode import Episode
from ..models.render import Render
from ..models.scene import Scene
from ..models.series import Series
from ..models.simulation import SimulationRun, ViewerReaction
from .simulation_service import aggregate_reactions

PENDING_STATUSES = ("IDEA", "SIMULATION", "REVIEW")

# Hard blocks: impersonation of real people (architecture §20).
REAL_PERSON_TERMS = [
    "taylor swift", "elon musk", "donald trump", "joe biden", "barack obama",
    "kim kardashian", "mrbeast", "pewdiepie", "oprah",
]
# Copyright-dependent content: never build the strategy on someone else's IP.
COPYRIGHT_TERMS = [
    "disney", "marvel", "star wars", "nintendo", "pokemon", "harry potter",
    "batman", "spider-man", "mickey mouse", "frozen",
]
# Sensitive topics: not banned, but always require human judgment.
SENSITIVE_TERMS = [
    "election", "vaccine", "medical advice", "diagnos", "investment advice",
    "crypto", "conspiracy", "religion", "tragedy", "lawsuit",
]
BANNED_TERMS = ["deepfake", "impersonat", "real person ", "buy views", "manipulate the algorithm"]

_STOPWORDS = {"the", "and", "his", "her", "that", "with", "from", "this", "have"}


def _words(text: str) -> set[str]:
    return {
        w.lower()
        for w in re.findall(r"[A-Za-z][A-Za-z'-]+", text)
        if len(w) > 3 and w.lower() not in _STOPWORDS
    }


def _overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


@dataclass
class Risk:
    code: str
    severity: str  # PASS | REVIEW | BLOCK
    detail: str


@dataclass
class ReviewPayload:
    episode: dict
    creator: dict | None
    series: dict | None
    scenes: list[dict]
    latest_render: dict | None
    simulation: dict | None
    risks: list[Risk] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def status(self) -> str:
        if any(r.severity == "BLOCK" for r in self.risks):
            return "BLOCK"
        if any(r.severity == "REVIEW" for r in self.risks):
            return "REVIEW"
        return "PASS"


def screen_episode(episode: Episode, sibling_premises: list[str]) -> list[Risk]:
    """Deterministic risk screen for the review screen (guide §19)."""
    text = " ".join(
        [episode.title, episode.premise, episode.synopsis, episode.script]
    ).lower()
    risks: list[Risk] = []

    for term in BANNED_TERMS:
        if term in text:
            risks.append(Risk("safety_violation", "BLOCK", f"contains banned term: {term!r}"))
    for term in REAL_PERSON_TERMS:
        if term in text:
            risks.append(
                Risk("real_person_reference", "BLOCK",
                     f"references real person {term!r} — impersonation is forbidden")
            )
    for term in COPYRIGHT_TERMS:
        if term in text:
            risks.append(
                Risk("copyright_dependency", "BLOCK",
                     f"references third-party IP {term!r}")
            )
    for term in SENSITIVE_TERMS:
        if term in text:
            risks.append(
                Risk("sensitive_topic", "REVIEW", f"touches sensitive topic: {term!r}")
            )

    for old in sibling_premises:
        if episode.premise and _overlap(episode.premise, old) > 0.6:
            risks.append(
                Risk("repetition", "REVIEW", f"premise resembles another episode: {old[:60]!r}")
            )

    risks.append(
        Risk("synthetic_media_disclosure", "REVIEW",
             "AI-generated content — confirm platform synthetic-media disclosure")
    )
    if not risks:
        risks.append(Risk("clean", "PASS", "no risks detected"))
    return risks


def _episode_dict(episode: Episode) -> dict:
    return {
        "id": episode.id,
        "creator_id": episode.creator_id,
        "series_id": episode.series_id,
        "episode_number": episode.episode_number,
        "title": episode.title,
        "premise": episode.premise,
        "synopsis": episode.synopsis,
        "script": episode.script,
        "status": episode.status.value,
        "created_at": episode.created_at.isoformat(),
        "updated_at": episode.updated_at.isoformat(),
    }


def latest_render_for(db: Session, episode_id: int) -> Render | None:
    return (
        db.query(Render)
        .filter(Render.episode_id == episode_id)
        .order_by(Render.id.desc())
        .first()
    )


def latest_simulation_for(db: Session, episode_id: int) -> SimulationRun | None:
    return (
        db.query(SimulationRun)
        .filter(
            SimulationRun.target_type == "episode",
            SimulationRun.target_id == episode_id,
        )
        .order_by(SimulationRun.id.desc())
        .first()
    )


def review_payload(db: Session, episode: Episode) -> ReviewPayload:
    creator = db.get(Creator, episode.creator_id)
    series = db.get(Series, episode.series_id)
    scenes = [
        {"scene_number": s.scene_number, "title": s.title, "direction": s.direction}
        for s in db.query(Scene)
        .filter(Scene.episode_id == episode.id)
        .order_by(Scene.scene_number)
        .all()
    ]

    render = latest_render_for(db, episode.id)
    render_dict = None
    if render is not None and render.status == "READY":
        base = f"/media/generated/episode_{episode.id}/render_{render.id}"
        render_dict = {
            "render_id": render.id,
            "video_url": f"{base}/final.mp4",
            "captions_url": f"{base}/captions.srt",
            "manifest_url": f"{base}/manifest.json",
            "total_duration": render.total_duration,
            "card_version": render.card_version,
            "identity_version": render.identity_version,
        }

    sim = latest_simulation_for(db, episode.id)
    sim_dict = None
    if sim is not None:
        reactions = (
            db.query(ViewerReaction).filter(ViewerReaction.run_id == sim.id).all()
        )
        if reactions:
            sim_dict = {
                "run_id": sim.id,
                "model": sim.model,
                "prompt_version": sim.prompt_version,
                "audience_version": sim.audience_version,
                "aggregate": aggregate_reactions(reactions),
            }

    siblings = [
        e.premise
        for e in db.query(Episode)
        .filter(Episode.series_id == episode.series_id, Episode.id != episode.id)
        .all()
        if e.premise
    ]
    risks = screen_episode(episode, siblings)

    return ReviewPayload(
        episode=_episode_dict(episode),
        creator={
            "id": creator.id,
            "name": creator.name,
            "slug": creator.slug,
        }
        if creator
        else None,
        series={"id": series.id, "name": series.name} if series else None,
        scenes=scenes,
        latest_render=render_dict,
        simulation=sim_dict,
        risks=risks,
        metadata={
            "status": episode.status.value,
            "episode_number": episode.episode_number,
            "created_at": episode.created_at.isoformat(),
            "updated_at": episode.updated_at.isoformat(),
            "scene_count": len(scenes),
            "word_count": len(episode.script.split()) if episode.script else 0,
        },
    )


def review_queue(db: Session) -> list[Episode]:
    return (
        db.query(Episode)
        .filter(Episode.status.in_(PENDING_STATUSES))
        .order_by(Episode.id.desc())
        .all()
    )
