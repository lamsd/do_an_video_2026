#!/usr/bin/env python3
"""Audit and mirror UIT-VSMEC XLSX splits as a separate legacy multiclass corpus.

This tool intentionally preserves the publisher-provided split assignment. It does
not convert emotion labels to binary sentiment and it never writes to approved
meeting-sentiment data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import unicodedata
import xml.etree.ElementTree as etree
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
TEXT_COLUMNS = ("text_vi", "sentence", "text", "content", "utterance")
LABEL_COLUMNS = ("emotion", "label", "sentiment")


@dataclass(frozen=True)
class SourceRecord:
    text_vi: str
    source_label: str
    source_split: str
    source_file: str
    source_row: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalise_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def text_key(text: str) -> str:
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


def column_index(reference: str) -> int:
    """Return zero-based column index from an XLSX reference such as B17."""

    letters = "".join(char for char in reference if char.isalpha())
    if not letters:
        raise ValueError(f"Ô XLSX không có tham chiếu cột hợp lệ: {reference!r}")
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = etree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.itertext()) for node in root.findall(f"{XLSX_NS}si")]


def read_xlsx_rows(path: Path) -> tuple[list[tuple[int, str]], list[list[str]], list[dict[str, int]]]:
    """Read a simple XLSX sheet with the Python standard library only."""

    if not path.is_file():
        raise ValueError(f"Không tìm thấy tệp UIT-VSMEC: {path}")
    with zipfile.ZipFile(path) as archive:
        sheet_names = [name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")]
        if len(sheet_names) != 1:
            raise ValueError(f"{path} phải có đúng một worksheet, nhận được {len(sheet_names)}.")
        strings = shared_strings(archive)
        sheet_root = etree.fromstring(archive.read(sheet_names[0]))

    rows: list[list[str]] = []
    for row in sheet_root.findall(f".//{XLSX_NS}sheetData/{XLSX_NS}row"):
        values: dict[int, str] = {}
        next_index = 0
        for cell in row.findall(f"{XLSX_NS}c"):
            index = column_index(cell.attrib["r"]) if "r" in cell.attrib else next_index
            next_index = index + 1
            cell_type = cell.attrib.get("t")
            value_node = cell.find(f"{XLSX_NS}v")
            if cell_type == "s" and value_node is not None:
                shared_index = int(value_node.text or "0")
                value = strings[shared_index]
            elif cell_type == "inlineStr":
                inline = cell.find(f"{XLSX_NS}is")
                value = "".join(inline.itertext()) if inline is not None else ""
            else:
                value = value_node.text if value_node is not None and value_node.text is not None else ""
            values[index] = value
        if values:
            rows.append([values.get(index, "") for index in range(max(values) + 1)])

    if not rows:
        raise ValueError(f"{path} không có dòng dữ liệu.")
    raw_headers = [value.strip().lstrip("\ufeff") for value in rows[0]]
    width = len(raw_headers)
    data_rows = [row + [""] * (width - len(row)) for row in rows[1:]]
    named_headers = [(index, name) for index, name in enumerate(raw_headers) if name]
    unnamed_indexes = [index for index, name in enumerate(raw_headers) if not name]
    if not named_headers or len({name for _, name in named_headers}) != len(named_headers):
        raise ValueError(f"{path} có header trùng lặp hoặc không có header hợp lệ.")
    unnamed_columns = [
        {
            "zero_based_column_index": index,
            "nonempty_cells": sum(bool(row[index].strip()) for row in data_rows),
        }
        for index in unnamed_indexes
    ]
    return named_headers, data_rows, unnamed_columns


def select_column(headers: list[str], candidates: tuple[str, ...], role: str) -> str:
    matched = [header for header in headers if header.strip().casefold() in candidates]
    if len(matched) != 1:
        raise ValueError(
            f"Không xác định được duy nhất cột {role}; headers={headers!r}, candidates={list(candidates)!r}."
        )
    return matched[0]


def read_split(path: Path, split_name: str) -> tuple[list[SourceRecord], dict[str, object]]:
    indexed_headers, rows, unnamed_columns = read_xlsx_rows(path)
    headers = [name for _, name in indexed_headers]
    text_column = select_column(headers, TEXT_COLUMNS, "nội dung")
    label_column = select_column(headers, LABEL_COLUMNS, "nhãn")
    text_index = next(index for index, name in indexed_headers if name == text_column)
    label_index = next(index for index, name in indexed_headers if name == label_column)
    records: list[SourceRecord] = []

    for source_row, row in enumerate(rows, start=2):
        text = row[text_index]
        label = row[label_index].strip()
        if not normalise_text(text):
            raise ValueError(f"{path}:{source_row} có nội dung rỗng.")
        if not label:
            raise ValueError(f"{path}:{source_row} có nhãn rỗng.")
        records.append(
            SourceRecord(
                text_vi=text,
                source_label=label,
                source_split=split_name,
                source_file=path.name,
                source_row=source_row,
            )
        )

    metadata: dict[str, object] = {
        "filename": path.name,
        "sha256": sha256_file(path),
        "rows_read": len(records),
        "headers": headers,
        "text_column": text_column,
        "label_column": label_column,
        "label_counts": dict(sorted(Counter(record.source_label for record in records).items())),
        "excluded_unnamed_columns": unnamed_columns,
    }
    return records, metadata


def duplicate_audit(records: list[SourceRecord]) -> dict[str, object]:
    occurrences: dict[str, list[SourceRecord]] = defaultdict(list)
    for record in records:
        occurrences[text_key(record.text_vi)].append(record)

    within_split: dict[str, int] = {}
    split_sets: dict[str, set[str]] = defaultdict(set)
    for key, record_group in occurrences.items():
        split_counts = Counter(record.source_split for record in record_group)
        for split_name, count in split_counts.items():
            if count > 1:
                within_split[split_name] = within_split.get(split_name, 0) + count - 1
        for split_name in split_counts:
            split_sets[split_name].add(key)

    cross_split_keys = sum(1 for group in occurrences.values() if len({record.source_split for record in group}) > 1)
    label_conflict_keys = sum(1 for group in occurrences.values() if len({record.source_label for record in group}) > 1)
    flagged_keys = []
    for key, group in sorted(occurrences.items()):
        splits = {record.source_split for record in group}
        labels = {record.source_label for record in group}
        if len(splits) > 1 or len(labels) > 1:
            flagged_keys.append(
                {
                    "normalized_text_sha256": key,
                    "occurrences": [
                        {
                            "source_split": record.source_split,
                            "source_file": record.source_file,
                            "source_row": record.source_row,
                            "source_label": record.source_label,
                        }
                        for record in group
                    ],
                }
            )
    return {
        "normalization": "Unicode NFKC, collapse whitespace, casefold, SHA-256 key",
        "total_rows": len(records),
        "unique_normalized_texts": len(occurrences),
        "duplicate_rows": len(records) - len(occurrences),
        "within_source_split_duplicate_rows": dict(sorted(within_split.items())),
        "cross_source_split_duplicate_keys": cross_split_keys,
        "label_conflict_keys": label_conflict_keys,
        "flagged_collisions_without_text": flagged_keys,
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-input", type=Path, required=True)
    parser.add_argument("--validation-input", type=Path, required=True)
    parser.add_argument("--test-input", type=Path, required=True)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dataset-version", default="uit-vsmec-multiclass-legacy-v1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_specs = [
        ("train", args.train_input),
        ("validation", args.validation_input),
        ("test", args.test_input),
    ]
    records_by_split: dict[str, list[SourceRecord]] = {}
    input_metadata: dict[str, dict[str, object]] = {}
    all_records: list[SourceRecord] = []
    for split_name, path in source_specs:
        records, metadata = read_split(path, split_name)
        records_by_split[split_name] = records
        input_metadata[split_name] = metadata
        all_records.extend(records)

    audit = duplicate_audit(all_records)
    summary = {
        "dataset_kind": "legacy-vietnamese-multiclass-emotion-corpus",
        "input_splits": input_metadata,
        "combined_label_counts": dict(sorted(Counter(record.source_label for record in all_records).items())),
        "duplicate_audit": audit,
    }
    if args.audit_only:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0

    if args.output_dir is None:
        raise ValueError("Cần --output-dir khi không dùng --audit-only.")
    if args.output_dir.exists():
        raise FileExistsError(f"Thư mục đích đã tồn tại nên không ghi đè: {args.output_dir}")
    if audit["cross_source_split_duplicate_keys"]:
        raise ValueError("Có nội dung trùng giữa source split; không tạo corpus để tránh rò rỉ đánh giá.")
    if audit["label_conflict_keys"]:
        raise ValueError("Có cùng nội dung nhưng nhãn khác nhau; cần rà soát thủ công trước khi tạo corpus.")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    output_paths: dict[str, Path] = {}
    for split_name, records in records_by_split.items():
        output_path = args.output_dir / f"{split_name}.csv"
        write_csv(
            output_path,
            ["text_vi", "source_label"],
            [{"text_vi": record.text_vi, "source_label": record.source_label} for record in records],
        )
        output_paths[split_name] = output_path

    all_path = args.output_dir / "all_records.csv"
    write_csv(
        all_path,
        ["text_vi", "source_label", "source_split", "source_file"],
        [
            {
                "text_vi": record.text_vi,
                "source_label": record.source_label,
                "source_split": record.source_split,
                "source_file": record.source_file,
            }
            for record in all_records
        ],
    )
    output_paths["all_records"] = all_path

    manifest = {
        "schema_version": 1,
        "dataset_version": args.dataset_version,
        "dataset_kind": "legacy-vietnamese-multiclass-emotion-corpus",
        "intended_use": "Nghiên cứu offline về phân loại cảm xúc đa lớp tiếng Việt.",
        "prohibited_uses": [
            "Gộp hoặc ép nhãn vào corpus nhị phân tram_cam mà không có mapping được phê duyệt.",
            "Huấn luyện hoặc đánh giá MeetingSentiment-PhoBERT.",
            "Dùng trong dashboard, API, worker hoặc pilot phân tích cuộc họp.",
            "Sàng lọc, chẩn đoán hoặc suy luận sức khoẻ tâm thần về con người.",
        ],
        "label_semantics": "Giữ nguyên source_label từ workbook; công cụ không tự diễn giải hoặc đổi mapping nhãn.",
        "inputs": input_metadata,
        "combined_label_counts": summary["combined_label_counts"],
        "split_policy": "Giữ nguyên phân chia train/validation/test do nguồn cung cấp; không tái chia.",
        "duplicate_audit": audit,
        "output_sha256": {name: sha256_file(path) for name, path in sorted(output_paths.items())},
        "limitations": [
            "Không có tài liệu giấy phép hoặc citation của UIT-VSMEC trong thư mục nguồn; phải xác minh trước khi phân phối hoặc huấn luyện.",
            "Nhãn đa lớp không tương đương nhãn sentiment nhị phân và không phải transcript cuộc họp.",
            "Đây là bản mirror nghiên cứu; không phải dữ liệu approved cho use case cuộc họp.",
        ],
    }
    (args.output_dir / "dataset-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "README.md").write_text(
        "# UIT-VSMEC multiclass legacy corpus\n\n"
        "Corpus này mirror ba split XLSX gốc với nhãn đa lớp giữ nguyên dưới tên `source_label`. "
        "Công cụ không đổi nhãn cảm xúc sang nhãn sentiment nhị phân.\n\n"
        "Không được gộp vào `approved/meeting-sentiment-pilot-v1`, model/dashboard/API/pilot cuộc họp, "
        "hoặc dùng để suy luận sức khoẻ tâm thần. Trước khi train hoặc phân phối, xác minh license, "
        "citation và điều kiện sử dụng từ nguồn UIT-VSMEC chính thức.\n\n"
        "Các file `train.csv`, `validation.csv`, `test.csv` giữ nguyên split nguồn; `all_records.csv` "
        "bổ sung provenance. `dataset-manifest.json` lưu hash, schema, thống kê nhãn và audit trùng lặp.\n",
        encoding="utf-8",
    )
    print(json.dumps({"output_dir": str(args.output_dir), **summary}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError, zipfile.BadZipFile) as error:
        print(f"LỖI: {error}", file=sys.stderr)
        raise SystemExit(2)
