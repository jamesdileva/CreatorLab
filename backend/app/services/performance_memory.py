"""Performance memory distillation (roadmap Sprint 10.1, guide §16, arch §13).

Derives evidence-backed lessons from a creator's real performance history
(real views per episode, simulated scores where present) and stores them as
structured memories so later generations can reference actual results:

- topic buckets ("tractor" episodes average 1.6x the channel mean) and
- structure buckets (multi-scene vs short episodes) become AUDIENCE_DISCOVERY;
- strong buckets additionally yield a hedged CONTENT_LESSON with an action.

Guide §16 rule: lessons carry Observation + Confidence + Sample + Action and
never become absolute rules — content strings say so explicitly.
Re-distillation refreshes: prior auto-distilled ("PERF:") rows are replaced.
"""
import re

from sqlalchemy.orm import Session

from ..models.creator_memory import CreatorMemory, MemoryType
from ..models.episode import Episode
from ..models.published_video import PublishedVideo
from ..models.scene import Scene
from ..models.video_metrics import VideoMetrics
from ..models.simulation import ViewerReaction
from .review_service import latest_simulation_for
from .simulation_service import aggregate_reactions

MIN_EPISODES = 3  # need several published episodes before distilling
MIN_BUCKET = 2  # a bucket needs at least this many episodes to claim
STRONG_LIFT = 1.25  # bucket avg >= 1.25x overall mean → strong
WEAK_LIFT = 0.75  # bucket avg <= 0.75x overall mean → weak

PREFIX = "PERF:"


def _topic_tag(premise: str | None) -> str:
    for word in re.findall(r"[A-Za-z][A-Za-z'-]+", premise or ""):
        if len(word) > 5:
            return word.lower()
    return "unknown"


def _structure_tag(n_scenes: int) -> str:
    if n_scenes <= 2:
        return "short"
    if n_scenes <= 4:
        return "standard"
    return "long"


def _confidence_label(n: int) -> tuple[str, float]:
    if n >= 5:
        return "High", 0.8
    if n >= 3:
        return "Medium", 0.65
    return "Low", 0.5


def _importance(lift: float) -> float:
    return round(min(0.5 + abs(lift - 1.0) * 0.5, 0.9), 3)


def episode_performance(db: Session, creator_id: int) -> list[dict]:
    """One row per episode with real metrics (+ sim score where present)."""
    rows: list[dict] = []
    episodes = (
        db.query(Episode)
        .filter(Episode.creator_id == creator_id)
        .order_by(Episode.id)
        .all()
    )
    for episode in episodes:
        videos = (
            db.query(PublishedVideo)
            .filter(PublishedVideo.episode_id == episode.id)
            .all()
        )
        best_views: int | None = None
        for video in videos:
            snap = (
                db.query(VideoMetrics)
                .filter(VideoMetrics.published_video_id == video.id)
                .order_by(VideoMetrics.id.desc())
                .first()
            )
            if snap is not None and (best_views is None or snap.views > best_views):
                best_views = snap.views
        if best_views is None:
            continue  # no reality yet — nothing to learn from
        sim_watch: float | None = None
        run = latest_simulation_for(db, episode.id)
        if run is not None:
            reactions = (
                db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
            )
            if reactions:
                sim_watch = aggregate_reactions(reactions)["means"]["watch_probability"]
        n_scenes = (
            db.query(Scene).filter(Scene.episode_id == episode.id).count()
        )
        rows.append(
            {
                "episode_id": episode.id,
                "title": episode.title,
                "topic": _topic_tag(episode.premise),
                "structure": _structure_tag(n_scenes),
                "views": best_views,
                "sim_watch": sim_watch,
            }
        )
    return rows


