import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    vexa_meeting_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    platform: Mapped[str] = mapped_column(String(32))
    native_meeting_id: Mapped[str] = mapped_column(String(512), index=True)
    status: Mapped[str] = mapped_column(String(64), default="requested", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("meeting_id", "vexa_segment_id", name="uq_segment_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    vexa_segment_id: Mapped[str] = mapped_column(String(256))
    speaker_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    speaker_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    retracted: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IncomingWebhook(Base):
    __tablename__ = "incoming_webhooks"

    event_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_outbox_dedupe"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(512))
    event_type: Mapped[str] = mapped_column(String(128))
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id", "kind", "source_revision", "model_version", name="uq_analysis_run"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # live, final, backfill
    source_revision: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(128))
    preprocessing_version: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisUnit(Base):
    __tablename__ = "analysis_units"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    source_revision: Mapped[int] = mapped_column(Integer, index=True)
    speaker_key: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    speaker_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    segment_ids: Mapped[list] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="unknown")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quality_status: Mapped[str] = mapped_column(String(32), default="accepted", index=True)
    quality_reasons: Mapped[list] = mapped_column(JSON, default=list)
    preprocessing_version: Mapped[str] = mapped_column(String(128))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SentimentPrediction(Base):
    __tablename__ = "sentiment_predictions"
    __table_args__ = (UniqueConstraint("analysis_run_id", "analysis_unit_id", name="uq_prediction_run_unit"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    analysis_unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_units.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    probabilities: Mapped[dict] = mapped_column(JSON)
    polarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    inference_ms: Mapped[int] = mapped_column(Integer, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MeetingSentimentWindow(Base):
    __tablename__ = "meeting_sentiment_windows"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id", "source_revision", "scope", "speaker_key", "window_start", name="uq_window"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    source_revision: Mapped[int] = mapped_column(Integer, index=True)
    scope: Mapped[str] = mapped_column(String(32), default="meeting")
    speaker_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    positive_weight: Mapped[float] = mapped_column(Float, default=0)
    neutral_weight: Mapped[float] = mapped_column(Float, default=0)
    negative_weight: Mapped[float] = mapped_column(Float, default=0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage: Mapped[float] = mapped_column(Float, default=0)
    unit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
