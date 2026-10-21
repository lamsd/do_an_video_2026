#!/usr/bin/env python3
"""Build a deduplicated legacy binary corpus from the tram_cam CSV exports.

This tool deliberately has no dependency on the MeetingSentiment data pipeline.
The source label codes have undocumented semantics, so they are emitted as
``legacy_label`` rather than sentiment names.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = {"text_vi", "sentiment"}
VALID_LABELS = {"0", "1"}


@dataclass
class LegacyRecord:
    """A source-deduplicated record, retaining only permitted provenance."""

    text_vi: str
    legacy_label: str
    source_files: set[str] = field(default_factory=set)


def normalize_for_deduplication(text: str) -> str:
    """Canonicalise only for equality comparison; retain the first raw text."""

    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def label_counts(rows: Iterable[LegacyRecord]) -> dict[str, int]:
    counts = Counter(row.legacy_label for row in rows)
    return {label: counts.get(label, 0) for label in sorted(VALID_LABELS)}


def read_and_coalesce(inputs: list[Path]) -> tuple[dict[str, LegacyRecord], dict[str, int]]:
    records: dict[str, LegacyRecord] = {}
    source_rows: dict[str, int] = {}

    for input_path in inputs:
        if not input_path.is_file():
            raise ValueError(f"Không tìm thấy tệp đầu vào: {input_path}")

        row_count = 0
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or [])
            missing_columns = REQUIRED_COLUMNS - headers
            if missing_columns:
                raise ValueError(
                    f"{input_path} thiếu cột bắt buộc: {', '.join(sorted(missing_columns))}"
                )

            for source_row_number, row in enumerate(reader, start=2):
                row_count += 1
                raw_text = row.get("text_vi") or ""
                canonical_text = normalize_for_deduplication(raw_text)
                label = (row.get("sentiment") or "").strip()

                if not canonical_text:
                    raise ValueError(f"{input_path}:{source_row_number} có text_vi rỗng.")
                if label not in VALID_LABELS:
                    raise ValueError(
                        f"{input_path}:{source_row_number} có nhãn không hợp lệ: {label!r}."
                    )

                key = sha256_bytes(canonical_text.encode("utf-8"))
                existing = records.get(key)
                if existing is None:
                    records[key] = LegacyRecord(
                        text_vi=raw_text,
                        legacy_label=label,
                        source_files={input_path.name},
                    )
                elif existing.legacy_label != label:
                    raise ValueError(
                        "Phát hiện nhãn mâu thuẫn cho cùng nội dung sau chuẩn hoá: "
                        f"{input_path}:{source_row_number}."
                    )
                else:
                    existing.source_files.add(input_path.name)

        source_rows[input_path.name] = row_count

    return records, source_rows


def deterministic_stratified_split(
    records: dict[str, LegacyRecord], *, seed: int, validation_ratio: float, test_ratio: float
) -> dict[str, list[tuple[str, LegacyRecord]]]:
    """Split each label deterministically by a salted hash of the canonical key."""

    split_rows: dict[str, list[tuple[str, LegacyRecord]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    by_label: dict[str, list[tuple[str, LegacyRecord]]] = {label: [] for label in sorted(VALID_LABELS)}
    for key, record in records.items():
        by_label[record.legacy_label].append((key, record))

    for label, rows in by_label.items():
        ordered_rows = sorted(
            rows,
            key=lambda item: sha256_bytes(f"{seed}\0{label}\0{item[0]}".encode("utf-8")),
        )
        validation_count = math.floor(len(ordered_rows) * validation_ratio)
        test_count = math.floor(len(ordered_rows) * test_ratio)
        split_rows["validation"].extend(ordered_rows[:validation_count])
        split_rows["test"].extend(ordered_rows[validation_count : validation_count + test_count])
        split_rows["train"].extend(ordered_rows[validation_count + test_count :])

    for split_name in split_rows:
        split_rows[split_name].sort(key=lambda item: item[0])
    return split_rows


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def count_by_source(records: Iterable[LegacyRecord]) -> dict[str, int]:
    counts = Counter(";".join(sorted(record.source_files)) for record in records)
    return dict(sorted(counts.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True, help="CSV input; pass twice.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-version", default="legacy-binary-tram-cam-v1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.80)
    parser.add_argument("--validation-ratio", type=float, default=0.10)
    parser.add_argument("--test-ratio", type=float, default=0.10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if len(args.input) != 2:
        raise ValueError("Cần đúng hai tệp --input theo phạm vi đã phê duyệt.")
    ratios = args.train_ratio + args.validation_ratio + args.test_ratio
    if not math.isclose(ratios, 1.0, abs_tol=1e-9):
        raise ValueError("Tổng train/validation/test ratio phải bằng 1.0.")
    if min(args.train_ratio, args.validation_ratio, args.test_ratio) <= 0:
        raise ValueError("Các tỷ lệ chia phải lớn hơn 0.")
    if args.output_dir.exists():
        raise FileExistsError(
            f"Thư mục đích đã tồn tại nên không ghi đè: {args.output_dir}"
        )

    records, source_rows = read_and_coalesce(args.input)
    source_total = sum(source_rows.values())
    split_rows = deterministic_stratified_split(
        records,
        seed=args.seed,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
    )

    args.output_dir.mkdir(parents=True, exist_ok=False)
    all_rows_path = args.output_dir / "all_deduplicated.csv"
    write_csv(
        all_rows_path,
        ["text_vi", "legacy_label", "source_files"],
        (
            {
                "text_vi": record.text_vi,
                "legacy_label": record.legacy_label,
                "source_files": ";".join(sorted(record.source_files)),
            }
            for _, record in sorted(records.items())
        ),
    )

    output_paths = {"all_deduplicated": all_rows_path}
    split_counts: dict[str, dict[str, object]] = {}
    for split_name, rows in split_rows.items():
        output_path = args.output_dir / f"{split_name}.csv"
        write_csv(
            output_path,
            ["text_vi", "legacy_label"],
            ({"text_vi": record.text_vi, "legacy_label": record.legacy_label} for _, record in rows),
        )
        output_paths[split_name] = output_path
        split_counts[split_name] = {"rows": len(rows), "label_counts": label_counts(record for _, record in rows)}

    manifest = {
        "schema_version": 1,
        "dataset_version": args.dataset_version,
        "dataset_kind": "legacy-binary-text-corpus",
        "intended_use": "Nghiên cứu offline về corpus nhị phân legacy.",
        "prohibited_uses": [
            "Huấn luyện hoặc đánh giá MeetingSentiment-PhoBERT.",
            "Dùng trong dashboard, API, worker hoặc pilot phân tích cuộc họp.",
            "Sàng lọc, chẩn đoán, can thiệp hoặc suy luận sức khoẻ tâm thần về con người.",
        ],
        "label_semantics": (
            "Mã nguồn 0/1 không có tài liệu ngữ nghĩa đáng tin cậy. "
            "Không được đổi tên thành positive/negative hay nhãn lâm sàng."
        ),
        "inputs": [
            {"filename": path.name, "rows_read": source_rows[path.name], "sha256": sha256_file(path)}
            for path in args.input
        ],
        "deduplication": {
            "canonicalization": "Unicode NFKC, collapse whitespace, casefold, SHA-256 key",
            "source_rows": source_total,
            "unique_rows": len(records),
            "coalesced_duplicate_rows": source_total - len(records),
            "conflicting_labels": 0,
            "provenance_group_counts": count_by_source(records.values()),
        },
        "split_policy": {
            "method": "deterministic stratified split by undocumented source code",
            "seed": args.seed,
            "requested_ratios": {
                "train": args.train_ratio,
                "validation": args.validation_ratio,
                "test": args.test_ratio,
            },
            "allocation": "floor validation/test per code; remainder to train",
            "group_aware": False,
        },
        "label_counts": label_counts(records.values()),
        "split_counts": split_counts,
        "output_sha256": {name: sha256_file(path) for name, path in sorted(output_paths.items())},
        "limitations": [
            "Không có meeting_id hoặc thực thể để chia theo nhóm và kiểm tra rò rỉ theo phiên.",
            "Không có tài liệu xác nhận ý nghĩa của mã 0/1.",
            "Dữ liệu không đại diện cho lời nói hoặc transcript cuộc họp thực tế.",
        ],
    }
    manifest_path = args.output_dir / "dataset-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    readme_path = args.output_dir / "README.md"
    readme_path.write_text(
        "# Legacy binary corpus — tram_cam v1\n\n"
        "## Phạm vi\n\n"
        "Corpus này chỉ phục vụ nghiên cứu offline về dữ liệu nhị phân legacy. "
        "Nó **không phải** dữ liệu sentiment cuộc họp, không thuộc `approved/`, "
        "và không được dùng để huấn luyện/đánh giá model, dashboard, API hay pilot cuộc họp. "
        "Không dùng cho sàng lọc hoặc suy luận sức khoẻ tâm thần.\n\n"
        "Nhãn `legacy_label` giữ nguyên mã nguồn `0`/`1`; ngữ nghĩa của chúng không được tài liệu hoá, "
        "nên không được diễn giải thành positive/negative hoặc nhãn lâm sàng.\n\n"
        "## Tệp\n\n"
        "- `all_deduplicated.csv`: hợp nhất đã khử trùng lặp, có tên tệp nguồn để truy vết.\n"
        "- `train.csv`, `validation.csv`, `test.csv`: chia xác định 80/10/10, stratified theo mã nhãn.\n"
        "- `dataset-manifest.json`: hash đầu vào/đầu ra, thống kê và giới hạn sử dụng.\n\n"
        "## Tái lập\n\n"
        "Chạy `python3 Reports/New_folder/tram_cam/tools/build_legacy_binary_corpus.py` với đúng hai "
        "tệp nguồn, thứ tự và tham số ghi trong manifest. Công cụ từ chối ghi đè thư mục đích.\n",
        encoding="utf-8",
    )

    # Aggregate-only output avoids exposing source text in logs.
    summary = {
        "output_dir": str(args.output_dir),
        "source_rows": source_total,
        "unique_rows": len(records),
        "label_counts": label_counts(records.values()),
        "split_counts": split_counts,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError) as error:
        print(f"LỖI: {error}", file=sys.stderr)
        raise SystemExit(2)
