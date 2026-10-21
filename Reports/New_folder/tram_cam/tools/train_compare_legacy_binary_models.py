#!/usr/bin/env python3
"""Train and compare *legacy-only* binary text classifiers.

This experiment is deliberately isolated from the meeting-sentiment system.
The corpus carries anonymous legacy label codes (0/1), not the application's
negative/neutral/positive contract.  Consequently, all saved models are
research artifacts and are never written to source/model-artifacts or used by
the backend.

The script uses fixed, documented configurations rather than test-set tuning:
  - majority-class baseline;
  - length-only logistic regression (a confound diagnostic);
  - word TF-IDF + logistic regression;
  - character TF-IDF + logistic regression.

It validates the manifest hashes and split integrity before fitting.  Outputs
contain aggregate statistics and serialized local research models only; the
script never write samples or raw corpus text to logs/reports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import shutil
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


SPLITS = ("train", "validation", "test")
LABELS = (0, 1)
REQUIRED_FIELDS = {"text_vi", "legacy_label"}
SCOPE_WARNING = (
    "CHỈ DÙNG NGHIÊN CỨU LEGACY: nhãn 0/1 không có ngữ nghĩa sentiment cuộc họp "
    "đã được phê duyệt. Artifact này không được triển khai vào API, dashboard, "
    "source/model-artifacts/ hay source/model-data/approved/."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        required=True,
        help="Thư mục chứa train.csv, validation.csv, test.csv và dataset-manifest.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Thư mục artifact mới. Phải chưa tồn tại và không nằm trong approved/.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed cho Logistic Regression.")
    parser.add_argument(
        "--include-phobert",
        action="store_true",
        help="Thêm PhoBERT fine-tune vào benchmark legacy-only. Không bật mặc định vì cần checkpoint và GPU.",
    )
    parser.add_argument("--phobert-model-name", default="vinai/phobert-base-v2")
    parser.add_argument(
        "--phobert-revision",
        help="Optional Hugging Face revision/commit hash. Ghi lại resolved revision trong artifact để tái lập.",
    )
    parser.add_argument("--phobert-max-length", type=int, default=256)
    parser.add_argument("--phobert-epochs", type=int, default=3)
    parser.add_argument("--phobert-learning-rate", type=float, default=2e-5)
    parser.add_argument("--phobert-batch-size", type=int, default=8)
    parser.add_argument(
        "--phobert-device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help="Thiết bị fine-tune. auto ưu tiên CUDA.",
    )
    parser.add_argument(
        "--allow-cpu-phobert",
        action="store_true",
        help="Cho phép fine-tune PhoBERT bằng CPU. Chỉ dùng khi chủ động chấp nhận thời gian chạy rất lâu.",
    )
    parser.add_argument(
        "--phobert-local-files-only",
        action="store_true",
        help="Không tải checkpoint; chỉ dùng cache Hugging Face cục bộ đã có.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonicalize(text: str) -> str:
    """Canonical form used only for integrity checks and model input cleanup."""
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def read_split(path: Path) -> tuple[list[str], list[int]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not REQUIRED_FIELDS.issubset(reader.fieldnames):
            raise ValueError(f"{path.name}: phải có các cột {sorted(REQUIRED_FIELDS)}.")

        texts: list[str] = []
        labels: list[int] = []
        for row_number, row in enumerate(reader, start=2):
            raw_text = row.get("text_vi")
            raw_label = row.get("legacy_label")
            if raw_text is None or raw_label is None:
                raise ValueError(f"{path.name}: dòng {row_number} thiếu text hoặc nhãn.")
            text = canonicalize(raw_text)
            if not text:
                raise ValueError(f"{path.name}: dòng {row_number} có text rỗng sau chuẩn hoá.")
            if raw_label.strip() not in {"0", "1"}:
                raise ValueError(f"{path.name}: dòng {row_number} có nhãn ngoài {{0, 1}}.")
            texts.append(text)
            labels.append(int(raw_label))

    if not texts:
        raise ValueError(f"{path.name}: split rỗng.")
    return texts, labels


def load_and_validate_corpus(corpus_dir: Path) -> tuple[dict[str, tuple[list[str], list[int]]], dict[str, Any]]:
    manifest_path = corpus_dir / "dataset-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy {manifest_path}.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_kind") != "legacy-binary-text-corpus":
        raise ValueError("dataset_kind không phải legacy-binary-text-corpus; dừng để tránh lẫn domain.")
    if not manifest.get("prohibited_uses"):
        raise ValueError("Manifest thiếu prohibited_uses; không đủ ràng buộc phạm vi sử dụng.")

    expected_hashes = manifest.get("output_sha256", {})
    corpus: dict[str, tuple[list[str], list[int]]] = {}
    split_pairs: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        path = corpus_dir / f"{split}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Không tìm thấy split {path}.")
        expected = expected_hashes.get(split)
        observed = sha256_file(path)
        if not expected or observed != expected:
            raise ValueError(f"SHA-256 của {path.name} không khớp manifest; dừng chạy.")
        texts, labels = read_split(path)
        mapping: dict[str, int] = {}
        for text, label in zip(texts, labels):
            if text in mapping:
                raise ValueError(f"{path.name}: phát hiện duplicate sau chuẩn hoá; dừng chạy.")
            mapping[text] = label
        corpus[split] = (texts, labels)
        split_pairs[split] = mapping

    for index, first in enumerate(SPLITS):
        for second in SPLITS[index + 1 :]:
            overlap = set(split_pairs[first]).intersection(split_pairs[second])
            if overlap:
                raise ValueError(f"Split leakage: {first}/{second} có {len(overlap)} text trùng.")

    all_path = corpus_dir / "all_deduplicated.csv"
    if all_path.is_file():
        all_texts, all_labels = read_split(all_path)
        all_mapping = dict(zip(all_texts, all_labels))
        if len(all_mapping) != len(all_texts):
            raise ValueError("all_deduplicated.csv có duplicate sau chuẩn hoá.")
        combined: dict[str, int] = {}
        for split in SPLITS:
            combined.update(split_pairs[split])
        if combined != all_mapping:
            raise ValueError("Hợp các split không khớp all_deduplicated.csv; dừng chạy.")

    return corpus, manifest


def length_features(texts: Iterable[str]) -> np.ndarray:
    """Two non-semantic features: log character and whitespace-token counts."""
    return np.asarray(
        [[np.log1p(len(text)), np.log1p(len(text.split()))] for text in texts], dtype=np.float64
    )


class PhoBERTFineTuner:
    """Minimal two-code PhoBERT fine-tuner used only by the legacy benchmark.

    Transformers, PyTorch and underthesea are imported lazily so the standard
    TF-IDF comparison remains offline and dependency-light.  The model class
    deliberately has no backend/runtime integration path.
    """

    def __init__(
        self,
        *,
        model_name: str,
        revision: str | None,
        max_length: int,
        epochs: int,
        learning_rate: float,
        batch_size: int,
        seed: int,
        device_preference: str,
        allow_cpu: bool,
        local_files_only: bool,
    ) -> None:
        if not 8 <= max_length <= 256:
            raise ValueError("PhoBERT max_length phải nằm trong khoảng 8..256.")
        if epochs < 1 or batch_size < 1 or learning_rate <= 0:
            raise ValueError("PhoBERT epochs, batch_size và learning_rate không hợp lệ.")
        self.model_name = model_name
        self.revision = revision
        self.max_length = max_length
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.seed = seed
        self.device_preference = device_preference
        self.allow_cpu = allow_cpu
        self.local_files_only = local_files_only
        self.tokenizer: Any | None = None
        self.model: Any | None = None
        self.device: Any | None = None
        self.runtime_metadata: dict[str, Any] = {}

    def _dependencies(self) -> tuple[Any, Any, Any, Any]:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            from underthesea import word_tokenize
        except ImportError as exc:
            raise RuntimeError(
                "PhoBERT cần torch, transformers và underthesea trong virtual environment. "
                "Cài dependencies vào .venv, không cài vào Python hệ thống."
            ) from exc
        return torch, AutoModelForSequenceClassification, AutoTokenizer, word_tokenize

    def _resolve_device(self, torch: Any) -> Any:
        cuda_available = bool(torch.cuda.is_available())
        if self.device_preference == "cuda" and not cuda_available:
            raise RuntimeError("--phobert-device cuda được chọn nhưng CUDA không khả dụng.")
        if self.device_preference == "auto":
            device_name = "cuda" if cuda_available else "cpu"
        else:
            device_name = self.device_preference
        if device_name == "cpu" and not self.allow_cpu:
            raise RuntimeError(
                "PhoBERT fine-tune bị chặn trên CPU để tránh chạy rất lâu. "
                "Dùng GPU hoặc thêm --allow-cpu-phobert nếu bạn chủ động chấp nhận giới hạn này."
            )
        return torch.device(device_name)

    @staticmethod
    def _segment(texts: list[str], word_tokenize: Any) -> list[str]:
        return [word_tokenize(text, format="text") for text in texts]

    def _tokenize(self, texts: list[str], torch: Any, word_tokenize: Any) -> dict[str, Any]:
        if self.tokenizer is None:
            raise RuntimeError("PhoBERT tokenizer chưa được nạp.")
        encoded = self.tokenizer(
            self._segment(texts, word_tokenize),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        if self.device is None:
            raise RuntimeError("PhoBERT device chưa được khởi tạo.")
        return {name: tensor.to(self.device) for name, tensor in encoded.items()}

    def fit(self, texts: list[str], labels: list[int]) -> "PhoBERTFineTuner":
        if len(texts) != len(labels) or not texts:
            raise ValueError("PhoBERT cần texts và labels cùng độ dài, không rỗng.")
        if set(labels) != set(LABELS):
            raise ValueError("PhoBERT benchmark yêu cầu cả hai mã nhãn 0 và 1 trong train split.")
        torch, auto_model, auto_tokenizer, word_tokenize = self._dependencies()
        self.device = self._resolve_device(torch)
        torch.manual_seed(self.seed)
        if self.device.type == "cuda":
            torch.cuda.manual_seed_all(self.seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            torch.cuda.reset_peak_memory_stats(self.device)

        try:
            self.tokenizer = auto_tokenizer.from_pretrained(
                self.model_name,
                use_fast=False,
                revision=self.revision,
                local_files_only=self.local_files_only,
            )
            self.model = auto_model.from_pretrained(
                self.model_name,
                num_labels=len(LABELS),
                id2label={index: str(label) for index, label in enumerate(LABELS)},
                label2id={str(label): index for index, label in enumerate(LABELS)},
                revision=self.revision,
                local_files_only=self.local_files_only,
            )
        except OSError as exc:
            cache_hint = "checkpoint cache cục bộ" if self.local_files_only else "Hugging Face hoặc checkpoint cache cục bộ"
            raise RuntimeError(
                f"Không thể nạp {self.model_name} từ {cache_hint}. "
                "Checkpoint PhoBERT lớn (~540 MB weights); chỉ chạy sau khi đã chuẩn bị network/cache và GPU."
            ) from exc

        self.model.to(self.device)
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=self.learning_rate)
        generator = torch.Generator().manual_seed(self.seed)
        self.model.train()
        for _epoch in range(self.epochs):
            indices = torch.randperm(len(texts), generator=generator).tolist()
            for start in range(0, len(indices), self.batch_size):
                batch_indices = indices[start : start + self.batch_size]
                batch_texts = [texts[index] for index in batch_indices]
                batch_labels = torch.tensor(
                    [labels[index] for index in batch_indices], dtype=torch.long, device=self.device
                )
                batch = self._tokenize(batch_texts, torch, word_tokenize)
                optimizer.zero_grad(set_to_none=True)
                output = self.model(**batch, labels=batch_labels)
                output.loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                optimizer.step()

        self.model.eval()
        self.runtime_metadata = {
            "framework": "transformers-pytorch-manual-loop",
            "base_model": self.model_name,
            "requested_revision": self.revision,
            "resolved_revision": getattr(self.model.config, "_commit_hash", None),
            "preprocessing": "underthesea.word_tokenize(format='text')",
            "device": str(self.device),
            "max_length": self.max_length,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "local_files_only": self.local_files_only,
        }
        if self.device.type == "cuda":
            self.runtime_metadata["cuda_peak_allocated_megabytes"] = round(
                float(torch.cuda.max_memory_allocated(self.device) / (1024 * 1024)), 6
            )
            self.runtime_metadata["cuda_peak_reserved_megabytes"] = round(
                float(torch.cuda.max_memory_reserved(self.device) / (1024 * 1024)), 6
            )
        return self

    def predict(self, texts: list[str]) -> np.ndarray:
        if self.model is None or self.tokenizer is None or self.device is None:
            raise RuntimeError("PhoBERT chưa được fit hoặc nạp artifact.")
        torch, _auto_model, _auto_tokenizer, word_tokenize = self._dependencies()
        predictions: list[np.ndarray] = []
        self.model.eval()
        with torch.no_grad():
            for start in range(0, len(texts), self.batch_size):
                batch = self._tokenize(texts[start : start + self.batch_size], torch, word_tokenize)
                logits = self.model(**batch).logits.detach().cpu().numpy()
                predictions.append(np.argmax(logits, axis=1))
        return np.concatenate(predictions).astype(int, copy=False)

    def save_pretrained(self, destination: Path) -> None:
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Không thể lưu PhoBERT trước khi fit.")
        destination.mkdir(parents=True, exist_ok=False)
        self.model.save_pretrained(destination, safe_serialization=True)
        self.tokenizer.save_pretrained(destination)
        write_json(
            destination / "legacy-phobert-config.json",
            {
                "scope_warning": SCOPE_WARNING,
                "label_codes": list(LABELS),
                "runtime_metadata": self.runtime_metadata,
            },
        )


def build_models(
    seed: int,
    *,
    include_phobert: bool = False,
    phobert_config: dict[str, Any] | None = None,
) -> list[tuple[str, str, Any, str]]:
    """Return (id, display name, estimator, input kind), all fixed pre-registered specs."""
    logistic_kwargs = {"max_iter": 2000, "class_weight": "balanced", "random_state": seed}
    models: list[tuple[str, str, Any, str]] = [
        (
            "majority-class",
            "Majority-class baseline",
            DummyClassifier(strategy="most_frequent"),
            "placeholder_text",
        ),
        (
            "length-only-logreg",
            "Length-only Logistic Regression",
            Pipeline([("scale", StandardScaler()), ("classifier", LogisticRegression(**logistic_kwargs))]),
            "length_features",
        ),
        (
            "word-tfidf-logreg",
            "Word TF-IDF (1–2 gram) + Logistic Regression",
            Pipeline(
                [
                    (
                        "tfidf",
                        TfidfVectorizer(
                            lowercase=True,
                            ngram_range=(1, 2),
                            min_df=2,
                            max_features=100_000,
                            sublinear_tf=True,
                            dtype=np.float32,
                        ),
                    ),
                    ("classifier", LogisticRegression(**logistic_kwargs)),
                ]
            ),
            "text",
        ),
        (
            "char-tfidf-logreg",
            "Character TF-IDF (3–5 gram) + Logistic Regression",
            Pipeline(
                [
                    (
                        "tfidf",
                        TfidfVectorizer(
                            analyzer="char_wb",
                            lowercase=True,
                            ngram_range=(3, 5),
                            min_df=2,
                            max_features=100_000,
                            sublinear_tf=True,
                            dtype=np.float32,
                        ),
                    ),
                    ("classifier", LogisticRegression(**logistic_kwargs)),
                ]
            ),
            "text",
        ),
    ]
    if include_phobert:
        config = phobert_config or {}
        models.append(
            (
                "phobert-finetune",
                "PhoBERT-base-v2 fine-tune (legacy-only)",
                PhoBERTFineTuner(seed=seed, **config),
                "text",
            )
        )
    return models


def model_input(texts: list[str], kind: str) -> Any:
    if kind == "length_features":
        return length_features(texts)
    if kind == "placeholder_text":
        return [""] * len(texts)
    if kind == "text":
        return texts
    raise ValueError(f"Unknown input kind: {kind}")


def artifact_size_bytes(path: Path) -> int:
    """Return the aggregate size for a model file or a Hugging Face model directory."""
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    raise FileNotFoundError(f"Không tìm thấy artifact model: {path}")


def save_model_artifact(estimator: Any, models_dir: Path, model_id: str) -> Path:
    """Persist an estimator without mixing research artifacts into runtime paths."""
    if isinstance(estimator, PhoBERTFineTuner):
        artifact_path = models_dir / model_id
        estimator.save_pretrained(artifact_path)
        return artifact_path
    artifact_path = models_dir / f"{model_id}.joblib"
    joblib.dump(estimator, artifact_path, compress=3)
    return artifact_path


def process_memory_snapshot() -> dict[str, float | None]:
    """Read current and high-water RSS on Linux without adding a runtime dependency."""
    status_path = Path("/proc/self/status")
    if not status_path.is_file():
        return {"rss_megabytes": None, "high_water_megabytes": None}
    values: dict[str, float | None] = {"rss_megabytes": None, "high_water_megabytes": None}
    for line in status_path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key not in {"VmRSS", "VmHWM"}:
            continue
        amount_kib = value.strip().split(maxsplit=1)[0]
        if amount_kib.isdigit():
            result_key = "rss_megabytes" if key == "VmRSS" else "high_water_megabytes"
            values[result_key] = round(int(amount_kib) / 1024, 6)
    return values


def memory_delta_megabytes(before: dict[str, float | None], after: dict[str, float | None]) -> float | None:
    start = before["rss_megabytes"]
    end = after["rss_megabytes"]
    if start is None or end is None:
        return None
    return round(end - start, 6)


def phobert_config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model_name": args.phobert_model_name,
        "revision": args.phobert_revision,
        "max_length": args.phobert_max_length,
        "epochs": args.phobert_epochs,
        "learning_rate": args.phobert_learning_rate,
        "batch_size": args.phobert_batch_size,
        "device_preference": args.phobert_device,
        "allow_cpu": args.allow_cpu_phobert,
        "local_files_only": args.phobert_local_files_only,
    }


def preflight_phobert(config: dict[str, Any], seed: int) -> dict[str, Any]:
    """Validate local PhoBERT dependencies/device before creating any output directory."""
    candidate = PhoBERTFineTuner(seed=seed, **config)
    torch, _auto_model, _auto_tokenizer, _word_tokenize = candidate._dependencies()
    device = candidate._resolve_device(torch)
    return {
        "device": str(device),
        "cuda_available": bool(torch.cuda.is_available()),
        "torch_version": str(torch.__version__),
        "note": "Checkpoint availability is verified only when fine-tuning starts.",
    }


def evaluate(estimator: Any, x: Any, y: list[int]) -> dict[str, Any]:
    started = time.perf_counter()
    prediction = estimator.predict(x)
    elapsed_seconds = time.perf_counter() - started
    precision, recall, f1, support = precision_recall_fscore_support(
        y, prediction, labels=LABELS, zero_division=0
    )
    return {
        "rows": len(y),
        "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "macro_f1": float(np.mean(f1)),
        "per_code": {
            str(label): {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(LABELS)
        },
        "confusion_matrix_true_rows_predicted_columns": confusion_matrix(y, prediction, labels=LABELS).tolist(),
        "prediction_seconds_total": round(elapsed_seconds, 6),
        "prediction_milliseconds_per_row": round(elapsed_seconds * 1000 / len(y), 6),
    }


def benchmark_single_request_latency(
    estimator: Any,
    texts: list[str],
    input_kind: str,
    *,
    warmup_requests: int = 10,
    measured_requests: int = 50,
) -> dict[str, Any]:
    """Measure local p50/p95 latency for one request at a time without emitting text.

    This is a technical benchmark only.  It includes model_input() and predict()
    in one local Python process, but excludes transcript capture, network I/O,
    API serialization, dashboard rendering and model loading from disk.
    """
    if not texts:
        raise ValueError("Không thể benchmark latency trên danh sách text rỗng.")
    if warmup_requests < 0 or measured_requests < 1:
        raise ValueError("warmup_requests phải >= 0 và measured_requests phải >= 1.")

    sample_count = min(measured_requests, len(texts))
    sample_indices = np.linspace(0, len(texts) - 1, num=sample_count, dtype=int)
    warmup_count = min(warmup_requests, sample_count)
    for index in sample_indices[:warmup_count]:
        estimator.predict(model_input([texts[int(index)]], input_kind))

    latencies_ms: list[float] = []
    for index in sample_indices:
        started = time.perf_counter_ns()
        estimator.predict(model_input([texts[int(index)]], input_kind))
        latencies_ms.append((time.perf_counter_ns() - started) / 1_000_000)

    values = np.asarray(latencies_ms, dtype=np.float64)
    return {
        "request_count": int(sample_count),
        "warmup_request_count": int(warmup_count),
        "p50_milliseconds": round(float(np.percentile(values, 50)), 6),
        "p95_milliseconds": round(float(np.percentile(values, 95)), 6),
        "mean_milliseconds": round(float(np.mean(values)), 6),
        "max_milliseconds": round(float(np.max(values)), 6),
        "measurement_scope": (
            "single local request; includes input transformation and predict; excludes "
            "model loading, transcript capture, network, API and dashboard"
        ),
    }


def percentage(value: float) -> str:
    return f"{value * 100:.2f}%"


def metric(value: float) -> str:
    return f"{value:.4f}"


def optional_number(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_report(results: dict[str, Any]) -> str:
    corpus = results["corpus"]
    rows = []
    for item in results["models"]:
        validation = item["validation"]
        test = item["test"]
        latency = item["single_request_latency"]
        process_memory = item["process_memory"]
        runtime_metadata = item.get("runtime_metadata", {})
        rows.append(
            "| {name} | {val} | {test_f1} | {bal} | {acc} | {f1_0} | {f1_1} | {size:.2f} | {rss} | {gpu} | {p50:.3f} | {p95:.3f} |".format(
                name=item["display_name"],
                val=metric(validation["macro_f1"]),
                test_f1=metric(test["macro_f1"]),
                bal=metric(test["balanced_accuracy"]),
                acc=metric(test["accuracy"]),
                f1_0=metric(test["per_code"]["0"]["f1"]),
                f1_1=metric(test["per_code"]["1"]["f1"]),
                size=item["artifact_size_megabytes"],
                rss=optional_number(process_memory["rss_delta_megabytes"]),
                gpu=optional_number(runtime_metadata.get("cuda_peak_allocated_megabytes")),
                p50=latency["p50_milliseconds"],
                p95=latency["p95_milliseconds"],
            )
        )

    selected = results["provisional_selection"]
    split_lines = []
    for split in SPLITS:
        counts = corpus["split_label_counts"][split]
        split_lines.append(f"| {split} | {corpus['split_rows'][split]} | {counts['0']} | {counts['1']} |")

    return f"""# So sánh mô hình — corpus legacy binary

