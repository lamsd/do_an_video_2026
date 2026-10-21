from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentProfileOut(BaseModel):
    id: str
    label: str
    personality: str
    voice: str
    speaking_style: str


class CreateSessionRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=2_000)
    rounds: int = Field(default=1, ge=1, le=8)


class AddUserMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)


class TurnOut(BaseModel):
    id: str
    sequence: int
    round_number: int
    speaker_type: str
    agent_id: str | None
    transcript: str
    voice: str | None
    intended_style: str | None
    audio_url: str | None
    generation_backend: str | None
    feature_extraction_version: str | None
    features: dict[str, Any] | None
    emotion_prediction: dict[str, Any] | None
    created_at: datetime | None


class SessionOut(BaseModel):
    id: str
    topic: str
    requested_rounds: int
    completed_rounds: int
    status: Literal["created", "running", "paused", "stopped", "completed", "failed"]
    created_at: datetime | None
    updated_at: datetime | None
    turns: list[TurnOut] = []


class AudioAnalysisOut(BaseModel):
    session_id: str
    turn_id: str
    features: dict[str, Any]
    emotion_prediction: dict[str, Any]

