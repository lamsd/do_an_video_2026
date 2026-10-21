import hashlib
import time
from pathlib import Path
from typing import Protocol

import joblib

from .contracts import Prediction, UnitDraft


class SentimentClassifier(Protocol):
    model_version: str

    def predict(self, units: list[UnitDraft]) -> list[Prediction]: ...


class RuleBaselineClassifier:
    """Deterministic safety baseline; replace through the SentimentClassifier protocol."""

    # v2 adds stricter transcript-quality filtering and duplicate suppression.
    model_version = "baseline-rules-v2"
    positive_markers = ("yêu", "thương", "cảm ơn", "tốt", "vui", "happy", "love")
    negative_markers = ("vang", "không được", "lỗi", "khó", "tệ", "bực", "frustrat")

    def __init__(self, confidence_threshold: float):
        self.confidence_threshold = confidence_threshold

    def predict(self, units: list[UnitDraft]) -> list[Prediction]:
        predictions: list[Prediction] = []
        for unit in units:
            started = time.perf_counter()
            text = unit.text.lower()
            positive = sum(marker in text for marker in self.positive_markers)
            negative = sum(marker in text for marker in self.negative_markers)
            if unit.language != "vi":
                probabilities = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
                predictions.append(Prediction("unknown", 0.0, probabilities, None, 0))
                continue
            if positive == negative:
                label, confidence = "neutral", 0.70
            elif positive > negative:
                label, confidence = "positive", min(0.90, 0.65 + positive * 0.10)
            else:
                label, confidence = "negative", min(0.90, 0.65 + negative * 0.10)
            probabilities = {"positive": 0.15, "neutral": 0.15, "negative": 0.15}
            probabilities[label] = confidence
            remaining = (1 - confidence) / 2
            for key in probabilities:
                if key != label:
                    probabilities[key] = remaining
            final_label = label if confidence >= self.confidence_threshold else "unknown"
            predictions.append(
                Prediction(
                    final_label,
                    confidence,
                    probabilities,
                    probabilities["positive"] - probabilities["negative"],
                    int((time.perf_counter() - started) * 1000),
                )
            )
        return predictions


class DummyContractClassifier:
    """Deterministic second adapter used only to verify the adapter boundary.

    It is deliberately not a trained sentiment model and must not be used for
    model-quality claims. Its fixed output lets an integration run demonstrate
    that API, persistence and dashboard do not depend on RuleBaselineClassifier.
    """

    model_version = "dummy-contract-v1"

    def __init__(self, confidence_threshold: float):
        self.confidence_threshold = confidence_threshold

    def predict(self, units: list[UnitDraft]) -> list[Prediction]:
        predictions: list[Prediction] = []
        for index, unit in enumerate(units):
            started = time.perf_counter()
            if unit.language != "vi":
                probabilities = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
                predictions.append(Prediction("unknown", 0.0, probabilities, None, 0))
                continue
            label = ("neutral", "positive", "negative")[index % 3]
            confidence = 0.80
            probabilities = {"positive": 0.10, "neutral": 0.10, "negative": 0.10}
            probabilities[label] = confidence
            predictions.append(
                Prediction(
                    label if confidence >= self.confidence_threshold else "unknown",
                    confidence,
                    probabilities,
                    probabilities["positive"] - probabilities["negative"],
                    int((time.perf_counter() - started) * 1000),
                )
            )
        return predictions


