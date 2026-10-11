"""Google/YouTube OAuth client (Sprint 7.1).

All network access goes through an injectable httpx client so the flow is
testable without real credentials (MockTransport) — official API only
(architecture §5.8).
"""
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from ...core.config import settings

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
CHANNELS_ENDPOINT = "https://www.googleapis.com/youtube/v3/channels"
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
)

_STATE_TTL_SECONDS = 600


class OAuthError(RuntimeError):
    """OAuth flow failure (bad state, token exchange, channel lookup)."""


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: float
    scope: str = ""

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 30

    def to_json(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
        }

    @classmethod
    def from_json(cls, data: dict) -> "TokenBundle":
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=float(data.get("expires_at", 0)),
            scope=data.get("scope", ""),
        )


class GoogleOAuthClient:
    """Minimal OAuth 2.0 web-server flow for the YouTube Data API."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        scopes: list[str] | None = None,
        http_client: httpx.Client | None = None,
        token_store_dir: Path | str | None = None,
    ) -> None:
        self.client_id = client_id if client_id is not None else settings.youtube_client_id
        self.client_secret = (
            client_secret if client_secret is not None else settings.youtube_client_secret
        )
        self.redirect_uri = redirect_uri or settings.youtube_redirect_uri
        self.scopes = scopes or [
            s for s in settings.youtube_scopes.split() if s
        ] or list(DEFAULT_SCOPES)
        self._client = http_client or httpx.Client(timeout=20.0)
        self._states: dict[str, float] = {}
        self.token_store = Path(token_store_dir) if token_store_dir else None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # ---- authorization URL + state ----

    def authorize_url(self, state: str) -> str:
        if not self.configured:
            raise OAuthError("YouTube OAuth is not configured (missing client id/secret)")
        self._states[state] = time.time() + _STATE_TTL_SECONDS
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        query = httpx.QueryParams(params)
        return f"{AUTH_ENDPOINT}?{query}"

    def consume_state(self, state: str) -> None:
        expiry = self._states.pop(state, None)
        if expiry is None:
            raise OAuthError("unknown OAuth state")
        if time.time() > expiry:
            raise OAuthError("OAuth state expired")

    # ---- token exchange / refresh ----

    def exchange_code(self, code: str) -> TokenBundle:
        if not self.configured:
            raise OAuthError("YouTube OAuth is not configured (missing client id/secret)")
        try:
            res = self._client.post(
                TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            res.raise_for_status()
            body = res.json()
        except httpx.HTTPError as exc:
            raise OAuthError(f"token exchange failed: {exc}") from exc
        try:
            expires_in = int(body.get("expires_in", 3600))
            bundle = TokenBundle(
                access_token=body["access_token"],
                refresh_token=body.get("refresh_token", ""),
                expires_at=time.time() + expires_in,
                scope=body.get("scope", ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OAuthError(f"malformed token response: {exc}") from exc
        if not bundle.refresh_token:
            raise OAuthError("token response missing refresh_token")
        return bundle

    def refresh(self, refresh_token: str) -> TokenBundle:
        if not self.configured:
            raise OAuthError("YouTube OAuth is not configured (missing client id/secret)")
        try:
            res = self._client.post(
                TOKEN_ENDPOINT,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                },
            )
            res.raise_for_status()
            body = res.json()
            expires_in = int(body.get("expires_in", 3600))
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise OAuthError(f"token refresh failed: {exc}") from exc
        return TokenBundle(
            access_token=body["access_token"],
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
            scope=body.get("scope", ""),
        )

    def access_token(self, refresh_token: str) -> str:
        bundle = self.refresh(refresh_token)
        return bundle.access_token

    # ---- channel identity ----

    def fetch_channel(self, access_token: str) -> dict:
        try:
            res = self._client.get(
                CHANNELS_ENDPOINT,
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            res.raise_for_status()
            items = res.json().get("items", [])
        except httpx.HTTPError as exc:
            raise OAuthError(f"channel lookup failed: {exc}") from exc
        if not items:
            raise OAuthError("no channel returned for this account")
        item = items[0]
        return {
            "channel_id": item["id"],
            "title": item.get("snippet", {}).get("title", ""),
        }
