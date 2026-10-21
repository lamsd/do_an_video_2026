from app.config import Settings
from app.emotion.classifier import AudioEmotionClassifier


def test_classifier_abstains_without_evaluated_checkpoint() -> None:
    prediction = AudioEmotionClassifier(Settings()).predict({"rms_energy": 0.02})
    assert prediction["status"] == "unavailable"
    assert prediction["label"] == "unknown"
    assert "depression" in prediction["reason"]

