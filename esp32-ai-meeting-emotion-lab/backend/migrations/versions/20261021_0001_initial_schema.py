"""Create the initial experiment, turn, and device-status schema."""

import sqlalchemy as sa
from alembic import op

revision = "20261021_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("requested_rounds", sa.Integer(), nullable=False),
        sa.Column("completed_rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_agent_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="waiting_for_devices"),
        sa.Column("active_turn_token", sa.String(length=36), nullable=True),
        sa.Column("active_turn_id", sa.String(length=36), nullable=True),
        sa.Column("active_sequence_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("active_turn_token"),
    )
    op.create_table(
        "device_status",
        sa.Column("agent_id", sa.String(length=32), nullable=False),
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False, server_default="disconnected"),
        sa.Column("mqtt_client_id", sa.String(length=96), nullable=True),
        sa.Column("firmware_version", sa.String(length=32), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("agent_id"),
        sa.UniqueConstraint("device_id"),
    )
    op.create_table(
        "experiment_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=32), nullable=False),
        sa.Column("turn_token", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("voice", sa.String(length=32), nullable=False),
        sa.Column("audio_file_path", sa.Text(), nullable=True),
        sa.Column("acoustic_metadata", sa.JSON(), nullable=True),
        sa.Column("emotion_prediction", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["experiment_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_token"),
    )
    op.create_index("ix_experiment_turns_session_id", "experiment_turns", ["session_id"])
    op.create_index("ix_experiment_turns_agent_id", "experiment_turns", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_experiment_turns_agent_id", table_name="experiment_turns")
    op.drop_index("ix_experiment_turns_session_id", table_name="experiment_turns")
    op.drop_table("experiment_turns")
    op.drop_table("device_status")
    op.drop_table("experiment_sessions")
