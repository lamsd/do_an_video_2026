from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

SCHEMA_VERSION = "mqtt-v1"


class Envelope(BaseModel):
    schema_version: str = SCHEMA_VERSION
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_id: str | None = None
    device_id: str | None = None
    session_id: str | None = None
    event_type: str = "unspecified"
    turn_id: str | None = None
    turn_token: str | None = None
    sequence_number: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def as_json_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")


def topic_device(agent_id: str, suffix: str) -> str:
    return f"lab/device/{agent_id}/{suffix}"


def topic_context(session_id: str) -> str:
    return f"lab/session/{session_id}/context"

