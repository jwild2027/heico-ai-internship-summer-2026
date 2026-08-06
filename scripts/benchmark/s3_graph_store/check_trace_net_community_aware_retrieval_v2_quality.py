#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_community_aware_retrieval_v2 import (
    add_common_quality_args,
    check_community_aware_retrieval_v2_quality,
    print_summary,
    thresholds_from_args,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Community-Aware Retrieval v2 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_quality_args(parser)
    args = parser.parse_args()

    report = check_community_aware_retrieval_v2_quality(
        report_path=args.report_path,
        thresholds=thresholds_from_args(args),
        write_json_report=args.write_json,
    )
    print_summary(report, title="TRACE-Net Community-Aware Retrieval v2 quality")
    if report.get("quality_failures"):
        print(" quality_failures:")
        for failure in report["quality_failures"]:
            print("  -", failure)
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
