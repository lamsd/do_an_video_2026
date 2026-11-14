from sqlalchemy import UniqueConstraint

from app.models import AnalysisRun
from app.repositories.analysis import snapshot_fingerprint


def payload(text: str, revision: int = 1) -> dict:
    return {
        "source_segment_id": "00000000-0000-0000-0000-000000000001",
        "vexa_segment_id": "segment-1",
        "source_segment_revision": revision,
        "speaker_key": "speaker-1",
        "speaker_name": "Demo speaker",
        "language": "vi",
        "text": text,
        "start_seconds": 10.0,
        "end_seconds": 12.0,
        "is_final": True,
        "retracted": False,
    }


def test_snapshot_fingerprint_is_stable_for_identical_input():
    assert snapshot_fingerprint([payload("Nội dung gốc")]) == snapshot_fingerprint(
        [payload("Nội dung gốc")]
    )


def test_snapshot_fingerprint_changes_when_source_revision_or_text_changes():
    original = snapshot_fingerprint([payload("Nội dung gốc")])

    assert original != snapshot_fingerprint([payload("Nội dung đã sửa")])
    assert original != snapshot_fingerprint([payload("Nội dung gốc", revision=2)])


def test_run_identity_includes_preprocessing_version():
    identities = {
        tuple(column.name for column in constraint.columns)
        for constraint in AnalysisRun.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert (
        "meeting_id",
        "kind",
        "source_revision",
        "model_version",
        "preprocessing_version",
    ) in identities
