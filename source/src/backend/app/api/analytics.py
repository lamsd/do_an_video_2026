from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
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


async def _run_for_view(
    db: AsyncSession, meeting_id: UUID, run_id: UUID | None
) -> AnalysisRun | None:
    """Resolve one run within its meeting; never mix evidence across models."""
    statement = select(AnalysisRun).where(AnalysisRun.meeting_id == meeting_id)
    if run_id is not None:
        statement = statement.where(AnalysisRun.id == run_id)
    statement = statement.order_by(AnalysisRun.created_at.desc())
    run = await db.scalar(statement)
    if run_id is not None and run is None:
        raise HTTPException(404, "analysis run not found")
    return run


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
            "preprocessing_version": run.preprocessing_version, "metrics": run.metrics,
            "error_code": run.error_code, "created_at": run.created_at,
            "finished_at": run.finished_at,
        }
        for run in runs
    ]


@router.get("/analytics/overview")
async def overview(
    meeting_id: UUID,
    run_id: UUID | None = None,
    db: AsyncSession = Depends(session),
    user: str = Depends(owner),
):
    await _owned(db, meeting_id, user)
    run = await _run_for_view(db, meeting_id, run_id)
    if run is None:
        return {
            "status": "not_requested", "coverage": 0, "score": None,
            "model_version": None, "run_id": None, "metrics": {},
        }
    rows = (
        await db.scalars(
            select(MeetingSentimentWindow).where(
                MeetingSentimentWindow.analysis_run_id == run.id,
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
        "run_id": str(run.id), "status": run.status,
        "source_revision": run.source_revision, "model_version": run.model_version,
        "preprocessing_version": run.preprocessing_version,
        "metrics": run.metrics,
        "coverage": run.metrics.get("coverage", 0), "score": score,
        "ratios": {key: value / total if total else 0 for key, value in {"positive": positive, "neutral": neutral, "negative": negative}.items()},
    }


@router.get("/analytics/timeline")
async def timeline(
    meeting_id: UUID,
    run_id: UUID | None = None,
    db: AsyncSession = Depends(session),
    user: str = Depends(owner),
):
    await _owned(db, meeting_id, user)
    run = await _run_for_view(db, meeting_id, run_id)
    if run is None:
        return []
    rows = (
        await db.scalars(
            select(MeetingSentimentWindow)
            .where(
                MeetingSentimentWindow.analysis_run_id == run.id,
                MeetingSentimentWindow.scope == "meeting",
            )
            .order_by(MeetingSentimentWindow.window_start)
        )
    ).all()
    return [{"start": row.window_start, "end": row.window_end, "score": row.score, "coverage": row.coverage, "unit_count": row.unit_count} for row in rows]


@router.get("/analytics/speakers")
async def speakers(
    meeting_id: UUID,
    run_id: UUID | None = None,
    db: AsyncSession = Depends(session),
    user: str = Depends(owner),
):
    """Return an independent sentiment summary for each transcript speaker."""
    await _owned(db, meeting_id, user)
    run = await _run_for_view(db, meeting_id, run_id)
    if run is None:
        return []

    windows = (
        await db.scalars(
            select(MeetingSentimentWindow)
            .where(
                MeetingSentimentWindow.analysis_run_id == run.id,
                MeetingSentimentWindow.scope == "speaker",
            )
            .order_by(MeetingSentimentWindow.speaker_key, MeetingSentimentWindow.window_start)
        )
    ).all()
    names = {
        key or "": name
        for key, name in (
            await db.execute(
                select(AnalysisUnit.speaker_key, AnalysisUnit.speaker_name)
                .where(
                    AnalysisUnit.analysis_run_id == run.id,
                )
            )
        ).all()
        if name
    }
    grouped: dict[str, dict] = {}
    for window in windows:
        source_key = window.speaker_key or ""
        speaker = " ".join((names.get(source_key) or "").split())
        # Vexa may rotate diarization keys during one meeting. A supplied name
        # is the stable display identity, so merge its windows into one person.
        identity = f"name:{speaker.casefold()}" if speaker else f"key:{source_key or 'unassigned'}"
        group = grouped.setdefault(
            identity,
            {"speaker": speaker or "Chưa gán speaker", "speaker_keys": set(), "rows": []},
        )
        group["speaker_keys"].add(source_key)
        group["rows"].append(window)

    summaries = []
    for group in grouped.values():
        rows = group["rows"]
        positive = sum(row.positive_weight for row in rows)
        neutral = sum(row.neutral_weight for row in rows)
        negative = sum(row.negative_weight for row in rows)
        total = positive + neutral + negative
        score_weight = sum(row.unit_count for row in rows if row.score is not None)
        unit_count = sum(row.unit_count for row in rows)
        coverage_weight = sum(row.coverage * row.unit_count for row in rows)
        summaries.append(
            {
                "speaker_key": next(iter(group["speaker_keys"]), "") or None,
                "speaker": group["speaker"],
                "unit_count": unit_count,
                "coverage": coverage_weight / unit_count if unit_count else 0,
                "score": sum((row.score or 0) * row.unit_count for row in rows) / score_weight if score_weight else None,
                "ratios": {
                    key: value / total if total else 0
                    for key, value in {"positive": positive, "neutral": neutral, "negative": negative}.items()
                },
            }
        )
    return sorted(summaries, key=lambda item: (-item["unit_count"], item["speaker"]))


@router.get("/analytics/units")
async def units(
    meeting_id: UUID,
    run_id: UUID | None = None,
    label: str | None = None,
    speaker_key: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    min_confidence: float = Query(default=0, ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(session),
    user: str = Depends(owner),
):
    await _owned(db, meeting_id, user)
    run = await _run_for_view(db, meeting_id, run_id)
    if run is None:
        return []
    if window_start and window_end and window_start >= window_end:
        raise HTTPException(422, "window_start must be earlier than window_end")
    statement = (
        select(AnalysisUnit, SentimentPrediction)
        .outerjoin(
            SentimentPrediction,
            and_(
                SentimentPrediction.analysis_unit_id == AnalysisUnit.id,
                SentimentPrediction.analysis_run_id == run.id,
            ),
        )
        .where(AnalysisUnit.analysis_run_id == run.id)
        .order_by(AnalysisUnit.start_at)
    )
    if speaker_key:
        statement = statement.where(AnalysisUnit.speaker_key == speaker_key)
    if label:
        if label == "unknown":
            statement = statement.where(
                or_(SentimentPrediction.label == "unknown", SentimentPrediction.id.is_(None))
            )
        else:
            statement = statement.where(SentimentPrediction.label == label)
    if min_confidence:
        statement = statement.where(SentimentPrediction.confidence >= min_confidence)
    if window_start:
        statement = statement.where(AnalysisUnit.start_at >= window_start)
    if window_end:
        statement = statement.where(AnalysisUnit.start_at < window_end)
    statement = statement.offset(offset).limit(limit)
    rows = (await db.execute(statement)).all()
    return [
        {"run_id": str(run.id), "unit_id": str(unit.id), "speaker_key": unit.speaker_key, "speaker": unit.speaker_name,
         "segment_ids": unit.segment_ids, "text": unit.text, "start": unit.start_at, "end": unit.end_at,
         "quality_status": unit.quality_status, "quality_reasons": unit.quality_reasons,
         "label": prediction.label if prediction else "unknown", "confidence": prediction.confidence if prediction else 0,
         "probabilities": prediction.probabilities if prediction else {}}
        for unit, prediction in rows
    ]
