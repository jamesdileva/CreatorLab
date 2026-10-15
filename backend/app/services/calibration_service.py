"""Prediction calibration — absolute view ranges from simulator scores (15.1).

Not good/bad: a predicted performance RANGE for a given simulator score, fit
by least squares over observed (score, real views) pairs, with the range width
driven by residual spread. Guide §15: no interpretation below MIN_SAMPLES.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models.experiment import ContentExperiment

MIN_SAMPLES = 5
RANGE_Z = 1.28  # ≈80% interval for roughly normal residuals


@dataclass
class CalibrationModel:
    slope: float
    intercept: float
    residual_std: float
    samples: int

    @property
    def sufficient(self) -> bool:
        return self.samples >= MIN_SAMPLES

    def predict(self, score: float) -> dict:
        point = self.slope * score + self.intercept
        margin = RANGE_Z * self.residual_std
        return {
            "point": round(max(0.0, point), 1),
            "low": round(max(0.0, point - margin), 1),
            "high": round(max(0.0, point + margin), 1),
        }


@dataclass
class Observation:
    experiment_id: int
    score: float
    views: int


def _observations(db: Session) -> list[Observation]:
    rows: list[Observation] = []
    for experiment in (
        db.query(ContentExperiment)
        .filter(ContentExperiment.simulation_score.isnot(None))
        .order_by(ContentExperiment.id)
        .all()
    ):
        metrics = experiment.real_metrics or {}
        views = metrics.get("views")
        if views is None:
            continue
        rows.append(
            Observation(
                experiment_id=experiment.id,
                score=round(float(experiment.simulation_score), 3),
                views=int(views),
            )
        )
    return rows


def fit_calibration(db: Session) -> tuple[CalibrationModel, list[Observation]]:
    observations = _observations(db)
    n = len(observations)
    if n < 2:
        model = CalibrationModel(slope=0.0, intercept=0.0, residual_std=0.0, samples=n)
        return model, observations

    mean_x = sum(o.score for o in observations) / n
    mean_y = sum(o.views for o in observations) / n
    var_x = sum((o.score - mean_x) ** 2 for o in observations)
    if var_x == 0:
        # every observed score is identical: no signal to fit a slope from
        model = CalibrationModel(slope=0.0, intercept=round(mean_y, 1), residual_std=0.0, samples=n)
        return model, observations

    slope = sum((o.score - mean_x) * (o.views - mean_y) for o in observations) / var_x
    intercept = mean_y - slope * mean_x
    residuals = [o.views - (slope * o.score + intercept) for o in observations]
    residual_std = (sum(r * r for r in residuals) / (n - 1)) ** 0.5
    model = CalibrationModel(
        slope=round(slope, 3),
        intercept=round(intercept, 1),
        residual_std=round(residual_std, 1),
        samples=n,
    )
    return model, observations


def evaluate_calibration(db: Session) -> dict:
    model, observations = fit_calibration(db)
    rows = []
    covered = 0
    abs_errors: list[float] = []
    pct_errors: list[float] = []
    for obs in observations:
        prediction = model.predict(obs.score)
        inside = prediction["low"] <= obs.views <= prediction["high"]
        covered += 1 if inside else 0
        abs_errors.append(abs(prediction["point"] - obs.views))
        if obs.views:
            pct_errors.append(abs(prediction["point"] - obs.views) / obs.views)
        rows.append(
            {
                "experiment_id": obs.experiment_id,
                "simulator_score": obs.score,
                "observed_views": obs.views,
                "predicted": prediction,
                "within_range": inside,
            }
        )
    n = len(observations)
    aggregates: dict = (
        {
            "coverage": round(covered / n, 3),
            "mae": round(sum(abs_errors) / n, 1),
            "mape": round(sum(pct_errors) / len(pct_errors), 3)
            if pct_errors
            else None,
            "verdict": (
                "absolute prediction looks usable"
                if covered / n >= 0.7
                else "ranges unreliable — keep relative ranking"
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
            "slope": model.slope,
            "intercept": model.intercept,
            "residual_std": model.residual_std,
            "form": "views ≈ slope * simulator_score + intercept",
        },
        **aggregates,
        "predictions": rows,
    }
