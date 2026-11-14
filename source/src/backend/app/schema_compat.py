"""Temporary compatibility upgrades for databases created before Alembic is introduced."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_compatibility_upgrades(connection: AsyncConnection) -> None:
    """Safe compatibility upgrades; never rewrite existing transcript data."""
    await connection.execute(
        text("ALTER TABLE IF EXISTS meetings ADD COLUMN IF NOT EXISTS transcript_revision integer NOT NULL DEFAULT 0")
    )
    await connection.execute(
        text("ALTER TABLE IF EXISTS transcript_segments ADD COLUMN IF NOT EXISTS language varchar(16)")
    )
    # Before experiment support, aggregates were unique only by meeting
    # revision.  A second model on the same revision therefore conflicted with
    # the first one, and old units could not be tied to their producing run.
    # Existing rows are deliberately left unlinked rather than guessed at;
    # rerunning creates fully traceable records without altering transcript
    # history.  The old uniqueness constraint is replaced, not data-deleted.
    await connection.execute(
        text("ALTER TABLE IF EXISTS analysis_units ADD COLUMN IF NOT EXISTS analysis_run_id uuid")
    )
    await connection.execute(
        text("ALTER TABLE IF EXISTS analysis_units ADD COLUMN IF NOT EXISTS language_source varchar(64)")
    )
    await connection.execute(
        text("ALTER TABLE IF EXISTS meeting_sentiment_windows ADD COLUMN IF NOT EXISTS analysis_run_id uuid")
    )
    await connection.execute(
        text("ALTER TABLE IF EXISTS analysis_runs ADD COLUMN IF NOT EXISTS source_fingerprint varchar(64)")
    )
    await connection.execute(
        text("ALTER TABLE IF EXISTS analysis_runs ADD COLUMN IF NOT EXISTS input_segment_count integer NOT NULL DEFAULT 0")
    )
    await connection.execute(
        text("ALTER TABLE IF EXISTS analysis_runs ADD COLUMN IF NOT EXISTS input_snapshot_at timestamptz")
    )
    await connection.execute(
        text("ALTER TABLE IF EXISTS sentiment_predictions ADD COLUMN IF NOT EXISTS abstention_reason varchar(128)")
    )
    # A preprocessing change (for example, different language routing or unit
    # boundaries) changes the meaning of an analysis run.  Older databases
    # identified a run only by source revision and model version, so replace
    # that legacy uniqueness rule without touching historical rows.
    await connection.execute(
        text(
            "DO $$ BEGIN "
            "IF to_regclass('analysis_runs') IS NOT NULL THEN "
            "IF EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conrelid = 'analysis_runs'::regclass "
            "AND conname = 'uq_analysis_run' "
            "AND pg_get_constraintdef(oid) NOT LIKE '%preprocessing_version%') THEN "
            "ALTER TABLE analysis_runs DROP CONSTRAINT uq_analysis_run; "
            "END IF; "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conrelid = 'analysis_runs'::regclass "
            "AND contype = 'u' "
            "AND pg_get_constraintdef(oid) LIKE '%preprocessing_version%') THEN "
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_run_versioned "
            "ON analysis_runs (meeting_id, kind, source_revision, model_version, preprocessing_version); "
            "END IF; "
            "END IF; END $$;"
        )
    )
    await connection.execute(
        text(
            "DO $$ BEGIN "
            "IF to_regclass('meeting_sentiment_windows') IS NOT NULL THEN "
            "ALTER TABLE meeting_sentiment_windows DROP CONSTRAINT IF EXISTS uq_window; "
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_window_run "
            "ON meeting_sentiment_windows (analysis_run_id, scope, speaker_key, window_start); "
            "END IF; END $$;"
        )
    )
