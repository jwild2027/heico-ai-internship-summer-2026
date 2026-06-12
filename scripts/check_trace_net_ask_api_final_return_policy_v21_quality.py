from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_ask_api_final_return_policy_v21 import quality_report, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Ask API Final Return Policy v2.1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-policy-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-return-allowed", type=int, default=0)
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-retrieval-critic-quality-pass", action="store_true")
    parser.add_argument("--require-evidence-sufficiency-quality-pass", action="store_true")
    parser.add_argument("--require-answer-claim-critic-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()
    report = read_json(args.report_path)
    q = quality_report(
        report,
        min_policy_records=args.min_policy_records,
        min_queries=args.min_queries,
        min_return_allowed=args.min_return_allowed,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_retrieval_critic_quality_pass=args.require_retrieval_critic_quality_pass,
        require_evidence_sufficiency_quality_pass=args.require_evidence_sufficiency_quality_pass,
        require_answer_claim_critic_quality_pass=args.require_answer_claim_critic_quality_pass,
    )
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_ask_api_final_return_policy_v21_quality.json")
        write_json(quality_path, q)
    print("TRACE-Net Ask API Final Return Policy v2.1 quality")
    print(f" Status: {q['quality_status']}")
    for key in [
        "policy_record_count",
        "query_count",
        "final_answer_return_allowed_count",
        "audit_required_count",
        "retrieval_only_final_gate_required_count",
        "unsafe_return_allowed_count",
        "hard_safety_violation_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {q.get(key, 0)}")
    for issue in q.get("issues", []):
        print(f" issue: {issue['issue_code']} - {issue['message']}")
    return 0 if q["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
