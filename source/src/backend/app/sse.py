"""Small, testable helpers for resumable meeting SSE streams."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from .models import OutboxEvent


@dataclass(frozen=True)
class EventCursor:
    created_at: datetime
    event_id: UUID


def cursor_for(event: OutboxEvent) -> EventCursor:
    return EventCursor(created_at=event.created_at, event_id=event.id)


def event_is_after_cursor(event: EventCursor, cursor: EventCursor) -> bool:
    """Use a UUID tie-breaker so equal database timestamps remain deterministic."""
    return (event.created_at, event.event_id) > (cursor.created_at, cursor.event_id)


def event_query(meeting_id: UUID, cursor: EventCursor | None):
    statement = select(OutboxEvent).where(OutboxEvent.meeting_id == meeting_id)
    if cursor is not None:
        statement = statement.where(
            or_(
                OutboxEvent.created_at > cursor.created_at,
                and_(
                    OutboxEvent.created_at == cursor.created_at,
                    OutboxEvent.id > cursor.event_id,
                ),
            )
        )
    return statement.order_by(OutboxEvent.created_at, OutboxEvent.id)
