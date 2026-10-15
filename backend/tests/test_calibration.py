"""Sprint 15.1 — calibration: absolute view ranges from simulator scores."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.experiment import ContentExperiment
from app.services.calibration_service import (
    MIN_SAMPLES,
    CalibrationModel,
    evaluate_calibration,
    fit_calibration,
)

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


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


def _experiment(score, views):
    db = TestingSession()
    exp = ContentExperiment(
        creator_id=1,
        episode_id=1,
        simulation_score=score,
        real_metrics={"views": views},
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    db.close()
    return exp.id


def test_fit_recovers_linear_relationship(client):
    # views = 1000 * score + 200, exactly
    for score in (0.4, 0.5, 0.6, 0.7, 0.8):
        _experiment(score, 1000 * score + 200)

    db = TestingSession()
    model, observations = fit_calibration(db)
    db.close()
    assert model.slope == pytest.approx(1000, rel=1e-3)
    assert model.intercept == pytest.approx(200, rel=1e-3)
    assert model.residual_std == 0.0
    assert len(observations) == 5
    assert model.sufficient is True


def test_prediction_ranges_widen_with_residuals():
    tight = CalibrationModel(slope=1000, intercept=0, residual_std=10, samples=5)
    loose = CalibrationModel(slope=1000, intercept=0, residual_std=500, samples=5)
    assert tight.predict(0.5)["high"] - tight.predict(0.5)["low"] < (
        loose.predict(0.5)["high"] - loose.predict(0.5)["low"]
    )
    assert tight.predict(0.5)["point"] == 500.0


def test_prediction_never_negative():
    model = CalibrationModel(slope=-100, intercept=10, residual_std=50, samples=5)
    predicted = model.predict(0.9)
    assert predicted["low"] >= 0.0
    assert predicted["point"] >= 0.0


def test_evaluation_reports_coverage(client):
    # perfectly linear data: every observed value sits inside its range
    for score in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        _experiment(score, 1000 * score + 200)
    report = evaluate_calibration(_db())
    assert report["samples"] == 6
    assert report["interpretation_allowed"] is True
    assert report["coverage"] == 1.0
    assert report["mae"] == 0.0
    assert "usable" in report["verdict"]
    assert len(report["predictions"]) == 6


def _db():
    return TestingSession()


def test_insufficient_data_is_gated(client):
    _experiment(0.5, 700)
    report = evaluate_calibration(_db())
    assert report["samples"] == 1
    assert report["interpretation_allowed"] is False
    assert report["coverage"] is None
    assert report["mae"] is None
    assert report["verdict"].startswith("insufficient data")


def test_endpoint(client):
    for score in (0.4, 0.5, 0.6, 0.7, 0.8):
        _experiment(score, 800 * score + 300)
    res = client.get("/api/experiments/calibration")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["samples"] == 5
    assert body["min_samples"] == MIN_SAMPLES
    assert body["model"]["form"].startswith("views")
    first = body["predictions"][0]
    assert {"experiment_id", "simulator_score", "observed_views",
            "predicted", "within_range"} <= set(first)


def test_identical_scores_have_no_slope_signal(client):
    for _ in range(5):
        _experiment(0.6, 900)
    db = TestingSession()
    model, _ = fit_calibration(db)
    db.close()
    assert model.slope == 0.0
    assert model.intercept == pytest.approx(900, rel=1e-3)