> {SCOPE_WARNING}

## Phạm vi và tính tái lập

- Dataset: `{results['dataset']['name']}`; SHA-256 split đã được kiểm trước khi huấn luyện.
- Thời điểm chạy (UTC): {results['run']['started_at_utc']}; seed: `{results['run']['seed']}`.
- Tất cả cấu hình được cố định trước khi xem test. Validation được dùng để chọn ứng viên tạm thời; test được chạy một lần cho từng cấu hình cố định.
- Nhãn chỉ là mã legacy `0` và `1`. Báo cáo không diễn giải chúng là tích cực/tiêu cực, không suy ra trầm cảm, và không có khuyến nghị lâm sàng.

## Quy mô dữ liệu

| Split | Số dòng | Mã 0 | Mã 1 |
| --- | ---: | ---: | ---: |
{chr(10).join(split_lines)}

Tỷ lệ mã `0:1` toàn corpus là `{corpus['class_ratio_code_0_to_code_1']:.3f}:1`.

## Kết quả

| Mô hình | Validation macro-F1 | Test macro-F1 | Test balanced accuracy | Test accuracy | Test F1 mã 0 | Test F1 mã 1 | Artifact MB | RSS Δ MB | GPU peak MB | p50 ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

Ứng viên tạm thời theo validation macro-F1: **{selected['display_name']}** (`{selected['model_id']}`, {metric(selected['validation_macro_f1'])}). Việc chọn này chỉ có giá trị trong nghiên cứu legacy.

