from datetime import UTC, datetime

from ..models import TranscriptSegment
from .contracts import UnitDraft
from .quality import evaluate_segment


def _as_datetime(epoch_seconds: float) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)


def build_units(segments: list[TranscriptSegment]) -> list[UnitDraft]:
    """Build bounded same-speaker units from finalized transcript rows."""
    units: list[UnitDraft] = []
    current: list[tuple[TranscriptSegment, str, str]] = []
    last_accepted: dict[str, tuple[str, float]] = {}

    def flush() -> None:
        if not current:
            return
        first, _, language = current[0]
        last = current[-1][0]
        text = " ".join(item[1] for item in current)
        units.append(
            UnitDraft(
                speaker_key=first.speaker_key,
                speaker_name=first.speaker_name,
                segment_ids=[item[0].vexa_segment_id for item in current],
                text=text,
                language=language,
                token_count=len(text.split()),
                start_at=_as_datetime(first.start_seconds),
                end_at=_as_datetime(last.end_seconds),
                quality_status="accepted",
                quality_reasons=[],
            )
        )
        current.clear()

    for segment in segments:
        decision = evaluate_segment(
            text=segment.text,
            upstream_language=segment.language,
            is_final=segment.is_final,
            retracted=segment.retracted,
            duration=segment.end_seconds - segment.start_seconds,
        )
        if decision.status != "accepted":
            flush()
            units.append(
                UnitDraft(
                    speaker_key=segment.speaker_key,
                    speaker_name=segment.speaker_name,
                    segment_ids=[segment.vexa_segment_id],
                    text=decision.normalized_text,
                    language=decision.language,
                    token_count=len(decision.normalized_text.split()),
                    start_at=_as_datetime(segment.start_seconds),
                    end_at=_as_datetime(segment.end_seconds),
                    quality_status=decision.status,
                    quality_reasons=decision.reasons,
                )
            )
            continue
        speaker_identity = (segment.speaker_name or segment.speaker_key or "").strip().casefold()
        previous = last_accepted.get(speaker_identity)
        if previous and previous[0] == decision.normalized_text.casefold() and segment.start_seconds - previous[1] <= 3:
            # The provider occasionally emits the same finalized phrase twice a
            # few milliseconds apart. Keep the source transcript intact, but do
            # not let a duplicate distort the sentiment aggregate.
            continue
        last_accepted[speaker_identity] = (decision.normalized_text.casefold(), segment.start_seconds)
        same_speaker = bool(current) and current[0][0].speaker_key == segment.speaker_key
        within_window = bool(current) and segment.end_seconds - current[0][0].start_seconds <= 45
        if current and (not same_speaker or not within_window or len(current) >= 3):
            flush()
        current.append((segment, decision.normalized_text, decision.language))
    flush()
    return units
