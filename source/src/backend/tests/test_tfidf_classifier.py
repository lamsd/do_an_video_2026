import hashlib
import json
from datetime import UTC, datetime

import joblib
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.analysis.classifier import TfidfLogisticRegressionClassifier, build_classifier
from app.analysis.contracts import UnitDraft


def unit(text: str, language: str = "vi") -> UnitDraft:
    return UnitDraft(
        speaker_key="speaker-a",
        speaker_name="Test speaker",
        segment_ids=["segment-a"],
        text=text,
        language=language,
        token_count=len(text.split()),
        start_at=datetime.now(UTC),
        end_at=datetime.now(UTC),
        quality_status="accepted",
        quality_reasons=[],
    )


def artifact(tmp_path):
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer()),
            ("classifier", LogisticRegression(max_iter=1_000, random_state=42)),
        ]
    )
    pipeline.fit(
        [
            "dịch vụ rất tệ", "gặp lỗi khó chịu", "nội dung bình thường", "cuộc họp ổn định",
            "cảm ơn hỗ trợ tốt", "tôi rất hài lòng",
        ],
        ["negative", "negative", "neutral", "neutral", "positive", "positive"],
    )
    model_path = tmp_path / "model.joblib"
    joblib.dump(
        {
            "schema_version": 1,
            "model_type": "tfidf-logreg",
            "model_version": "tfidf-logreg-test-v1",
            "labels": ["negative", "neutral", "positive"],
            "pipeline": pipeline,
        },
        model_path,
    )
    artifact_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_type": "tfidf-logreg",
                "model_version": "tfidf-logreg-test-v1",
                "artifact_sha256": artifact_hash,
            }
        ),
        encoding="utf-8",
    )
    return artifact_hash


def test_tfidf_adapter_returns_contract_predictions(tmp_path):
    artifact_hash = artifact(tmp_path)
    classifier = build_classifier(
        "tfidf-logreg", 0, artifact_dir=str(tmp_path), artifact_sha256=artifact_hash
    )
    assert isinstance(classifier, TfidfLogisticRegressionClassifier)
    predictions = classifier.predict([unit("cảm ơn dịch vụ rất tốt"), unit("hello world", "en")])
    assert predictions[0].label in {"negative", "neutral", "positive"}
    assert set(predictions[0].probabilities) == {"negative", "neutral", "positive"}
    assert sum(predictions[0].probabilities.values()) == pytest.approx(1)
    assert predictions[1].label == "unknown"
    assert predictions[1].confidence == 0


def test_tfidf_adapter_rejects_unverified_artifact(tmp_path):
    artifact(tmp_path)
    with pytest.raises(ValueError, match="SHA-256"):
        build_classifier("tfidf-logreg", 0.6, artifact_dir=str(tmp_path), artifact_sha256="bad")
