from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.classifier import SentimentClassifier
from ..analysis.units import build_units
from ..models import (
    AnalysisRun,
    AnalysisUnit,
    Meeting,
    MeetingSentimentWindow,
    OutboxEvent,
    SentimentPrediction,
    TranscriptSegment,
)


async def get_or_create_run(
    db: AsyncSession,
    *,
    meeting: Meeting,
    kind: str,
    model_version: str,
    preprocessing_version: str,
) -> AnalysisRun:
    existing = await db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.meeting_id == meeting.id,
            AnalysisRun.kind == kind,
            AnalysisRun.source_revision == meeting.transcript_revision,
            AnalysisRun.model_version == model_version,
        )
    )
    if existing:
        return existing
    run = AnalysisRun(
        meeting_id=meeting.id,
        kind=kind,
        source_revision=meeting.transcript_revision,
        model_version=model_version,
        preprocessing_version=preprocessing_version,
    )
    db.add(run)
    await db.flush()
    return run


async def execute_run(
    db: AsyncSession, *, run: AnalysisRun, classifier: SentimentClassifier
) -> AnalysisRun:
    if run.status == "succeeded":
        return run
    run.status = "running"
    run.attempt += 1
    run.started_at = datetime.now(UTC)
    segments = (
        await db.scalars(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.meeting_id == run.meeting_id,
                TranscriptSegment.is_final.is_(True),
                TranscriptSegment.retracted.is_(False),
            )
            .order_by(TranscriptSegment.start_seconds)
        )
    ).all()
    await db.execute(
        update(AnalysisUnit)
        .where(AnalysisUnit.meeting_id == run.meeting_id, AnalysisUnit.is_current.is_(True))
        .values(is_current=False)
    )
    await db.execute(
        update(SentimentPrediction)
        .where(SentimentPrediction.analysis_run_id == run.id)
        .values(is_current=False)
    )
    drafts = build_units(segments)
    units: list[AnalysisUnit] = []
    inferable = []
    for draft in drafts:
        unit = AnalysisUnit(
            meeting_id=run.meeting_id,
            source_revision=run.source_revision,
            speaker_key=draft.speaker_key,
            speaker_name=draft.speaker_name,
            segment_ids=draft.segment_ids,
            text=draft.text,
            language=draft.language,
            token_count=draft.token_count,
            start_at=draft.start_at,
            end_at=draft.end_at,
            quality_status=draft.quality_status,
            quality_reasons=draft.quality_reasons,
            preprocessing_version=run.preprocessing_version,
        )
        db.add(unit)
        units.append(unit)
        if draft.quality_status == "accepted":
            inferable.append((unit, draft))
    await db.flush()
    predictions = classifier.predict([draft for _, draft in inferable])
    for (unit, _), prediction in zip(inferable, predictions, strict=True):
        db.add(
            SentimentPrediction(
                analysis_run_id=run.id,
                analysis_unit_id=unit.id,
                label=prediction.label,
                confidence=prediction.confidence,
                probabilities=prediction.probabilities,
                polarity_score=prediction.polarity_score,
                inference_ms=prediction.inference_ms,
            )
        )
    await db.flush()
    await _aggregate(db, run)
    accepted = len(inferable)
    run.metrics = {"unit_count": len(units), "accepted_unit_count": accepted, "coverage": accepted / len(units) if units else 0}
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    db.add(
        OutboxEvent(
            dedupe_key=f"analysis:{run.id}:succeeded",
            event_type="analysis.sentiment.updated",
            meeting_id=run.meeting_id,
            payload={"analysis_run_id": str(run.id), "source_revision": run.source_revision, "model_version": run.model_version},
        )
    )
    return run


async def _aggregate(db: AsyncSession, run: AnalysisRun) -> None:
    rows = (
        await db.execute(
            select(AnalysisUnit, SentimentPrediction)
            .join(SentimentPrediction, SentimentPrediction.analysis_unit_id == AnalysisUnit.id)
            .where(SentimentPrediction.analysis_run_id == run.id, SentimentPrediction.is_current.is_(True))
        )
    ).all()
    buckets: dict[tuple[datetime, str, str], list[tuple[AnalysisUnit, SentimentPrediction]]] = {}
    for unit, prediction in rows:
        start = unit.start_at.replace(second=0, microsecond=0)
        for scope, speaker_key in (("meeting", ""), ("speaker", unit.speaker_key or "")):
            buckets.setdefault((start, scope, speaker_key), []).append((unit, prediction))
    for (start, scope, speaker_key), values in buckets.items():
        weights = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
        score_total = 0.0
        score_weight = 0.0
        for unit, prediction in values:
            if prediction.label not in weights:
                continue
            weight = max(1, unit.token_count) * prediction.confidence
            weights[prediction.label] += weight
            if prediction.polarity_score is not None:
                score_total += prediction.polarity_score * weight
                score_weight += weight
        db.add(
            MeetingSentimentWindow(
                meeting_id=run.meeting_id,
                source_revision=run.source_revision,
                scope=scope,
                speaker_key=speaker_key,
                window_start=start,
                window_end=start + timedelta(minutes=1),
                positive_weight=weights["positive"],
                neutral_weight=weights["neutral"],
                negative_weight=weights["negative"],
                score=score_total / score_weight if score_weight else None,
                coverage=sum(1 for _, prediction in values if prediction.label != "unknown") / len(values),
                unit_count=len(values),
            )
        )
