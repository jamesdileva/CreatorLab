"""App configuration — env-driven, no secrets in repo."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./creatorlab.db"
    backend_port: int = 8000

    # AI layer — never hard-code one model (architecture §7)
    llm_provider: str = "stub"
    creator_prompt_version: str = "creator_prompt_v1"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Scheduler runs the 15-minute analytics sweep (Sprint 8.1, off by default)
    enable_scheduler: bool = False

    # YouTube Data API (official API first; emulators are future-only, arch §5.8)
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://localhost:8000/api/youtube/oauth/callback"
    youtube_scopes: str = "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube.upload"
    # MVP publishes private/unlisted only; public automated publishing waits for
    # verification (roadmap 7.4). Values: manual | private_api | public_api
    publishing_mode: str = "private_api"


settings = Settings()
