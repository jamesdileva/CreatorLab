"""APScheduler jobs — periodic sweeps (Sprint 8.1; APScheduler for MVP per arch)."""
import logging

logger = logging.getLogger("creatorlab.scheduler")


def collect_due_metrics_job() -> int:
    """Snapshot every published video with a due ladder step.

    Returns the number of snapshots taken. Never raises out of the job:
    individual failures are swallowed by collect_due, and DB errors are
    logged so the scheduler survives.
    """
    from ..core.database import SessionLocal
    from ..services.analytics_service import collect_due

    db = SessionLocal()
    try:
        collected = collect_due(db)
        if collected:
            logger.info("analytics sweep: %d snapshot(s)", len(collected))
        return len(collected)
    except Exception as exc:  # noqa: BLE001 - the sweep must not kill the job
        logger.warning("analytics sweep failed: %s", exc)
        return 0
    finally:
        db.close()


def create_scheduler():
    """15-minute sweep. Started only when settings.enable_scheduler is true."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        collect_due_metrics_job,
        trigger="interval",
        minutes=15,
        id="analytics_sweep",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


_scheduler = None


def start_scheduler() -> bool:
    """Start the background scheduler once. Returns True when running."""
    from ..core.config import settings

    global _scheduler
    if not settings.enable_scheduler:
        return False
    if _scheduler is None:
        _scheduler = create_scheduler()
        _scheduler.start()
    return True
