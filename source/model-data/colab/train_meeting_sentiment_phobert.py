"""Train MeetingSentiment-PhoBERT in Google Colab.

Colab setup (run in a notebook cell, then upload or mount only approved data):

    !pip -q install "transformers>=4.46,<5" "datasets>=3,<4" \
        "accelerate>=1,<2" "scikit-learn>=1.4,<2" "underthesea>=6,<9"
    !python train_meeting_sentiment_phobert.py \
        --train /content/data/train.csv \
        --validation /content/data/validation.csv \
        --test /content/data/test.csv \
        --dataset-manifest /content/data/dataset-manifest.json \
        --dataset-version meeting-sentiment-consented-v1 \
        --model-version meeting-sentiment-phobert-v1 \
        --output-dir /content/meeting-sentiment-phobert-v1

Each CSV must be UTF-8 and have exactly these semantic fields:
    text,label,meeting_id

`label` is one of negative, neutral, positive. `meeting_id` is mandatory so the
script can reject leakage across train/validation/test. Do not use this script
with depression, clinical, or unapproved transcript datasets.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


MODEL_DATA_ROOT = Path(__file__).resolve().parents[1]
if str(MODEL_DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_DATA_ROOT))

from meeting_dataset_quality import (  # noqa: E402
    DATASET_PROFILES,
    LABELS,
    DatasetQualityError,
    Record,
    evaluate_dataset,
    require_ready,
    write_quality_report,
)

import numpy as np
from datasets import Dataset
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments
from underthesea import word_tokenize


LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune PhoBERT for consented meeting-transcript sentiment.")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--dataset-profile", choices=DATASET_PROFILES, default="approved-meeting")
    parser.add_argument(
        "--acknowledge-proxy-smoke",
        action="store_true",
        help="Required with --dataset-profile proxy-smoke; proxy outputs are never meeting-quality evidence.",
    )
    parser.add_argument(
        "--quality-report",
        type=Path,
        help="Optional path to write the aggregate preflight report, including when validation is blocked.",
    )
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--model-name", default="vinai/phobert-base-v2")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--epochs", type=float, default=4.0)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-coverage", type=float, default=0.80)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the three splits and exit without downloading a model or creating an artifact.",
    )
    return parser.parse_args()


def segment(text: str) -> str:
    # PhoBERT was trained with Vietnamese word segmentation. Keep the raw source
    # text outside this training script; this string is only the model input.
    return word_tokenize(text, format="text")


def to_dataset(examples: list[Record], tokenizer: Any, max_length: int) -> Dataset:
    dataset = Dataset.from_dict(
        {
            "text": [segment(example.text) for example in examples],
            "labels": [LABEL_TO_ID[example.label] for example in examples],
        }
    )
    return dataset.map(
        lambda batch: tokenizer(batch["text"], truncation=True, max_length=max_length),
        batched=True,
        remove_columns=["text"],
    )


def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    scaled = logits / temperature
    shifted = scaled - scaled.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    # Deterministic grid search keeps the Colab dependency set minimal.
    candidates = np.linspace(0.5, 3.0, 101)
    losses = []
    for temperature in candidates:
        probabilities = softmax(logits, float(temperature))
        losses.append(float(-np.log(np.clip(probabilities[np.arange(len(labels)), labels], 1e-12, 1.0)).mean()))
    return float(candidates[int(np.argmin(losses))])


def choose_unknown_threshold(probabilities: np.ndarray, labels: np.ndarray, min_coverage: float) -> dict[str, float]:
    best: dict[str, float] | None = None
    predicted = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    for threshold in np.linspace(1 / len(LABELS), 0.95, 63):
        accepted = confidence >= threshold
        coverage = float(accepted.mean())
        if coverage < min_coverage or accepted.sum() == 0:
            continue
        score = float(f1_score(labels[accepted], predicted[accepted], labels=range(len(LABELS)), average="macro", zero_division=0))
        candidate = {"threshold": float(threshold), "coverage": coverage, "accepted_macro_f1": score}
        if best is None or (score, coverage) > (best["accepted_macro_f1"], best["coverage"]):
            best = candidate
    if best is None:
        raise ValueError("no unknown threshold satisfies --min-coverage on validation data")
    return best


def metrics(labels: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict[str, Any]:
    predicted = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    accepted = confidence >= threshold
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predicted, labels=range(len(LABELS)), zero_division=0
    )
    result: dict[str, Any] = {
        "accuracy": float(accuracy_score(labels, predicted)),
        "macro_f1": float(f1_score(labels, predicted, labels=range(len(LABELS)), average="macro", zero_division=0)),
        "coverage": float(accepted.mean()),
        "unknown_rate": float((~accepted).mean()),
        "confusion_matrix": confusion_matrix(labels, predicted, labels=range(len(LABELS))).tolist(),
        "per_label": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(LABELS)
        },
    }
    if accepted.any():
        result["accepted_macro_f1"] = float(
            f1_score(labels[accepted], predicted[accepted], labels=range(len(LABELS)), average="macro", zero_division=0)
        )
    return result


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not 0 < args.min_coverage <= 1:
        raise ValueError("--min-coverage must be in (0, 1]")
    if args.dataset_profile == "proxy-smoke" and not args.acknowledge_proxy_smoke:
        raise ValueError("--dataset-profile proxy-smoke requires --acknowledge-proxy-smoke")
    random.seed(args.seed)
    np.random.seed(args.seed)

    splits, quality_report = evaluate_dataset(
        {"train": args.train, "validation": args.validation, "test": args.test},
        profile=args.dataset_profile,
        manifest_path=args.dataset_manifest,
        expected_dataset_version=args.dataset_version,
    )
    if args.quality_report:
        write_quality_report(args.quality_report, quality_report)
    require_ready(quality_report)
    if args.validate_only:
        for name, examples in splits.items():
            label_counts = Counter(example.label for example in examples)
            meeting_count = len({example.meeting_id for example in examples})
            print(f"{name}: {len(examples)} examples; {meeting_count} groups; labels={dict(label_counts)}")
        print("Quality gate passed. No model or artifact was created.")
        return 0
    if args.output_dir is None:
        raise ValueError("--output-dir is required unless --validate-only is set")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / "quality-report.json", quality_report)
    (args.output_dir / "dataset-manifest.json").write_bytes(args.dataset_manifest.read_bytes())

    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_fast=False)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=len(LABELS),
        id2label={index: label for index, label in enumerate(LABELS)},
        label2id=LABEL_TO_ID,
    )
    encoded = {name: to_dataset(examples, tokenizer, args.max_length) for name, examples in splits.items()}

    def compute_metrics(prediction: Any) -> dict[str, float]:
        logits, labels = prediction
        predicted = np.argmax(logits, axis=1)
        return {
            "macro_f1": float(f1_score(labels, predicted, labels=range(len(LABELS)), average="macro", zero_division=0)),
            "accuracy": float(accuracy_score(labels, predicted)),
        }

    training_args = TrainingArguments(
        output_dir=str(args.output_dir / "checkpoints"),
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        num_train_epochs=args.epochs,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        seed=args.seed,
        report_to="none",
        logging_strategy="steps",
        logging_steps=25,
        save_total_limit=2,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=encoded["train"],
        eval_dataset=encoded["validation"],
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
    )
    trainer.train()

    validation_prediction = trainer.predict(encoded["validation"])
    validation_logits = np.asarray(validation_prediction.predictions)
    validation_labels = np.asarray(validation_prediction.label_ids)
    temperature = fit_temperature(validation_logits, validation_labels)
    threshold_selection = choose_unknown_threshold(
        softmax(validation_logits, temperature), validation_labels, args.min_coverage
    )

    test_prediction = trainer.predict(encoded["test"])
    test_logits = np.asarray(test_prediction.predictions)
    test_labels = np.asarray(test_prediction.label_ids)
    threshold = threshold_selection["threshold"]
    evaluation = {
        "schema_version": 1,
        "model_type": "phobert-sequence-classification",
        "model_version": args.model_version,
        "dataset_version": args.dataset_version,
        "dataset_profile": args.dataset_profile,
        "dataset_manifest_sha256": quality_report["manifest_sha256"],
        "quality_gate": {
            "ready_to_train": quality_report["ready_to_train"],
            "warning_count": len(quality_report["warnings"]),
        },
        "labels": list(LABELS),
        "temperature": temperature,
        "unknown_threshold": threshold,
        "threshold_selection_validation": threshold_selection,
        "validation": metrics(validation_labels, softmax(validation_logits, temperature), threshold),
        "test": metrics(test_labels, softmax(test_logits, temperature), threshold),
        "split_counts": {
            name: {"units": len(examples), "meetings": len({item.meeting_id for item in examples})}
            for name, examples in splits.items()
        },
        "hyperparameters": {
            "base_model": args.model_name,
            "max_length": args.max_length,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "batch_size": args.batch_size,
            "seed": args.seed,
        },
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
    }
    trainer.save_model(str(args.output_dir / "model"))
    tokenizer.save_pretrained(str(args.output_dir / "model"))
    write_json(args.output_dir / "evaluation.json", evaluation)
    write_json(args.output_dir / "label_mapping.json", LABEL_TO_ID)
    (args.output_dir / "MODEL_CARD.md").write_text(
        "# MeetingSentiment-PhoBERT\n\n"
        f"- Model version: `{args.model_version}`\n"
        f"- Dataset version: `{args.dataset_version}`\n"
        f"- Dataset profile: `{args.dataset_profile}`\n"
        "- Task: three-class polarity of consented Vietnamese meeting transcript units.\n"
        "- Labels: `negative`, `neutral`, `positive`; low-confidence inference is `unknown`.\n"
        "- Not for depression screening, clinical assessment, employment, education, or automated decisions about people.\n"
        "- See `evaluation.json` for the locked-test metrics, threshold and calibration temperature.\n",
        encoding="utf-8",
    )
    print(json.dumps({"model_version": args.model_version, "output_dir": str(args.output_dir), "test": evaluation["test"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DatasetQualityError as error:
        raise SystemExit(f"ERROR: {error}")
