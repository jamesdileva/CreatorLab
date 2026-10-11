"""YouTube OAuth endpoints (Sprint 7.1) — official API only."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..integrations.youtube.auth import GoogleOAuthClient, OAuthError
from ..models.youtube_account import YouTubeAccount
from ..services import youtube_service

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
