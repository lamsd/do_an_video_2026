import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import AnalysisRun, Meeting, OutboxEvent, TranscriptSegment
from .queue import enqueue_analysis
from .repositories.analysis import get_or_create_run
from .vexa import VexaClient

log = logging.getLogger(__name__)


def _segment_id(raw: dict, index: int) -> str:
    return str(raw.get("segment_id") or f"legacy:{raw.get('start', 0)}:{raw.get('end', 0)}:{index}")


def _speaker_identity(raw: dict, fallback_name: str) -> tuple[str | None, str | None]:
    """Preserve provider attribution, using a verified local host only as fallback."""
    provided_name = str(raw.get("speaker") or "").strip()
    provided_key = str(raw.get("speaker_key") or "").strip()
    fallback_name = fallback_name.strip()
    if provided_name:
        return provided_key or None, provided_name
    if fallback_name:
        return provided_key or f"fallback:{fallback_name.casefold()}", fallback_name
    return provided_key or None, None


def _source_retracted(raw: dict) -> bool:
    """Map explicit provider retraction signals without guessing from absence.

    A missing segment from a REST response is not enough evidence to retract it:
    some providers return partial snapshots.  Only an explicit event/status may
    invalidate an already stored transcript segment.
    """
    status = str(raw.get("status") or raw.get("state") or "").strip().lower()
    return bool(raw.get("retracted") or raw.get("is_retracted")) or status in {
        "retracted",
        "deleted",
        "revoked",
    }


def _apply_meeting_status(meeting: Meeting, raw_status: object) -> dict | None:
    """Apply one provider status transition and return its UI-safe event payload.

    Transcript polling is also how the application learns that a bot is waiting
    for admission or has become active.  Make that transition explicit so the
    SSE dashboard does not remain on the initial ``joining`` value until a
    transcript segment happens to arrive.
    """
    status = str(raw_status or "").strip()
    if not status or status == meeting.status:
        return None
    previous_status = meeting.status
    meeting.status = status
    return {"previous_status": previous_status, "status": status}


async def get_owned_meeting(db: AsyncSession, meeting_id: UUID, owner_id: str) -> Meeting:
    meeting = await db.scalar(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.owner_id == owner_id)
    )
    if meeting is None:
        raise LookupError("meeting not found")
    return meeting


async def _queue_live_analysis_if_due(db: AsyncSession, meeting: Meeting) -> str:
    """Create a durable live run after new transcript data, at a bounded rate.

    A run has an immutable source snapshot, so creating one for every tiny STT
    revision only produces stale work.  This uses the configured debounce as a
    *minimum live-analysis interval*: the first usable revision is queued
    immediately, then later revisions coalesce until the interval passes.
    Manual/final analysis remains available without this rate limit.
    """
    settings = get_settings()
    has_final = await db.scalar(
        select(TranscriptSegment.id)
        .where(
            TranscriptSegment.meeting_id == meeting.id,
            TranscriptSegment.is_final.is_(True),
            TranscriptSegment.retracted.is_(False),
        )
        .limit(1)
    )
    if has_final is None:
        return "waiting_for_final"

    latest = await db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.meeting_id == meeting.id, AnalysisRun.kind == "live")
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    if latest is not None and latest.created_at is not None:
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - created_at < timedelta(seconds=settings.analysis_debounce_seconds):
            return "debounced"

    run = await get_or_create_run(
        db,
        meeting=meeting,
        kind="live",
        model_version=settings.model_version,
        preprocessing_version=settings.preprocessing_version,
    )
    await db.commit()
    if run.status != "queued":
        return run.status
    try:
        await enqueue_analysis(run.id)
    except Exception:
        # The run is committed before enqueueing.  The worker's recovery scan
        # will pick it up, and transcript ingestion must never fail merely
        # because the analysis queue had a transient outage.
        log.exception("could not enqueue live analysis run %s", run.id)
        return "queued_recoverable"
    return "queued"


async def reconcile(db: AsyncSession, vexa: VexaClient, meeting: Meeting) -> dict:
    payload = await vexa.transcript(meeting.platform, meeting.native_meeting_id)
    fallback_name = get_settings().fallback_speaker_name
    changed = 0
    for index, raw in enumerate(payload.get("segments") or []):
        segment_id = _segment_id(raw, index)
        row = await db.scalar(
            select(TranscriptSegment).where(
                TranscriptSegment.meeting_id == meeting.id,
                TranscriptSegment.vexa_segment_id == segment_id,
            )
        )
        speaker_key, speaker_name = _speaker_identity(raw, fallback_name)
        values = {
            "speaker_key": speaker_key,
            "speaker_name": speaker_name,
            "language": raw.get("language"),
            "text": raw.get("text") or "",
            "start_seconds": float(raw.get("start") or 0),
            "end_seconds": float(raw.get("end") or raw.get("start") or 0),
            "is_final": bool(raw.get("completed", True)),
            "retracted": _source_retracted(raw),
        }
        # Retraction notifications are often sparse and contain only a segment
        # ID plus status. Preserve the prior source evidence instead of
        # replacing it with empty text/zero timestamps.
        if row is not None and values["retracted"]:
            if "text" not in raw:
                values["text"] = row.text
            if "language" not in raw:
                values["language"] = row.language
            if "start" not in raw:
                values["start_seconds"] = row.start_seconds
            if "end" not in raw:
                values["end_seconds"] = row.end_seconds
            if "completed" not in raw:
                values["is_final"] = row.is_final
            if "speaker" not in raw and "speaker_key" not in raw:
                values["speaker_key"] = row.speaker_key
                values["speaker_name"] = row.speaker_name
        if row is None:
            # The outbox key below includes the segment revision. Set it on
            # the Python object rather than relying on a database-side column
            # default, which is populated only when the INSERT is flushed.
            row = TranscriptSegment(
                meeting_id=meeting.id,
                vexa_segment_id=segment_id,
                revision=1,
                **values,
            )
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
                        "retracted": values["retracted"],
                        "upstream_language": values["language"],
                    },
                )
            )
    status_event = _apply_meeting_status(meeting, payload.get("status"))
    if status_event is not None:
        db.add(
            OutboxEvent(
                # A status normally advances monotonically for one meeting.
                # This key makes repeated transcript polls idempotent while
                # retaining one durable event for each visible state.
                dedupe_key=f"meeting-status:{meeting.id}:{status_event['status']}",
                event_type="meeting.status.updated",
                meeting_id=meeting.id,
                payload=status_event,
            )
        )
    if meeting.status in {"completed", "failed"} and meeting.ended_at is None:
        meeting.ended_at = datetime.now(UTC)
    await db.commit()
    analysis_status = "unchanged"
    if changed:
        try:
            analysis_status = await _queue_live_analysis_if_due(db, meeting)
        except Exception:
            # Reconciliation is the durable source-of-truth path.  Keep it
            # available even if optional analytics scheduling fails.
            await db.rollback()
            log.exception("could not schedule live analysis for meeting %s", meeting.id)
            analysis_status = "schedule_failed"
    return {
        "changed": changed,
        "total": len(payload.get("segments") or []),
        "status": meeting.status,
        "analysis": analysis_status,
    }
