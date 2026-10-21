from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import numpy as np


class AcousticAnalyzer:
    """Versioned signal features, deliberately separate from emotion inference."""

    version = "acoustic-v1"

    def extract(self, audio_path: Path) -> dict[str, Any]:
        try:
            import librosa

            signal, sample_rate = librosa.load(audio_path, sr=None, mono=True)
            if signal.size == 0:
                raise ValueError("empty audio")
            hop_length = 512
            rms = librosa.feature.rms(y=signal, hop_length=hop_length)[0]
            zcr = librosa.feature.zero_crossing_rate(signal, hop_length=hop_length)[0]
            centroid = librosa.feature.spectral_centroid(
                y=signal, sr=sample_rate, hop_length=hop_length
            )[0]
            bandwidth = librosa.feature.spectral_bandwidth(
                y=signal, sr=sample_rate, hop_length=hop_length
            )[0]
            mfcc = librosa.feature.mfcc(y=signal, sr=sample_rate, n_mfcc=13, hop_length=hop_length)
            mel = librosa.feature.melspectrogram(y=signal, sr=sample_rate, n_mels=40, hop_length=hop_length)
            pitch, _, _ = librosa.pyin(
                signal,
                fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C7"),
                sr=sample_rate,
                hop_length=hop_length,
            )
            return {
                "version": self.version,
                "duration_seconds": self._rounded(len(signal) / sample_rate),
                "sample_rate": int(sample_rate),
                "rms_energy": self._rounded(float(np.mean(rms))),
                "zero_crossing_rate": self._rounded(float(np.mean(zcr))),
                "pitch_hz": self._finite_mean(pitch),
                "spectral_centroid_hz": self._rounded(float(np.mean(centroid))),
                "spectral_bandwidth_hz": self._rounded(float(np.mean(bandwidth))),
                "waveform": self._downsample(signal, 180),
                "pitch_track_hz": self._downsample(pitch, 120),
                "rms_track": self._downsample(rms, 120),
                "mfcc": [[self._rounded(float(value)) for value in row[:80]] for row in mfcc],
                "mel_spectrogram_db": [
                    [self._rounded(float(value)) for value in row[:80]]
                    for row in librosa.power_to_db(mel, ref=np.max)
                ],
            }
        except ImportError:
            return self._minimal_wave_features(audio_path)

    def _minimal_wave_features(self, audio_path: Path) -> dict[str, Any]:
        with wave.open(str(audio_path), "rb") as source:
            sample_rate = source.getframerate()
            frames = source.readframes(source.getnframes())
            sample_width = source.getsampwidth()
            channels = source.getnchannels()
        if sample_width != 2:
            raise RuntimeError("librosa is required to analyse a non-PCM16 WAV")
        signal = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        if channels > 1:
            signal = signal.reshape(-1, channels).mean(axis=1)
        zcr = np.mean(np.abs(np.diff(np.signbit(signal)))) if len(signal) > 1 else 0.0
        return {
            "version": f"{self.version}-minimal",
            "duration_seconds": self._rounded(len(signal) / sample_rate),
            "sample_rate": int(sample_rate),
            "rms_energy": self._rounded(float(np.sqrt(np.mean(np.square(signal))))),
            "zero_crossing_rate": self._rounded(float(zcr)),
            "pitch_hz": None,
            "spectral_centroid_hz": None,
            "spectral_bandwidth_hz": None,
            "waveform": self._downsample(signal, 180),
            "pitch_track_hz": [],
            "rms_track": [],
            "mfcc": [],
            "mel_spectrogram_db": [],
            "analysis_note": "Install librosa for pitch, MFCC, spectral, and Mel features.",
        }

    @staticmethod
    def _rounded(value: float | np.floating[Any]) -> float:
        return round(float(value), 6)

    def _finite_mean(self, values: np.ndarray) -> float | None:
        finite = values[np.isfinite(values)]
        return self._rounded(float(np.mean(finite))) if finite.size else None

    def _downsample(self, values: np.ndarray, target: int) -> list[float | None]:
        if not values.size:
            return []
        indices = np.linspace(0, len(values) - 1, min(target, len(values))).astype(int)
        return [self._rounded(value) if np.isfinite(value) else None for value in values[indices]]

