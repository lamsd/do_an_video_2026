import pytest

from app.vexa import VexaError, parse_google_meet_url


def test_vexa_error_retains_upstream_status_code():
    error = VexaError("conflict", status_code=409)
    assert error.status_code == 409


def test_google_meet_parser_rejects_markdown_link_notation():
    with pytest.raises(ValueError):
        parse_google_meet_url("[https://meet.google.com/abc-defg-hij](https://meet.google.com/abc-defg-hij)")
