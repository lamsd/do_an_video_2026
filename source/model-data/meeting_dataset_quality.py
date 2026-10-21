"""Privacy-preserving quality gate for meeting-sentiment CSV splits.

The gate only emits aggregate statistics, file hashes, and structural errors.
It never writes source text, speaker identifiers, or sample rows to a report.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SPLITS = ("train", "validation", "test")
LABELS = ("negative", "neutral", "positive")
REQUIRED_COLUMNS = frozenset({"text", "label", "meeting_id"})
PROFILE_APPROVED_MEETING = "approved-meeting"
PROFILE_PROXY_SMOKE = "proxy-smoke"
DATASET_PROFILES = (PROFILE_APPROVED_MEETING, PROFILE_PROXY_SMOKE)

_PROFILE_MANIFEST_RULES = {
    PROFILE_APPROVED_MEETING: {
        "dataset_kind": "consented-meeting-transcript-sentiment",
        "required_fields": (
            "dataset_version",
            "dataset_kind",
            "source",
            "license_or_consent",
            "collection_period",
            "redaction_policy",
            "label_guideline_version",
            "annotation_policy",
            "split_policy",
            "meeting_id_policy",
            "output_sha256",
        ),
    },
    PROFILE_PROXY_SMOKE: {
        "dataset_kind": "external-emotion-to-polarity-proxy",
        "required_fields": (
            "dataset_version",
            "dataset_kind",
            "intended_use",
            "prohibited_use",
            "meeting_id_policy",
            "output_sha256",
        ),
    },
}


@dataclass(frozen=True)
class Record:
    text: str
    label: str
    meeting_id: str


class DatasetQualityError(ValueError):
    """Raised when a dataset cannot pass the pre-training quality gate."""


def normalise_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def text_hash(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _error(path: Path, message: str) -> DatasetQualityError:
    return DatasetQualityError(f"{path.name}: {message}")


def read_split(path: Path) -> list[Record]:
    """Read one UTF-8 split and reject invalid rows without exposing their text."""
    if not path.is_file():
        raise _error(path, "split file does not exist")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = frozenset(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise _error(path, f"missing required column(s): {', '.join(missing)}")
        records: list[Record] = []
        for line_number, row in enumerate(reader, start=2):
            text = normalise_text(row.get("text") or "")
            label = (row.get("label") or "").strip().lower()
            meeting_id = (row.get("meeting_id") or "").strip()
            if not text or not label or not meeting_id:
                raise _error(path, f"row {line_number} has an empty text, label, or meeting_id")
            if label not in LABELS:
                raise _error(path, f"row {line_number} has unsupported label {label!r}")
            records.append(Record(text=text, label=label, meeting_id=meeting_id))
    if not records:
        raise _error(path, "has no data row")
    return records


def read_splits(paths: Mapping[str, Path]) -> dict[str, list[Record]]:
    expected = set(SPLITS)
    if set(paths) != expected:
        raise DatasetQualityError(f"split names must be exactly: {', '.join(SPLITS)}")
    records: dict[str, list[Record]] = {}
    errors: list[str] = []
    for name in SPLITS:
        try:
            records[name] = read_split(paths[name])
        except DatasetQualityError as error:
            errors.append(str(error))
    if errors:
        raise DatasetQualityError("; ".join(errors))
    return records


def _nearest_rank(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _length_summary(values: list[int]) -> dict[str, float | int]:
    return {
        "min": min(values),
        "mean": round(statistics.fmean(values), 2),
        "median": _nearest_rank(values, 0.50),
        "p95": _nearest_rank(values, 0.95),
        "max": max(values),
    }


def _split_summary(records: list[Record]) -> dict[str, Any]:
    hashes = [text_hash(record.text) for record in records]
    labels = Counter(record.label for record in records)
    groups = Counter(record.meeting_id for record in records)
    lengths = [len(record.text) for record in records]
    token_lengths = [len(record.text.split()) for record in records]
    return {
        "rows": len(records),
        "unique_meeting_ids": len(groups),
        "single_unit_meeting_ids": sum(count == 1 for count in groups.values()),
        "unique_texts": len(set(hashes)),
        "duplicate_text_rows": len(hashes) - len(set(hashes)),
        "label_counts": {label: labels[label] for label in LABELS},
        "character_length": _length_summary(lengths),
        "whitespace_token_length": _length_summary(token_lengths),
        "rows_over_256_whitespace_tokens": sum(length > 256 for length in token_lengths),
    }


def _pairwise_overlap(values: Mapping[str, set[str]]) -> dict[str, int]:
    return {
        "train_validation": len(values["train"] & values["validation"]),
        "train_test": len(values["train"] & values["test"]),
        "validation_test": len(values["validation"] & values["test"]),
    }


def _load_manifest(path: Path | None) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    if path is None:
        return None, None, ["dataset manifest is required"]
    if not path.is_file():
        return None, None, [f"dataset manifest does not exist: {path.name}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, None, [f"dataset manifest is not valid JSON: {path.name}"]
    if not isinstance(value, dict):
        return None, None, ["dataset manifest must be a JSON object"]
    return value, sha256_file(path), []


def _validate_manifest(
    manifest: dict[str, Any] | None,
    *,
    paths: Mapping[str, Path],
    profile: str,
    expected_dataset_version: str | None,
) -> list[str]:
    if manifest is None:
        return []
    rules = _PROFILE_MANIFEST_RULES[profile]
    issues: list[str] = []
    for key in rules["required_fields"]:
        if key not in manifest or manifest[key] in (None, "", [], {}):
            issues.append(f"manifest missing required field: {key}")
    if manifest.get("dataset_kind") != rules["dataset_kind"]:
        issues.append(
            f"manifest dataset_kind must be {rules['dataset_kind']!r} for profile {profile!r}"
        )
    if expected_dataset_version and manifest.get("dataset_version") != expected_dataset_version:
        issues.append("manifest dataset_version does not match --dataset-version")
    output_hashes = manifest.get("output_sha256")
    if isinstance(output_hashes, dict):
        for split in SPLITS:
            expected_hash = output_hashes.get(split)
            if not isinstance(expected_hash, str) or not expected_hash:
                issues.append(f"manifest output_sha256 missing {split}")
            elif not paths[split].is_file():
                issues.append(f"split file does not exist: {paths[split].name}")
            elif expected_hash != sha256_file(paths[split]):
                issues.append(f"manifest output_sha256 does not match {split}.csv")
    elif "output_sha256" in manifest:
        issues.append("manifest output_sha256 must map train, validation, and test")
    return issues


def evaluate_dataset(
    paths: Mapping[str, Path],
    *,
    profile: str = PROFILE_APPROVED_MEETING,
    manifest_path: Path | None = None,
    expected_dataset_version: str | None = None,
) -> tuple[dict[str, list[Record]], dict[str, Any]]:
    """Return parsed records and an aggregate preflight report.

    A malformed split still produces a report with blocking issues where possible,
    enabling CI or a researcher to see why training did not start.
    """
    if profile not in DATASET_PROFILES:
        raise DatasetQualityError(f"unsupported dataset profile: {profile}")

    manifest, manifest_hash, manifest_issues = _load_manifest(manifest_path)
    issues = list(manifest_issues)
    issues.extend(
        _validate_manifest(
            manifest,
            paths=paths,
            profile=profile,
            expected_dataset_version=expected_dataset_version,
        )
    )
    records: dict[str, list[Record]] = {}
    try:
        records = read_splits(paths)
    except DatasetQualityError as error:
        issues.append(str(error))

    report: dict[str, Any] = {
        "schema_version": 1,
        "dataset_profile": profile,
        "dataset_version": expected_dataset_version or (manifest or {}).get("dataset_version"),
        "manifest_sha256": manifest_hash,
        "input_sha256": {name: sha256_file(path) if path.is_file() else None for name, path in paths.items()},
        "blocking_issues": issues,
        "warnings": [],
        "splits": {},
        "quality": {},
        "ready_to_train": False,
    }
    if not records:
        return records, report

    split_summaries = {name: _split_summary(records[name]) for name in SPLITS}
    text_sets = {name: {text_hash(record.text) for record in records[name]} for name in SPLITS}
    meeting_sets = {name: {record.meeting_id for record in records[name]} for name in SPLITS}
    text_overlap = _pairwise_overlap(text_sets)
    meeting_overlap = _pairwise_overlap(meeting_sets)
    report["splits"] = split_summaries
    report["quality"] = {
        "cross_split_exact_text": text_overlap,
        "cross_split_meeting_id": meeting_overlap,
    }

    for split, summary in split_summaries.items():
        missing_labels = [label for label, count in summary["label_counts"].items() if count == 0]
        if missing_labels:
            issues.append(f"{split} is missing label(s): {', '.join(missing_labels)}")
        if summary["duplicate_text_rows"]:
            issues.append(f"{split} has {summary['duplicate_text_rows']} duplicate normalized text row(s)")
        if summary["unique_meeting_ids"] < 2:
            report["warnings"].append(f"{split} has fewer than two meeting IDs")
        if summary["single_unit_meeting_ids"] == summary["unique_meeting_ids"]:
            report["warnings"].append(
                f"every meeting_id in {split} has one unit; group-level generalization is not measurable"
            )
        if summary["rows_over_256_whitespace_tokens"]:
            report["warnings"].append(
                f"{split} has {summary['rows_over_256_whitespace_tokens']} row(s) over 256 whitespace tokens; "
                "review truncation/chunking policy"
            )
        if profile == PROFILE_APPROVED_MEETING and any(
            record.meeting_id.startswith("proxy-") for record in records[split]
        ):
            issues.append(f"{split} uses a proxy-prefixed meeting_id under the approved-meeting profile")

    for pair, count in text_overlap.items():
        if count:
            issues.append(f"exact-text leakage between {pair.replace('_', ' / ')}: {count}")
    for pair, count in meeting_overlap.items():
        if count:
            issues.append(f"meeting_id leakage between {pair.replace('_', ' / ')}: {count}")

    report["blocking_issues"] = issues
    report["ready_to_train"] = not issues
    return records, report


def require_ready(report: Mapping[str, Any]) -> None:
    issues = report.get("blocking_issues", [])
    if issues:
        raise DatasetQualityError("quality gate blocked training: " + "; ".join(str(item) for item in issues))


def write_quality_report(path: Path, report: Mapping[str, Any], *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise DatasetQualityError(f"quality report already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
