from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ExperimentSession(Base):
    __tablename__ = "experiment_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    topic: Mapped[str] = mapped_column(Text)
    requested_rounds: Mapped[int] = mapped_column(Integer)
    completed_rounds: Mapped[int] = mapped_column(Integer, default=0)
    next_agent_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="waiting_for_devices")
    active_turn_token: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    active_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    turns: Mapped[list[ExperimentTurn]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ExperimentTurn.sequence"
    )


class ExperimentTurn(Base):
    __tablename__ = "experiment_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("experiment_sessions.id"), index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    turn_token: Mapped[str] = mapped_column(String(36), unique=True)
    sequence: Mapped[int] = mapped_column(Integer)
    round_number: Mapped[int] = mapped_column(Integer)
    transcript: Mapped[str] = mapped_column(Text)
    voice: Mapped[str] = mapped_column(String(32))
    audio_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    acoustic_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    emotion_prediction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    session: Mapped[ExperimentSession] = relationship(back_populates="turns")


class DeviceStatus(Base):
    __tablename__ = "device_status"

    agent_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(32), unique=True)
    state: Mapped[str] = mapped_column(String(40), default="disconnected")
    mqtt_client_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

