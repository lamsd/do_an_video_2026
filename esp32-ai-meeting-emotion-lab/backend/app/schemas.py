from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StartExperimentRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=2_000)
    rounds: int = Field(default=1, ge=1, le=8)


class DeviceOut(BaseModel):
    agent_id: str
    device_id: str
    display_name: str
    voice: str
    state: str
    firmware_version: str | None
    last_seen_at: datetime | None
    last_error: str | None


class TurnOut(BaseModel):
    id: str
    agent_id: str
    sequence: int
    round_number: int
    transcript: str
    voice: str
    audio_url: str | None
    acoustic_metadata: dict[str, Any] | None
    emotion_prediction: dict[str, Any] | None
    created_at: datetime | None


class SessionOut(BaseModel):
    id: str
    topic: str
    requested_rounds: int
    completed_rounds: int
    status: Literal[
        "waiting_for_devices", "running", "paused", "completed", "stopped", "failed"
    ]
    created_at: datetime | None
    updated_at: datetime | None
    turns: list[TurnOut] = []

