from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_evidence_sufficiency_critic_v1 import read_json, write_json, quality_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Evidence Sufficiency Critic v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-sufficiency-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-retrieval-critic-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    report = read_json(args.report_path)
    quality = quality_report(
        report,
        min_sufficiency_records=args.min_sufficiency_records,
        min_queries=args.min_queries,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_retrieval_critic_quality_pass=args.require_retrieval_critic_quality_pass,
    )
    if args.write_json:
        path = Path(args.report_path)
        out = path.with_name("trace_net_evidence_sufficiency_critic_v1_quality.json")
        write_json(out, quality)
    summary = quality.get("summary", {})
    print("TRACE-Net Evidence Sufficiency Critic v1 quality")
    print(f" Status: {quality.get('status')}")
    print(f" sufficiency_record_count: {summary.get('sufficiency_record_count')}")
    print(f" final_evidence_sufficient_count: {summary.get('final_evidence_sufficient_count')}")
    print(f" final_artifact_evidence_sufficient_count: {summary.get('final_artifact_evidence_sufficient_count')}")
    print(f" final_evidence_sufficient_but_retrieval_audit_required_count: {summary.get('final_evidence_sufficient_but_retrieval_audit_required_count')}")
    print(f" sufficient_for_final_gate_attempt_count: {summary.get('sufficient_for_final_gate_attempt_count')}")
    print(f" unsafe_sufficiency_record_count: {summary.get('unsafe_sufficiency_record_count')}")
    print(f" sufficiency_can_answer_directly_count: {summary.get('sufficiency_can_answer_directly_count')}")
    print(f" sufficiency_can_prove_claims_count: {summary.get('sufficiency_can_prove_claims_count')}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count')}")
    return 0 if quality.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
