"""Narrow local-only runner for the Dashboard setup form.

This component has Docker access, so it never runs user-supplied commands.
It accepts only a fixed allow-list of configuration keys, updates settings.env
atomically, and schedules one fixed Compose recreate command after replying.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Timer
from typing import Any

SETTINGS_PATH = Path(os.environ["SETTINGS_PATH"])
COMPOSE_FILE_PATH = Path(os.environ["COMPOSE_FILE_PATH"])
PROJECT_DIRECTORY = Path(os.environ["PROJECT_DIRECTORY"])
LOCAL_DEVELOPMENT = os.environ.get("APP_ENV", "development") == "development"
WRITE_LOCK = Lock()
KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
ALLOWED_KEYS = {
    "vexa_api_key": "VEXA_API_KEY",
    "classifier_adapter": "CLASSIFIER_ADAPTER",
    "model_version": "MODEL_VERSION",
    "preprocessing_version": "PREPROCESSING_VERSION",
    "sentiment_confidence_threshold": "SENTIMENT_CONFIDENCE_THRESHOLD",
    "model_artifact_dir": "MODEL_ARTIFACT_DIR",
    "model_artifact_sha256": "MODEL_ARTIFACT_SHA256",
}


def _read_settings() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in SETTINGS_PATH.read_text(encoding="utf-8").splitlines():
        if KEY_PATTERN.match(line):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _validate(values: dict[str, Any]) -> None:
    adapter = values.get("CLASSIFIER_ADAPTER", "rules")
    if adapter not in {"rules", "tfidf-logreg"}:
        raise ValueError("Unsupported classifier adapter")
    for key in ("MODEL_VERSION", "PREPROCESSING_VERSION"):
        value = values.get(key, "")
        if not isinstance(value, str) or not value.strip() or len(value) > 128 or "\n" in value:
            raise ValueError(f"Invalid {key}")
    threshold = values.get("SENTIMENT_CONFIDENCE_THRESHOLD", "")
    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid confidence threshold") from exc
    if not 0 <= threshold_value <= 1:
        raise ValueError("Confidence threshold must be from 0 to 1")
    key = values.get("VEXA_API_KEY", "")
    if key and not key.startswith("vxa_"):
        raise ValueError("Invalid Vexa API key")
    if adapter == "tfidf-logreg":
        artifact_dir = values.get("MODEL_ARTIFACT_DIR", "")
        artifact_hash = values.get("MODEL_ARTIFACT_SHA256", "")
        if not artifact_dir.startswith("/models"):
            raise ValueError("tfidf-logreg requires a /models artifact directory")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", artifact_hash):
            raise ValueError("tfidf-logreg requires a 64-character artifact SHA-256")


def _atomic_update(replacements: dict[str, str]) -> None:
    lines = SETTINGS_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    emitted: set[str] = set()
    updated: list[str] = []
    for line in lines:
        if KEY_PATTERN.match(line):
            key = line.split("=", 1)[0]
            if key in replacements:
                if key not in emitted:
                    updated.append(f"{key}={replacements[key]}\n")
                    emitted.add(key)
                continue
        updated.append(line)
    for key, value in replacements.items():
        if key not in emitted:
            updated.append(f"{key}={value}\n")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=SETTINGS_PATH.parent, delete=False
    ) as temporary:
        temporary.writelines(updated)
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o600)
    temporary_path.replace(SETTINGS_PATH)


def _run_fixed_recreate() -> None:
    subprocess.run(
        [
            "docker", "compose", "--env-file", str(SETTINGS_PATH), "-f", str(COMPOSE_FILE_PATH),
            "up", "-d", "--build", "--force-recreate", "backend", "worker", "dashboard",
        ],
        cwd=PROJECT_DIRECTORY,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "MeetingIntelligenceOperatorRunner/1.0"

    def log_message(self, format: str, *args: object) -> None:
        # Never log request bodies: they may contain a Vexa API key.
        print(f"operator-runner {self.command} {self.path} {args[-1] if args else ''}", flush=True)

    def _send(self, status: HTTPStatus, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(HTTPStatus.OK, {"status": "ok"})
        else:
            self._send(HTTPStatus.NOT_FOUND, {"detail": "not found"})

    def do_POST(self) -> None:
        if not LOCAL_DEVELOPMENT:
            self._send(HTTPStatus.FORBIDDEN, {"detail": "local setup is disabled"})
            return
        if self.path != "/apply":
            self._send(HTTPStatus.NOT_FOUND, {"detail": "not found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 2 or content_length > 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict) or any(key not in ALLOWED_KEYS for key in payload):
                raise ValueError("Unsupported setup field")
            replacements = {ALLOWED_KEYS[key]: str(value) for key, value in payload.items()}
            with WRITE_LOCK:
                merged = _read_settings()
                merged.update(replacements)
                _validate(merged)
                _atomic_update(replacements)
            Timer(0.8, _run_fixed_recreate).start()
        except (OSError, ValueError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"detail": "Setup data was rejected"})
            return
        self._send(HTTPStatus.ACCEPTED, {"status": "scheduled"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
