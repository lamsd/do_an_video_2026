from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DiscussionSession(Base):
    __tablename__ = "discussion_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    topic: Mapped[str] = mapped_column(Text)
    requested_rounds: Mapped[int] = mapped_column(Integer)
    completed_rounds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    turns: Mapped[list[DiscussionTurn]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="DiscussionTurn.sequence"
    )


class DiscussionTurn(Base):
    __tablename__ = "discussion_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("discussion_sessions.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    round_number: Mapped[int] = mapped_column(Integer)
    speaker_type: Mapped[str] = mapped_column(String(16), default="agent")
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transcript: Mapped[str] = mapped_column(Text)
    voice: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intended_style: Mapped[str | None] = mapped_column(String(128), nullable=True)
    audio_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_backend: Mapped[str | None] = mapped_column(String(48), nullable=True)
    feature_extraction_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    emotion_prediction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    session: Mapped[DiscussionSession] = relationship(back_populates="turns")

