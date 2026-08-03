from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import check_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Check TRACE-Net relationship final gate hardener v30 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-relationship-final-gates", type=int, default=0)
    parser.add_argument("--min-passed-relationship-final-gates", type=int, default=0)
    parser.add_argument("--min-repaired-relationship-answers", type=int, default=0)
    parser.add_argument("--min-relationship-records", type=int, default=0)
    parser.add_argument("--max-post-gate-issue-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    report = check_report(
        report_path=args.report_path,
        min_relationship_final_gates=args.min_relationship_final_gates,
        min_passed_relationship_final_gates=args.min_passed_relationship_final_gates,
        min_repaired_relationship_answers=args.min_repaired_relationship_answers,
        min_relationship_records=args.min_relationship_records,
        max_post_gate_issue_count=args.max_post_gate_issue_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
        write_json=args.write_json,
    )

    print("TRACE-Net E2E Relationship Final Gate Hardener v30 Quality")
    print(f" quality_status: {report['quality_status']}")
    for check in report.get("quality_checks", []):
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}")

    if report["quality_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
