import asyncio
import hashlib
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .api.analytics import router as analytics_router
from .auth import owner
from .config import get_settings
from .db import SessionLocal, engine, session
from .models import Base, IncomingWebhook, Meeting, OutboxEvent, TranscriptSegment
from .queue import enqueue_analysis
from .repositories.analysis import get_or_create_run
from .schema_compat import apply_compatibility_upgrades
from .schemas import MeetingResponse, SegmentResponse, StartMeetingRequest
from .service import get_owned_meeting, reconcile
from .vexa import VexaClient, VexaError, parse_google_meet_url

log = logging.getLogger(__name__)


def client() -> VexaClient:
    settings = get_settings()
    if not settings.vexa_api_key:
        raise HTTPException(503, "Vexa API key is not configured")
    return VexaClient(str(settings.vexa_api_base), settings.vexa_api_key)


def meeting_response(row: Meeting) -> MeetingResponse:
    return MeetingResponse(
        id=row.id,
        vexa_meeting_id=row.vexa_meeting_id,
        platform=row.platform,
        native_meeting_id=row.native_meeting_id,
        status=row.status,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await apply_compatibility_upgrades(connection)
        await connection.run_sync(Base.metadata.create_all)
    poller = asyncio.create_task(poll_active_meetings(), name="vexa-transcript-reconciler")
    try:
        yield
    finally:
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass
    await engine.dispose()


app = FastAPI(title="Meeting Intelligence Backend", version="0.1.0", lifespan=lifespan)
app.include_router(analytics_router)


async def poll_active_meetings() -> None:
    """Near-realtime REST fallback, retained even after direct Vexa WS ingestion is added."""
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.poll_interval_seconds)
        if not settings.vexa_api_key:
            continue
        async with SessionLocal() as db:
            meetings = (
                await db.scalars(
                    select(Meeting).where(
                        Meeting.status.in_({"requested", "joining", "awaiting_admission", "active"})
                    )
                )
            ).all()
            for meeting in meetings:
                try:
                    await reconcile(db, client(), meeting)
                except VexaError:
                    # A transient Vexa or STT failure is retried in the next interval.
                    await db.rollback()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/meetings", response_model=MeetingResponse, status_code=201)
async def start_meeting(
    body: StartMeetingRequest, db: AsyncSession = Depends(session), user: str = Depends(owner)
):
    try:
        parsed = parse_google_meet_url(body.meeting_url)
        spawned = await client().start_bot(parsed, body.bot_name)
    except (ValueError, VexaError) as exc:
        raise HTTPException(502, str(exc)) from exc
    row = Meeting(
        owner_id=user,
        vexa_meeting_id=str(spawned.get("id")) if spawned.get("id") else None,
        platform=parsed.platform,
        native_meeting_id=parsed.native_meeting_id,
        status=str(spawned.get("status") or "requested"),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return meeting_response(row)


@app.get("/v1/meetings/{meeting_id}", response_model=MeetingResponse)
async def meeting_status(
    meeting_id: UUID, db: AsyncSession = Depends(session), user: str = Depends(owner)
):
    try:
        return meeting_response(await get_owned_meeting(db, meeting_id, user))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/v1/meetings/{meeting_id}/sync")
async def sync_meeting(
    meeting_id: UUID, db: AsyncSession = Depends(session), user: str = Depends(owner)
):
    try:
        meeting = await get_owned_meeting(db, meeting_id, user)
        return await reconcile(db, client(), meeting)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except VexaError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/v1/meetings/{meeting_id}/transcript", response_model=list[SegmentResponse])
async def transcript(
    meeting_id: UUID, db: AsyncSession = Depends(session), user: str = Depends(owner)
):
    try:
        await get_owned_meeting(db, meeting_id, user)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    rows = (
        await db.scalars(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.meeting_id == meeting_id, TranscriptSegment.retracted.is_(False)
            )
            .order_by(TranscriptSegment.start_seconds)
        )
    ).all()
    return [
        SegmentResponse(
            id=row.id,
            vexa_segment_id=row.vexa_segment_id,
            speaker=row.speaker_name,
            text=row.text,
            start=row.start_seconds,
            end=row.end_seconds,
            is_final=row.is_final,
            revision=row.revision,
        )
        for row in rows
    ]


