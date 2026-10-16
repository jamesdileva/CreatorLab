"""Sprint 15.2 — early performance forecasting (1h → 24h)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.published_video import PublishedVideo
from app.models.video_metrics import VideoMetrics
from app.services.forecast_service import (
    MIN_SAMPLES,
    ForecastModel,
    evaluate_forecast,
    fit_forecast,
)

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

UPLOAD = datetime(2026, 1, 1, 12, 0, 0)


def _override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _db():
    return TestingSession()


def _video(early_views, mature_views=None, early_hours=1.0, mature_hours=24.0,
           extra_early_hours=None):
    db = _db()
    record = PublishedVideo(
        episode_id=1,
        render_id=1,
        channel_id="UC_MOCK",
        video_id=f"vid-{early_views}-{mature_views}",
        upload_time=UPLOAD,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    readings = [(early_hours, early_views)]
    if extra_early_hours is not None:
        readings.append((extra_early_hours, early_views))
    if mature_views is not None:
        readings.append((mature_hours, mature_views))
    for hours, views in readings:
        db.add(
            VideoMetrics(
                published_video_id=record.id,
                video_id=record.video_id,
                captured_at=UPLOAD + timedelta(hours=hours),
                views=views,
            )
        )
    db.commit()
    record_id = record.id
    db.close()
    return record_id


# ---------- fitting ----------


def test_factor_recovered_from_consistent_growth(client):
    for early in (50, 100, 150, 200, 250):
        _video(early, early * 4)
    db = _db()
    model, observations = fit_forecast(db)
    db.close()
    assert model.factor == pytest.approx(4.0, rel=1e-3)
    assert model.factor_std == 0.0
    assert len(observations) == 5
    assert model.sufficient is True


def test_prediction_scales_with_early_views():
    model = ForecastModel(factor=4.0, factor_std=0.0, samples=5)
    assert model.predict(100)["point"] == 400.0
    assert model.predict(100)["low"] == model.predict(100)["high"] == 400.0
    assert model.predict(0)["point"] == 0.0


def test_prediction_range_widens_with_factor_spread():
    tight = ForecastModel(factor=4.0, factor_std=0.1, samples=5)
    loose = ForecastModel(factor=4.0, factor_std=1.5, samples=5)
    assert tight.predict(100)["high"] - tight.predict(100)["low"] < (
        loose.predict(100)["high"] - loose.predict(100)["low"]
    )


def test_zero_early_views_is_skipped(client):
    _video(0, 0)
    db = _db()
    model, observations = fit_forecast(db)
    db.close()
    assert observations == []
    assert model.samples == 0


def test_video_without_mature_reading_is_skipped(client):
    only = _video(120, None)  # 1h snapshot only
    assert only
    db = _db()
    _, observations = fit_forecast(db)
    db.close()
    assert observations == []


def test_early_reading_closest_to_one_hour_is_used(client):
    # snapshots at 15m, 1h and 24h → early should be the 1h one
    _video(100, 500, early_hours=1.0, extra_early_hours=0.25)
    db = _db()
    _, observations = fit_forecast(db)
    db.close()
    assert len(observations) == 1
    assert observations[0].early_hours == pytest.approx(1.0)
    assert observations[0].growth == pytest.approx(5.0)


# ---------- evaluation ----------


def test_evaluation_reports_coverage(client):
    for early in (50, 100, 150, 200, 250, 300):
        _video(early, early * 3)
    report = evaluate_forecast(_db())
    assert report["samples"] == 6
    assert report["interpretation_allowed"] is True
    assert report["coverage"] == 1.0
    assert report["mae"] == 0.0
    assert "usable" in report["verdict"]
    assert len(report["forecasts"]) == 6


def test_insufficient_data_is_gated(client):
    _video(100, 400)
    report = evaluate_forecast(_db())
    assert report["samples"] == 1
    assert report["interpretation_allowed"] is False
    assert report["coverage"] is None
    assert report["mae"] is None
    assert report["verdict"].startswith("insufficient data")


# ---------- endpoint ----------


def test_endpoint(client):
    for early in (50, 100, 150, 200, 250):
        _video(early, early * 4)
    res = client.get("/api/youtube/analytics/forecast")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["samples"] == 5
    assert body["min_samples"] == MIN_SAMPLES
    assert body["model"]["form"] == "views_24h ≈ factor * views_1h"
    first = body["forecasts"][0]
    assert {"published_video_id", "early_views", "actual_24h_views",
            "predicted", "within_range"} <= set(first)

    with_prediction = client.get(
        "/api/youtube/analytics/forecast", params={"early_views": 100}
    ).json()
    assert with_prediction["prediction_for_early_views"]["point"] == pytest.approx(
        400.0, rel=1e-2
    )
