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


settings = Settings()
