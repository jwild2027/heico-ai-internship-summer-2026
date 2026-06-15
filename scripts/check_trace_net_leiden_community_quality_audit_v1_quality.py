#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_leiden_community_quality_audit_v1 import (
    PASS,
    check_arg_parser,
    check_leiden_community_quality_audit,
    thresholds_from_args,
)


def main() -> int:
    parser = check_arg_parser()
    args = parser.parse_args()
    report = check_leiden_community_quality_audit(
        report_path=args.report_path,
        thresholds=thresholds_from_args(args),
        write_json_report=args.write_json,
    )
    summary = report.get("summary", {})
    print("TRACE-Net Leiden Community Quality Audit v1 quality")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "leiden_community_count",
        "community_audit_record_count",
        "effective_page_count",
        "orphan_edge_count",
        "review_recommended_community_count",
        "unsafe_community_record_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    if summary.get("quality_errors"):
        print(" quality_errors:", summary.get("quality_errors"))
    return 0 if report.get("quality_status") == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
