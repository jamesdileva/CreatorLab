"""Experiment binding — one record for the whole lifecycle (Sprint 8.2).

simulation + episode + render + YouTube video + analytics in a single row,
plus the immutable markdown notebook record (guide §21).
"""
from pathlib import Path

from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.episode import Episode
from ..models.experiment import ContentExperiment
from ..models.published_video import PublishedVideo
from ..models.render import Render
from ..models.series import Series
from ..models.simulation import SimulationRun, ViewerReaction
from ..models.video_metrics import VideoMetrics
from .review_service import latest_render_for, latest_simulation_for
from .simulation_service import aggregate_reactions

EXPERIMENTS_DIR = Path("docs/experiments")


def _latest_series_scores(db: Session, series_id: int) -> list[tuple[int, float]]:
    """(episode_id, latest watch mean) for every episode with a sim run."""
    scores: list[tuple[int, float]] = []
    for episode in (
        db.query(Episode).filter(Episode.series_id == series_id).order_by(Episode.id).all()
    ):
        run = latest_simulation_for(db, episode.id)
        if run is None:
            continue
        reactions = (
            db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
        )
        if not reactions:
            continue
        scores.append((episode.id, aggregate_reactions(reactions)["means"]["watch_probability"]))
    scores.sort(key=lambda t: (-t[1], t[0]))
    return scores


def _latest_published(db: Session, episode_id: int) -> PublishedVideo | None:
    return (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id == episode_id)
        .order_by(PublishedVideo.id.desc())
        .first()
    )


def _latest_metrics(db: Session, published_id: int | None) -> list[VideoMetrics]:
    if published_id is None:
        return []
    return (
        db.query(VideoMetrics)
        .filter(VideoMetrics.published_video_id == published_id)
        .order_by(VideoMetrics.id)
        .all()
    )


