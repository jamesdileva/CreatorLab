"""Audience segments — group viewers from behavior, not profile labels (Sprint 11.3).

Segments are derived from how viewers actually reacted: mean watch, mean
follow, engagement rate (like/comment/share per watch) and specialization
(how concentrated a viewer's top-exposure creators are). Labels are derived
from those signals, never hard-coded per viewer:

- loyalist: high watch and high follow (the subscribers)
- reactor: mid watch but high engagement (they like/comment/share)
  - replier: high comment share within engagement (they talk back)
- passionate: everything elevated (deep fans of the landscape)
- lurker: high watch, little reaction (they just watch)
"""
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.episode import Episode
from ..models.simulation import SimulationRun, ViewerReaction
from ..models.viewer import AUDIENCE_VERSION, SyntheticViewer

WATCH_HIGH = 0.5
FOLLOW_HIGH = 0.25
ENGAGE_HIGH = 0.22
COMMENT_SHARE = 0.45  # of a reactor's engagement
TOP_EXPOSURE = 0.3  # share of exposure in the top creator

SEGMENT_ORDER = ["loyalist", "passionate", "replier", "reactor", "lurker", "sampler"]


def _viewers(db: Session) -> list[SyntheticViewer]:
    viewers = (
        db.query(SyntheticViewer)
        .filter(SyntheticViewer.audience_version == AUDIENCE_VERSION)
        .order_by(SyntheticViewer.seed_index)
        .all()
    )
    return viewers or db.query(SyntheticViewer).order_by(SyntheticViewer.seed_index).all()


def viewer_signals(db: Session, viewer: SyntheticViewer) -> dict:
    reactions = (
        db.query(ViewerReaction).filter(ViewerReaction.viewer_id == viewer.id).all()
    )
    if not reactions:
        return None
    n = len(reactions)
    watch = sum(r.watch_probability for r in reactions) / n
    follow = sum(r.follow_probability for r in reactions) / n
    engagement = sum(
        (r.like_probability + r.comment_probability + r.share_probability) / 3 for r in reactions
    ) / n
    comment_share = (
        sum(r.comment_probability for r in reactions)
        / max(1e-9, sum(r.like_probability + r.comment_probability for r in reactions))
    )
    return {
        "viewer_id": viewer.id,
        "handle": viewer.handle,
        "runs": n,
        "watch": round(watch, 3),
        "follow": round(follow, 3),
        "engagement": round(engagement, 3),
        "comment_share": round(comment_share, 3),
    }


def label_segment(signals: dict) -> str:
    """Derive the segment label from the viewer's reaction profile."""
    watch, follow, engage = signals["watch"], signals["follow"], signals["engagement"]
    if watch >= WATCH_HIGH and follow >= FOLLOW_HIGH:
        return "loyalist"
    if watch >= WATCH_HIGH and engage >= ENGAGE_HIGH:
        return "passionate"
    if watch >= WATCH_HIGH and engage >= ENGAGE_HIGH * 0.6 and signals["comment_share"] >= COMMENT_SHARE:
        return "replier"
    if engage >= ENGAGE_HIGH:
        return "reactor"
    if watch >= WATCH_HIGH:
        return "lurker"
    return "sampler"


def _exposure_by_creator(
    db: Session, viewer_id: int
) -> tuple[dict[int, float], float]:
    runs = db.query(SimulationRun).order_by(SimulationRun.id).all()
    watched = {
        r.run_id: r.watch_probability
        for r in db.query(ViewerReaction).filter(ViewerReaction.viewer_id == viewer_id).all()
    }
    exposure: dict[int, float] = {}
    for run in runs:
        if run.target_type != "episode":
            continue
        episode = db.get(Episode, run.target_id)
        if episode is None:
            continue
        exposure[episode.creator_id] = (
            exposure.get(episode.creator_id, 0.0) + watched.get(run.id, 0.0)
        )
    total = sum(exposure.values())
    return exposure, total


SIGNAL_KEYS = ("watch", "follow", "engagement")
K_CLUSTERS = 3  # small MVP population; deterministic seeding, no randomness


def _seed_indices(points: list[list[float]], k: int) -> list[int]:
    """Most-spread rows: highest, lowest, then farthest-from-chosen (k-medoids-ish)."""
    n = len(points)
    highest = max(range(n), key=lambda i: points[i])
    lowest = min(range(n), key=lambda i: points[i])
    chosen = [highest] if lowest == highest else [highest, lowest]
    while len(chosen) < k:
        remaining = [i for i in range(n) if i not in chosen]
        nxt = max(
            remaining,
            key=lambda i: min(
                sum((a - b) ** 2 for a, b in zip(points[i], points[c])) for c in chosen
            ),
        )
        chosen.append(nxt)
    return chosen


