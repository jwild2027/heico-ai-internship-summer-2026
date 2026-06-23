from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, evaluate_quality, load_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E LLM-assisted query planner v17 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-query-plans", type=int, default=5)
    parser.add_argument("--min-validated-query-plans", type=int, default=5)
    parser.add_argument("--min-plans-with-v2-summary-guidance", type=int, default=5)
    parser.add_argument("--min-plans-with-leiden-guidance", type=int, default=5)
    parser.add_argument("--min-plans-with-source-truth-fields", type=int, default=5)
    parser.add_argument("--min-allowed-tunnel-validations", type=int, default=20)
    parser.add_argument("--max-invalid-tunnel-count", type=int, default=0)
    parser.add_argument("--max-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_json(args.report_path, {})
    thresholds = QualityThresholds(
        min_query_plans=args.min_query_plans,
        min_validated_query_plans=args.min_validated_query_plans,
        min_plans_with_v2_summary_guidance=args.min_plans_with_v2_summary_guidance,
        min_plans_with_leiden_guidance=args.min_plans_with_leiden_guidance,
        min_plans_with_source_truth_fields=args.min_plans_with_source_truth_fields,
        min_allowed_tunnel_validations=args.min_allowed_tunnel_validations,
        max_invalid_tunnel_count=args.max_invalid_tunnel_count,
        max_proof_authority_violations=args.max_proof_authority_violations,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["quality_checks"] = quality["quality_checks"]
    print("TRACE-Net E2E LLM-Assisted Query Planner v17 Quality")
    print(f" quality_status: {quality['quality_status']}")
    for check in quality["quality_checks"]:
        prefix = "PASS" if check["passed"] else "FAIL"
        print(f" {prefix} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}")
    if args.write_json:
        write_json(args.report_path, report)
    return 0 if quality["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
