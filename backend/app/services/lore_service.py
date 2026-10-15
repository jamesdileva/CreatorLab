"""Audience lore — distill recurring viewer reactions into themes (Sprint 14.2).

All signals come from simulation behavior: phrase recurrence across distinct
episodes the audience watched above the median. Promotion into series canon
stays a human action (architecture §5.6).
"""
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.audience_lore import AudienceLore
from ..models.canon import Canon, CanonCategory
from ..models.episode import Episode
from ..models.simulation import SimulationRun, ViewerReaction

RECURRING_THRESHOLD = 2  # distinct episodes before a theme counts as recurring

_STOPWORDS = {
    "the", "and", "his", "her", "that", "with", "from", "this", "have", "has",
    "was", "for", "are", "not", "but", "into", "than", "then", "them", "they",
    "about", "when", "what", "which", "their", "there", "here", "over", "just",
    "morning", "evening",
}


def _bigrams(text: str) -> set[str]:
    words = [
        w.strip(".,;:!?\"'()").lower()
        for w in re.findall(r"[A-Za-z][A-Za-z'-]+", text or "")
    ]
    words = [w for w in words if w not in _STOPWORDS and len(w) >= 3]
    return {
        f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)
    }


def _run_mean_watch(db: Session, run: SimulationRun) -> float | None:
    reactions = (
        db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
    )
    if not reactions:
        return None
    return sum(r.watch_probability for r in reactions) / len(reactions)


def _status_for(episode_count: int) -> str:
    return "recurring" if episode_count >= RECURRING_THRESHOLD else "emerging"


def distill_lore(db: Session, min_watch: float | None = None) -> list[AudienceLore]:
    """Create/refresh lore themes from episode-level simulation runs."""
    runs = (
        db.query(SimulationRun)
        .filter(SimulationRun.target_type == "episode")
        .order_by(SimulationRun.id)
        .all()
    )
    scored: list[tuple[SimulationRun, Episode, float, set[str]]] = []
    for run in runs:
        episode = db.get(Episode, run.target_id)
        if episode is None:
            continue
        mean_watch = _run_mean_watch(db, run)
        if mean_watch is None:
            continue
        phrases = _bigrams(f"{episode.title} {episode.premise}")
        if phrases:
            scored.append((run, episode, mean_watch, phrases))

    if not scored:
        return []

    values = [s[2] for s in scored]
    mean_watch = sum(values) / len(values)
    threshold = min_watch if min_watch is not None else mean_watch

    # theme -> {episode_id: watch} for episodes above the threshold
    observed: dict[tuple[str, int], dict[int, float]] = {}
    for run, episode, mean_watch, phrases in scored:
        if mean_watch < threshold:
            continue
        for phrase in phrases:
            observed.setdefault((phrase, episode.creator_id), {})[episode.id] = mean_watch

    now = datetime.now(timezone.utc)
    results: list[AudienceLore] = []
    for (theme, creator_id), episodes in sorted(observed.items()):
        watches = list(episodes.values())
        lore = (
            db.query(AudienceLore)
            .filter_by(theme=theme, creator_id=creator_id)
            .one_or_none()
        )
        if lore is None:
            lore = AudienceLore(
                theme=theme,
                creator_id=creator_id,
                episode_ids=[],
                mention_count=0,
                avg_watch=0.0,
                status="emerging",
                first_seen=now,
            )
            db.add(lore)
        lore.episode_ids = sorted(episodes)
        lore.mention_count = len(episodes)
        lore.avg_watch = round(sum(watches) / len(watches), 3)
        lore.status = _status_for(len(episodes))
        lore.last_seen = now
        results.append(lore)
    db.commit()
    for lore in results:
        db.refresh(lore)
    results.sort(key=lambda l: (-l.mention_count, -l.avg_watch, l.theme))
    return results


def promote_lore(db: Session, lore_id: int) -> Canon:
    """Human-approved promotion into the series' RUNNING_JOKE canon."""
    lore = db.get(AudienceLore, lore_id)
    if lore is None:
        raise ValueError("audience lore not found")
    if lore.status == "promoted" and lore.promoted_canon_id:
        existing = db.get(Canon, lore.promoted_canon_id)
        if existing is not None:
            return existing  # idempotent
    if lore.status == "emerging":
        raise ValueError(
            "theme is still emerging (seen in one episode); distill more runs first"
        )

    episode = db.get(Episode, lore.episode_ids[0]) if lore.episode_ids else None
    if episode is None:
        raise ValueError("lore has no episode to attach canon to")

    canon = Canon(
        series_id=episode.series_id,
        category=CanonCategory.RUNNING_JOKE,
        statement=f"Audience lore: {lore.theme}",
    )
    db.add(canon)
    db.flush()
    lore.status = "promoted"
    lore.promoted_canon_id = canon.id
    db.commit()
    db.refresh(canon)
    db.refresh(lore)
    return canon
