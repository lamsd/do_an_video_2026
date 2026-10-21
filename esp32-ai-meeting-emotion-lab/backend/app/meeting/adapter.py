from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from app.identities import AgentIdentity


@dataclass(frozen=True)
class VirtualParticipant:
    agent_id: str
    display_name: str
    voice: str
    audio_path: Path


ConnectionState = Literal["new", "connected", "joined", "closed", "failed"]


class MeetingAdapter(Protocol):
    """Contract for a media-capable, consent-aware meeting transport.

    An implementation owns transport credentials and raw media tracks.  It is deliberately
    separate from the browser-facing Jitsi IFrame API, which cannot publish raw bot audio.
    """

    def connect(self) -> None: ...

    def join_room(self, room: str, participant: VirtualParticipant) -> None: ...

    def leave_room(self, agent_id: str) -> None: ...

    def list_participants(self) -> list[VirtualParticipant]: ...

    def subscribe_audio(self, agent_id: str) -> None: ...

    def publish_audio(self, agent_id: str, wav_path: Path) -> None: ...

    def get_connection_state(self) -> ConnectionState: ...

    def close(self) -> None: ...


class InMemoryMeetingAdapter:
    """Test double; it records identities and audio hand-offs without joining Jitsi."""

    def __init__(self) -> None:
        self._state: ConnectionState = "new"
        self._participants: dict[str, VirtualParticipant] = {}
        self.published_audio: list[tuple[str, Path]] = []
        self.subscriptions: list[str] = []

    def connect(self) -> None:
        self._state = "connected"

    def join_room(self, _room: str, participant: VirtualParticipant) -> None:
        if self._state not in {"connected", "joined"}:
            raise RuntimeError("Adapter must connect before participants join")
        self._participants[participant.agent_id] = participant
        self._state = "joined"

    def leave_room(self, agent_id: str) -> None:
        self._participants.pop(agent_id, None)

    def list_participants(self) -> list[VirtualParticipant]:
        return list(self._participants.values())

    def subscribe_audio(self, agent_id: str) -> None:
        if agent_id not in self._participants:
            raise KeyError(agent_id)
        self.subscriptions.append(agent_id)

    def publish_audio(self, agent_id: str, wav_path: Path) -> None:
        if agent_id not in self._participants:
            raise KeyError(agent_id)
        self.published_audio.append((agent_id, wav_path))

    def get_connection_state(self) -> ConnectionState:
        return self._state

    def close(self) -> None:
        self._participants.clear()
        self._state = "closed"


def participant_for(agent: AgentIdentity, audio_path: Path) -> VirtualParticipant:
    return VirtualParticipant(
        agent_id=agent.agent_id,
        display_name=f"AI Bot · {agent.display_name}",
        voice=agent.voice,
        audio_path=audio_path,
    )

