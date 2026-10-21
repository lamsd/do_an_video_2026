from pathlib import Path

from app.agents.profiles import AGENT_PROFILES
from app.audio.analysis import AcousticAnalyzer
from app.audio.synthesis import SpeechSynthesizer
from app.config import Settings


def test_placeholder_audio_has_versioned_features(tmp_path: Path) -> None:
    settings = Settings(media_root=tmp_path)
    synthesizer = SpeechSynthesizer(settings)
    # Exercise the deterministic placeholder writer directly; no network or API key.
    output = tmp_path / "sample.wav"
    synthesizer._write_labelled_placeholder_tone(output, AGENT_PROFILES[0], "A concise test turn.")
    features = AcousticAnalyzer().extract(output)
    assert features["duration_seconds"] > 0
    assert features["sample_rate"] == 24_000
    assert features["version"].startswith("acoustic-v1")

