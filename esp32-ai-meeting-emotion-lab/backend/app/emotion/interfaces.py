from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class AcousticEmotionClassifier(Protocol):
    """A research model contract; implementations must be trained/evaluated externally."""

    def predict(self, wav_path: Path, acoustic_features: dict[str, Any]) -> dict[str, Any]: ...


def model_not_available(checkpoint: Path | None, tts_backend: str) -> dict[str, Any]:
    """Return an explicit abstention, never a fabricated affect or clinical label."""
    return {
        "status": "unavailable",
        "label": "unknown",
        "confidence": None,
        "checkpoint_configured": bool(checkpoint),
        "input_kind": "synthetic" if tts_backend != "openai-tts" else "synthetic_tts",
        "reason": (
            "No separately trained and evaluated acoustic-emotion checkpoint is loaded. "
            "This system does not infer depression, diagnosis, or mental-health risk from voice data."
        ),
    }
