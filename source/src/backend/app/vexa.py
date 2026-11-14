import re
from dataclasses import dataclass

import httpx

GOOGLE_MEET_CODE = re.compile(
    r"^https?://meet\.google\.com/(?:meet/)?([a-z]{3}-[a-z]{4}-[a-z]{3})(?:[/?#].*)?$", re.IGNORECASE
)
JITSI_MEET_ROOM = re.compile(
    r"^https://meet\.jit\.si/([^/?#\s]+?)/?(?:[?#].*)?$", re.IGNORECASE
)


class VexaError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ParsedMeeting:
    platform: str
    native_meeting_id: str
    # A Jitsi room is scoped to its deployment host. Vexa therefore needs the
    # full URL instead of constructing one from the room name alone.
    meeting_url: str | None = None


def parse_meeting_url(url: str) -> ParsedMeeting:
    """Parse supported links while retaining the full Jitsi deployment URL."""
    normalized = url.strip()
    google = GOOGLE_MEET_CODE.match(normalized)
    if google:
        return ParsedMeeting(platform="google_meet", native_meeting_id=google.group(1).lower())

    jitsi = JITSI_MEET_ROOM.match(normalized)
    if jitsi:
        return ParsedMeeting(
            platform="jitsi",
            native_meeting_id=jitsi.group(1),
            meeting_url=normalized,
        )

    raise ValueError("meeting_url must be a Jitsi Meet URL such as https://meet.jit.si/MyRoom")


class VexaClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=3)) as client:
            response = await client.request(
                method, f"{self.base_url}{path}", headers=self.headers, **kwargs
            )
        if response.is_error:
            raise VexaError(
                f"Vexa {method} {path} returned {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )
        return response.json()

    async def start_bot(
        self, parsed: ParsedMeeting, bot_name: str, transcription_language: str = "vi"
    ) -> dict:
        payload = {
            "platform": parsed.platform,
            "native_meeting_id": parsed.native_meeting_id,
            "bot_name": bot_name,
            "transcribe_enabled": True,
            "recording_enabled": False,
        }
        if parsed.meeting_url:
            payload["meeting_url"] = parsed.meeting_url
        # Passing an explicit language prevents a short Vietnamese utterance
        # from being repeatedly auto-detected as an unrelated language.  Do
        # not send ``auto``: Vexa omits the form field in that case, which is
        # how its Whisper client requests language detection.
        if transcription_language != "auto":
            payload["language"] = transcription_language
        return await self._request(
            "POST",
            "/bots",
            json=payload,
        )

    async def transcript(self, platform: str, native_id: str) -> dict:
        return await self._request("GET", f"/transcripts/{platform}/{native_id}")

    async def stop_bot(self, platform: str, native_id: str) -> dict:
        return await self._request("DELETE", f"/bots/{platform}/{native_id}")
