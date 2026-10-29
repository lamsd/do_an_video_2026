import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.operator_settings import (
    LocalSetupRequest,
    _validate_local_setup,
    build_operator_settings,
)


def test_operator_settings_hide_secret_values_and_expose_safe_state():
    settings = SimpleNamespace(
        app_env="development",
        dashboard_local_setup_enabled=True,
        vexa_mode="self_host",
        vexa_api_base="http://gateway:8000",
        vexa_api_key="vxa_secret_do_not_expose",
        vexa_webhook_secret="webhook_secret_do_not_expose",
        classifier_adapter="tfidf-logreg",
        model_version="pilot-v1",
        preprocessing_version="2026-10-v1",
        transcription_service_url="http://transcription.internal:8083",
        transcription_service_token="transcription_secret_do_not_expose",
        transcription_model="whisper-large-v3",
        sentiment_confidence_threshold=0.72,
        model_artifact_dir="/models/pilot-v1",
        model_artifact_sha256="a" * 64,
        poll_interval_seconds=3,
        analysis_debounce_seconds=20,
        analysis_max_retries=5,
    )

    payload = build_operator_settings(settings)
    rendered = json.dumps(payload)

    assert "vxa_secret_do_not_expose" not in rendered
    assert "webhook_secret_do_not_expose" not in rendered
    assert "transcription_secret_do_not_expose" not in rendered
    assert payload["security"]["secrets_are_hidden"] is True
    assert payload["security"]["dashboard_submit_available"] is True
    assert payload["integrations"][0]["status"] == "configured"
    assert payload["integrations"][2]["status"] == "configured"
    assert payload["model"]["artifact_required"] is True
    assert payload["restart"]["command"] == "./scripts/runtime-settings.sh apply"


def test_operator_settings_marks_missing_vexa_key_without_returning_it():
    settings = SimpleNamespace(
        app_env="development",
        dashboard_local_setup_enabled=True,
        vexa_mode="self_host",
        vexa_api_base="http://gateway:8000",
        vexa_api_key="",
        vexa_webhook_secret="CHANGE_ME",
        classifier_adapter="rules",
        model_version="baseline-rules-v2",
        preprocessing_version="2026-09-v1",
        transcription_service_url="",
        transcription_service_token="",
        transcription_model="",
        sentiment_confidence_threshold=0.6,
        model_artifact_dir="",
        model_artifact_sha256="",
        poll_interval_seconds=3,
        analysis_debounce_seconds=20,
        analysis_max_retries=5,
    )

    payload = build_operator_settings(settings)

    assert payload["integrations"][0]["status"] == "needs_secret"
    assert payload["integrations"][1]["status"] == "not_required"
    assert payload["integrations"][2]["status"] == "needs_configuration"


def test_local_setup_rejects_a_non_vexa_key_without_echoing_it():
    request = LocalSetupRequest(
        vexa_api_key="not-a-vexa-key",
        classifier_adapter="rules",
        model_version="baseline-rules-v2",
        preprocessing_version="2026-09-v1",
        sentiment_confidence_threshold=0.6,
    )

    with pytest.raises(HTTPException, match="must start with vxa_") as exc_info:
        _validate_local_setup(request)

    assert "not-a-vexa-key" not in str(exc_info.value.detail)


def test_local_setup_validates_tfidf_artifact_metadata_when_provided():
    request = LocalSetupRequest(
        classifier_adapter="tfidf-logreg",
        model_version="tfidf-v1",
        preprocessing_version="2026-10-v1",
        sentiment_confidence_threshold=0.7,
        model_artifact_dir="/tmp/not-mounted",
        model_artifact_sha256="a" * 64,
    )

    with pytest.raises(HTTPException, match="mounted below /models"):
        _validate_local_setup(request)
