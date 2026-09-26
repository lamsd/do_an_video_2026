from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class QualityDecision:
    status: str
    reasons: list[str]
    normalized_text: str
    language: str


@dataclass(frozen=True)
class UnitDraft:
    speaker_key: str | None
    speaker_name: str | None
    segment_ids: list[str]
    text: str
    language: str
    token_count: int
    start_at: datetime
    end_at: datetime
    quality_status: str
    quality_reasons: list[str]


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float
    probabilities: dict[str, float]
    polarity_score: float | None
    inference_ms: int
