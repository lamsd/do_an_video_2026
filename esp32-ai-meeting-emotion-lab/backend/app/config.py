from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # DATABASE_URL is useful for direct local development. Docker Compose instead supplies
    # separate values so SQLAlchemy can safely encode any PostgreSQL password characters.
    database_url: str | None = None
    database_host: str | None = None
    database_port: int = 5432
    database_name: str = "meeting_agent"
    database_user: str = "meeting_agent"
    database_password: str | None = None
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_backend_password: str | None = None
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4.1-mini"
    openai_tts_model: str = "tts-1"
    emotion_model_checkpoint: Path | None = None
    media_root: Path = Path("./data/media")
    cors_origins: str = "http://localhost:8080"
    heartbeat_ttl_seconds: int = 15

    @property
    def cors(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.database_host:
            return URL.create(
                "postgresql+psycopg",
                username=self.database_user,
                password=self.database_password,
                host=self.database_host,
                port=self.database_port,
                database=self.database_name,
            ).render_as_string(hide_password=False)
        return "sqlite:///./data/meeting_agent.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()

