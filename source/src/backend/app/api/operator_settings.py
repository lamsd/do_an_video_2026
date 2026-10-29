"""Read-only operator configuration summary for the local dashboard.

The endpoint deliberately returns capability and configuration state rather
than values from ``settings.env``.  In particular, API keys, webhook secrets,
database credentials, URLs and artifact paths must never cross the API
boundary into a browser.
"""

from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import owner
from ..config import Settings, get_settings

router = APIRouter(prefix="/v1/operator", tags=["operator"])

RECREATE_SERVICES = ["backend", "worker", "dashboard"]
RESTART_REQUIRED_FOR = [
    "VEXA_API_KEY",
    "VEXA_API_BASE",
    "VEXA_WEBHOOK_SECRET",
    "CLASSIFIER_ADAPTER",
    "MODEL_VERSION",
    "MODEL_ARTIFACT_DIR",
    "MODEL_ARTIFACT_SHA256",
    "PREPROCESSING_VERSION",
    "SENTIMENT_CONFIDENCE_THRESHOLD",
    "POLL_INTERVAL_SECONDS",
    "ANALYSIS_DEBOUNCE_SECONDS",
]


class LocalSetupRequest(BaseModel):
    """Allowed fields for the local setup form; unknown values are ignored."""

    vexa_api_key: str | None = None
    classifier_adapter: Literal["rules", "tfidf-logreg"]
    model_version: str
    preprocessing_version: str
    sentiment_confidence_threshold: float
    model_artifact_dir: str | None = None
    model_artifact_sha256: str | None = None


def _configured(value: str | None) -> bool:
    """A placeholder is not a configured value, but its contents stay private."""
    return bool(value and value != "CHANGE_ME")


def build_operator_settings(settings: Settings) -> dict[str, Any]:
    """Build a browser-safe configuration summary from application settings."""
    model_requires_artifact = settings.classifier_adapter == "tfidf-logreg"
    transcription_url_configured = _configured(settings.transcription_service_url)
    transcription_token_configured = _configured(settings.transcription_service_token)
    transcription_status = (
        "configured"
        if transcription_url_configured and transcription_token_configured
        else "needs_secret"
        if transcription_url_configured
        else "needs_configuration"
    )
    return {
        "environment": settings.app_env,
        "security": {
            "secrets_are_hidden": True,
            "apply_method": "local_operator_script",
            "dashboard_submit_available": (
                settings.app_env == "development" and settings.dashboard_local_setup_enabled
            ),
            "message": "Secrets are entered only in the local operator terminal and are never shown here.",
        },
        "restart": {
            "recreate_services": RECREATE_SERVICES,
            "required_for": RESTART_REQUIRED_FOR,
            "command": "./scripts/runtime-settings.sh apply",
        },
        "model": {
            "classifier_adapter": settings.classifier_adapter,
            "model_version": settings.model_version,
            "preprocessing_version": settings.preprocessing_version,
            "sentiment_confidence_threshold": settings.sentiment_confidence_threshold,
            "artifact_required": model_requires_artifact,
            "artifact_configured": _configured(settings.model_artifact_dir),
            "artifact_integrity_configured": _configured(settings.model_artifact_sha256),
        },
        "analysis": {
            "poll_interval_seconds": settings.poll_interval_seconds,
            "debounce_seconds": settings.analysis_debounce_seconds,
            "max_retries": settings.analysis_max_retries,
        },
        "integrations": [
            {
                "id": "vexa",
                "label": "Vexa meeting bot",
                "status": "configured" if _configured(settings.vexa_api_key) else "needs_secret",
                "secret_fields": ["VEXA_API_KEY", "VEXA_WEBHOOK_SECRET"],
                "configuration": {
                    "mode": settings.vexa_mode,
                    "api_base_configured": bool(settings.vexa_api_base),
                    "webhook_secret_configured": _configured(settings.vexa_webhook_secret),
                },
            },
            {
                "id": "model_artifact",
                "label": "Model artifact",
                "status": (
                    "not_required"
                    if not model_requires_artifact
                    else "configured"
                    if _configured(settings.model_artifact_dir)
                    and _configured(settings.model_artifact_sha256)
                    else "needs_configuration"
                ),
                "secret_fields": [],
                "configuration": {
                    "adapter": settings.classifier_adapter,
                    "artifact_required": model_requires_artifact,
                    "artifact_configured": _configured(settings.model_artifact_dir),
                    "integrity_hash_configured": _configured(settings.model_artifact_sha256),
                },
            },
            {
                "id": "transcription",
                "label": "Transcription service",
                "status": transcription_status,
                "secret_fields": ["TRANSCRIPTION_SERVICE_TOKEN"],
                "configuration": {
                    "endpoint_configured": transcription_url_configured,
                    "model_configured": _configured(settings.transcription_model),
                    "token_configured": transcription_token_configured,
                },
            },
        ],
    }


def _validate_local_setup(request: LocalSetupRequest) -> None:
    if request.vexa_api_key is not None and request.vexa_api_key and not request.vexa_api_key.startswith("vxa_"):
        raise HTTPException(422, "Vexa API key must start with vxa_")
    if not request.model_version.strip() or len(request.model_version) > 128:
        raise HTTPException(422, "Model version must contain 1 to 128 characters")
    if not request.preprocessing_version.strip() or len(request.preprocessing_version) > 128:
        raise HTTPException(422, "Preprocessing version must contain 1 to 128 characters")
    if not 0 <= request.sentiment_confidence_threshold <= 1:
        raise HTTPException(422, "Confidence threshold must be from 0 to 1")
    if request.classifier_adapter == "tfidf-logreg":
        if request.model_artifact_dir is not None and not request.model_artifact_dir.startswith("/models"):
            raise HTTPException(422, "Model artifact directory must be mounted below /models")
        if request.model_artifact_sha256 is not None and (
            len(request.model_artifact_sha256) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in request.model_artifact_sha256)
        ):
            raise HTTPException(422, "Model artifact SHA-256 must contain 64 hexadecimal characters")


@router.post("/setup", status_code=202)
async def submit_local_setup(
    request: LocalSetupRequest,
    _: str = Depends(owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Store an allow-listed local setup draft and schedule a safe recreate.

    This route is deliberately unavailable outside development.  It forwards
    data to a Docker-network-only runner rather than giving the browser shell
    or Docker-socket access.
    """
    if settings.app_env != "development" or not settings.dashboard_local_setup_enabled:
        raise HTTPException(403, "Dashboard setup is available only in local development")
    _validate_local_setup(request)
    payload = request.model_dump(exclude_none=True)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(f"{settings.operator_runner_url}apply", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Local setup runner is unavailable") from exc
    if response.status_code != 202:
        raise HTTPException(502, "Local setup runner rejected the configuration")
    return {
        "status": "scheduled",
        "message": "Configuration was saved locally. Backend, worker and dashboard are restarting.",
    }


@router.get("/settings")
async def operator_settings(
    _: str = Depends(owner), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Return only safe runtime state for the operator settings panel."""
    return build_operator_settings(settings)
