"""Viewer memory — creator familiarity tiers (roadmap Sprint 11.2).

Familiarity grows from what a viewer has already watched. Per creator it is
the watch-weighted exposure, then tiered unknown → familiar → favorite and
converted to a gentle affinity used downstream (same-target reruns excluded,
so reruns stay reproducible).

Existing explicit affinities win when set (Sprint 4.1 preview endpoint),
so this fills the gap rather than overwriting operator intent. Episodes
only — concept runs stay memory-free per 11.1.
"""
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.episode import Episode
from ..models.simulation import SimulationRun, ViewerReaction
from .viewer_memory import content_words_for_run

FAMILIAR_MIN = 1.2  # exposure needed to leave "unknown"
FAVORITE_MIN = 3.0  # exposure needed to reach "favorite"
FAMILIAR_STRENGTH = 0.35  # affinity assigned at/below the familiar threshold
FAVORITE_STRENGTH = 0.75

T_UNKNOWN = "unknown"
T_FAMILIAR = "familiar"
T_FAVORITE = "favorite"


def tier_for(exposure: float) -> str:
    if exposure >= FAVORITE_MIN:
        return T_FAVORITE
    if exposure >= FAMILIAR_MIN:
        return T_FAMILIAR
    return T_UNKNOWN


def strength_for(exposure: float) -> float:
    """Monotonic affinity: 0 while unknown, climbing toward favorite level."""
    if exposure <= FAMILIAR_MIN:
        return 0.0
    if exposure >= FAVORITE_MIN:
        return FAVORITE_STRENGTH
    span = FAVORITE_MIN - FAMILIAR_MIN
    share = (exposure - FAMILIAR_MIN) / span
    return round(FAMILIAR_STRENGTH + share * (FAVORITE_STRENGTH - FAMILIAR_STRENGTH), 3)


def exposure_map(
    db: Session,
    viewer_id: int,
    creator_id: int,
    exclude_type: str,
    exclude_id: int,
) -> dict[int, float]:
    """Watch-weighted exposure per episode of one creator (same target excluded)."""
    episodes = (
        db.query(Episode).filter(Episode.creator_id == creator_id).order_by(Episode.id).all()
    )
    if not episodes:
        return {}
    watched = {
        r.run_id: r.watch_probability
        for r in db.query(ViewerReaction).filter(ViewerReaction.viewer_id == viewer_id).all()
    }
    exposure: dict[int, float] = {}
    for run in db.query(SimulationRun).order_by(SimulationRun.id).all():
        if run.target_type != exclude_type:
            continue
        if run.target_id == exclude_id:
            continue
        episode = next((e for e in episodes if e.id == run.target_id), None)
        if episode is None:
            continue
        exposure[episode.id] = exposure.get(episode.id, 0.0) + watched.get(run.id, 0.0)
    return {eid: round(v, 3) for eid, v in exposure.items() if v > 0}


def familiarity_for(
    db: Session,
    viewer_id: int,
    creator_id: int,
    exclude_type: str,
    exclude_id: int,
) -> tuple[str, float, float]:
    """(tier, affinity, exposure) for a viewer on a creator's content."""
    exposure = sum(exposure_map(db, viewer_id, creator_id, exclude_type, exclude_id).values())
    return tier_for(exposure), strength_for(exposure), round(exposure, 3)


def describe_creator_audience(db: Session, creator_id: int) -> dict:
    """Familiarity breakdown across the audience for one creator."""
    from ..models.viewer import SyntheticViewer

    creator = db.get(Creator, creator_id)
    if creator is None:
        raise ValueError("creator not found")
    viewers = (
        db.query(SyntheticViewer)
        .filter(SyntheticViewer.audience_version == SyntheticViewer.audience_version)
        .all()
    )
    if not viewers:
        viewers = (
            db.query(SyntheticViewer).order_by(SyntheticViewer.seed_index).all()
        )
    tiers = {T_UNKNOWN: 0, T_FAMILIAR: 0, T_FAVORITE: 0}
    per_viewer = []
    for viewer in viewers:
        exposure = sum(exposure_map(db, viewer.id, creator_id, "episode", -1).values())
        tier = tier_for(exposure)
        tiers[tier] += 1
        per_viewer.append(
            {"viewer_id": viewer.id, "handle": viewer.handle, "exposure": round(exposure, 3), "tier": tier}
        )
    return {
        "creator_id": creator_id,
        "creator_slug": creator.slug,
        "viewer_count": len(viewers),
        "tiers": tiers,
        "familiar_or_better": tiers[T_FAMILIAR] + tiers[T_FAVORITE],
        "viewers": sorted(per_viewer, key=lambda v: -v["exposure"]),
    }
