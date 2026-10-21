from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JitsiPlaybackRequest:
    """A host-side virtual-microphone playback request, never a participant stream."""

    session_id: str
    turn_id: str
    wav_path: Path


class JitsiVirtualAudioAdapter:
    """Builds safe requests for the Ubuntu host playback script.

    The web process does not run PulseAudio commands: its container is not the
    desktop audio session that owns the selected Jitsi input device. An operator
    or trusted host-side runner invokes the returned command instead.
    """

    def __init__(self, playback_script: Path):
        self.playback_script = playback_script

    def command_for(self, request: JitsiPlaybackRequest) -> list[str]:
        path = request.wav_path.resolve()
        if path.suffix.lower() != ".wav" or not path.is_file():
            raise ValueError("Jitsi virtual-audio playback requires an existing WAV artifact")
        return [str(self.playback_script), str(path)]

