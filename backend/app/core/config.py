"""App configuration — env-driven, no secrets in repo."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./creatorlab.db"
    backend_port: int = 8000


settings = Settings()
