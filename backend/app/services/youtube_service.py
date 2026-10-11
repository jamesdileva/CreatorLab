"""YouTube connection service — OAuth flow + token storage (Sprint 7.1).

Refresh tokens are written to a secrets/ directory that is never committed
(guide §12: "never commit credentials"); the database stores only a reference.
"""
import json
import secrets as _pysecrets
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..integrations.youtube.auth import (
    GoogleOAuthClient,
    OAuthError,
    TokenBundle,
)
from ..models.youtube_account import YouTubeAccount

SECRETS_DIR = Path("secrets")
TOKEN_FILE = "youtube_tokens.json"


class NotConfiguredError(OAuthError):
    pass


class StateError(OAuthError):
    pass


def _oauth() -> GoogleOAuthClient:
    client = GoogleOAuthClient()
    if not client.configured:
        raise NotConfiguredError(
            "set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env to connect"
        )
    return client


def start_connect() -> str:
    """Return the Google consent URL (frontend redirects the user there)."""
    state = _pysecrets.token_urlsafe(24)
    return _oauth().authorize_url(state)


def _token_path() -> Path:
    SECRETS_DIR.mkdir(exist_ok=True)
    return SECRETS_DIR / TOKEN_FILE


def _load_tokens() -> dict:
    path = _token_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_token(channel_id: str, bundle: TokenBundle) -> str:
    tokens = _load_tokens()
    tokens[channel_id] = bundle.to_json()
    path = _token_path()
    path.write_text(json.dumps(tokens, indent=2))
    return path.as_posix()


def complete_connect(
    code: str, db: Session | None = None, oauth: GoogleOAuthClient | None = None
) -> YouTubeAccount:
    """Exchange the code, fetch the channel, persist account + refresh token.

    Returns the tracked account. Errors propagate as OAuthError subclasses.
    """
    client = oauth or _oauth()
    bundle = client.exchange_code(code)  # raises on failure
    channel = client.fetch_channel(bundle.access_token)
    return _persist(db, channel, bundle, scopes=" ".join(client.scopes))


def _persist(
    db: Session | None, channel: dict, bundle: TokenBundle, scopes: str = ""
) -> YouTubeAccount:
    """DB write kept separate so the service is testable without a live DB."""
    from ..core.database import SessionLocal

    own_session = db is None
    session = db or SessionLocal()
    try:
        account = (
            session.query(YouTubeAccount)
            .filter_by(channel_id=channel["channel_id"])
            .one_or_none()
        )
        if account is None:
            account = YouTubeAccount(
                channel_id=channel["channel_id"],
                channel_name=channel["title"],
                scopes=scopes,
                status="active",
                last_sync=datetime.now(timezone.utc),
            )
            session.add(account)
        else:
            account.channel_name = channel["title"]
            account.scopes = scopes
            account.status = "active"
            account.last_sync = datetime.now(timezone.utc)
        oauth_reference = _save_token(channel["channel_id"], bundle)
        account.oauth_reference = oauth_reference
        session.commit()
        session.refresh(account)
        return account
    finally:
        if own_session:
            session.close()


def handle_callback(
    code: str, db: Session | None = None, oauth: GoogleOAuthClient | None = None
) -> YouTubeAccount:
    """Callback entrypoint used by the API route."""
    return complete_connect(code, db=db, oauth=oauth)


def load_token(channel_id: str) -> TokenBundle | None:
    tokens = _load_tokens()
    data = tokens.get(channel_id)
    return TokenBundle.from_json(data) if data else None


def access_token_for(channel_id: str, oauth: GoogleOAuthClient | None = None) -> str:
    bundle = load_token(channel_id)
    if bundle is None:
        raise OAuthError(f"no stored token for channel {channel_id}")
    client = oauth or GoogleOAuthClient()
    if bundle.expired:
        bundle = client.refresh(bundle.refresh_token)
        _save_token(channel_id, bundle)
    return bundle.access_token
