from datetime import UTC, datetime

from app.analysis.classifier import RuleBaselineClassifier
from app.analysis.contracts import UnitDraft


def draft(text: str, *, language: str = "vi") -> UnitDraft:
    return UnitDraft(
        speaker_key="speaker-1",
        speaker_name="Speaker 1",
        segment_ids=["segment-1"],
        text=text,
        language=language,
        token_count=len(text.split()),
        start_at=datetime.now(UTC),
        end_at=datetime.now(UTC),
        quality_status="accepted",
        quality_reasons=[],
    )


def test_baseline_v3_keeps_unknown_as_an_abstention():
    classifier = RuleBaselineClassifier(confidence_threshold=0.6)
    prediction = classifier.predict([draft("hello", language="en")])[0]
    assert classifier.model_version == "baseline-rules-v3"
    assert prediction.label == "unknown"
    assert prediction.label != "neutral"


def test_classifier_adapter_contract_returns_one_prediction_per_unit():
    classifier = RuleBaselineClassifier(confidence_threshold=0.6)
    predictions = classifier.predict([draft("Cảm ơn, mọi việc rất tốt"), draft("Kết quả thật tệ")])
    assert [item.label for item in predictions] == ["positive", "negative"]
