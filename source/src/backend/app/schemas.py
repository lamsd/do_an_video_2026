from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StartMeetingRequest(BaseModel):
    meeting_url: str
    bot_name: str = Field(default="Meeting Assistant", max_length=128)
    # The default reflects the local dashboard's Vietnamese meeting workflow.
    # ``auto`` remains available for deliberately multilingual meetings.
    transcription_language: Literal["vi", "en", "auto"] = "vi"


class MeetingResponse(BaseModel):
    id: UUID
    vexa_meeting_id: str | None
    platform: str
    native_meeting_id: str
    status: str


class SegmentResponse(BaseModel):
    id: UUID
    vexa_segment_id: str
    speaker: str | None
    text: str
    language: str | None
    start: float
    end: float
    is_final: bool
    revision: int
    # Source text is never discarded merely because it is unsuitable for the
    # analytics model.  These fields let the dashboard make that distinction
    # explicit instead of presenting noisy STT output as model input.
    analysis_eligible: bool
    quality_reasons: list[str]
    analysis_language: str
