import re
from dataclasses import dataclass

import httpx

MEET_CODE = re.compile(
    r"^https?://meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})(?:[/?#].*)?$", re.IGNORECASE
)


class VexaError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ParsedMeeting:
    platform: str
    native_meeting_id: str


def parse_google_meet_url(url: str) -> ParsedMeeting:
    match = MEET_CODE.match(url.strip())
    if not match:
        raise ValueError(
            "meeting_url must be a Google Meet URL such as https://meet.google.com/abc-defg-hij"
        )
    return ParsedMeeting(platform="google_meet", native_meeting_id=match.group(1).lower())


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

    async def start_bot(self, parsed: ParsedMeeting, bot_name: str) -> dict:
        return await self._request(
            "POST",
            "/bots",
            json={
                "platform": parsed.platform,
                "native_meeting_id": parsed.native_meeting_id,
                "bot_name": bot_name,
                "transcribe_enabled": True,
                "recording_enabled": False,
            },
        )

    async def transcript(self, platform: str, native_id: str) -> dict:
        return await self._request("GET", f"/transcripts/{platform}/{native_id}")

    async def stop_bot(self, platform: str, native_id: str) -> dict:
        return await self._request("DELETE", f"/bots/{platform}/{native_id}")
