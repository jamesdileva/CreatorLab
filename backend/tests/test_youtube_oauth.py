"""Sprint 7.1 — YouTube OAuth: consent URL, code exchange, channel binding."""
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.integrations.youtube.auth import GoogleOAuthClient, OAuthError, TokenBundle
from app.main import app
from app.services import youtube_service

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


def _mock_transport(token_body=None, channel_body=None, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            body = token_body if token_body is not None else {
                "access_token": "access-123",
                "refresh_token": "refresh-123",
                "expires_in": 3600,
                "scope": "youtube.readonly",
            }
            return httpx.Response(status_code, json=body)
        if "channels" in request.url.path:
            return httpx.Response(
                status_code,
                json=channel_body
                if channel_body is not None
                else {"items": [{"id": "UC_TEST", "snippet": {"title": "Hank's Channel"}}]},
            )
        return httpx.Response(404, json={"error": "not mocked"})

    return httpx.MockTransport(handler)


def _client(tmp_path, token_body=None, channel_body=None, status_code=200):
    transport = _mock_transport(token_body, channel_body, status_code)
    http = httpx.Client(transport=transport, base_url="https://google.test")
    oauth = GoogleOAuthClient(
        client_id="client.apps.test",
        client_secret="secret-test",
        redirect_uri="http://localhost:8000/api/youtube/oauth/callback",
        http_client=http,
        token_store_dir=tmp_path / "secrets",
    )
    return oauth


@pytest.fixture
def client(tmp_path, monkeypatch):
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    monkeypatch.chdir(tmp_path)
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def configured_client(client, tmp_path):
    """Client whose service uses the mocked OAuth client + temp secrets."""
    oauth = _client(tmp_path)
    import app.services.youtube_service as svc

    svc._oauth = lambda: oauth  # type: ignore[assignment]
    monkey_target = tmp_path / "secrets2"
    return client


def test_auth_url_contains_scopes_state_and_type():
    oauth = GoogleOAuthClient(
        client_id="client.apps.test",
        client_secret="secret-test",
        http_client=httpx.Client(),
    )
    url = oauth.authorize_url("state-abc")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "client_id=client.apps.test" in url
    assert "state=state-abc" in url
    assert "offline" in url
    assert "youtube" in url


def test_unconfigured_client_raises():
    oauth = GoogleOAuthClient(
        client_id="", client_secret="", http_client=httpx.Client()
    )
    with pytest.raises(OAuthError):
        oauth.authorize_url("state")


def test_state_must_be_issued():
    oauth = _client_no_http()
    with pytest.raises(OAuthError):
        oauth.consume_state("never-issued")


def _client_no_http() -> GoogleOAuthClient:
    return GoogleOAuthClient(
        client_id="client.apps.test",
        client_secret="secret-test",
        http_client=httpx.Client(),
    )


def test_exchange_code_returns_refresh_token(tmp_path):
    oauth = _client(tmp_path)
    bundle = oauth.exchange_code("code-abc")
    assert bundle.access_token == "access-123"
    assert bundle.refresh_token == "refresh-123"
    assert bundle.expired is False


def test_exchange_code_rejects_missing_refresh(tmp_path):
    oauth = _client(
        tmp_path,
        token_body={"access_token": "a", "expires_in": 60},
    )
    with pytest.raises(OAuthError):
        oauth.exchange_code("code")


def test_exchange_code_http_error_raises(tmp_path):
    oauth = _client(tmp_path, status_code=400)
    with pytest.raises(OAuthError):
        oauth.exchange_code("bad-code")


def test_fetch_channel(tmp_path):
    oauth = _client(tmp_path)
    channel = oauth.fetch_channel("token")
    assert channel == {"channel_id": "UC_TEST", "title": "Hank's Channel"}


def test_refresh_keeps_refresh_token(tmp_path):
    oauth = _client(tmp_path)
    bundle = oauth.refresh("refresh-123")
    assert bundle.access_token == "access-123"
    assert bundle.refresh_token == "refresh-123"


def test_token_bundle_roundtrip(tmp_path):
    oauth = _client(tmp_path)
    bundle = oauth.exchange_code("code-abc")
    restored = TokenBundle.from_json(bundle.to_json())
    assert restored.access_token == bundle.access_token
    assert restored.refresh_token == bundle.refresh_token


def test_service_persists_account_and_token_file(tmp_path, monkeypatch, client):
    monkeypatch.chdir(tmp_path)
    oauth = _client(tmp_path)

    import app.services.youtube_service as svc

    monkeypatch.setattr(svc, "_oauth", lambda: oauth)
    db = TestingSession()
    account = svc.handle_callback("code-abc", db=db)
    assert account.channel_id == "UC_TEST"
    assert account.channel_name == "Hank's Channel"
    assert account.status == "active"
    assert account.oauth_reference.endswith("youtube_tokens.json")

    # token file written outside version control, never printed
    token_file = tmp_path / account.oauth_reference
    assert token_file.is_file()
    assert "refresh-123" not in account.oauth_reference

    loaded = svc.load_token("UC_TEST")
    assert loaded is not None and loaded.refresh_token == "refresh-123"


def test_status_endpoint_reports_config_only(client, tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    body = client.get("/api/youtube/status").json()
    assert set(body) == {"configured"}


def test_oauth_start_requires_configuration(client, monkeypatch):
    import app.services.youtube_service as svc

    monkeypatch.setattr(
        svc, "_oauth", lambda: (_ for _ in ()).throw(
            svc.NotConfiguredError("set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET")
        ),
    )
    assert client.get("/api/youtube/oauth/start").status_code == 400


def test_accounts_endpoint(client):
    assert client.get("/api/youtube/accounts").json() == []


def test_full_callback_creates_account(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    oauth = _client(tmp_path)

    import app.services.youtube_service as svc

    monkeypatch.setattr(svc, "_oauth", lambda: oauth)
    res = client.get("/api/youtube/oauth/callback?code=code-abc&state=st", follow_redirects=False)
    assert res.status_code == 307
    assert "connected=UC_TEST" in res.headers["location"]

    accounts = client.get("/api/youtube/accounts").json()
    assert len(accounts) == 1
    assert accounts[0]["channel_id"] == "UC_TEST"


def test_callback_missing_code_redirects_error(client):
    res = client.get("/api/youtube/oauth/callback", follow_redirects=False)
    assert res.status_code == 307
    assert "error=missing_code" in res.headers["location"]


def test_callback_oauth_error_redirects_error(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    oauth = _client(tmp_path, status_code=400)

    import app.services.youtube_service as svc

    monkeypatch.setattr(svc, "_oauth", lambda: oauth)
    res = client.get("/api/youtube/oauth/callback?code=bad", follow_redirects=False)
    assert res.status_code == 307
    assert "error=oauth_failed" in res.headers["location"]
    assert client.get("/api/youtube/accounts").json() == []
