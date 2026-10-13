"""Viewer memory — repetition fatigue (roadmap Sprint 11.1).

Viewers remember what they have already seen. Effective exposure to new
content is the watch-weighted recall of its words across past runs: a viewer
who actually watched five tractor episodes is heavily exposed, one who
scrolled past barely registers them.

Same-target reruns are excluded, so identical reruns stay bit-identical
(guide §9). No new tables: memory is derived from stored runs + reactions.

Scope: fatigue applies to episode runs only. Episodes are the aired content
viewers remember (roadmap: "prior episodes"); concept evaluations are
internal drafts the audience never saw, so ranking candidates through the
same population stays a clean read of content differences.
"""
from sqlalchemy.orm import Session

from ..models.simulation import SimulationRun, ViewerReaction
from .audience_service import _words

FATIGUE_SLOPE = 0.12  # watch lost per effective exposure past the free allowance
FATIGUE_FREE = 0.75  # roughly the first full viewing is free (novelty grace)
FATIGUE_CAP = 0.35  # fatigue never erases more than this
MIN_SHARED_WORDS = 2  # a past run counts only with this many shared words


def content_words_for_run(db: Session, run: SimulationRun) -> set[str]:
    """Word set of a past run's content; empty when its target is gone."""
    from .simulation_service import _resolve_content

    try:
        title, premise, hook, tags = _resolve_content(db, run.target_type, run.target_id)
    except ValueError:
        return set()
    return _words(title) | _words(premise) | _words(hook) | _words(" ".join(tags))


def effective_exposures(
    db: Session,
    viewer_id: int,
    words: set[str],
    exclude_type: str,
    exclude_id: int,
) -> float:
    """Watch-weighted recall of `words` across past runs (same target excluded)."""
    if not words:
        return 0.0
    runs = db.query(SimulationRun).order_by(SimulationRun.id).all()
    watched = {
        r.run_id: r.watch_probability
        for r in db.query(ViewerReaction).filter(ViewerReaction.viewer_id == viewer_id).all()
    }
    total = 0.0
    for run in runs:
        if run.target_type == exclude_type and run.target_id == exclude_id:
            continue
        past = content_words_for_run(db, run)
        shared = words & past
        if len(shared) >= MIN_SHARED_WORDS:
            total += watched.get(run.id, 0.0) * (len(shared) / len(words))
    return round(total, 3)


def fatigue_penalty(effective: float) -> float:
    """Watch-probability penalty for a given effective exposure."""
    return round(min(FATIGUE_CAP, FATIGUE_SLOPE * max(0.0, effective - FATIGUE_FREE)), 3)
