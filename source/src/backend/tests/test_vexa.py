import pytest

from app.vexa import VexaError, parse_google_meet_url


def test_vexa_error_retains_upstream_status_code():
    error = VexaError("conflict", status_code=409)
    assert error.status_code == 409


@pytest.mark.parametrize(
    "url",
    [
        "https://meet.google.com/abc-defg-hij",
        "https://meet.google.com/meet/abc-defg-hij",
    ],
)
def test_google_meet_parser_accepts_direct_and_meet_prefixed_urls(url):
    parsed = parse_google_meet_url(url)
    assert parsed.platform == "google_meet"
    assert parsed.native_meeting_id == "abc-defg-hij"


def test_google_meet_parser_rejects_markdown_link_notation():
    with pytest.raises(ValueError):
        parse_google_meet_url("[https://meet.google.com/abc-defg-hij](https://meet.google.com/abc-defg-hij)")
