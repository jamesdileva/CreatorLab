"""App configuration — env-driven, no secrets in repo."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./creatorlab.db"
    backend_port: int = 8000

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
