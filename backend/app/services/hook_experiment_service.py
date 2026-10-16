"""Hook experiment — do the simulator and reality agree on hook types? (16.1).

Content strategy experiment (roadmap 16.1): label each episode's opening hook as
one of four types, then compare how the synthetic audience and the real audience
respond to each type.

Hook text = first sentence of the episode synopsis (the same text the reaction
engine treats as the episode hook), falling back to the premise then the title.

Classification is deterministic and documented (priority: question → character →
absurd → direct). Interpretation is gated (guide §15): numbers always carry
sample counts, the verdict waits for MIN_TOTAL episodes.
"""
import re

from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.episode import Episode
from ..models.published_video import PublishedVideo
from ..models.simulation import ViewerReaction
from ..models.video_metrics import VideoMetrics
from .review_service import latest_simulation_for
from .simulation_service import aggregate_reactions

HOOK_TYPES = ("direct", "question", "absurd", "character")

MIN_TOTAL = 4
MIN_PER_TYPE = 2

_QUESTION_STARTERS = {
    "what", "why", "how", "who", "when", "where", "which", "whose",
    "do", "does", "did", "can", "could", "is", "are", "was", "were",
    "will", "would", "should", "shall", "may", "might",
}

# concrete absurdity/hyperbole markers (word-boundary matched)
_ABSURD_MARKERS = {
    "literally", "impossible", "glitch", "explodes", "explode", "exploded",
    "alien", "aliens", "portal", "vortex", "sentient", "haunted", "screams",
    "scream", "sues", "lawsuit", "zombie", "wizard", "dragon", "time-travel",
    "conspiracy", "teleport", "mutant", "possessed",
}


def first_sentence(text: str | None) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    match = re.search(r"[.!?]", text)
    return text[: match.end()].strip() if match else text


def episode_hook(episode: Episode) -> str:
    """The text the reaction engine / classifier treats as the hook."""
    return (
        first_sentence(episode.synopsis)
        or first_sentence(episode.premise)
        or (episode.title or "").strip()
    )


def classify_hook(hook: str | None, character_names: tuple[str, ...] = ()) -> str:
    """Map hook text to one of HOOK_TYPES (priority question → character → absurd)."""
    text = (hook or "").strip()
    if not text:
        return "direct"
    lowered = text.lower()
    words = set(re.findall(r"[a-z][a-z'-]+", lowered))
    first_word = (re.match(r"[a-z][a-z'-]+", lowered) or [None])[0]

    if text.endswith("?") or first_word in _QUESTION_STARTERS:
        return "question"

    names = {n.lower().strip() for n in character_names if n and n.strip()}
    for name in names:
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return "character"
    if re.search(r"\b(i'?m|i am|my name is|call me)\b", lowered):
        return "character"

    if words & _ABSURD_MARKERS:
        return "absurd"

    return "direct"


def _character_names(db: Session) -> tuple[str, ...]:
    names: list[str] = []
    for creator in db.query(Creator).order_by(Creator.id).all():
        full = (creator.name or "").strip()
        if not full:
            continue
        names.append(full)
        first = re.split(r"\s+", full)[0]
        if first and first != full:
            names.append(first)
    return tuple(names)


def _sim_watch(db: Session, episode_id: int) -> float | None:
    run = latest_simulation_for(db, episode_id)
    if run is None:
        return None
    reactions = db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
    if not reactions:
        return None
    return aggregate_reactions(reactions)["means"]["watch_probability"]


def _real_views(db: Session, episode_id: int) -> int | None:
    video = (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id == episode_id)
        .order_by(PublishedVideo.id.desc())
        .first()
    )
    if video is None:
        return None
    snap = (
        db.query(VideoMetrics)
        .filter(VideoMetrics.published_video_id == video.id)
        .order_by(VideoMetrics.id.desc())
        .first()
    )
    return snap.views if snap is not None else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def hook_experiment_report(db: Session, creator_id: int | None = None) -> dict:
    """Per-hook-type simulation vs reality comparison across episodes."""
    names = _character_names(db)
    query = db.query(Episode).order_by(Episode.id)
    if creator_id is not None:
        query = query.filter(Episode.creator_id == creator_id)
    episodes = query.all()

    hooks: list[dict] = []
    grouped: dict[str, dict[str, list]] = {t: {"sim": [], "real": []} for t in HOOK_TYPES}
    for episode in episodes:
        hook = episode_hook(episode)
        if not hook:
            continue
        hook_type = classify_hook(hook, names)
        sim_watch = _sim_watch(db, episode.id)
        real_views = _real_views(db, episode.id)
        if sim_watch is not None:
            grouped[hook_type]["sim"].append(sim_watch)
        if real_views is not None:
            grouped[hook_type]["real"].append(real_views)
        hooks.append(
            {
                "episode_id": episode.id,
                "hook": hook,
                "hook_type": hook_type,
                "sim_watch": sim_watch,
                "real_views": real_views,
            }
        )

    by_type: dict[str, dict] = {}
    for hook_type in HOOK_TYPES:
        sims = grouped[hook_type]["sim"]
        reals = grouped[hook_type]["real"]
        by_type[hook_type] = {
            "episodes": sum(1 for h in hooks if h["hook_type"] == hook_type),
            "with_sim": len(sims),
            "with_reality": len(reals),
            "mean_sim_watch": _mean(sims),
            "mean_real_views": _mean([float(v) for v in reals]),
            "sim_sufficient": len(sims) >= MIN_PER_TYPE,
            "reality_sufficient": len(reals) >= MIN_PER_TYPE,
        }

    def preferred(metric: str) -> str | None:
        candidates = [
            (t, by_type[t][metric])
            for t in HOOK_TYPES
            if by_type[t][metric] is not None
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda pair: (-pair[1], HOOK_TYPES.index(pair[0])))
        return candidates[0][0]

    sim_preferred = preferred("mean_sim_watch")
    reality_preferred = preferred("mean_real_views")
    total = sum(1 for h in hooks if h["sim_watch"] is not None or h["real_views"] is not None)
    interpretation_allowed = total >= MIN_TOTAL
    agreement = (
        sim_preferred == reality_preferred
        if sim_preferred is not None and reality_preferred is not None
        else None
    )

    if not interpretation_allowed:
        verdict = "insufficient data — no interpretation (guide §15)"
    elif agreement is None:
        verdict = "need both simulation and reality samples to compare"
    elif agreement:
        verdict = "simulator agrees with reality on the preferred hook"
    else:
        verdict = "simulator and reality disagree on the preferred hook"

    return {
        "hook_types": list(HOOK_TYPES),
        "min_total": MIN_TOTAL,
        "min_per_type": MIN_PER_TYPE,
        "episodes_considered": total,
        "interpretation_allowed": interpretation_allowed,
        "hooks": hooks,
        "by_type": by_type,
        "simulation_preferred": sim_preferred,
        "reality_preferred": reality_preferred,
        "agreement": agreement,
        "verdict": verdict,
    }
