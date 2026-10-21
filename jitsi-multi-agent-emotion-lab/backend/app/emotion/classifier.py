from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings


class AudioEmotionClassifier:
    """Checkpoint gate for a future validated acoustic-emotion model.

    No score is emitted merely because features exist. A checkpoint must be evaluated
    on a licensed human-labelled dataset and supplied explicitly by the operator.
    """

    def __init__(self, settings: Settings):
        self.checkpoint: Path | None = settings.emotion_checkpoint
        self.model_version = settings.emotion_model_version

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        if not self.checkpoint or not self.checkpoint.is_file() or not self.model_version:
            return {
                "status": "unavailable",
                "label": "unknown",
                "confidence": None,
                "model_version": None,
                "reason": (
                    "No separately evaluated emotion checkpoint is configured. "
                    "Acoustic features are not an emotion or depression assessment."
                ),
            }
        # The contract is intentionally strict: an incompatible checkpoint abstains.
        try:
            import torch

            artifact = torch.load(self.checkpoint, map_location="cpu", weights_only=True)
            if not isinstance(artifact, dict) or "predict" not in artifact:
                raise ValueError("checkpoint does not implement the lab inference contract")
        except Exception as error:
            return {
                "status": "unavailable",
                "label": "unknown",
                "confidence": None,
                "model_version": self.model_version,
                "reason": f"Configured checkpoint is unavailable for inference: {type(error).__name__}",
            }
        return {
            "status": "abstained",
            "label": "unknown",
            "confidence": None,
            "model_version": self.model_version,
            "reason": "Checkpoint adapter is present but no validated inference head is registered.",
        }

