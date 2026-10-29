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
        text("ALTER TABLE IF EXISTS meeting_sentiment_windows ADD COLUMN IF NOT EXISTS analysis_run_id uuid")
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
