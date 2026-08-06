#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_hybrid_retrieval_runtime_v1 import QualityThresholds, evaluate_quality, load_json, write_json


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check TRACE-Net E2E hybrid retrieval runtime v1 quality.")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-source-query-records", type=int, default=1)
    p.add_argument("--min-source-bridge-records", type=int, default=1)
    p.add_argument("--min-retrieval-queries", type=int, default=1)
    p.add_argument("--min-successful-retrieval-queries", type=int, default=1)
    p.add_argument("--min-retrieval-groups", type=int, default=1)
    p.add_argument("--min-total-retrieval-hits", type=int, default=1)
    p.add_argument("--min-pages-with-retrieval-hits", type=int, default=1)
    p.add_argument("--min-field-count", type=int, default=1)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-source-query-input-quality-pass", action="store_true")
    p.add_argument("--require-source-bridge-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    report = load_json(args.report_path)
    thresholds = QualityThresholds(
        min_source_query_records=args.min_source_query_records,
        min_source_bridge_records=args.min_source_bridge_records,
        min_retrieval_queries=args.min_retrieval_queries,
        min_successful_retrieval_queries=args.min_successful_retrieval_queries,
        min_retrieval_groups=args.min_retrieval_groups,
        min_total_retrieval_hits=args.min_total_retrieval_hits,
        min_pages_with_retrieval_hits=args.min_pages_with_retrieval_hits,
        min_field_count=args.min_field_count,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_query_input_quality_pass=args.require_source_query_input_quality_pass,
        require_source_bridge_quality_pass=args.require_source_bridge_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    status, checks = evaluate_quality(report, thresholds)
    report["quality_status"] = status
    report["quality_checks"] = checks
    if args.write_json:
        write_json(args.report_path, report)
        qpath = Path(args.report_path).with_name("trace_net_e2e_hybrid_retrieval_runtime_v1_quality.json")
        write_json(qpath, {"quality_status": status, "summary": report.get("summary", {}), "quality_checks": checks})
    print("TRACE-Net E2E Hybrid Retrieval Runtime v1 Quality")
    print(" quality_status:", status)
    for check in checks:
        prefix = "PASS" if check["passed"] else "FAIL"
        print(f" {prefix} {check['name']}: observed={check['observed']} expected={check['expected']}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
