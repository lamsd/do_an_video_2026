from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Meeting, OutboxEvent, TranscriptSegment
from .vexa import VexaClient


def _segment_id(raw: dict, index: int) -> str:
    return str(raw.get("segment_id") or f"legacy:{raw.get('start', 0)}:{raw.get('end', 0)}:{index}")


async def get_owned_meeting(db: AsyncSession, meeting_id: UUID, owner_id: str) -> Meeting:
    meeting = await db.scalar(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.owner_id == owner_id)
    )
    if meeting is None:
        raise LookupError("meeting not found")
    return meeting


async def reconcile(db: AsyncSession, vexa: VexaClient, meeting: Meeting) -> dict:
    payload = await vexa.transcript(meeting.platform, meeting.native_meeting_id)
    changed = 0
    for index, raw in enumerate(payload.get("segments") or []):
        segment_id = _segment_id(raw, index)
        row = await db.scalar(
            select(TranscriptSegment).where(
                TranscriptSegment.meeting_id == meeting.id,
                TranscriptSegment.vexa_segment_id == segment_id,
            )
        )
        values = {
            "speaker_key": raw.get("speaker_key"),
            "speaker_name": raw.get("speaker"),
            "language": raw.get("language"),
            "text": raw.get("text") or "",
            "start_seconds": float(raw.get("start") or 0),
            "end_seconds": float(raw.get("end") or raw.get("start") or 0),
            "is_final": bool(raw.get("completed", True)),
        }
        if row is None:
            row = TranscriptSegment(meeting_id=meeting.id, vexa_segment_id=segment_id, **values)
            db.add(row)
            changed += 1
            segment_changed = True
        elif any(getattr(row, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(row, key, value)
            row.revision += 1
            changed += 1
            segment_changed = True
        else:
            segment_changed = False
        if segment_changed:
            meeting.transcript_revision += 1
            db.add(
                OutboxEvent(
                    dedupe_key=f"segment:{meeting.id}:{segment_id}:{row.revision}",
                    event_type="transcript.segment.upserted",
                    meeting_id=meeting.id,
                    payload={
                        "segment_id": segment_id,
                        "text": values["text"],
                        "is_final": values["is_final"],
                    },
                )
            )
    status = payload.get("status")
    if status:
        meeting.status = str(status)
    if meeting.status in {"completed", "failed"} and meeting.ended_at is None:
        meeting.ended_at = datetime.now(UTC)
    await db.commit()
    return {
        "changed": changed,
        "total": len(payload.get("segments") or []),
        "status": meeting.status,
    }
