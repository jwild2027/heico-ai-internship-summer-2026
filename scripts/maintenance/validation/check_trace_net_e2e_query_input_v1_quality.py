#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_query_input_v1 import QUALITY_PASS, QueryBuildConfig, evaluate_quality  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E query input v1 quality.")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-query-records", type=int, default=1)
    parser.add_argument("--min-routeable-queries", type=int, default=1)
    parser.add_argument("--min-unique-intents", type=int, default=1)
    parser.add_argument("--min-planned-retrieval-queries", type=int, default=1)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    config = QueryBuildConfig(
        min_query_records=args.min_query_records,
        min_routeable_queries=args.min_routeable_queries,
        min_unique_intents=args.min_unique_intents,
        min_planned_retrieval_queries=args.min_planned_retrieval_queries,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality_status, checks = evaluate_quality(report, config)
    report["quality_status"] = quality_status
    report["quality_checks"] = checks

    print("TRACE-Net E2E Query Input v1 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        label = "PASS" if check["passed"] else "FAIL"
        print(f" {label} {check['name']}: observed={check['observed']} expected={check['expected']}")

    if args.write_json:
        report["quality_path"] = str(args.report_path.with_name("trace_net_e2e_query_input_v1_quality.json"))
        args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        Path(report["quality_path"]).write_text(
            json.dumps({"quality_status": quality_status, "quality_checks": checks, "summary": report.get("summary", {})}, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    return 0 if quality_status == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