def cluster_viewers(signal_rows: list[dict], k: int = K_CLUSTERS) -> dict:
    """Deterministic k-means over (watch, follow, engagement).

    Seeds are picked as the k most-spread signal rows so the result never
    depends on iteration order or RNG — repeatable runs are required for
    reproducible simulations (guide §9).
    """
    points = [[float(s[key]) for key in SIGNAL_KEYS] for s in signal_rows]
    n = len(points)
    if n == 0:
        return {"k": 0, "assignments": [], "centroids": []}
    k = min(k, n)

    seeds = _seed_indices(points, k)
    centroids = [points[i][:] for i in seeds]
    assignments = [0] * n

    for _ in range(50):
        changed = False
        for i, point in enumerate(points):
            nearest = min(
                range(k),
                key=lambda c: sum((a - b) ** 2 for a, b in zip(point, centroids[c])),
            )
            if nearest != assignments[i]:
                assignments[i] = nearest
                changed = True
        for c in range(k):
            members = [points[i] for i in range(n) if assignments[i] == c]
            if members:
                centroids[c] = [
                    round(sum(m[d] for m in members) / len(members), 4) for d in range(3)
                ]
        if not changed:
            break

    # order clusters by overall engagement so labels are stable across runs
    order = sorted(
        range(k),
        key=lambda c: -sum(centroids[c]),
    )
    rank = {c: rank_index for rank_index, c in enumerate(order)}
    return {
        "k": k,
        "assignments": [rank[a] for a in assignments],
        "centroids": [
            {
                "watch": round(centroids[c][0], 3),
                "follow": round(centroids[c][1], 3),
                "engagement": round(centroids[c][2], 3),
            }
            for c in order
        ],
    }


def _cluster_label(centroid: dict) -> str:
    if centroid["watch"] >= 0.5 and centroid["engagement"] >= 0.22:
        return "deep-fans"
    if centroid["watch"] >= 0.5:
        return "steady-watchers"
    if centroid["engagement"] >= 0.22:
        return "casual-engagers"
    return "skimmers"


def build_segments(db: Session) -> dict:
    viewers = _viewers(db)
    segments: dict[str, list[dict]] = {}
    slugs = {c.id: c.slug for c in db.query(Creator).all()}
    if not slugs:
        slugs = {}

    classified = 0
    for viewer in viewers:
        signals = viewer_signals(db, viewer)
        if signals is None:
            continue
        signals["segment"] = label_segment(signals)
        exposure, total = _exposure_by_creator(db, viewer.id)
        ranked = sorted(exposure.items(), key=lambda kv: -kv[1])
        signals["specialization"] = round(ranked[0][1] / total, 3) if total else 0.0
        signals["top_creator"] = slugs.get(ranked[0][0], f"creator-{ranked[0][0]}") if ranked else None
        segments.setdefault(signals["segment"], []).append(signals)
        classified += 1

    for label in list(segments):
        segments[label].sort(key=lambda s: (-s["watch"], -s["follow"], s["viewer_id"]))

    ordered: dict[str, list[dict]] = {}
    for label in SEGMENT_ORDER:
        if label in segments:
            ordered[label] = segments[label]
    for label, members in segments.items():
        ordered.setdefault(label, members)

    # behavior clusters over the same signals (roadmap 11.3: clusters from
    # simulation behavior, not profile labels)
    signal_rows = [s for group in ordered.values() for s in group]
    clustering = cluster_viewers(signal_rows)
    labels = [_cluster_label(c) for c in clustering["centroids"]]
    for signals, cluster_index in zip(signal_rows, clustering["assignments"]):
        signals["cluster"] = cluster_index
    clusters: dict[str, list[dict]] = {}
    for signals, cluster_index in zip(signal_rows, clustering["assignments"]):
        clusters.setdefault(labels[cluster_index], []).append(signals)

    return {
        "viewer_count": len(viewers),
        "classified": classified,
        "segments": ordered,
        "counts": {label: len(members) for label, members in ordered.items()},
        "clusters": {
            "k": clustering["k"],
            "labels": labels,
            "centroids": clustering["centroids"],
            "members": clusters,
            "counts": {label: len(members) for label, members in clusters.items()},
        },
        "interpretation_allowed": classified >= 2,
    }
