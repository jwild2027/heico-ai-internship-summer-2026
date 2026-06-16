#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_graph_query_api_v1 import (
    ApiQualityThresholds,
    check_graph_query_api_quality,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Graph Query API v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-route-records", type=int, default=5)
    parser.add_argument("--min-query-records", type=int, default=3)
    parser.add_argument("--require-helper-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    thresholds = ApiQualityThresholds(
        min_route_records=args.min_route_records,
        min_query_records=args.min_query_records,
        require_helper_quality_pass=args.require_helper_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = check_graph_query_api_quality(
        args.report_path,
        thresholds=thresholds,
        write_json_report=args.write_json,
    )
    summary = report.get("summary", {})
    print("TRACE-Net Graph Query API v1 quality")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "source_graph_query_helper_quality_status",
        "route_record_count",
        "query_record_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    for failure in report.get("failures", []):
        print(f" FAILURE: {failure}")
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
