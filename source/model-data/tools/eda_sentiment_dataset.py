#!/usr/bin/env python3
"""Create a privacy-preserving EDA report for three sentiment CSV splits.

The report contains only aggregate counts and length statistics. It never emits
the source text, speaker identity, or a sample row, so it can be stored next to
an approved dataset manifest without exposing transcript content.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any


MODEL_DATA_ROOT = Path(__file__).resolve().parents[1]
if str(MODEL_DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_DATA_ROOT))

from meeting_dataset_quality import (  # noqa: E402
    DATASET_PROFILES,
    evaluate_dataset,
    require_ready,
    write_quality_report,
)

SPLITS = ("train", "validation", "test")
DEFAULT_LABELS = ("negative", "neutral", "positive")
REQUIRED_COLUMNS = frozenset({"text", "label", "meeting_id"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate aggregate EDA for train/validation/test sentiment CSVs.")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--dataset-profile", choices=DATASET_PROFILES, default="approved-meeting")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument(
        "--group-id-meaning",
        default="meeting ID",
        help="Describe what meeting_id represents. Do not call a synthetic ID a meeting ID.",
    )
    parser.add_argument(
        "--limitation",
        action="append",
        default=[],
        help="Add a limitation to the report. Repeat this option for multiple limitations.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def normalise_text(value: str) -> str:
    return " ".join(value.strip().split())


def text_hash(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()


def read_split(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"split file does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = frozenset(reader.fieldnames or ())
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"{path.name} is missing required column(s): {', '.join(sorted(missing))}")
        records: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            text = normalise_text(row.get("text") or "")
            label = (row.get("label") or "").strip().lower()
            group = (row.get("meeting_id") or "").strip()
            if not text or not label or not group:
                raise ValueError(f"{path.name}:{line_number} has an empty text, label, or meeting_id")
            records.append({"text": text, "label": label, "meeting_id": group})
    if not records:
        raise ValueError(f"{path.name} has no data row")
    return records


def nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        raise ValueError("cannot calculate a percentile for an empty collection")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def length_summary(values: list[int]) -> dict[str, float | int]:
    return {
        "min": min(values),
        "mean": round(statistics.fmean(values), 2),
        "median": nearest_rank(values, 0.50),
        "p95": nearest_rank(values, 0.95),
        "max": max(values),
    }


def label_summary(records: list[dict[str, str]], labels: tuple[str, ...]) -> dict[str, dict[str, float | int]]:
    counts = Counter(record["label"] for record in records)
    unknown = set(counts) - set(labels)
    if unknown:
        raise ValueError(f"unsupported label(s): {', '.join(sorted(unknown))}")
    total = len(records)
    return {
        label: {"count": counts[label], "percent": round(100 * counts[label] / total, 2)} for label in labels
    }


def split_summary(records: list[dict[str, str]], labels: tuple[str, ...]) -> dict[str, Any]:
    text_lengths = [len(record["text"]) for record in records]
    token_lengths = [len(record["text"].split()) for record in records]
    hashes = [text_hash(record["text"]) for record in records]
    return {
        "rows": len(records),
        "unique_group_ids": len({record["meeting_id"] for record in records}),
        "unique_texts": len(set(hashes)),
        "duplicate_text_rows": len(hashes) - len(set(hashes)),
        "label_distribution": label_summary(records, labels),
        "character_length": length_summary(text_lengths),
        "whitespace_token_length": length_summary(token_lengths),
    }


def shared_text_count(left: list[dict[str, str]], right: list[dict[str, str]]) -> int:
    return len({text_hash(record["text"]) for record in left} & {text_hash(record["text"]) for record in right})


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    divider = ["---"] * len(headers)
    rendered = ["| " + " | ".join(headers) + " |", "| " + " | ".join(divider) + " |"]
    rendered.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(rendered)


def render_markdown(summary: dict[str, Any]) -> str:
    labels = summary["labels"]
    split_rows = []
    for split in SPLITS:
        item = summary["splits"][split]
        split_rows.append(
            [
                split,
                str(item["rows"]),
                str(item["unique_group_ids"]),
                str(item["duplicate_text_rows"]),
                str(item["whitespace_token_length"]["median"]),
                str(item["whitespace_token_length"]["p95"]),
            ]
        )
    label_rows = []
    overall = summary["overall"]["label_distribution"]
    for label in labels:
        values = overall[label]
        label_rows.append([label, str(values["count"]), f"{values['percent']:.2f}%"])
    leakage = summary["quality"]["cross_split_exact_text"]
    quality_rows = [
        ["Empty text", str(summary["quality"]["empty_text_rows"])],
        ["Exact text: train / validation", str(leakage["train_validation"])],
        ["Exact text: train / test", str(leakage["train_test"])],
        ["Exact text: validation / test", str(leakage["validation_test"])],
        ["Group-ID meaning", summary["group_id_meaning"]],
    ]
    limitations = summary["limitations"] or ["No limitation supplied by the caller."]
    return "\n".join(
        [
            f"# EDA — {summary['dataset_name']}",
            "",
            "> Generated from aggregate statistics only; no source text is included.",
            "",
            "## Dataset overview",
            "",
            f"- Total rows: {summary['overall']['rows']}",
            f"- Unique normalized texts: {summary['overall']['unique_texts']}",
            f"- Labels: {', '.join(labels)}",
            "",
            markdown_table(
                ["Split", "Rows", "Unique group IDs", "Duplicate text rows", "Median tokens", "P95 tokens"], split_rows
            ),
            "",
            "## Label distribution",
            "",
            markdown_table(["Label", "Rows", "Share"], label_rows),
            "",
            "## Text length",
            "",
            "Token length uses whitespace tokenization for EDA only; PhoBERT tokenization is separate.",
            "",
            markdown_table(
                ["Measure", "Characters: min / median / P95 / max", "Whitespace tokens: min / median / P95 / max"],
                [
                    [
                        "All splits",
                        " / ".join(str(summary["overall"]["character_length"][key]) for key in ("min", "median", "p95", "max")),
                        " / ".join(
                            str(summary["overall"]["whitespace_token_length"][key])
                            for key in ("min", "median", "p95", "max")
                        ),
                    ]
                ],
            ),
            "",
            "## Split integrity",
            "",
            markdown_table(["Check", "Result"], quality_rows),
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in limitations],
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    paths = {"train": args.train, "validation": args.validation, "test": args.test}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "eda-summary.json"
    markdown_path = args.output_dir / "eda-report.md"
    quality_path = args.output_dir / "quality-report.json"
    if not args.overwrite and (json_path.exists() or markdown_path.exists() or quality_path.exists()):
        raise ValueError("EDA output exists; use --overwrite to replace it")

    checked_records, quality_report = evaluate_dataset(
        paths,
        profile=args.dataset_profile,
        manifest_path=args.dataset_manifest,
        expected_dataset_version=args.dataset_version,
    )
    write_quality_report(quality_path, quality_report, overwrite=args.overwrite)
    require_ready(quality_report)
    records = {
        name: [
            {"text": item.text, "label": item.label, "meeting_id": item.meeting_id}
            for item in checked_records[name]
        ]
        for name in SPLITS
    }
    labels = DEFAULT_LABELS
    all_records = [record for split in SPLITS for record in records[split]]
    summary = {
        "dataset_name": args.dataset_name,
        "labels": list(labels),
        "group_id_meaning": args.group_id_meaning,
        "inputs": {name: path.name for name, path in paths.items()},
        "splits": {name: split_summary(records[name], labels) for name in SPLITS},
        "overall": {
            "rows": len(all_records),
            "unique_texts": len({text_hash(record["text"]) for record in all_records}),
            "label_distribution": label_summary(all_records, labels),
            "character_length": length_summary([len(record["text"]) for record in all_records]),
            "whitespace_token_length": length_summary([len(record["text"].split()) for record in all_records]),
        },
        "quality": {
            "empty_text_rows": sum(not record["text"] for record in all_records),
            "cross_split_exact_text": {
                "train_validation": shared_text_count(records["train"], records["validation"]),
                "train_test": shared_text_count(records["train"], records["test"]),
                "validation_test": shared_text_count(records["validation"], records["test"]),
            },
        },
        "limitations": args.limitation,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        raise SystemExit(f"ERROR: {error}")
