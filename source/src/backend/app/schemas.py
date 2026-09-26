from uuid import UUID

from pydantic import BaseModel, Field


class StartMeetingRequest(BaseModel):
    meeting_url: str
    bot_name: str = Field(default="Meeting Assistant", max_length=128)


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
    start: float
    end: float
    is_final: bool
    revision: int
