"""Temporary compatibility upgrades for databases created before Alembic is introduced."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_compatibility_upgrades(connection: AsyncConnection) -> None:
    """Safe additive upgrades; never drop or rewrite existing transcript data."""
    await connection.execute(
        text("ALTER TABLE IF EXISTS meetings ADD COLUMN IF NOT EXISTS transcript_revision integer NOT NULL DEFAULT 0")
    )
    await connection.execute(
        text("ALTER TABLE IF EXISTS transcript_segments ADD COLUMN IF NOT EXISTS language varchar(16)")
    )
