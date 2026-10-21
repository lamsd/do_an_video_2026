from pathlib import Path

from app.integrations.jitsi import JitsiPlaybackRequest, JitsiVirtualAudioAdapter


def test_jitsi_adapter_only_accepts_existing_wav(tmp_path: Path) -> None:
    wav = tmp_path / "turn.wav"
    wav.write_bytes(b"RIFF")
    command = JitsiVirtualAudioAdapter(Path("scripts/play_audio_to_jitsi.sh")).command_for(
        JitsiPlaybackRequest(session_id="session", turn_id="turn", wav_path=wav)
    )
    assert command[-1] == str(wav.resolve())