@app.post("/v1/meetings/{meeting_id}/stop")
async def stop_meeting(
    meeting_id: UUID, db: AsyncSession = Depends(session), user: str = Depends(owner)
):
    try:
        meeting = await get_owned_meeting(db, meeting_id, user)
        await client().stop_bot(meeting.platform, meeting.native_meeting_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except VexaError as exc:
        raise HTTPException(502, str(exc)) from exc
    meeting.status = "stopping"
    await db.commit()
    return {"status": "stopping"}


@app.get("/v1/meetings/{meeting_id}/events")
async def events(
    meeting_id: UUID,
    request: Request,
    db: AsyncSession = Depends(session),
    user: str = Depends(owner),
):
    try:
        await get_owned_meeting(db, meeting_id, user)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    async def stream():
        sent_ids: set[str] = set()
        while not await request.is_disconnected():
            async with SessionLocal() as event_db:
                rows = (
                    await event_db.scalars(
                        select(OutboxEvent)
                        .where(OutboxEvent.meeting_id == meeting_id)
                        .order_by(OutboxEvent.created_at)
                    )
                ).all()
            for row in rows:
                event_id = str(row.id)
                if event_id in sent_ids:
                    continue
                sent_ids.add(event_id)
                body = json.dumps(
                    {
                        "event_id": str(row.id),
                        "type": row.event_type,
                        "meeting_id": str(meeting_id),
                        "data": row.payload,
                    }
                )
                yield f"id: {event_id}\nevent: {row.event_type}\ndata: {body}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")


async def finalize(vexa_meeting_id: str | None):
    if not vexa_meeting_id:
        return
    async with SessionLocal() as db:
        meeting = await db.scalar(select(Meeting).where(Meeting.vexa_meeting_id == vexa_meeting_id))
        if meeting is None:
            return
        for delay in (0, 2, 5, 10):
            if delay:
                await asyncio.sleep(delay)
            try:
                await reconcile(db, client(), meeting)
                break
            except VexaError:
                continue
        meeting.finalized_at = datetime.now(UTC)
        await db.commit()
        settings = get_settings()
        run = await get_or_create_run(
            db,
            meeting=meeting,
            kind="final",
            model_version=settings.model_version,
            preprocessing_version=settings.preprocessing_version,
        )
        await db.commit()
    if run.status == "queued":
        try:
            await enqueue_analysis(run.id)
        except (OSError, RedisError):
            # The committed run remains recoverable; do not turn a valid webhook into a 5xx.
            log.exception("could not enqueue final analysis run %s", run.id)


@app.post("/v1/webhooks/vexa", status_code=200)
async def vexa_webhook(
    request: Request,
    background: BackgroundTasks,
    x_webhook_timestamp: str = Header(default=""),
    x_webhook_signature: str = Header(default=""),
):
    settings = get_settings()
    raw = await request.body()
    if not settings.vexa_webhook_secret:
        raise HTTPException(503, "webhook receiver is not configured")
    try:
        timestamp = int(x_webhook_timestamp)
    except ValueError as exc:
        raise HTTPException(401, "invalid webhook timestamp") from exc
    if abs(time.time() - timestamp) > 300:
        raise HTTPException(401, "expired webhook timestamp")
    signed = f"{x_webhook_timestamp}.".encode() + raw
    expected = (
        "sha256="
        + hmac.new(settings.vexa_webhook_secret.encode(), signed, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(expected, x_webhook_signature):
        raise HTTPException(401, "invalid webhook signature")
    payload = json.loads(raw)
    event_id = str(payload.get("event_id") or "")
    if not event_id:
        raise HTTPException(422, "webhook event_id is required")
    async with SessionLocal() as db:
        db.add(
            IncomingWebhook(
                event_id=event_id,
                event_type=str(payload.get("event_type") or "unknown"),
                payload=payload,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return {"status": "duplicate"}
    if payload.get("event_type") in {"meeting.completed", "bot.failed"}:
        background.add_task(
            finalize, str((payload.get("data") or {}).get("meeting", {}).get("id") or "")
        )
    return {"status": "accepted"}
