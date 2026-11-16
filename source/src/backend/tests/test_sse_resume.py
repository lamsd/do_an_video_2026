from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.dialects import postgresql

from app.sse import EventCursor, event_is_after_cursor, event_query


def cursor(identifier: int, seconds: int = 0) -> EventCursor:
    return EventCursor(
        created_at=datetime(2026, 11, 16, tzinfo=UTC) + timedelta(seconds=seconds),
        event_id=UUID(int=identifier),
    )


def test_reconnect_cursor_skips_delivered_event_and_keeps_same_timestamp_successor():
    delivered = cursor(1)

    assert not event_is_after_cursor(delivered, delivered)
    assert event_is_after_cursor(cursor(2), delivered)
    assert event_is_after_cursor(cursor(1, seconds=1), delivered)


def test_event_query_applies_meeting_and_resume_cursor_filters():
    statement = event_query(UUID(int=9), cursor(1))
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "outbox_events.meeting_id" in compiled
    assert "outbox_events.created_at >" in compiled
    assert "outbox_events.id >" in compiled
