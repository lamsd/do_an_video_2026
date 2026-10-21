from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODEL_DATA_ROOT = Path(__file__).resolve().parents[1]
if str(MODEL_DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_DATA_ROOT))

from meeting_dataset_quality import evaluate_dataset, sha256_file


def write_split(path: Path, prefix: str) -> None:
    rows = [
        {"text": f"{prefix} văn bản tiêu cực một", "label": "negative", "meeting_id": f"{prefix}-a"},
        {"text": f"{prefix} văn bản trung tính một", "label": "neutral", "meeting_id": f"{prefix}-a"},
        {"text": f"{prefix} văn bản tích cực một", "label": "positive", "meeting_id": f"{prefix}-a"},
        {"text": f"{prefix} văn bản tiêu cực hai", "label": "negative", "meeting_id": f"{prefix}-b"},
        {"text": f"{prefix} văn bản trung tính hai", "label": "neutral", "meeting_id": f"{prefix}-b"},
        {"text": f"{prefix} văn bản tích cực hai", "label": "positive", "meeting_id": f"{prefix}-b"},
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["text", "label", "meeting_id"])
        writer.writeheader()
        writer.writerows(rows)


def write_manifest(path: Path, splits: dict[str, Path], version: str = "meeting-test-v1") -> None:
    manifest = {
        "dataset_version": version,
        "dataset_kind": "consented-meeting-transcript-sentiment",
        "source": "consented test fixture",
        "license_or_consent": "test consent record",
        "collection_period": "2026-10",
        "redaction_policy": "test redaction",
        "label_guideline_version": "test-v1",
        "annotation_policy": "two annotators and adjudication",
        "split_policy": "split by meeting_id",
        "meeting_id_policy": "stable internal meeting IDs",
        "output_sha256": {name: sha256_file(value) for name, value in splits.items()},
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")


class MeetingDatasetQualityTests(unittest.TestCase):
    def test_approved_dataset_passes_with_manifest_and_disjoint_splits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = {name: root / f"{name}.csv" for name in ("train", "validation", "test")}
            for name, path in paths.items():
                write_split(path, name)
            manifest_path = root / "dataset-manifest.json"
            write_manifest(manifest_path, paths)

            records, report = evaluate_dataset(
                paths,
                manifest_path=manifest_path,
                expected_dataset_version="meeting-test-v1",
            )

            self.assertTrue(report["ready_to_train"])
            self.assertEqual(18, sum(len(value) for value in records.values()))
            self.assertEqual(0, report["quality"]["cross_split_exact_text"]["train_validation"])

    def test_duplicate_text_between_splits_blocks_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = {name: root / f"{name}.csv" for name in ("train", "validation", "test")}
            for name, path in paths.items():
                write_split(path, name)
            with paths["test"].open("a", encoding="utf-8", newline="") as stream:
                csv.DictWriter(stream, fieldnames=["text", "label", "meeting_id"]).writerow(
                    {"text": "train văn bản tiêu cực một", "label": "negative", "meeting_id": "test-c"}
                )
            manifest_path = root / "dataset-manifest.json"
            write_manifest(manifest_path, paths)

            _, report = evaluate_dataset(
                paths,
                manifest_path=manifest_path,
                expected_dataset_version="meeting-test-v1",
            )

            self.assertFalse(report["ready_to_train"])
            self.assertTrue(any("exact-text leakage" in issue for issue in report["blocking_issues"]))

    def test_manifest_hash_mismatch_blocks_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = {name: root / f"{name}.csv" for name in ("train", "validation", "test")}
            for name, path in paths.items():
                write_split(path, name)
            manifest_path = root / "dataset-manifest.json"
            write_manifest(manifest_path, paths)
            with paths["train"].open("a", encoding="utf-8", newline="") as stream:
                csv.DictWriter(stream, fieldnames=["text", "label", "meeting_id"]).writerow(
                    {"text": "train bản ghi sau khi tạo manifest", "label": "positive", "meeting_id": "train-c"}
                )

            _, report = evaluate_dataset(
                paths,
                manifest_path=manifest_path,
                expected_dataset_version="meeting-test-v1",
            )

            self.assertFalse(report["ready_to_train"])
            self.assertTrue(any("output_sha256 does not match train.csv" in issue for issue in report["blocking_issues"]))

    def test_missing_training_schema_returns_blocking_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = {name: root / f"{name}.csv" for name in ("train", "validation", "test")}
            for path in paths.values():
                path.write_text("text_vi,sentiment\nMẫu,0\n", encoding="utf-8")
            manifest_path = root / "dataset-manifest.json"
            write_manifest(manifest_path, paths)

            _, report = evaluate_dataset(
                paths,
                manifest_path=manifest_path,
                expected_dataset_version="meeting-test-v1",
            )

            self.assertFalse(report["ready_to_train"])
            self.assertTrue(any("missing required column(s)" in issue for issue in report["blocking_issues"]))


if __name__ == "__main__":
    unittest.main()
