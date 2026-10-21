from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/meeting_agent.db"
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_backend_password: str | None = None
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4.1-mini"
    openai_tts_model: str = "gpt-4o-mini-tts"
    emotion_model_checkpoint: Path | None = None
    media_root: Path = Path("./data/media")
    cors_origins: str = "http://localhost:8080"
    heartbeat_ttl_seconds: int = 15

    @property
    def cors(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

