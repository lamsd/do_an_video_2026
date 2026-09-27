from app.analysis.units import build_units
from app.models import TranscriptSegment


def segment(identifier: str, start: float, text: str, *, speaker: str = "ch-0") -> TranscriptSegment:
    return TranscriptSegment(
        vexa_segment_id=identifier,
        speaker_key=speaker,
        speaker_name="Test Speaker",
        language="vi",
        text=text,
        start_seconds=start,
        end_seconds=start + 2,
        is_final=True,
        retracted=False,
    )


def test_builder_groups_adjacent_final_segments_from_same_speaker():
    units = build_units(
        [
            segment("one", 1_700_000_000, "Bạn là ai vậy"),
            segment("two", 1_700_000_003, "bạn đến từ đâu"),
            segment("three", 1_700_000_006, "tôi cần thông tin"),
        ]
    )
    assert len(units) == 1
    assert units[0].segment_ids == ["one", "two", "three"]
    assert units[0].quality_status == "accepted"


def test_builder_keeps_hallucination_as_non_inferable_evidence():
    units = build_units(
        [
            segment("noise", 1_700_000_000, "Hãy subscribe cho kênh La La School"),
        ]
    )
    assert len(units) == 1
    assert units[0].quality_status == "rejected"
    assert "known_hallucination" in units[0].quality_reasons