class TfidfLogisticRegressionClassifier:
    """Load a trusted, versioned scikit-learn sentiment artifact.

    The classifier deliberately refuses an absent, malformed or hash-mismatched
    artifact. Falling back to the rules classifier would make the persisted
    ``model_version`` untruthful. Joblib is pickle-based, so the artifact
    directory is a local operator boundary, not a browser/user upload surface.
    """

    supported_labels = ("negative", "neutral", "positive")

    def __init__(
        self, confidence_threshold: float, *, artifact_dir: str, artifact_sha256: str = ""
    ):
        if not artifact_dir:
            raise ValueError("MODEL_ARTIFACT_DIR is required for classifier_adapter=tfidf-logreg")
        directory = Path(artifact_dir)
        model_path = directory / "model.joblib"
        metadata_path = directory / "metadata.json"
        if not model_path.is_file() or not metadata_path.is_file():
            raise ValueError("TF-IDF artifact requires model.joblib and metadata.json")
        actual_hash = _sha256(model_path)
        metadata = _load_metadata(metadata_path)
        expected_hash = artifact_sha256 or str(metadata.get("artifact_sha256") or "")
        if not expected_hash or actual_hash != expected_hash:
            raise ValueError("TF-IDF model artifact SHA-256 does not match the approved metadata")
        if metadata.get("schema_version") != 1 or metadata.get("model_type") != "tfidf-logreg":
            raise ValueError("unsupported TF-IDF artifact metadata")
        version = metadata.get("model_version")
        if not isinstance(version, str) or not version:
            raise ValueError("TF-IDF artifact metadata has no model_version")
        try:
            artifact = joblib.load(model_path)
        except Exception as exc:  # pragma: no cover - third-party deserialization errors vary by version
            raise ValueError("could not load TF-IDF model artifact") from exc
        if not isinstance(artifact, dict) or artifact.get("model_version") != version:
            raise ValueError("TF-IDF artifact and metadata versions differ")
        if tuple(artifact.get("labels") or ()) != self.supported_labels:
            raise ValueError("TF-IDF artifact labels must be negative, neutral, positive")
        pipeline = artifact.get("pipeline")
        if not hasattr(pipeline, "predict_proba"):
            raise ValueError("TF-IDF artifact has no probability-capable pipeline")
        classes = tuple(str(label) for label in getattr(pipeline, "classes_", ()))
        if set(classes) != set(self.supported_labels):
            raise ValueError("TF-IDF pipeline classes are incompatible with the sentiment contract")
        self.model_version = version
        self.confidence_threshold = confidence_threshold
        self.pipeline = pipeline
        self.classes = classes

    def predict(self, units: list[UnitDraft]) -> list[Prediction]:
        predictions: list[Prediction] = []
        inferable = [unit for unit in units if unit.language == "vi"]
        probabilities_by_unit: dict[int, dict[str, float]] = {}
        started = time.perf_counter()
        if inferable:
            matrix = self.pipeline.predict_proba([unit.text for unit in inferable])
            for unit, values in zip(inferable, matrix, strict=True):
                probabilities_by_unit[id(unit)] = {
                    label: float(value) for label, value in zip(self.classes, values, strict=True)
                }
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        for unit in units:
            if unit.language != "vi":
                predictions.append(
                    Prediction("unknown", 0.0, {label: 0.0 for label in self.supported_labels}, None, 0)
                )
                continue
            probabilities = probabilities_by_unit[id(unit)]
            label = max(self.supported_labels, key=probabilities.__getitem__)
            confidence = probabilities[label]
            predictions.append(
                Prediction(
                    label if confidence >= self.confidence_threshold else "unknown",
                    confidence,
                    probabilities,
                    probabilities["positive"] - probabilities["negative"],
                    elapsed_ms,
                )
            )
        return predictions


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_metadata(path: Path) -> dict:
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("could not read TF-IDF artifact metadata") from exc
    if not isinstance(data, dict):
        raise TypeError("TF-IDF artifact metadata must be a JSON object")
    return data


def build_classifier(
    adapter: str,
    confidence_threshold: float,
    *,
    artifact_dir: str = "",
    artifact_sha256: str = "",
) -> SentimentClassifier:
    """Create only an explicitly configured adapter with a stable version."""
    adapters = {
        "rules": RuleBaselineClassifier,
        "dummy-contract": DummyContractClassifier,
        "tfidf-logreg": TfidfLogisticRegressionClassifier,
    }
    try:
        if adapter == "tfidf-logreg":
            return TfidfLogisticRegressionClassifier(
                confidence_threshold, artifact_dir=artifact_dir, artifact_sha256=artifact_sha256
            )
        return adapters[adapter](confidence_threshold)
    except KeyError as exc:
        raise ValueError(f"classifier adapter {adapter!r} is not installed") from exc
