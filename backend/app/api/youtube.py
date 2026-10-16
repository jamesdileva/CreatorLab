"""YouTube OAuth endpoints (Sprint 7.1) — official API only."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..integrations.youtube.auth import GoogleOAuthClient, OAuthError
from ..models.published_video import PublishedVideo
from ..models.video_metrics import VideoMetrics
from ..models.youtube_account import YouTubeAccount
from ..services import youtube_service
from ..services.analytics_service import AnalyticsError, due_videos, snapshot_video
from ..services.youtube_upload_service import (
    PublishGateError,
    UploadError,
    publish_episode,
    refresh_published_status,
    retry_publish,
    set_video_thumbnail,
    update_video_metadata,
)

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: str
    channel_name: str
    oauth_reference: str
    status: str
    scopes: str
    last_sync: datetime | None
    created_at: datetime


class StatusOut(BaseModel):
    configured: bool


class PublishIn(BaseModel):
    channel_id: str | None = None
    privacy: str = "private"


class VerificationIn(BaseModel):
    status: str
    notes: str = ""


class PublishedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    episode_id: int
    render_id: int
    channel_id: str
    video_id: str
    title: str
    description: str
    privacy_status: str
    status: str
    youtube_status: str
    attempts: int
    total_duration: float
    error: str
    upload_time: datetime


@router.get("/status", response_model=StatusOut)
def youtube_status() -> StatusOut:
    """True when client id/secret are present in .env (never reveals values)."""
    return StatusOut(configured=GoogleOAuthClient().configured)


@router.get("/oauth/start")
def oauth_start() -> dict:
    try:
        url = youtube_service.start_connect()
    except OAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"authorize_url": url}


@router.get("/oauth/callback")
def oauth_callback(
    code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)
):
    from fastapi.responses import RedirectResponse

    if error:
        return RedirectResponse(f"/youtube?error={error}")
    if not code:
        return RedirectResponse("/youtube?error=missing_code")
    try:
        account = youtube_service.handle_callback(code, db=db)
    except OAuthError:
        return RedirectResponse("/youtube?error=oauth_failed")
    return RedirectResponse(f"/youtube?connected={account.channel_id}")


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)) -> list[YouTubeAccount]:
    return db.query(YouTubeAccount).order_by(YouTubeAccount.id).all()


# ---------- Private upload (Sprint 7.2) ----------


@router.post(
    "/episodes/{episode_id}/publish",
    status_code=status.HTTP_201_CREATED,
    response_model=PublishedRead,
)
def publish_episode_video(
    episode_id: int, payload: PublishIn, db: Session = Depends(get_db)
) -> PublishedRead:
    try:
        record = publish_episode(
            db, episode_id, channel_id=payload.channel_id, privacy=payload.privacy
        )
    except PublishGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except UploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return PublishedRead.model_validate(record)


@router.get("/episodes/{episode_id}/videos", response_model=list[PublishedRead])
def episode_videos(episode_id: int, db: Session = Depends(get_db)) -> list:
    return (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id == episode_id)
        .order_by(PublishedVideo.id.desc())
        .all()
    )


@router.post("/videos/{record_id}/status", response_model=PublishedRead)
def refresh_video_status(
    record_id: int, db: Session = Depends(get_db)
) -> PublishedRead:
    try:
        record = refresh_published_status(db, record_id)
    except PublishGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except UploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return PublishedRead.model_validate(record)


@router.post("/videos/{record_id}/retry", response_model=PublishedRead)
def retry_video_upload(record_id: int, db: Session = Depends(get_db)) -> PublishedRead:
    try:
        record = retry_publish(db, record_id)
    except PublishGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except UploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return PublishedRead.model_validate(record)


class MetadataIn(BaseModel):
    title: str | None = None
    description: str | None = None


@router.patch("/videos/{record_id}", response_model=PublishedRead)
def update_video_metadata_endpoint(
    record_id: int, payload: MetadataIn, db: Session = Depends(get_db)
) -> PublishedRead:
    try:
        record = update_video_metadata(
            db, record_id, title=payload.title, description=payload.description
        )
    except PublishGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except UploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return PublishedRead.model_validate(record)


@router.post("/videos/{record_id}/thumbnail", response_model=PublishedRead)
def set_thumbnail(record_id: int, db: Session = Depends(get_db)) -> PublishedRead:
    try:
        record = set_video_thumbnail(db, record_id)
    except PublishGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except UploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return PublishedRead.model_validate(record)


# ---------- Analytics snapshots (Sprint 8.1) ----------


class MetricsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    published_video_id: int
    video_id: str
    captured_at: datetime
    views: int
    likes: int
    comments: int
    subscriber_count: int
    subscribers_gained: int
    estimated_minutes_watched: float | None
    source: str


@router.post(
    "/published/{record_id}/snapshot",
    status_code=status.HTTP_201_CREATED,
    response_model=MetricsRead,
)
def snapshot_record(record_id: int, db: Session = Depends(get_db)) -> MetricsRead:
    try:
        row = snapshot_video(db, record_id)
    except AnalyticsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return MetricsRead.model_validate(row)


@router.get("/published/{record_id}/metrics", response_model=list[MetricsRead])
def published_metrics(record_id: int, db: Session = Depends(get_db)) -> list:
    if db.get(PublishedVideo, record_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="published video not found"
        )
    return (
        db.query(VideoMetrics)
        .filter(VideoMetrics.published_video_id == record_id)
        .order_by(VideoMetrics.id)
        .all()
    )


@router.get("/analytics/due", response_model=list[int])
def analytics_due(db: Session = Depends(get_db)) -> list[int]:
    return due_videos(db)


# ---------- Early performance forecasting (Sprint 15.2) ----------


@router.get("/analytics/forecast")
def analytics_forecast(
    early_views: float | None = None, db: Session = Depends(get_db)
) -> dict:
    from ..services.forecast_service import evaluate_forecast, fit_forecast

    report = evaluate_forecast(db)
    if early_views is not None:
        model, _ = fit_forecast(db)
        report["prediction_for_early_views"] = {
            "early_views": early_views,
            **model.predict(early_views),
        }
    return report


@router.get("/videos", response_model=list[PublishedRead])
def list_published(db: Session = Depends(get_db)) -> list:
    return db.query(PublishedVideo).order_by(PublishedVideo.id.desc()).all()


# ---------- Publication policy + verification (Sprint 7.4) ----------


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_name: str
    status: str
    scopes_requested: str
    notes: str
    updated_at: datetime


@router.get("/publication-policy")
def get_publication_policy(db: Session = Depends(get_db)) -> dict:
    from ..services.publish_policy import policy

    return policy(db)


@router.get("/verification", response_model=AuditRead)
def get_verification(db: Session = Depends(get_db)) -> AuditRead:
    from ..services.publish_policy import get_audit_status

    return AuditRead.model_validate(get_audit_status(db))


@router.patch("/verification", response_model=AuditRead)
def update_verification(
    payload: VerificationIn, db: Session = Depends(get_db)
) -> AuditRead:
    from ..services.publish_policy import record_audit_status

    try:
        return AuditRead.model_validate(
            record_audit_status(db, payload.status, notes=payload.notes)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
