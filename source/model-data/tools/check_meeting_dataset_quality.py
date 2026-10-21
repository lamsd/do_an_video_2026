#!/usr/bin/env python3
"""Run the required aggregate quality gate before sentiment-model training."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


MODEL_DATA_ROOT = Path(__file__).resolve().parents[1]
if str(MODEL_DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_DATA_ROOT))

from meeting_dataset_quality import (  # noqa: E402
    DATASET_PROFILES,
    DatasetQualityError,
    evaluate_dataset,
    write_quality_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--dataset-profile", choices=DATASET_PROFILES, default="approved-meeting")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _, report = evaluate_dataset(
        {"train": args.train, "validation": args.validation, "test": args.test},
        profile=args.dataset_profile,
        manifest_path=args.dataset_manifest,
        expected_dataset_version=args.dataset_version,
    )
    write_quality_report(args.report, report, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "ready_to_train": report["ready_to_train"],
                "blocking_issue_count": len(report["blocking_issues"]),
                "warning_count": len(report["warnings"]),
                "report": str(args.report),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["ready_to_train"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DatasetQualityError as error:
        raise SystemExit(f"ERROR: {error}")
