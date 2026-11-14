"""OpenAI-compatible transcription endpoint — auth + request-validation contract.

The happy path (real model inference) is a GPU/integration concern, exercised by the deploy
unit's smoke, not the unit gate. Here we pin the seam the bot's whisper client relies on:
token auth and multipart validation, both reachable without loading a model.
"""
from __future__ import annotations

import io

import numpy as np
import soundfile as sf


def _wav_bytes(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(int(16_000 * seconds), dtype=np.float32), 16_000, format="WAV")
    return buffer.getvalue()


class _Segment:
    start = 0.0
    end = 1.0
    text = "nhiễu không đáng tin"
    avg_logprob = -1.3
    compression_ratio = 1.0
    no_speech_prob = 0.1


class _RejectedCandidateModel:
    def transcribe(self, *_args, **_kwargs):
        info = type("Info", (), {"language": "zh", "language_probability": 0.2})()
        return iter([_Segment()]), info


class _UnexpectedModel:
    def transcribe(self, *_args, **_kwargs):  # pragma: no cover - assertion is the contract
        raise AssertionError("short audio must be rejected before inference")


class _KnownHallucinationSegment:
    start = 0.0
    end = 2.0
    text = "Hãy subscribe cho kênh La La School để không bỏ lỡ những video hấp dẫn"
    # These values intentionally look healthy: the phrase filter protects the
    # service when acoustic-confidence gates cannot distinguish media artifacts.
    avg_logprob = -0.1
    compression_ratio = 1.0
    no_speech_prob = 0.01


class _KnownHallucinationModel:
    def transcribe(self, *_args, **_kwargs):
        info = type("Info", (), {"language": "vi", "language_probability": 1.0})()
        return iter([_KnownHallucinationSegment()]), info


class _PromptCaptureSegment:
    start = 0.0
    end = 2.0
    text = "Hôm nay chúng ta họp về tiến độ dự án"
    avg_logprob = -0.1
    compression_ratio = 1.0
    no_speech_prob = 0.01


class _PromptCaptureModel:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, *_args, **kwargs):
        self.kwargs = kwargs
        info = type("Info", (), {"language": "vi", "language_probability": 1.0})()
        return iter([_PromptCaptureSegment()]), info


def test_transcribe_requires_token_when_configured(client, monkeypatch):
    import transcription.main as svc

    monkeypatch.setattr(svc, "API_TOKEN", "secret-token")
    # No X-API-Key / Bearer → rejected before any model work.
    r = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", b"RIFF....", "audio/wav")},
        data={"model": "large-v3-turbo"},
    )
    assert r.status_code == 401


def test_transcribe_rejects_missing_file(client, monkeypatch):
    import transcription.main as svc

    # No token configured → auth open; FastAPI multipart validation rejects the missing file.
    monkeypatch.setattr(svc, "API_TOKEN", "")
    r = client.post("/v1/audio/transcriptions", data={"model": "large-v3-turbo"})
    assert r.status_code == 422


def test_rejected_low_quality_candidate_is_not_published_as_transcript(client, monkeypatch):
    """Regression: never fall back to text that the service just rejected."""
    import transcription.main as svc

    monkeypatch.setattr(svc, "API_TOKEN", "")
    monkeypatch.setattr(svc, "model", _RejectedCandidateModel())
    r = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
        data={"model": "small"},
    )

    assert r.status_code == 200
    assert r.json()["text"] == ""
    assert r.json()["segments"] == []


def test_tiny_audio_is_dropped_before_whisper_inference(client, monkeypatch):
    import transcription.main as svc

    monkeypatch.setattr(svc, "API_TOKEN", "")
    monkeypatch.setattr(svc, "model", _UnexpectedModel())
    r = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("tiny.wav", _wav_bytes(0.1), "audio/wav")},
        data={"model": "small", "language": "vi"},
    )

    assert r.status_code == 200
    assert r.json()["text"] == ""
    assert r.json()["segments"] == []


def test_known_media_outro_hallucination_is_not_published(client, monkeypatch):
    import transcription.main as svc

    monkeypatch.setattr(svc, "API_TOKEN", "")
    monkeypatch.setattr(svc, "model", _KnownHallucinationModel())
    r = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", _wav_bytes(2), "audio/wav")},
        data={"model": "small", "language": "vi"},
    )

    assert r.status_code == 200
    assert r.json()["text"] == ""
    assert r.json()["segments"] == []


def test_subscribe_variant_is_recognized_as_media_outro_hallucination():
    import transcription.main as svc

    assert svc._known_hallucination("Đừng quên nhấn đăng ký kênh và bật chuông thông báo nhé")


def test_client_prompt_is_disabled_for_live_audio_by_default(client, monkeypatch):
    import transcription.main as svc

    model = _PromptCaptureModel()
    monkeypatch.setattr(svc, "API_TOKEN", "")
    monkeypatch.setattr(svc, "USE_REQUEST_PROMPT", False)
    monkeypatch.setattr(svc, "model", model)
    r = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", _wav_bytes(2), "audio/wav")},
        data={"model": "small", "language": "vi", "prompt": "Câu STT sai từ lần trước"},
    )

    assert r.status_code == 200
    assert r.json()["text"] == "Hôm nay chúng ta họp về tiến độ dự án"
    assert model.kwargs["initial_prompt"] is None
