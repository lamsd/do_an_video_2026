from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.config import Settings
from app.emotion.interfaces import model_not_available
from app.identities import AgentIdentity


@dataclass(frozen=True)
class AudioArtifact:
    path: Path
    features: dict[str, Any]
    tts_backend: str


class AudioPipeline:
    """Backend-only TTS and acoustic artifact creation for an accepted turn."""

    feature_version = "esp32-lab-acoustic-v1"

    def __init__(self, settings: Settings):
        self.settings = settings

    def create(self, session_id: str, turn_id: str, agent: AgentIdentity, text: str) -> AudioArtifact:
        directory = self.settings.media_root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{turn_id}.wav"
        if self.settings.openai_api_key:
            self._openai_tts(path, agent, text)
            backend = "openai-tts"
        else:
            self._placeholder_tone(path, agent, text)
            backend = "synthetic-tone-placeholder"
        return AudioArtifact(path=path, features=self._extract(path), tts_backend=backend)

    def _openai_tts(self, path: Path, agent: AgentIdentity, text: str) -> None:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)
        with client.audio.speech.with_streaming_response.create(
            model=self.settings.openai_tts_model,
            voice=agent.voice,
            input=text,
            instructions=(
                f"Nói hoàn toàn bằng tiếng Việt với phong cách {agent.speaking_style}. "
                "Đây là tác nhân AI được gắn nhãn rõ ràng trong nghiên cứu."
            ),
            response_format="wav",
        ) as response:
            response.stream_to_file(path)

    @staticmethod
    def _placeholder_tone(path: Path, agent: AgentIdentity, text: str) -> None:
        """Offline test fixture; it is never represented as semantic spoken audio."""
        sample_rate = 24_000
        duration = min(4.0, max(0.8, len(text) / 95))
        frequency = {"empathy": 220, "critical": 165, "optimistic": 294, "moderator": 247}[agent.agent_id]
        samples = np.arange(int(sample_rate * duration), dtype=np.float32)
        fade = sample_rate * 0.08
        envelope = np.minimum(1, np.minimum(samples / fade, (len(samples) - samples) / fade))
        signal = (0.1 * envelope * np.sin(2 * math.pi * frequency * samples / sample_rate)).astype(
            np.float32
        )
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes((signal * 32767).astype("<i2").tobytes())

    def _extract(self, path: Path) -> dict[str, Any]:
        try:
            import librosa

            signal, sample_rate = librosa.load(path, sr=None, mono=True)
            hop_length = 512
            rms = librosa.feature.rms(y=signal, hop_length=hop_length)[0]
            mfcc = librosa.feature.mfcc(y=signal, sr=sample_rate, n_mfcc=13, hop_length=hop_length)
            mel = librosa.feature.melspectrogram(
                y=signal, sr=sample_rate, n_mels=40, hop_length=hop_length
            )
            pitch, _, _ = librosa.pyin(
                signal,
                fmin=float(librosa.note_to_hz("C2")),
                fmax=float(librosa.note_to_hz("C7")),
                sr=sample_rate,
                hop_length=hop_length,
            )
            finite_pitch = pitch[np.isfinite(pitch)]
            return {
                "feature_version": self.feature_version,
                "sample_rate": int(sample_rate),
                "duration_seconds": round(len(signal) / sample_rate, 4),
                "rms_energy": round(float(np.mean(rms)), 6),
                "pitch_hz": round(float(np.mean(finite_pitch)), 3) if finite_pitch.size else None,
                "mfcc": [[round(float(item), 4) for item in row[:80]] for row in mfcc],
                "mel_spectrogram_db": [
                    [round(float(item), 3) for item in row[:80]]
                    for row in librosa.power_to_db(mel, ref=np.max)
                ],
            }
        except ImportError:
            return self._minimal_features(path)

    def _minimal_features(self, path: Path) -> dict[str, Any]:
        with wave.open(str(path), "rb") as source:
            rate = source.getframerate()
            samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32)
        normalized = samples / 32768.0
        return {
            "feature_version": f"{self.feature_version}-minimal",
            "sample_rate": rate,
            "duration_seconds": round(len(normalized) / rate, 4),
            "rms_energy": round(float(np.sqrt(np.mean(np.square(normalized)))), 6),
            "pitch_hz": None,
            "mfcc": [],
            "mel_spectrogram_db": [],
            "analysis_note": "Install librosa to compute pitch, MFCC, and Mel-spectrogram values.",
        }


def unavailable_emotion_prediction(tts_backend: str, checkpoint: Path | None) -> dict[str, Any]:
    return model_not_available(checkpoint, tts_backend)

