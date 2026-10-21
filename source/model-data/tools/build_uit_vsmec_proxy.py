#!/usr/bin/env python3
"""Build a clearly labelled UIT-VSMEC polarity *proxy* for Colab smoke tests.

This tool preserves UIT-VSMEC's supplied train/validation/test partitions and
maps only unambiguous emotion labels to three polarity labels.  It is not a
meeting-transcript dataset and it must not be used to claim meeting-sentiment
quality, populate the production registry, or replace a consented holdout set.

The output has the PhoBERT training schema ``text,label,meeting_id`` only when
``--smoke-test`` is supplied.  In that case ``meeting_id`` is deliberately a
synthetic, per-row ID with the ``proxy-vsmec-`` prefix.  It is not a real meeting
identifier; its only purpose is to exercise the current leakage checks without
misrepresenting the data source.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET


SPLITS = ("train", "validation", "test")
LABELS = ("negative", "neutral", "positive")
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Surprise is intentionally excluded by default: it is not reliably positive
# or neutral without reviewing its context for this three-polarity task.
EMOTION_TO_POLARITY = {
    "Anger": "negative",
    "Disgust": "negative",
    "Fear": "negative",
    "Sadness": "negative",
    "Enjoyment": "positive",
    "Other": "neutral",
}
KNOWN_EMOTIONS = frozenset((*EMOTION_TO_POLARITY, "Surprise"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert official UIT-VSMEC partitions into a polarity proxy for a PhoBERT smoke test."
    )
    parser.add_argument("--train-xlsx", type=Path, required=True, help="Official UIT-VSMEC train XLSX.")
    parser.add_argument("--validation-xlsx", type=Path, required=True, help="Official UIT-VSMEC validation XLSX.")
    parser.add_argument("--test-xlsx", type=Path, required=True, help="Official UIT-VSMEC test XLSX.")
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory for the proxy files.")
    parser.add_argument("--dataset-version", default="uit-vsmec-polarity-proxy-v1")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Acknowledge synthetic meeting IDs and write files compatible with the current Colab trainer.",
    )
    parser.add_argument(
        "--include-surprise-as-neutral",
        action="store_true",
        help="Map Surprise to neutral. Omit this flag to exclude it (recommended).",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def column_name(cell_reference: str) -> str:
    match = re.match(r"([A-Z]+)", cell_reference)
    if not match:
        raise ValueError("XLSX contains a cell without a column reference")
    return match.group(1)


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        document = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter(XML_NS + "t")) for item in document.findall(XML_NS + "si")]


def cell_value(cell: ET.Element, strings: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(XML_NS + "is")
        return "" if inline is None else "".join(node.text or "" for node in inline.iter(XML_NS + "t"))
    raw_node = cell.find(XML_NS + "v")
    raw = "" if raw_node is None or raw_node.text is None else raw_node.text
    if cell_type == "s":
        try:
            return strings[int(raw)]
        except (IndexError, ValueError) as error:
            raise ValueError("XLSX shared-string reference is invalid") from error
    return raw


def iter_xlsx_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    if not path.is_file():
        raise ValueError(f"input file does not exist: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            strings = shared_strings(archive)
            worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (ET.ParseError, KeyError, zipfile.BadZipFile) as error:
        raise ValueError(f"could not read worksheet 1 from {path.name}") from error

    rows: list[tuple[int, dict[str, str]]] = []
    for row in worksheet.findall(".//" + XML_NS + "row"):
        values = {
            column_name(cell.get("r", "")): cell_value(cell, strings)
            for cell in row.findall(XML_NS + "c")
        }
        if values:
            rows.append((int(row.get("r", "0")), values))
    if not rows:
        raise ValueError(f"{path.name} has no rows")

    header_row, header_cells = rows[0]
    headers = {value.strip(): column for column, value in header_cells.items() if value.strip()}
    missing = {"Emotion", "Sentence"} - set(headers)
    if missing:
        raise ValueError(f"{path.name} is missing required column(s): {', '.join(sorted(missing))}")

    for row_number, cells in rows[1:]:
        yield row_number, {header: cells.get(column, "") for header, column in headers.items()}


def normalise_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def text_hash(text: str) -> str:
    return hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()


def build_split(
    source_path: Path,
    split: str,
    mapping: dict[str, str],
    seen_all_splits: set[str],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    records: list[dict[str, str]] = []
    seen_in_split: set[str] = set()
    dropped_emotions: Counter[str] = Counter()
    dropped_duplicates = {"within_split": 0, "earlier_split": 0}
    source_rows = 0

    for row_number, row in iter_xlsx_rows(source_path):
        source_rows += 1
        emotion = row.get("Emotion", "").strip()
        text = normalise_text(row.get("Sentence", ""))
        if emotion not in KNOWN_EMOTIONS:
            raise ValueError(f"{source_path.name}:{row_number} has unknown emotion label {emotion!r}")
        if not text:
            raise ValueError(f"{source_path.name}:{row_number} has an empty sentence")
        label = mapping.get(emotion)
        if label is None:
            dropped_emotions[emotion] += 1
            continue

        digest = text_hash(text)
        if digest in seen_in_split:
            dropped_duplicates["within_split"] += 1
            continue
        if digest in seen_all_splits:
            dropped_duplicates["earlier_split"] += 1
            continue

        seen_in_split.add(digest)
        seen_all_splits.add(digest)
        records.append(
            {
                "text": text,
                "label": label,
                # This explicit prefix prevents callers from treating it as a real
                # meeting identifier in manifests or evaluation reports.
                "meeting_id": f"proxy-vsmec-{split}-{row_number:05d}",
            }
        )

    labels = Counter(record["label"] for record in records)
    missing_labels = [label for label in LABELS if not labels[label]]
    if missing_labels:
        raise ValueError(f"{split} has no example(s) for: {', '.join(missing_labels)}")
    return records, {
        "source_rows": source_rows,
        "retained_rows": len(records),
        "label_counts": dict(sorted(labels.items())),
        "dropped_emotion_counts": dict(sorted(dropped_emotions.items())),
        "dropped_duplicate_counts": dropped_duplicates,
    }


def write_csv(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["text", "label", "meeting_id"])
        writer.writeheader()
        writer.writerows(records)


def verify_output(splits: dict[str, list[dict[str, str]]]) -> None:
    for split, records in splits.items():
        labels = Counter(record["label"] for record in records)
        if set(labels) != set(LABELS):
            raise ValueError(f"generated {split} split does not contain exactly the three expected labels")
        hashes = [text_hash(record["text"]) for record in records]
        if len(hashes) != len(set(hashes)):
            raise ValueError(f"generated {split} split contains duplicate text")
    for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
        left_hashes = {text_hash(record["text"]) for record in splits[left]}
        right_hashes = {text_hash(record["text"]) for record in splits[right]}
        if left_hashes & right_hashes:
            raise ValueError(f"generated proxy has text leakage between {left} and {right}")


def main() -> int:
    args = parse_args()
    if not args.smoke_test:
        raise ValueError("refusing to create training-compatible proxy files without --smoke-test acknowledgement")
    if args.output_dir.exists():
        raise ValueError(f"output directory already exists: {args.output_dir}")

    mapping = dict(EMOTION_TO_POLARITY)
    if args.include_surprise_as_neutral:
        mapping["Surprise"] = "neutral"
    input_paths = {
        "train": args.train_xlsx,
        "validation": args.validation_xlsx,
        "test": args.test_xlsx,
    }

    seen_all_splits: set[str] = set()
    output_splits: dict[str, list[dict[str, str]]] = {}
    split_summary: dict[str, dict[str, object]] = {}
    for split in SPLITS:
        records, summary = build_split(input_paths[split], split, mapping, seen_all_splits)
        output_splits[split] = records
        split_summary[split] = summary
    verify_output(output_splits)

    args.output_dir.mkdir(parents=True, exist_ok=False)
    for split in SPLITS:
        write_csv(args.output_dir / f"{split}.csv", output_splits[split])

    manifest = {
        "dataset_version": args.dataset_version,
        "dataset_kind": "external-emotion-to-polarity-proxy",
        "intended_use": "PhoBERT/Colab smoke test and schema integration only",
        "prohibited_use": [
            "meeting sentiment quality claim",
            "production model promotion",
            "Chapter 8 final test metric",
            "replacement for consented meeting transcript data",
        ],
        "source": "UIT-VSMEC XLSX partitions supplied in this repository",
        "label_mapping": mapping,
        "excluded_emotions": sorted(KNOWN_EMOTIONS - set(mapping)),
        "split_policy": "preserve source partitions; remove exact-text duplicates from later partitions",
        "meeting_id_policy": "synthetic per-row ID prefixed proxy-vsmec-; not a meeting identifier",
        "input_sha256": {split: sha256_file(path) for split, path in input_paths.items()},
        "split_summary": split_summary,
        "output_sha256": {split: sha256_file(args.output_dir / f"{split}.csv") for split in SPLITS},
    }
    (args.output_dir / "dataset-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    for split in SPLITS:
        summary = split_summary[split]
        print(f"{split}: {summary['retained_rows']} rows; labels={summary['label_counts']}")
    print(f"Created proxy dataset: {args.output_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