def summarize_performance(db: Session, creator_id: int) -> dict:
    """Read-only performance summary: overall mean + topic/structure buckets."""
    from ..models.creator import Creator

    if db.get(Creator, creator_id) is None:
        raise ValueError("creator not found")
    rows = episode_performance(db, creator_id)
    n = len(rows)
    overall = round(sum(r["views"] for r in rows) / n, 1) if n else 0.0

    def buckets(key: str) -> dict:
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row[key], []).append(row)
        out = {}
        for tag, members in sorted(grouped.items()):
            avg = sum(m["views"] for m in members) / len(members)
            lift = (avg / overall) if overall else 1.0
            if len(members) >= MIN_BUCKET:
                verdict = "strong" if lift >= STRONG_LIFT else ("weak" if lift <= WEAK_LIFT else "neutral")
            else:
                verdict = "thin"
            out[tag] = {
                "episodes": len(members),
                "avg_views": round(avg, 1),
                "lift_vs_mean": round(lift, 3),
                "verdict": verdict,
            }
        return out

    sim_covered = sum(1 for r in rows if r["sim_watch"] is not None)
    return {
        "creator_id": creator_id,
        "episodes_with_metrics": n,
        "overall_avg_views": overall,
        "sim_coverage": sim_covered,
        "episodes": rows,
        "topics": buckets("topic"),
        "structures": buckets("structure"),
    }


def distill_performance_memories(
    db: Session, creator_id: int, min_episodes: int = MIN_EPISODES
) -> list[CreatorMemory]:
    """Distill a creator's performance history into structured memories."""
    from ..models.creator import Creator

    creator = db.get(Creator, creator_id)
    if creator is None:
        raise ValueError("creator not found")
    summary = summarize_performance(db, creator_id)
    n = summary["episodes_with_metrics"]
    if n < min_episodes:
        raise ValueError(
            f"need at least {min_episodes} episodes with real metrics, found {n}"
        )

    # Refresh: drop prior auto-distilled rows so re-distills don't duplicate.
    db.query(CreatorMemory).filter(
        CreatorMemory.creator_id == creator_id,
        CreatorMemory.content.startswith(PREFIX),
    ).delete(synchronize_session=False)

    created: list[CreatorMemory] = []

    def add(memory_type: MemoryType, content: str, importance: float, confidence: float) -> None:
        memory = CreatorMemory(
            creator_id=creator_id,
            type=memory_type,
            content=content,
            importance=importance,
            confidence=confidence,
        )
        db.add(memory)
        created.append(memory)

    overall = summary["overall_avg_views"]
    best = max(summary["episodes"], key=lambda r: r["views"])
    label, conf = _confidence_label(n)
    add(
        MemoryType.AUDIENCE_DISCOVERY,
        f"{PREFIX} Observation: {n} published episodes average {overall} views; "
        f"best is '{best['title']}' ({best['views']} views, topic '{best['topic']}'). "
        f"| Confidence: {label} | Sample: {n} episodes "
        f"| Action: keep publishing to extend the sample; not a rule, re-check after more episodes.",
        importance=0.6,
        confidence=conf,
    )

    for kind, memory_label in (("topics", "topic"), ("structures", "structure")):
        for tag, bucket in summary[kind].items():
            if bucket["verdict"] not in ("strong", "weak"):
                continue
            blabel, bconf = _confidence_label(bucket["episodes"])
            direction = "outperforms" if bucket["verdict"] == "strong" else "underperforms"
            add(
                MemoryType.AUDIENCE_DISCOVERY,
                f"{PREFIX} Observation: {memory_label} '{tag}' {direction} "
                f"({bucket['avg_views']} vs {overall} mean, lift {bucket['lift_vs_mean']}). "
                f"| Confidence: {blabel} | Sample: {bucket['episodes']} episodes "
                f"| Action: none yet — evidence only, not a rule.",
                importance=_importance(bucket["lift_vs_mean"]),
                confidence=bconf,
            )
            if bucket["verdict"] == "strong":
                verb = "develop more" if kind == "topics" else "prefer"
                add(
                    MemoryType.CONTENT_LESSON,
                    f"{PREFIX} Observation: {memory_label} '{tag}' performs strongly "
                    f"(lift {bucket['lift_vs_mean']} over {bucket['episodes']} episodes). "
                    f"| Confidence: {blabel} | Sample: {bucket['episodes']} episodes "
                    f"| Action: {verb} '{tag}' candidates, but keep testing alternatives.",
                    importance=_importance(bucket["lift_vs_mean"]),
                    confidence=bconf,
                )

    db.commit()
    for memory in created:
        db.refresh(memory)
    return created
