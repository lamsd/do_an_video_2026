#!/usr/bin/env python3
"""Evaluate a fixed, independently labelled sentiment CSV without extra packages.

Expected columns: unit_id,gold_label,predicted_label,accepted
Labels are positive, neutral, negative, or unknown.  Unknown predictions are
abstentions: they count as misses in all-labelled metrics, never as neutral.
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

LABELS = ("positive", "neutral", "negative")


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"unit_id", "gold_label", "predicted_label", "accepted"}
    if not rows or not required.issubset(rows[0]):
        raise SystemExit(f"CSV must contain: {', '.join(sorted(required))}")
    if any(row["gold_label"] not in LABELS for row in rows):
        raise SystemExit("gold_label must be positive, neutral, or negative")

    total = len(rows)
    accepted = [row for row in rows if row["accepted"].strip().lower() in {"1", "true", "yes"}]
    predicted = [row for row in accepted if row["predicted_label"] in LABELS]
    matrix = {gold: Counter() for gold in LABELS}
    for row in rows:
        matrix[row["gold_label"]][row["predicted_label"] or "unknown"] += 1
    per_class = {}
    all_f1, predicted_f1 = [], []
    for label in LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[gold][label] for gold in LABELS if gold != label)
        fn_all = sum(matrix[label][other] for other in matrix[label] if other != label)
        fn_predicted = sum(
            1 for row in predicted if row["gold_label"] == label and row["predicted_label"] != label
        )
        precision = ratio(tp, tp + fp)
        recall_all = ratio(tp, tp + fn_all)
        recall_predicted = ratio(tp, tp + fn_predicted)
        def f1(p, r): return round(2 * p * r / (p + r), 6) if p is not None and r is not None and p + r else 0.0
        per_class[label] = {"precision": precision, "recall_all": recall_all,
                            "f1_all": f1(precision, recall_all),
                            "recall_predicted": recall_predicted,
                            "f1_predicted": f1(precision, recall_predicted)}
        all_f1.append(per_class[label]["f1_all"])
        predicted_f1.append(per_class[label]["f1_predicted"])
    correct_all = sum(matrix[label][label] for label in LABELS)
    correct_predicted = sum(1 for row in predicted if row["gold_label"] == row["predicted_label"])
    result = {"sample_count": total, "accepted_A": len(accepted), "predicted_P": len(predicted),
              "total_T": total, "coverage_P_over_A": ratio(len(predicted), len(accepted)),
              "segment_acceptance_A_over_T": ratio(len(accepted), total),
              "prediction_over_total_P_over_T": ratio(len(predicted), total),
              "accuracy_all_labelled": ratio(correct_all, total),
              "accuracy_predicted_only": ratio(correct_predicted, len(predicted)),
              "macro_f1_all_labelled": round(sum(all_f1) / len(LABELS), 6),
              "macro_f1_predicted_only": round(sum(predicted_f1) / len(LABELS), 6),
              "per_class": per_class, "confusion_matrix": matrix}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=dict) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, default=dict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
