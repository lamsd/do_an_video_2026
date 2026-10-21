from app.service import _speaker_identity


def test_verified_host_is_used_only_when_provider_has_no_speaker():
    assert _speaker_identity({}, "HuynhLam") == ("fallback:huynhlam", "HuynhLam")
    assert _speaker_identity({"speaker_key": "vexa-7"}, "HuynhLam") == ("vexa-7", "HuynhLam")
    assert _speaker_identity({"speaker": "Phuong Nguyen"}, "HuynhLam") == (None, "Phuong Nguyen")


def test_unassigned_speaker_stays_empty_without_verified_fallback():
    assert _speaker_identity({}, "") == (None, None)
