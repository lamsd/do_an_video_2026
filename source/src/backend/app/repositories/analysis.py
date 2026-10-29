from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy import select
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


def run_metrics(
    *, total_units: int, accepted_units: int, predicted_units: int, inference_total_ms: int
) -> dict[str, float | int]:
    """Keep data acceptance distinct from usable model output.

    ``coverage`` is retained as a backwards-compatible alias for prediction
    coverage. New API clients should use the explicit metric names.
    """
    acceptance_rate = accepted_units / total_units if total_units else 0
    prediction_coverage = predicted_units / accepted_units if accepted_units else 0
    effective_coverage = predicted_units / total_units if total_units else 0
    return {
        "unit_count": total_units,
        "accepted_unit_count": accepted_units,
        "predicted_unit_count": predicted_units,
        "acceptance_rate": acceptance_rate,
        "prediction_coverage": prediction_coverage,
        "effective_coverage": effective_coverage,
        "coverage": prediction_coverage,
        # This is an end-to-end classifier batch duration, not a fabricated
        # per-unit percentile.  P50/P95 must come from repeated benchmark runs.
        "inference_total_ms": inference_total_ms,
    }


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
    drafts = build_units(segments)
    units: list[AnalysisUnit] = []
    inferable = []
    for draft in drafts:
        unit = AnalysisUnit(
            analysis_run_id=run.id,
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
    inference_started = perf_counter()
    predictions = classifier.predict([draft for _, draft in inferable])
    inference_total_ms = int((perf_counter() - inference_started) * 1000)
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
    predicted = sum(prediction.label != "unknown" for prediction in predictions)
    run.metrics = run_metrics(
        total_units=len(units),
        accepted_units=accepted,
        predicted_units=predicted,
        inference_total_ms=inference_total_ms,
    )
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
            # Baseline confidence is not calibrated and unit length does not
            # establish sentiment importance. Use count-based aggregation until
            # a calibrated model and a validated weighting policy exist.
            weight = 1.0
            weights[prediction.label] += weight
            if prediction.polarity_score is not None:
                score_total += prediction.polarity_score * weight
                score_weight += weight
        db.add(
            MeetingSentimentWindow(
                analysis_run_id=run.id,
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
