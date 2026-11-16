import time
from typing import Protocol

from .contracts import Prediction, UnitDraft


class SentimentClassifier(Protocol):
    model_version: str

    def predict(self, units: list[UnitDraft]) -> list[Prediction]: ...


class RuleBaselineClassifier:
    """Deterministic safety baseline; replace through the SentimentClassifier protocol."""

    model_version = "baseline-rules-v1"
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
