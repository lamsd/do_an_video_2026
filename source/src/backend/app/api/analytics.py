from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import owner
from ..config import get_settings
from ..db import session
from ..models import AnalysisRun, AnalysisUnit, MeetingSentimentWindow, SentimentPrediction
from ..queue import enqueue_analysis
from ..repositories.analysis import get_or_create_run
from ..service import get_owned_meeting

router = APIRouter(prefix="/v1/meetings/{meeting_id}", tags=["analytics"])


async def _owned(db: AsyncSession, meeting_id: UUID, user: str):
    try:
        return await get_owned_meeting(db, meeting_id, user)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/analysis", status_code=202)
async def request_analysis(
    meeting_id: UUID,
    kind: str = Query(default="live", pattern="^(live|final|backfill)$"),
    db: AsyncSession = Depends(session),
    user: str = Depends(owner),
):
    meeting = await _owned(db, meeting_id, user)
    settings = get_settings()
    run = await get_or_create_run(
        db,
        meeting=meeting,
        kind=kind,
        model_version=settings.model_version,
        preprocessing_version=settings.preprocessing_version,
    )
    await db.commit()
    if run.status == "queued":
        try:
            await enqueue_analysis(run.id)
        except Exception as exc:
            # The durable queued run is retained and can be recovered by the worker scanner.
            raise HTTPException(503, "analysis queue is unavailable; job remains queued") from exc
    return {"run_id": str(run.id), "status": run.status, "source_revision": run.source_revision}


@router.get("/analysis")
async def analysis_status(
    meeting_id: UUID, db: AsyncSession = Depends(session), user: str = Depends(owner)
):
    await _owned(db, meeting_id, user)
    runs = (
        await db.scalars(
            select(AnalysisRun)
            .where(AnalysisRun.meeting_id == meeting_id)
            .order_by(AnalysisRun.created_at.desc())
            .limit(20)
        )
    ).all()
    return [
        {
            "id": str(run.id), "kind": run.kind, "status": run.status,
            "source_revision": run.source_revision, "model_version": run.model_version,
            "metrics": run.metrics, "error_code": run.error_code,
        }
        for run in runs
    ]


@router.get("/analytics/overview")
async def overview(
    meeting_id: UUID, db: AsyncSession = Depends(session), user: str = Depends(owner)
):
    await _owned(db, meeting_id, user)
    run = await db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.meeting_id == meeting_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    if run is None:
        return {"status": "not_requested", "coverage": 0, "score": None, "model_version": None}
    rows = (
        await db.scalars(
            select(MeetingSentimentWindow).where(
                MeetingSentimentWindow.meeting_id == meeting_id,
                MeetingSentimentWindow.source_revision == run.source_revision,
                MeetingSentimentWindow.scope == "meeting",
            )
        )
    ).all()
    positive = sum(row.positive_weight for row in rows)
    neutral = sum(row.neutral_weight for row in rows)
    negative = sum(row.negative_weight for row in rows)
    total = positive + neutral + negative
    score_weight = sum(row.unit_count for row in rows if row.score is not None)
    score = sum((row.score or 0) * row.unit_count for row in rows) / score_weight if score_weight else None
    return {
        "status": run.status, "source_revision": run.source_revision, "model_version": run.model_version,
        "coverage": run.metrics.get("coverage", 0), "score": score,
        "ratios": {key: value / total if total else 0 for key, value in {"positive": positive, "neutral": neutral, "negative": negative}.items()},
    }


@router.get("/analytics/timeline")
async def timeline(
    meeting_id: UUID,
    db: AsyncSession = Depends(session),
    user: str = Depends(owner),
):
    await _owned(db, meeting_id, user)
    run = await db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.meeting_id == meeting_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    if run is None:
        return []
    rows = (
        await db.scalars(
            select(MeetingSentimentWindow)
            .where(MeetingSentimentWindow.meeting_id == meeting_id, MeetingSentimentWindow.source_revision == run.source_revision, MeetingSentimentWindow.scope == "meeting")
            .order_by(MeetingSentimentWindow.window_start)
        )
    ).all()
    return [{"start": row.window_start, "end": row.window_end, "score": row.score, "coverage": row.coverage, "unit_count": row.unit_count} for row in rows]


@router.get("/analytics/units")
async def units(
    meeting_id: UUID,
    label: str | None = None,
    speaker_key: str | None = None,
    min_confidence: float = Query(default=0, ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(session),
    user: str = Depends(owner),
):
    await _owned(db, meeting_id, user)
    statement = (
        select(AnalysisUnit, SentimentPrediction)
        .outerjoin(SentimentPrediction, SentimentPrediction.analysis_unit_id == AnalysisUnit.id)
        .where(AnalysisUnit.meeting_id == meeting_id, AnalysisUnit.is_current.is_(True))
        .order_by(AnalysisUnit.start_at)
        .limit(limit)
    )
    if speaker_key:
        statement = statement.where(AnalysisUnit.speaker_key == speaker_key)
    if label:
        statement = statement.where(SentimentPrediction.label == label)
    if min_confidence:
        statement = statement.where(SentimentPrediction.confidence >= min_confidence)
    rows = (await db.execute(statement)).all()
    return [
        {"unit_id": str(unit.id), "speaker_key": unit.speaker_key, "speaker": unit.speaker_name,
         "segment_ids": unit.segment_ids, "text": unit.text, "start": unit.start_at, "end": unit.end_at,
         "quality_status": unit.quality_status, "quality_reasons": unit.quality_reasons,
         "label": prediction.label if prediction else "unknown", "confidence": prediction.confidence if prediction else 0,
         "probabilities": prediction.probabilities if prediction else {}}
        for unit, prediction in rows
    ]