def bind_experiment(
    db: Session,
    episode_id: int,
    hypothesis: str = "",
    variant: str = "",
) -> ContentExperiment:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("episode not found")

    run = latest_simulation_for(db, episode.id)
    score = None
    if run is not None:
        reactions = (
            db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
        )
        if reactions:
            score = aggregate_reactions(reactions)["means"]["watch_probability"]

    rank = None
    ordered = _latest_series_scores(db, episode.series_id)
    for position, (eid, _) in enumerate(ordered, start=1):
        if eid == episode.id:
            rank = position

    published = _latest_published(db, episode.id)
    metrics = _latest_metrics(db, published.id if published else None)
    if metrics:
        latest = metrics[-1]
        real_metrics = {
            "views": latest.views,
            "likes": latest.likes,
            "comments": latest.comments,
            "subscriber_count": latest.subscriber_count,
            "captured_at": latest.captured_at.isoformat(),
            "snapshot_count": len(metrics),
        }
    else:
        real_metrics = None

    experiment = ContentExperiment(
        creator_id=episode.creator_id,
        episode_id=episode.id,
        hypothesis=hypothesis.strip(),
        variant=variant.strip(),
        simulation_run_id=run.id if run else None,
        simulation_score=score,
        simulation_rank=rank,
        published_video_id=published.id if published else None,
        real_metrics=real_metrics,
        reality_gap=None,  # Sprint 9.1
        conclusions="",
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    write_notebook_record(db, experiment)
    return experiment


def write_notebook_record(db: Session, experiment: ContentExperiment) -> Path:
    """Immutable markdown record (guide §21) — regenerated deterministically."""
    episode = db.get(Episode, experiment.episode_id)
    creator = db.get(Creator, experiment.creator_id) if episode else None
    run = (
        db.get(SimulationRun, experiment.simulation_run_id)
        if experiment.simulation_run_id
        else None
    )
    published = (
        db.get(PublishedVideo, experiment.published_video_id)
        if experiment.published_video_id
        else None
    )
    render = None
    if published is not None:
        from ..models.render import Render

        render = db.get(Render, published.render_id)

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPERIMENTS_DIR / f"EXPERIMENT-{experiment.id:04d}.md"
    lines = [
        f"# EXPERIMENT-{experiment.id:04d}",
        "",
        f"Created: {experiment.created_at.isoformat()}",
        "",
        f"Creator: {creator.name if creator else experiment.creator_id}",
        f"Episode: {(episode.title if episode else experiment.episode_id)}",
        "",
        f"Hypothesis: {experiment.hypothesis or '(none recorded)'}",
        f"Variant: {experiment.variant or '(none)'}",
        "",
        "## Simulation",
        f"Run: {run.id if run else '(none)'}",
        f"Score (watch mean): {experiment.simulation_score if experiment.simulation_score is not None else '(none)'}",
        f"Rank in series: {experiment.simulation_rank if experiment.simulation_rank is not None else '(none)'}",
        f"Model: {run.model if run else '(none)'} / {run.prompt_version if run else ''} "
        f"audience {run.audience_version if run else ''}".rstrip(),
        "",
        "## Publication",
        (
            f"Render: {render.id if render else '(none)'} / "
            f"{render.status if render else ''}".rstrip(" /")
        ),
        (
            f"Video: {(published.video_id if published else '(none)')} "
            f"({published.status if published else ''}, "
            f"{published.privacy_status if published else ''})".rstrip()
        ),
        "",
        "## Reality",
        f"Metrics: {experiment.real_metrics if experiment.real_metrics else '(none yet)'}",
        f"Reality gap: {experiment.reality_gap if experiment.reality_gap else '(Sprint 9.1)'}",
        "",
        "## Conclusions",
        experiment.conclusions or "(pending)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def refresh_experiment(db: Session, experiment: ContentExperiment) -> ContentExperiment:
    """Re-bind video/metrics/run links (called on creation and refresh)."""
    updated = bind_experiment_links(db, experiment)
    write_notebook_record(db, updated)
    return updated


def bind_experiment_links(db: Session, experiment: ContentExperiment) -> ContentExperiment:
    """Recompute links without creating a new experiment row."""
    run = latest_simulation_for(db, experiment.episode_id)
    if run is not None:
        experiment.simulation_run_id = run.id
        reactions = (
            db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
        )
        if reactions:
            experiment.simulation_score = aggregate_reactions(reactions)["means"][
                "watch_probability"
            ]
    episode = db.get(Episode, experiment.episode_id)
    if episode is not None:
        for position, (eid, _) in enumerate(
            _latest_series_scores(db, episode.series_id), start=1
        ):
            if eid == episode.id:
                experiment.simulation_rank = position
    published = _latest_published(db, experiment.episode_id)
    experiment.published_video_id = published.id if published else None
    metrics = _latest_metrics(db, published.id if published else None)
    if metrics:
        latest = metrics[-1]
        experiment.real_metrics = {
            "views": latest.views,
            "likes": latest.likes,
            "comments": latest.comments,
            "subscriber_count": latest.subscriber_count,
            "captured_at": latest.captured_at.isoformat(),
            "snapshot_count": len(metrics),
        }
    else:
        experiment.real_metrics = None
    db.commit()
    db.refresh(experiment)
    return experiment


def full_lifecycle(db: Session, experiment: ContentExperiment) -> dict:
    """One payload for the complete lifecycle (roadmap verification)."""
    episode = db.get(Episode, experiment.episode_id)
    creator = db.get(Creator, experiment.creator_id) if episode else None
    series = db.get(Series, episode.series_id) if episode else None
    run = (
        db.get(SimulationRun, experiment.simulation_run_id)
        if experiment.simulation_run_id
        else None
    )
    published = (
        db.get(PublishedVideo, experiment.published_video_id)
        if experiment.published_video_id
        else None
    )
    metrics = _latest_metrics(db, published.id if published else None)
    render = latest_render_for(db, episode.id) if episode else None

    simulation = None
    if run is not None:
        reactions = (
            db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
        )
        simulation = {
            "run_id": run.id,
            "model": run.model,
            "prompt_version": run.prompt_version,
            "audience_version": run.audience_version,
            "aggregate": aggregate_reactions(reactions) if reactions else None,
        }
    return {
        "experiment": {
            "id": experiment.id,
            "hypothesis": experiment.hypothesis,
            "variant": experiment.variant,
            "simulation_score": experiment.simulation_score,
            "simulation_rank": experiment.simulation_rank,
            "reality_gap": experiment.reality_gap,
            "conclusions": experiment.conclusions,
            "created_at": experiment.created_at.isoformat(),
        },
        "creator": {"id": creator.id, "name": creator.name} if creator else None,
        "series": {"id": series.id, "name": series.name} if series else None,
        "episode": {
            "id": episode.id,
            "title": episode.title,
            "episode_number": episode.episode_number,
            "status": episode.status.value,
        }
        if episode
        else None,
        "simulation": simulation,
        "render": {
            "id": render.id,
            "status": render.status,
            "total_duration": render.total_duration,
        }
        if render
        else None,
        "published_video": {
            "id": published.id,
            "video_id": published.video_id,
            "status": published.status,
            "privacy_status": published.privacy_status,
            "upload_time": published.upload_time.isoformat(),
        }
        if published
        else None,
        "metrics": [
            {
                "id": m.id,
                "captured_at": m.captured_at.isoformat(),
                "views": m.views,
                "likes": m.likes,
                "comments": m.comments,
                "subscriber_count": m.subscriber_count,
            }
            for m in metrics
        ],
    }
