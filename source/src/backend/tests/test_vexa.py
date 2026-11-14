import pytest

from app.vexa import ParsedMeeting, VexaClient, VexaError, parse_meeting_url


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
    parsed = parse_meeting_url(url)
    assert parsed.platform == "google_meet"
    assert parsed.native_meeting_id == "abc-defg-hij"


def test_google_meet_parser_rejects_markdown_link_notation():
    with pytest.raises(ValueError):
        parse_meeting_url("[https://meet.google.com/abc-defg-hij](https://meet.google.com/abc-defg-hij)")


@pytest.mark.parametrize("url", [
    "https://meet.jit.si/MeetingIntelligenceDemo",
    "https://meet.jit.si/MeetingIntelligenceDemo?config.prejoinPageEnabled=false",
])
def test_jitsi_parser_preserves_full_url_and_room(url):
    parsed = parse_meeting_url(url)
    assert parsed.platform == "jitsi"
    assert parsed.native_meeting_id == "MeetingIntelligenceDemo"
    assert parsed.meeting_url == url


@pytest.mark.asyncio
async def test_start_bot_passes_explicit_language_but_keeps_auto_detection_opt_in(monkeypatch):
    client = VexaClient("http://vexa.test", "vxa_test")
    parsed = ParsedMeeting("jitsi", "Room", "https://meet.jit.si/Room")
    payloads = []

    async def request(_method, _path, **kwargs):
        payloads.append(kwargs["json"])
        return {"id": "1", "status": "requested"}

    monkeypatch.setattr(client, "_request", request)

    await client.start_bot(parsed, "Assistant", "vi")
    await client.start_bot(parsed, "Assistant", "auto")

    assert payloads[0]["language"] == "vi"
    assert "language" not in payloads[1]