`length-only-logreg` là đối chứng chẩn đoán: nếu điểm của nó cao, độ dài văn bản có thể đang dự báo mã nhãn. Nó không phải bằng chứng cho hiểu biết ngữ nghĩa. `RSS Δ MB` là biến thiên RSS của process quanh một lần fit; `GPU peak MB` chỉ có khi chạy CUDA. `p50/p95` là latency local của từng request sau warm-up; chúng bao gồm biến đổi input và predict, nhưng loại trừ transcript capture, network, API, dashboard, model load. Vì vậy chúng chỉ để sàng lọc kỹ thuật trước realtime, không phải SLA production.

## Các model hiện có trong ứng dụng: không so sánh trực tiếp

`baseline-rules-v2`, adapter TF-IDF runtime và trainer PhoBERT của dự án yêu cầu contract `negative/neutral/positive`, `meeting_id`, dữ liệu transcript đã phê duyệt cùng quy tắc quyền riêng tư. Corpus này chỉ có mã `0/1` legacy và không có đơn vị cuộc họp. Vì vậy chúng được **loại trừ**, không ép ánh xạ nhãn và không sinh “điểm so sánh” giả tạo.

## Diễn giải bị giới hạn

- EDA đã cho thấy provenance gắn hoàn toàn với mã nhãn và phân phối độ dài chênh rõ giữa hai mã. Các điểm số có thể phản ánh nguồn/độ dài/dấu vết tiền xử lý thay vì nội dung.
- Split là ngẫu nhiên theo văn bản, không phải split theo `meeting_id`; không thể tính CI bootstrap theo đơn vị cuộc họp, không có inter-annotator agreement và không có nhãn sentiment ba lớp.
- Artifact ở `models/` chỉ để tái lập thí nghiệm local; tuyệt đối không chuyển sang API/dashboard hay bảng kết quả chính của Chương 8.
- Chỉ khi có corpus meeting đã phê duyệt, nhãn ba lớp, `meeting_id` và phép đo end-to-end mới có thể dùng latency để quyết định realtime.
- RSS delta có thể âm do allocator/reclaim của process; không dùng cột này để suy ra RAM peak độc lập của model. Với PhoBERT trên GPU, ưu tiên `GPU peak MB` và đo lại trong môi trường deploy mục tiêu.

