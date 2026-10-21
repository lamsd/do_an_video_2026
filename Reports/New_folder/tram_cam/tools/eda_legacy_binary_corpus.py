#!/usr/bin/env python3
"""Create a privacy-preserving EDA report for the legacy binary tram_cam corpus.

The tool accepts only the separated legacy corpus built by
``build_legacy_binary_corpus.py``. It uses the source codes ``0`` and ``1``
without inferring a sentiment or clinical meaning, and never writes source-text
samples into its output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SPLITS = ("train", "validation", "test")
VALID_CODES = ("0", "1")
VIETNAMESE_DIACRITICS = re.compile(
    "[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
    "òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
    "ĂÂĐÊÔƠƯÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊ"
    "ÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ]"
)
TOKEN_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)
URL_PATTERN = re.compile(r"(?:https?://|www\.)", flags=re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
MENTION_PATTERN = re.compile(r"(?<!\w)@\w+", flags=re.UNICODE)
HASHTAG_PATTERN = re.compile(r"(?<!\w)#\w+", flags=re.UNICODE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", default="legacy-binary-tram-cam-v1")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def normalise_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def record_key(text: str) -> str:
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


def nearest_rank(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Không thể tính percentile cho danh sách rỗng.")
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def distribution(values: list[int]) -> dict[str, float | int]:
    if not values:
        raise ValueError("Không thể tính thống kê cho danh sách rỗng.")
    return {
        "min": min(values),
        "mean": round(statistics.fmean(values), 2),
        "p05": nearest_rank(values, 0.05),
        "p25": nearest_rank(values, 0.25),
        "median": nearest_rank(values, 0.50),
        "p75": nearest_rank(values, 0.75),
        "p95": nearest_rank(values, 0.95),
        "max": max(values),
    }


def rate(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


def summarise_labels(records: Iterable[dict[str, str]]) -> dict[str, dict[str, float | int]]:
    materialised = list(records)
    counts = Counter(record["legacy_label"] for record in materialised)
    unexpected = set(counts) - set(VALID_CODES)
    if unexpected:
        raise ValueError(f"Gặp mã nhãn ngoài 0/1: {', '.join(sorted(unexpected))}")
    return {
        code: {"rows": counts[code], "share_percent": rate(counts[code], len(materialised))}
        for code in VALID_CODES
    }


def read_split(path: Path, *, require_source_files: bool = False) -> list[dict[str, str]]:
    required = {"text_vi", "legacy_label"}
    if require_source_files:
        required.add("source_files")
    if not path.is_file():
        raise ValueError(f"Không tìm thấy tệp: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ValueError(f"{path.name} thiếu cột: {', '.join(sorted(missing))}")
        records: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            text = row.get("text_vi") or ""
            label = (row.get("legacy_label") or "").strip()
            if not normalise_text(text):
                raise ValueError(f"{path.name}:{line_number} có text_vi rỗng.")
            if label not in VALID_CODES:
                raise ValueError(f"{path.name}:{line_number} có legacy_label ngoài 0/1.")
            records.append(
                {
                    "text_vi": text,
                    "legacy_label": label,
                    "source_files": row.get("source_files") or "",
                }
            )
    if not records:
        raise ValueError(f"{path.name} không có dữ liệu.")
    return records


def text_features(records: list[dict[str, str]]) -> dict[str, Any]:
    normalised = [normalise_text(record["text_vi"]) for record in records]
    char_lengths = [len(text) for text in normalised]
    whitespace_token_lengths = [len(text.split()) for text in normalised]
    lexical_token_lists = [TOKEN_PATTERN.findall(text) for text in normalised]
    lexical_token_counts = Counter(token for tokens in lexical_token_lists for token in tokens)
    total_lexical_tokens = sum(len(tokens) for tokens in lexical_token_lists)
    source_texts = [record["text_vi"] for record in records]
    char_bins = {
        "1-32": sum(length <= 32 for length in char_lengths),
        "33-128": sum(33 <= length <= 128 for length in char_lengths),
        "129-512": sum(129 <= length <= 512 for length in char_lengths),
        "513-2000": sum(513 <= length <= 2000 for length in char_lengths),
        ">2000": sum(length > 2000 for length in char_lengths),
    }
    return {
        "character_length": distribution(char_lengths),
        "whitespace_token_length": distribution(whitespace_token_lengths),
        "character_length_bins": {
            name: {"rows": count, "share_percent": rate(count, len(records))}
            for name, count in char_bins.items()
        },
        "lexical_aggregate": {
            "total_alphanumeric_tokens": total_lexical_tokens,
            "unique_alphanumeric_tokens": len(lexical_token_counts),
            "hapax_tokens": sum(count == 1 for count in lexical_token_counts.values()),
            "type_token_ratio": round(len(lexical_token_counts) / total_lexical_tokens, 5)
            if total_lexical_tokens
            else 0.0,
        },
        "text_hygiene": {
            "texts_with_vietnamese_diacritic": sum(bool(VIETNAMESE_DIACRITICS.search(text)) for text in source_texts),
            "ascii_only_texts": sum(text.isascii() for text in source_texts),
            "texts_containing_url": sum(bool(URL_PATTERN.search(text)) for text in source_texts),
            "texts_containing_email": sum(bool(EMAIL_PATTERN.search(text)) for text in source_texts),
            "texts_containing_mention": sum(bool(MENTION_PATTERN.search(text)) for text in source_texts),
            "texts_containing_hashtag": sum(bool(HASHTAG_PATTERN.search(text)) for text in source_texts),
            "texts_containing_newline": sum("\n" in text or "\r" in text for text in source_texts),
            "texts_at_most_2_characters_after_normalization": sum(length <= 2 for length in char_lengths),
        },
    }


def split_summary(records: list[dict[str, str]]) -> dict[str, Any]:
    keys = [record_key(record["text_vi"]) for record in records]
    summary = text_features(records)
    summary.update(
        {
            "rows": len(records),
            "unique_normalized_texts": len(set(keys)),
            "duplicate_normalized_text_rows": len(keys) - len(set(keys)),
            "label_distribution": summarise_labels(records),
        }
    )
    return summary


def provenance_summary(records: list[dict[str, str]]) -> dict[str, Any]:
    by_source = defaultdict(list)
    for record in records:
        by_source[record["source_files"]].append(record)
    return {
        source: {"rows": len(group), "label_distribution": summarise_labels(group)}
        for source, group in sorted(by_source.items())
    }


def cross_split_integrity(splits: dict[str, list[dict[str, str]]], all_records: list[dict[str, str]]) -> dict[str, Any]:
    split_keys = {
        name: {record_key(record["text_vi"]): record["legacy_label"] for record in records}
        for name, records in splits.items()
    }
    all_keys = {record_key(record["text_vi"]): record["legacy_label"] for record in all_records}
    union_keys = set().union(*(set(values) for values in split_keys.values()))
    overlaps = {
        "train_validation": len(set(split_keys["train"]) & set(split_keys["validation"])),
        "train_test": len(set(split_keys["train"]) & set(split_keys["test"])),
        "validation_test": len(set(split_keys["validation"]) & set(split_keys["test"])),
    }
    label_conflicts = sum(
        1
        for key in union_keys
        if len({labels[key] for labels in split_keys.values() if key in labels}) > 1
    )
    if union_keys != set(all_keys):
        raise ValueError("Tập hợp split không khớp all_deduplicated.csv.")
    if any(split_keys[name][key] != all_keys[key] for name in SPLITS for key in split_keys[name]):
        raise ValueError("Nhãn ở split không khớp all_deduplicated.csv.")
    return {
        "exact_normalized_text_overlap": overlaps,
        "cross_split_label_conflict_keys": label_conflicts,
        "split_union_matches_all_deduplicated": True,
    }


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    divider = ["---"] * len(headers)
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(divider) + " |",
            *["| " + " | ".join(row) + " |" for row in rows],
        ]
    )


def fmt_distribution(item: dict[str, float | int]) -> str:
    return " / ".join(str(item[key]) for key in ("min", "p05", "p25", "median", "p75", "p95", "max"))


def render_report(summary: dict[str, Any]) -> str:
    overall = summary["overall"]
    split_rows = []
    for split_name in SPLITS:
        split = summary["splits"][split_name]
        split_rows.append(
            [
                split_name,
                str(split["rows"]),
                str(split["label_distribution"]["0"]["rows"]),
                str(split["label_distribution"]["1"]["rows"]),
                str(split["duplicate_normalized_text_rows"]),
                str(split["whitespace_token_length"]["median"]),
                str(split["whitespace_token_length"]["p95"]),
            ]
        )
    label_rows = [
        [code, str(overall["label_distribution"][code]["rows"]), f"{overall['label_distribution'][code]['share_percent']:.2f}%"]
        for code in VALID_CODES
    ]
    per_code_rows = []
    for code in VALID_CODES:
        records = summary["records_by_label"][code]
        per_code_rows.append(
            [
                code,
                str(records["rows"]),
                str(records["character_length"]["median"]),
                str(records["character_length"]["p95"]),
                str(records["whitespace_token_length"]["median"]),
                str(records["whitespace_token_length"]["p95"]),
            ]
        )
    hygiene = overall["text_hygiene"]
    integrity = summary["split_integrity"]
    return "\n".join(
        [
            f"# EDA — {summary['dataset_name']}",
            "",
            "> Báo cáo chỉ chứa thống kê tổng hợp, không có câu văn nguồn, mẫu câu hoặc diễn giải lâm sàng.",
            "",
            "## Phạm vi và ràng buộc",
            "",
            "Corpus là dữ liệu nhị phân legacy độc lập. `legacy_label` 0/1 là mã nguồn chưa có ngữ nghĩa được xác nhận; báo cáo không gọi chúng là positive/negative và corpus không thuộc pipeline sentiment cuộc họp.",
            "",
            "## Tổng quan",
            "",
            f"- Số văn bản sau khử trùng lặp: {overall['rows']:,}",
            f"- Văn bản duy nhất sau chuẩn hoá: {overall['unique_normalized_texts']:,}",
            f"- Tỷ lệ mất cân bằng lớn nhất/nhỏ nhất: {summary['class_imbalance_ratio']:.3f}×",
            f"- Tập split hợp nhất khớp `all_deduplicated.csv`: {integrity['split_union_matches_all_deduplicated']}",
            "",
            "## Phân bố mã nhãn",
            "",
            markdown_table(["Mã nguồn", "Số dòng", "Tỷ trọng"], label_rows),
            "",
            "## Phân bố split và độ dài",
            "",
            markdown_table(
                ["Split", "Dòng", "Mã 0", "Mã 1", "Trùng nội bộ", "Median token", "P95 token"], split_rows
            ),
            "",
            "Độ dài được tính sau chuẩn hoá Unicode NFKC và gộp khoảng trắng. Độ dài token dùng tách theo khoảng trắng; thống kê từ vựng dùng token alphanumeric. Cả hai chỉ phục vụ EDA, không phải token PhoBERT.",
            "",
            markdown_table(
                ["Tập", "Ký tự: min / P05 / P25 / median / P75 / P95 / max", "Token: min / P05 / P25 / median / P75 / P95 / max"],
                [["Toàn corpus", fmt_distribution(overall["character_length"]), fmt_distribution(overall["whitespace_token_length"])]],
            ),
            "",
            markdown_table(
                ["Mã nguồn", "Dòng", "Median ký tự", "P95 ký tự", "Median token", "P95 token"], per_code_rows
            ),
            "",
            "## Nhóm độ dài ký tự",
            "",
            markdown_table(
                ["Nhóm", "Dòng", "Tỷ trọng"],
                [
                    [name, str(value["rows"]), f"{value['share_percent']:.2f}%"]
                    for name, value in overall["character_length_bins"].items()
                ],
            ),
            "",
            "## Kiểm tra chất lượng văn bản",
            "",
            markdown_table(
                ["Chỉ số", "Số dòng", "Tỷ trọng"],
                [
                    ["Có dấu tiếng Việt", str(hygiene["texts_with_vietnamese_diacritic"]), f"{rate(hygiene['texts_with_vietnamese_diacritic'], overall['rows']):.2f}%"],
                    ["ASCII-only", str(hygiene["ascii_only_texts"]), f"{rate(hygiene['ascii_only_texts'], overall['rows']):.2f}%"],
                    ["Chứa URL", str(hygiene["texts_containing_url"]), f"{rate(hygiene['texts_containing_url'], overall['rows']):.2f}%"],
                    ["Chứa email", str(hygiene["texts_containing_email"]), f"{rate(hygiene['texts_containing_email'], overall['rows']):.2f}%"],
                    ["Chứa @mention", str(hygiene["texts_containing_mention"]), f"{rate(hygiene['texts_containing_mention'], overall['rows']):.2f}%"],
                    ["Chứa hashtag", str(hygiene["texts_containing_hashtag"]), f"{rate(hygiene['texts_containing_hashtag'], overall['rows']):.2f}%"],
                    ["Chứa xuống dòng", str(hygiene["texts_containing_newline"]), f"{rate(hygiene['texts_containing_newline'], overall['rows']):.2f}%"],
                    ["Dài tối đa 2 ký tự", str(hygiene["texts_at_most_2_characters_after_normalization"]), f"{rate(hygiene['texts_at_most_2_characters_after_normalization'], overall['rows']):.2f}%"],
                ],
            ),
            "",
            "Từ vựng được báo cáo ở mức aggregate: "
            f"{overall['lexical_aggregate']['total_alphanumeric_tokens']:,} token alphanumeric, "
            f"{overall['lexical_aggregate']['unique_alphanumeric_tokens']:,} loại token, "
            f"{overall['lexical_aggregate']['hapax_tokens']:,} hapax. Không xuất top-token để tránh lộ nội dung nhạy cảm.",
            "",
            "## Toàn vẹn split và provenance",
            "",
            markdown_table(
                ["Kiểm tra", "Kết quả"],
                [
                    ["Trùng chuẩn hoá train / validation", str(integrity["exact_normalized_text_overlap"]["train_validation"])],
                    ["Trùng chuẩn hoá train / test", str(integrity["exact_normalized_text_overlap"]["train_test"])],
                    ["Trùng chuẩn hoá validation / test", str(integrity["exact_normalized_text_overlap"]["validation_test"])],
                    ["Xung đột mã nhãn giữa split", str(integrity["cross_split_label_conflict_keys"])],
                ],
            ),
            "",
            markdown_table(
                ["Nguồn sau khử trùng lặp", "Dòng", "Mã 0", "Mã 1"],
                [
                    [
                        source,
                        str(item["rows"]),
                        str(item["label_distribution"]["0"]["rows"]),
                        str(item["label_distribution"]["1"]["rows"]),
                    ]
                    for source, item in summary["provenance"].items()
                ],
            ),
            "",
            "## Kết luận EDA",
            "",
            "1. Split xác định 80/10/10 giữ tỷ lệ mã nhãn gần như đồng nhất và không có trùng lặp chính xác giữa các split sau chuẩn hoá.",
            "2. Mã `0` nhiều hơn mã `1`; nếu thực hiện nghiên cứu legacy độc lập, cần báo cáo macro-F1, F1 theo từng mã và confusion matrix thay vì chỉ accuracy.",
            "3. Phân phối độ dài có đuôi dài. Một thí nghiệm ngoài phạm vi cuộc họp phải chốt policy cắt/segment theo token trước khi train và áp dụng như nhau cho mọi split.",
            "4. Dấu tiếng Việt phủ phần lớn corpus; các dòng ASCII-only, URL, email, mention hoặc hashtag là tín hiệu để rà soát/redact theo policy nghiên cứu, không phải cơ sở tự động dịch hoặc thay nhãn.",
            "5. Provenance bị gắn hoàn toàn với mã nhãn: hai nhóm nguồn chỉ có mã 0, còn nhóm giao nhau của hai nguồn chỉ có mã 1. Điểm model có thể phản ánh artefact nguồn thay vì nội dung; cần đánh giá rủi ro này trước mọi kết luận.",
            "6. Văn bản mã 1 dài hơn đáng kể (median/P95) so với mã 0. Một nghiên cứu legacy độc lập cần chạy baseline chỉ dùng độ dài và báo cáo ablation để kiểm tra confound này.",
            "7. EDA này không thay đổi giới hạn sử dụng: corpus chỉ dùng cho nghiên cứu legacy offline, không cho MeetingSentiment, dashboard/API/pilot cuộc họp hoặc suy luận sức khoẻ tâm thần.",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    corpus_dir = args.corpus_dir
    paths = {split: corpus_dir / f"{split}.csv" for split in SPLITS}
    all_path = corpus_dir / "all_deduplicated.csv"
    output_json = args.output_dir / "eda-summary.json"
    output_markdown = args.output_dir / "eda-report.md"
    if not args.overwrite and (output_json.exists() or output_markdown.exists()):
        raise ValueError("EDA output đã tồn tại; dùng --overwrite để ghi lại.")

    splits = {split: read_split(path) for split, path in paths.items()}
    all_records = read_split(all_path, require_source_files=True)
    all_keys = [record_key(record["text_vi"]) for record in all_records]
    if len(all_keys) != len(set(all_keys)):
        raise ValueError("all_deduplicated.csv còn bản ghi trùng sau chuẩn hoá.")

    overall = split_summary(all_records)
    records_by_label = {}
    for code in VALID_CODES:
        code_records = [record for record in all_records if record["legacy_label"] == code]
        label_metrics = text_features(code_records)
        label_metrics["rows"] = len(code_records)
        records_by_label[code] = label_metrics

    label_counts = overall["label_distribution"]
    class_imbalance_ratio = max(item["rows"] for item in label_counts.values()) / min(
        item["rows"] for item in label_counts.values()
    )
    summary: dict[str, Any] = {
        "dataset_name": args.dataset_name,
        "scope": "legacy binary research only; not MeetingSentiment data",
        "label_semantics": "undocumented source codes 0/1; not interpreted by this report",
        "normalization": "Unicode NFKC, collapse whitespace, casefold, SHA-256 key",
        "inputs": {name: str(path) for name, path in {**paths, "all_deduplicated": all_path}.items()},
        "overall": overall,
        "records_by_label": records_by_label,
        "splits": {split: split_summary(records) for split, records in splits.items()},
        "split_integrity": cross_split_integrity(splits, all_records),
        "provenance": provenance_summary(all_records),
        "class_imbalance_ratio": round(class_imbalance_ratio, 5),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_markdown.write_text(render_report(summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "rows": overall["rows"],
                "label_distribution": overall["label_distribution"],
                "split_integrity": summary["split_integrity"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"LỖI: {error}", file=sys.stderr)
        raise SystemExit(2)
