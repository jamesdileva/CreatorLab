"""Early performance forecasting — estimate 24h views from the first hour (15.2).

The metrics ladder (analytics_service.METRICS_LADDER) gives append-only
snapshots. For every video that has both a ~1h reading and a ≥24h reading we
pair them, learn the growth factor (24h views ≈ factor · 1h views), and expose
a predicted RANGE from the spread of observed factors. Guide §15: no
interpretation below MIN_SAMPLES.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.published_video import PublishedVideo
from ..models.video_metrics import VideoMetrics

EARLY_TARGET_HOURS = 1.0
MATURE_TARGET_HOURS = 24.0
MIN_SAMPLES = 5
RANGE_Z = 1.28  # ≈80% interval


@dataclass
class ForecastObservation:
    published_video_id: int
    early_hours: float
    mature_hours: float
    early_views: int
    mature_views: int

    @property
    def growth(self) -> float:
        return self.mature_views / self.early_views


@dataclass
class ForecastModel:
    factor: float
    factor_std: float
    samples: int

    @property
    def sufficient(self) -> bool:
        return self.samples >= MIN_SAMPLES

    def predict(self, early_views: float) -> dict:
        point = self.factor * early_views
        margin = RANGE_Z * self.factor_std * early_views
        return {
            "point": round(max(0.0, point), 1),
            "low": round(max(0.0, point - margin), 1),
            "high": round(max(0.0, point + margin), 1),
        }


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _pick_pair(record: PublishedVideo, snapshots: list[VideoMetrics]) -> tuple[float, int, float, int] | None:
    """(early_hours, early_views, mature_hours, mature_views) or None.

    Mature = first snapshot at/after 24h. Early = the earlier distinct snapshot
    whose elapsed time is closest to 1h.
    """
    upload = _as_aware(record.upload_time)
    timed = [
        ((_as_aware(s.captured_at) - upload).total_seconds() / 3600.0, s.views)
        for s in snapshots
    ]
    timed.sort(key=lambda pair: pair[0])
    mature_idx = next(
        (i for i, (hours, _) in enumerate(timed) if hours >= MATURE_TARGET_HOURS),
        None,
    )
    if mature_idx is None or mature_idx == 0:
        return None
    earlier = timed[:mature_idx]
    early_hours, early_views = min(
        earlier, key=lambda pair: abs(pair[0] - EARLY_TARGET_HOURS)
    )
    mature_hours, mature_views = timed[mature_idx]
    return early_hours, early_views, mature_hours, mature_views


def _observations(db: Session) -> list[ForecastObservation]:
    rows: list[ForecastObservation] = []
    for record in db.query(PublishedVideo).order_by(PublishedVideo.id).all():
        if record.upload_time is None:
            continue
        snapshots = (
            db.query(VideoMetrics)
            .filter(VideoMetrics.published_video_id == record.id)
            .all()
        )
        pair = _pick_pair(record, snapshots)
        if pair is None:
            continue
        early_hours, early_views, mature_hours, mature_views = pair
        if early_views <= 0:
            continue
        rows.append(
            ForecastObservation(
                published_video_id=record.id,
                early_hours=round(early_hours, 2),
                mature_hours=round(mature_hours, 2),
                early_views=early_views,
                mature_views=mature_views,
            )
        )
    return rows


def fit_forecast(db: Session) -> tuple[ForecastModel, list[ForecastObservation]]:
    observations = _observations(db)
    n = len(observations)
    if n == 0:
        return ForecastModel(factor=0.0, factor_std=0.0, samples=0), observations
    ratios = [o.growth for o in observations]
    mean = sum(ratios) / n
    if n == 1:
        return ForecastModel(factor=round(mean, 3), factor_std=0.0, samples=n), observations
    variance = sum((r - mean) ** 2 for r in ratios) / (n - 1)
    return (
        ForecastModel(
            factor=round(mean, 3),
            factor_std=round(variance ** 0.5, 3),
            samples=n,
        ),
        observations,
    )


def evaluate_forecast(db: Session) -> dict:
    model, observations = fit_forecast(db)
    rows = []
    covered = 0
    abs_errors: list[float] = []
    pct_errors: list[float] = []
    for obs in observations:
        prediction = model.predict(obs.early_views)
        inside = prediction["low"] <= obs.mature_views <= prediction["high"]
        covered += 1 if inside else 0
        abs_errors.append(abs(prediction["point"] - obs.mature_views))
        if obs.mature_views:
            pct_errors.append(abs(prediction["point"] - obs.mature_views) / obs.mature_views)
        rows.append(
            {
                "published_video_id": obs.published_video_id,
                "early_hours": obs.early_hours,
                "early_views": obs.early_views,
                "actual_24h_views": obs.mature_views,
                "predicted": prediction,
                "within_range": inside,
            }
        )
    n = len(observations)
    aggregates = (
        {
            "coverage": round(covered / n, 3),
            "mae": round(sum(abs_errors) / n, 1),
            "mape": round(sum(pct_errors) / len(pct_errors), 3) if pct_errors else None,
            "verdict": (
                "1h→24h forecast looks usable"
                if covered / n >= 0.7
                else "forecasts unreliable — widen ranges or gather more videos"
            ),
        }
        if model.sufficient
        else {
            "coverage": None,
            "mae": None,
            "mape": None,
            "verdict": "insufficient data — no interpretation (guide §15)",
        }
    )
    return {
        "min_samples": MIN_SAMPLES,
        "samples": n,
        "interpretation_allowed": model.sufficient,
        "model": {
            "factor": model.factor,
            "factor_std": model.factor_std,
            "form": "views_24h ≈ factor * views_1h",
        },
        **aggregates,
        "forecasts": rows,
    }