## Artifact

- `results.json`: metric đầy đủ, confusion matrix, artifact size, latency local p50/p95, môi trường và hash.
- `run-manifest.json`: lệnh tái lập, cấu hình cố định và các ràng buộc phạm vi.
- `models/*.joblib` hoặc `models/phobert-finetune/`: estimator research-only; có thể chứa vocabulary/trọng số dẫn xuất từ corpus, không phát hành công khai.
"""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    corpus_dir = args.corpus_dir.resolve()
    output_dir = args.output_dir.resolve()
    if "approved" in output_dir.parts:
        raise ValueError("Output bị từ chối: experiment legacy không được đặt trong approved/.")
    if output_dir.exists():
        raise FileExistsError(f"Output đã tồn tại: {output_dir}. Không ghi đè artifact.")
    staging_dir = output_dir.with_name(f"{output_dir.name}.partial")
    if staging_dir.exists():
        raise FileExistsError(f"Staging đã tồn tại: {staging_dir}. Hãy kiểm tra trước khi chạy lại.")

    phobert_environment = (
        preflight_phobert(phobert_config_from_args(args), args.seed) if args.include_phobert else None
    )
    corpus, manifest = load_and_validate_corpus(corpus_dir)
    train_texts, train_labels = corpus["train"]
    validation_texts, validation_labels = corpus["validation"]
    test_texts, test_labels = corpus["test"]
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    staging_dir.mkdir(parents=True)
    models_dir = staging_dir / "models"
    models_dir.mkdir()
    model_results: list[dict[str, Any]] = []

    try:
        for model_id, display_name, estimator, input_kind in build_models(
            args.seed,
            include_phobert=args.include_phobert,
            phobert_config=phobert_config_from_args(args),
        ):
            train_input = model_input(train_texts, input_kind)
            validation_input = model_input(validation_texts, input_kind)
            test_input = model_input(test_texts, input_kind)
            memory_before_fit = process_memory_snapshot()
            fit_started = time.perf_counter()
            estimator.fit(train_input, train_labels)
            fit_seconds = time.perf_counter() - fit_started
            memory_after_fit = process_memory_snapshot()

            validation_result = evaluate(estimator, validation_input, validation_labels)
            test_result = evaluate(estimator, test_input, test_labels)
            model_path = save_model_artifact(estimator, models_dir, model_id)
            single_request_latency = benchmark_single_request_latency(
                estimator, test_texts, input_kind
            )
            artifact_bytes = artifact_size_bytes(model_path)
            model_results.append(
                {
                    "model_id": model_id,
                    "display_name": display_name,
                    "input_kind": input_kind,
                    "fit_seconds": round(fit_seconds, 6),
                    "validation": validation_result,
                    "test": test_result,
                    "artifact_size_bytes": artifact_bytes,
                    "artifact_size_megabytes": round(artifact_bytes / (1024 * 1024), 6),
                    "single_request_latency": single_request_latency,
                    "process_memory": {
                        "before_fit": memory_before_fit,
                        "after_fit": memory_after_fit,
                        "rss_delta_megabytes": memory_delta_megabytes(
                            memory_before_fit, memory_after_fit
                        ),
                    },
                    "runtime_metadata": getattr(estimator, "runtime_metadata", {}),
                    "artifact": str(model_path.relative_to(staging_dir)),
                }
            )

        selection = max(
            model_results,
            key=lambda item: (item["validation"]["macro_f1"], item["model_id"]),
        )
        split_rows = {split: len(corpus[split][0]) for split in SPLITS}
        split_label_counts = {
            split: {str(label): int(Counter(corpus[split][1])[label]) for label in LABELS}
            for split in SPLITS
        }
        total_counts = Counter(label for split in SPLITS for label in corpus[split][1])
        results: dict[str, Any] = {
            "scope": {
                "warning": SCOPE_WARNING,
                "allowed_use": "local legacy research comparison only",
                "excluded_from": [
                    "meeting-sentiment production runtime",
                    "API and dashboard",
                    "source/model-artifacts",
                    "source/model-data/approved",
                    "Chapter 8 primary meeting-sentiment results",
                ],
            },
            "dataset": {
                "name": manifest.get("dataset_name", corpus_dir.name),
                "dataset_kind": manifest["dataset_kind"],
                "corpus_dir": str(corpus_dir),
                "output_sha256_verified": {split: sha256_file(corpus_dir / f"{split}.csv") for split in SPLITS},
                "manifest_sha256": sha256_file(corpus_dir / "dataset-manifest.json"),
            },
            "run": {
                "started_at_utc": started_at,
                "finished_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "seed": args.seed,
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "numpy": np.__version__,
                "scikit_learn": sklearn.__version__,
                "joblib": joblib.__version__,
            },
            "corpus": {
                "split_rows": split_rows,
                "split_label_counts": split_label_counts,
                "total_rows": sum(split_rows.values()),
                "total_label_counts": {str(label): int(total_counts[label]) for label in LABELS},
                "class_ratio_code_0_to_code_1": total_counts[0] / total_counts[1],
                "split_policy": "Loaded as supplied; fixed configs fit only on train. Validation ranks candidates; test evaluated once per fixed candidate.",
            },
            "fixed_model_specs": {
                "majority-class": {"strategy": "most_frequent"},
                "length-only-logreg": {"features": ["log1p(characters)", "log1p(whitespace_tokens)"], "class_weight": "balanced", "max_iter": 2000},
                "word-tfidf-logreg": {"analyzer": "word", "ngram_range": [1, 2], "min_df": 2, "max_features": 100000, "sublinear_tf": True, "class_weight": "balanced", "max_iter": 2000},
                "char-tfidf-logreg": {"analyzer": "char_wb", "ngram_range": [3, 5], "min_df": 2, "max_features": 100000, "sublinear_tf": True, "class_weight": "balanced", "max_iter": 2000},
                **(
                    {
                        "phobert-finetune": {
                            **phobert_config_from_args(args),
                            "environment_preflight": phobert_environment,
                            "preprocessing": "underthesea.word_tokenize(format='text')",
                            "label_codes": list(LABELS),
                        }
                    }
                    if args.include_phobert
                    else {}
                ),
            },
            "models": model_results,
            "provisional_selection": {
                "model_id": selection["model_id"],
                "display_name": selection["display_name"],
                "validation_macro_f1": selection["validation"]["macro_f1"],
                "selection_rule": "highest validation macro-F1; fixed configurations only",
            },
            "realtime_readiness": {
                "status": "not_eligible_for_meeting_realtime_from_legacy_corpus",
                "technical_screening_available": True,
                "local_benchmark_scope": (
                    "Artifact size and single-request local p50/p95 are available only "
                    "for technical screening; they exclude I/O and do not establish an SLA."
                ),
                "required_before_any_realtime_selection": [
                    "approved meeting transcript corpus with consent and retention controls",
                    "negative/neutral/positive/unknown label contract",
                    "meeting_id group split and a locked test set",
                    "end-to-end latency measurement in the target deployment environment",
                    "human review or shadow-mode protocol",
                ],
            },
            "non_comparable_existing_runtime": [
                {
                    "component": "baseline-rules-v2 and meeting TF-IDF runtime adapter",
                    "reason": "They require negative/neutral/positive meeting-sentiment labels, whereas this corpus has anonymous legacy codes 0/1.",
                },
                {
                    "component": "train_meeting_sentiment_phobert.py",
                    "reason": "It requires approved meeting data, meeting_id and the three-class contract; it is intentionally not run here.",
                },
            ],
            "limitations": [
                "No semantic interpretation is assigned to label codes 0/1.",
                "No meeting_id exists: meeting-level holdout and meeting-level bootstrap confidence intervals are unavailable.",
                "EDA reports complete provenance/label association and substantial length differences, so scores can reflect provenance or length confounds.",
                "No annotator agreement, consent record or approved meeting transcript is present in this corpus.",
            ],
        }
        write_json(staging_dir / "results.json", results)
        write_json(
            staging_dir / "run-manifest.json",
            {
                "scope_warning": SCOPE_WARNING,
                "command": (
                    "python Reports/New_folder/tram_cam/tools/train_compare_legacy_binary_models.py "
                    "--corpus-dir Reports/New_folder/tram_cam/derived/legacy-binary-tram-cam-v1 "
                    "--output-dir <new-legacy-output-dir> --seed 42"
                    + (" --include-phobert <PhoBERT-options>" if args.include_phobert else "")
                ),
                "input_manifest": str(corpus_dir / "dataset-manifest.json"),
                "input_manifest_sha256": sha256_file(corpus_dir / "dataset-manifest.json"),
                "verified_split_hashes": results["dataset"]["output_sha256_verified"],
                "fixed_model_specs": results["fixed_model_specs"],
                "no_test_tuning": True,
                "test_evaluation_policy": "Once for each fixed candidate after validation evaluation.",
                "single_request_latency_policy": (
                    "50 evenly spaced test records after 10 warm-up requests; local model_input "
                    "and predict only, without text output."
                ),
                "include_phobert": args.include_phobert,
                "phobert_config": phobert_config_from_args(args) if args.include_phobert else None,
                "phobert_environment_preflight": phobert_environment,
            },
        )
        (staging_dir / "comparison.md").write_text(render_report(results), encoding="utf-8")
        staging_dir.replace(output_dir)
    except Exception:
        # Preserve a partial run for inspection instead of silently deleting generated artifacts.
        raise

    print(f"Completed legacy-only comparison: {output_dir}")
    print("Models evaluated: " + ", ".join(item["model_id"] for item in model_results))
    print("No raw corpus text was emitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
