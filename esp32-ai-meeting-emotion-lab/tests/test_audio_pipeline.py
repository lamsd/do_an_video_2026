from pathlib import Path

from app.audio.pipeline import AudioPipeline
from app.config import Settings
from app.identities import AGENT_BY_ID


def test_offline_audio_fixture_is_audible_and_labelled(tmp_path: Path) -> None:
    pipeline = AudioPipeline(Settings(openai_api_key=None, media_root=tmp_path))

    artifact = pipeline.create(
        session_id="session-a",
        turn_id="turn-a",
        agent=AGENT_BY_ID["moderator"],
        text="Đây là lượt kiểm thử tín hiệu âm thanh.",
    )

    assert artifact.path.is_file()
    assert artifact.tts_backend == "synthetic-tone-placeholder"
    assert artifact.features["audibility_check"]["status"] == "passed"
    assert artifact.features["audibility_check"]["rms_energy"] > 0.0005
    assert artifact.features["audibility_check"]["peak_amplitude"] > 0.002
