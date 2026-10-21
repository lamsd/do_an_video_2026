from functools import lru_cache

from pydantic import AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Docker Compose injects the single source/settings.env file. A local .env is
    # intentionally not loaded, so developers cannot silently run with stale secrets.
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8088
    vexa_mode: str = "cloud"
    database_url: str
    vexa_api_base: AnyHttpUrl
    vexa_api_key: str = ""
    vexa_webhook_secret: str = ""
    poll_interval_seconds: int = Field(default=3, ge=1, le=60)
    redis_url: str = "redis://redis:6379/0"
    analysis_stream: str = "ai.analysis.jobs"
    analysis_consumer_group: str = "sentiment-workers"
    analysis_debounce_seconds: int = Field(default=20, ge=1, le=300)
    analysis_max_retries: int = Field(default=5, ge=0, le=20)
    # The adapter is explicit so a test/demonstration never silently runs a
    # different classifier under the same model version.
    classifier_adapter: str = "rules"
    model_version: str = "baseline-rules-v2"
    # A read-only directory mounted into backend/worker for a versioned, trusted
    # model artifact. It is intentionally empty for the deterministic rule baseline.
    model_artifact_dir: str = ""
    model_artifact_sha256: str = ""
    preprocessing_version: str = "2026-09-v1"
    # Optional local correction when the transcript provider leaves the host's
    # speech unassigned. Leave blank unless the operator has verified it.
    fallback_speaker_name: str = ""
    sentiment_confidence_threshold: float = Field(default=0.60, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.vexa_mode not in {"cloud", "self_host"}:
            raise ValueError("VEXA_MODE must be cloud or self_host")
        if self.app_env == "production" and (not self.vexa_api_key or not self.vexa_webhook_secret):
            raise ValueError("VEXA_API_KEY and VEXA_WEBHOOK_SECRET are required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
