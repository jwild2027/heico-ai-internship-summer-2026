from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from tiff.trace_net_e2e_dynamic_plan_executor_v18 import quality_check_report, read_json, write_json


def main() -> int:
    ap = argparse.ArgumentParser(description="Check TRACE-Net E2E Dynamic Plan Executor v18 quality")
    ap.add_argument("--report-path", required=True)
    ap.add_argument("--min-query-plans", type=int, default=1)
    ap.add_argument("--min-ready-executions", type=int, default=1)
    ap.add_argument("--min-source-truth-evidence", type=int, default=1)
    ap.add_argument("--min-graph-guidance-records", type=int, default=0)
    ap.add_argument("--min-capped-result-disclosures", type=int, default=0)
    ap.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--write-json", action="store_true")
    args = ap.parse_args()
    report = read_json(args.report_path)
    status, checks = quality_check_report(
        report,
        min_query_plans=args.min_query_plans,
        min_ready_executions=args.min_ready_executions,
        min_source_truth_evidence=args.min_source_truth_evidence,
        min_graph_guidance_records=args.min_graph_guidance_records,
        min_capped_result_disclosures=args.min_capped_result_disclosures,
        max_graph_proof_authority_violations=args.max_graph_proof_authority_violations,
        max_summary_proof_authority_violations=args.max_summary_proof_authority_violations,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    print("TRACE-Net E2E Dynamic Plan Executor v18 Quality")
    print(f" quality_status: {status}")
    for c in checks:
        print(f" {'PASS' if c['passed'] else 'FAIL'} {c['name']}: observed={c['observed']} expected={c['op']} {c['expected']}")
    if args.write_json:
        report["quality_status"] = status
        report["quality_checks"] = checks
        if status != "PASS":
            report["status"] = "E2E_DYNAMIC_PLAN_EXECUTOR_NEEDS_REPAIR"
        write_json(args.report_path, report)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
