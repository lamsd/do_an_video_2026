from datetime import UTC, datetime

from app.analysis.classifier import RuleBaselineClassifier
from app.analysis.contracts import UnitDraft


def _unit(text: str, language: str) -> UnitDraft:
    now = datetime.now(UTC)
    return UnitDraft(
        speaker_key="speaker",
        speaker_name="Speaker",
        segment_ids=["segment"],
        text=text,
        language=language,
        language_source="test",
        token_count=len(text.split()),
        start_at=now,
        end_at=now,
        quality_status="accepted",
        quality_reasons=[],
    )


def test_rules_v3_supports_vietnamese_and_english_meeting_signals():
    classifier = RuleBaselineClassifier(0.6)
    vietnamese, english = classifier.predict([
        _unit("Cảm ơn, kết quả rất tốt", "vi"),
        _unit("I am very angry about this issue", "en"),
    ])

    assert classifier.model_version == "baseline-rules-v3"
    assert classifier.supported_languages == ("vi", "en")
    assert vietnamese.label == "positive"
    assert english.label == "negative"


def test_rules_v3_still_abstains_for_unsupported_language():
    prediction = RuleBaselineClassifier(0.6).predict([_unit("नमस्ते दुनिया", "hi")])[0]

    assert prediction.label == "unknown"
    assert prediction.abstention_reason == "unsupported_language"
