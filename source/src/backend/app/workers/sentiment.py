import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import select

from ..analysis.classifier import build_classifier
from ..config import get_settings
from ..db import SessionLocal
from ..models import AnalysisRun
from ..queue import decode_run_id
from ..repositories.analysis import execute_run

log = logging.getLogger(__name__)


async def process(run_id: UUID) -> None:
    settings = get_settings()
    classifier = build_classifier(
        settings.classifier_adapter,
        settings.sentiment_confidence_threshold,
        artifact_dir=settings.model_artifact_dir,
        artifact_sha256=settings.model_artifact_sha256,
    )
    if settings.model_version != classifier.model_version:
        raise RuntimeError(
            f"configured model version {settings.model_version!r} does not match "
            f"adapter version {classifier.model_version!r}"
        )
    async with SessionLocal() as db:
        run = await db.get(AnalysisRun, run_id)
        if run is None or run.status == "succeeded":
            return
        try:
            await execute_run(db, run=run, classifier=classifier)
            await db.commit()
        except Exception:
            await db.rollback()
            run = await db.get(AnalysisRun, run_id)
            if run:
                run.status = "failed"
                run.error_code = "worker_execution_failed"
                run.finished_at = datetime.now(UTC)
                await db.commit()
            raise


async def recover_queued_runs() -> int:
    """Recover durable jobs when Redis was unavailable at enqueue time."""
    async with SessionLocal() as db:
        run_ids = (
            await db.scalars(
                select(AnalysisRun.id)
                .where(AnalysisRun.status == "queued")
                .order_by(AnalysisRun.created_at)
                .limit(20)
            )
        ).all()
    for run_id in run_ids:
        try:
            await process(run_id)
        except Exception:
            log.exception("could not recover queued analysis run %s", run_id)
    return len(run_ids)


async def run() -> None:
    settings = get_settings()
    # xreadgroup blocks up to 5 s, so the socket timeout must be longer than that.
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=15,
        health_check_interval=30,
    )
    try:
        await redis.xgroup_create(
            settings.analysis_stream, settings.analysis_consumer_group, id="0", mkstream=True
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    consumer = "worker-1"
    try:
        while True:
            messages = await redis.xreadgroup(
                settings.analysis_consumer_group, consumer, {settings.analysis_stream: ">"}, count=4, block=5000
            )
            for _, entries in messages:
                for message_id, fields in entries:
                    try:
                        await process(UUID(decode_run_id(fields)))
                        await redis.xack(settings.analysis_stream, settings.analysis_consumer_group, message_id)
                    except Exception:
                        log.exception("analysis worker failed for message %s", message_id)
            if not messages:
                await recover_queued_runs()
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
