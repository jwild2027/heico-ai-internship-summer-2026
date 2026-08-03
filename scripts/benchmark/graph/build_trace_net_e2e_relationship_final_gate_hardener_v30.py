from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import build_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TRACE-Net relationship final gate hardener v30 artifact.")
    parser.add_argument("--relationship-router-hardening", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--include-synthetic-violations", action="store_true")
    parser.add_argument("--min-relationship-final-gates", type=int, default=0)
    parser.add_argument("--min-passed-relationship-final-gates", type=int, default=0)
    parser.add_argument("--min-repaired-relationship-answers", type=int, default=0)
    parser.add_argument("--min-relationship-records", type=int, default=0)
    parser.add_argument("--max-post-gate-issue-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    report = build_report(
        relationship_router_hardening=args.relationship_router_hardening,
        output_dir=args.output_dir,
        include_synthetic_violations=args.include_synthetic_violations,
        min_relationship_final_gates=args.min_relationship_final_gates,
        min_passed_relationship_final_gates=args.min_passed_relationship_final_gates,
        min_repaired_relationship_answers=args.min_repaired_relationship_answers,
        min_relationship_records=args.min_relationship_records,
        max_post_gate_issue_count=args.max_post_gate_issue_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
        quality=args.quality,
    )

    print("TRACE-Net E2E Relationship Final Gate Hardener v30")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "relationship_final_gate_count",
        "passed_relationship_final_gate_count",
        "relationship_record_count",
        "repaired_relationship_answer_count",
        "graph_as_proof_violation_count",
        "v2_summary_as_proof_violation_count",
        "nomenclature_as_proof_violation_count",
        "unsupported_relationship_claim_count",
        "post_gate_issue_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "report_path",
        "records_jsonl_path",
        "inspect_md_path",
    ]:
        print(f" {key}: {report.get(key)}")

    if args.quality and report["quality_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
