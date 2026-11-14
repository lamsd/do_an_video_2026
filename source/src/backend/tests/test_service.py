from app.models import Meeting
from app.service import _apply_meeting_status, _source_retracted, _speaker_identity


def test_verified_host_is_used_only_when_provider_has_no_speaker():
    assert _speaker_identity({}, "HuynhLam") == ("fallback:huynhlam", "HuynhLam")
    assert _speaker_identity({"speaker_key": "vexa-7"}, "HuynhLam") == ("vexa-7", "HuynhLam")
    assert _speaker_identity({"speaker": "Phuong Nguyen"}, "HuynhLam") == (None, "Phuong Nguyen")


def test_unassigned_speaker_stays_empty_without_verified_fallback():
    assert _speaker_identity({}, "") == (None, None)


def test_only_explicit_provider_signals_retract_a_segment():
    assert _source_retracted({"retracted": True}) is True
    assert _source_retracted({"status": "revoked"}) is True
    assert _source_retracted({"status": "completed"}) is False
    assert _source_retracted({}) is False


def test_meeting_status_transition_is_explicit_and_idempotent():
    meeting = Meeting(status="joining")

    assert _apply_meeting_status(meeting, "awaiting_admission") == {
        "previous_status": "joining",
        "status": "awaiting_admission",
    }
    assert meeting.status == "awaiting_admission"
    assert _apply_meeting_status(meeting, "awaiting_admission") is None
    assert _apply_meeting_status(meeting, "") is None
