"""Sprint 7.4 — publication policy: public uploads blocked until audit approval."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.audit_status import AuditStatus
from app.models.youtube_account import YouTubeAccount
from app.services import publish_policy
from app.services.youtube_upload_service import PublishGateError, UploadError

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


def test_public_upload_blocked_without_approval():
    from pathlib import Path

    from app.services.youtube_upload_service import upload_private_video

    with pytest.raises(PublishGateError, match="audit approval"):
        upload_private_video(Path("x.mp4"), "t", channel_id="UC", privacy="public")


def test_verification_record_lifecycle(client):
    first = client.get("/api/youtube/verification").json()
    assert first["status"] == "not_submitted"

    for label in ("in_review", "approved"):
        res = client.patch(
            "/api/youtube/verification", json={"status": label, "notes": f"moved to {label}"}
        )
        assert res.status_code == 200
        assert res.json()["status"] == label

    assert client.patch(
        "/api/youtube/verification", json={"status": "bogus"}
    ).status_code == 400


def test_policy_reports_blockers_until_approved(client):
    db = TestingSession()
    policy = publish_policy.policy(db)
    db.close()
    assert policy["public_automated_uploads_allowed"] is False
    assert any("publishing_mode" in b for b in policy["blockers"])
    assert any("audit" in b.lower() for b in policy["blockers"])
    assert "manual" in policy["fallback"]


def test_policy_endpoint_allows_public_when_verified(client, monkeypatch):
    db = TestingSession()
    db.add(
        YouTubeAccount(
            channel_id="UC_MOCK",
            channel_name="Mock",
            oauth_reference="secrets/youtube_tokens.json",
            status="active",
            scopes="https://www.googleapis.com/auth/youtube.readonly "
            "https://www.googleapis.com/auth/youtube.upload",
        )
    )
    record = publish_policy.record_audit_status(db, "approved", notes="audit passed")
    assert record.status == "approved"
    db.close()

    monkeypatch.setattr("app.core.config.settings.publishing_mode", "public_api")

    body = client.get("/api/youtube/publication-policy").json()
    assert body["public_automated_uploads_allowed"] is True
    assert body["blockers"] == []
    assert body["audit"]["status"] == "approved"