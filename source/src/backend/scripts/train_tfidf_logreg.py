"""Train a versioned Vietnamese TF-IDF + Logistic Regression sentiment artifact.

This command is intentionally separate from runtime. It accepts only an approved
CSV corpus, writes no raw text to the artifact metadata, and evaluates the
provided hold-out split exactly once. It does not make quality claims for a
different domain such as meeting transcripts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


MODEL_DATA_ROOT = Path(__file__).resolve().parents[3] / "model-data"
if str(MODEL_DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_DATA_ROOT))

from meeting_dataset_quality import (  # noqa: E402
    DATASET_PROFILES,
    DatasetQualityError,
    evaluate_dataset,
    require_ready,
)

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline

LABELS = ("negative", "neutral", "positive")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metrics(y_true: list[str], y_pred: list[str]) -> dict:
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, zero_division=0
    )
    return {
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(LABELS)
        },
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
        "labels": list(LABELS),
        "classification_report": classification_report(
            y_true, y_pred, labels=LABELS, output_dict=True, zero_division=0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--dataset-profile", choices=DATASET_PROFILES, default="approved-meeting")
    parser.add_argument("--acknowledge-proxy-smoke", action="store_true")
    arguments = parser.parse_args()

    if arguments.dataset_profile == "proxy-smoke" and not arguments.acknowledge_proxy_smoke:
        raise ValueError("--dataset-profile proxy-smoke requires --acknowledge-proxy-smoke")
    checked_records, quality_report = evaluate_dataset(
        {"train": arguments.train, "validation": arguments.validation, "test": arguments.test},
        profile=arguments.dataset_profile,
        manifest_path=arguments.dataset_manifest,
        expected_dataset_version=arguments.dataset_version,
    )
    require_ready(quality_report)
    split_rows = {
        name: (
            [record.text for record in checked_records[name]],
            [record.label for record in checked_records[name]],
            {record.meeting_id for record in checked_records[name]},
        )
        for name in ("train", "validation", "test")
    }
    meeting_ids = {name: rows[2] for name, rows in split_rows.items()}

    train_texts, train_labels, _ = split_rows["train"]
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("classifier", LogisticRegression(max_iter=2_000, class_weight="balanced", random_state=42)),
        ]
    )
    pipeline.fit(train_texts, train_labels)

    arguments.output.mkdir(parents=True, exist_ok=False)
    (arguments.output / "quality-report.json").write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (arguments.output / "dataset-manifest.json").write_bytes(arguments.dataset_manifest.read_bytes())
    model_path = arguments.output / "model.joblib"
    joblib.dump(
        {
            "schema_version": 1,
            "model_type": "tfidf-logreg",
            "model_version": arguments.model_version,
            "labels": list(LABELS),
            "pipeline": pipeline,
        },
        model_path,
    )
    artifact_sha256 = _sha256(model_path)
    validation_texts, validation_labels, _ = split_rows["validation"]
    test_texts, test_labels, _ = split_rows["test"]
    evaluation = {
        "model_version": arguments.model_version,
        "dataset_version": arguments.dataset_version,
        "dataset_profile": arguments.dataset_profile,
        "dataset_manifest_sha256": quality_report["manifest_sha256"],
        "dataset_files": {
            name: {"path": str(path), "sha256": _sha256(path)}
            for name, path in {
                "train": arguments.train,
                "validation": arguments.validation,
                "test": arguments.test,
            }.items()
        },
        "split_counts": {name: len(rows[0]) for name, rows in split_rows.items()},
        "split_label_counts": {name: dict(Counter(rows[1])) for name, rows in split_rows.items()},
        "meeting_ids_present": {name: bool(ids) for name, ids in meeting_ids.items()},
        "validation": _metrics(validation_labels, pipeline.predict(validation_texts).tolist()),
        "test": _metrics(test_labels, pipeline.predict(test_texts).tolist()),
    }
    metadata = {
        "schema_version": 1,
        "model_type": "tfidf-logreg",
        "model_version": arguments.model_version,
        "dataset_version": arguments.dataset_version,
        "dataset_profile": arguments.dataset_profile,
        "artifact_sha256": artifact_sha256,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "labels": list(LABELS),
        "runtime_note": "Trusted local artifact only; do not load unverified joblib files.",
    }
    (arguments.output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (arguments.output / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"artifact_dir": str(arguments.output), **metadata, "test_macro_f1": evaluation["test"]["macro_f1"]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except DatasetQualityError as error:
        raise SystemExit(f"ERROR: {error}")
