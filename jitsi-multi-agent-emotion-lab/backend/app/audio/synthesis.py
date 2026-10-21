from __future__ import annotations

import asyncio
import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.agents.profiles import AgentProfile
from app.config import Settings


@dataclass(frozen=True)
class SynthesisResult:
    path: Path
    backend: str


class SpeechSynthesizer:
    """Creates normalized WAV artifacts; only OpenAI mode produces spoken language."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def synthesize(
        self, session_id: str, turn_id: str, profile: AgentProfile, transcript: str
    ) -> SynthesisResult:
        output_dir = self.settings.media_root / session_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{turn_id}.wav"
        if self.settings.openai_api_key:
            await asyncio.to_thread(self._openai_tts, output_path, profile, transcript)
            self._normalize_in_place(output_path)
            return SynthesisResult(path=output_path, backend="openai-tts")

        # A tone is intentionally not represented as speech or an emotion prediction.
        await asyncio.to_thread(self._write_labelled_placeholder_tone, output_path, profile, transcript)
        return SynthesisResult(path=output_path, backend="synthetic-tone-placeholder")

    def _openai_tts(self, output_path: Path, profile: AgentProfile, transcript: str) -> None:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)
        with client.audio.speech.with_streaming_response.create(
            model=self.settings.openai_tts_model,
            voice=profile.voice,
            input=transcript,
            instructions=(
                f"Speak in a {profile.speaking_style} style for a research prototype. "
                "Do not add text outside the supplied response."
            ),
            response_format="wav",
        ) as response:
            response.stream_to_file(output_path)

    @staticmethod
    def _write_labelled_placeholder_tone(
        path: Path, profile: AgentProfile, transcript: str) -> None:
        sample_rate = 24_000
        seconds = min(4.0, max(0.8, len(transcript) / 95))
        frequency = {"empathy": 220, "critical": 165, "optimistic": 294, "moderator": 247}[profile.id]
        samples = np.arange(int(sample_rate * seconds), dtype=np.float32)
        envelope = np.minimum(1, np.minimum(samples / (sample_rate * 0.08), (len(samples) - samples) / (sample_rate * 0.08)))
        signal = (0.1 * envelope * np.sin(2 * math.pi * frequency * samples / sample_rate)).astype(np.float32)
        pcm = (signal * np.iinfo(np.int16).max).astype("<i2")
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(pcm.tobytes())

    @staticmethod
    def _normalize_in_place(path: Path) -> None:
        try:
            import soundfile as sf

            samples, sample_rate = sf.read(path, always_2d=False)
            peak = float(np.max(np.abs(samples))) if np.size(samples) else 0.0
            if peak > 0:
                samples = samples * min(1.0, 0.95 / peak)
            sf.write(path, samples, sample_rate, subtype="PCM_16")
        except Exception as error:
            raise RuntimeError(f"Cannot normalize generated WAV: {error}") from error

