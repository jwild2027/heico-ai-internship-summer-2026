from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_it_operations_console_v1 import check_it_operations_console_quality


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net IT Operations Console v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--max-critical-issues", type=int, default=0)
    parser.add_argument("--allow-stage-failures", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    quality = check_it_operations_console_quality(
        args.report_path,
        max_critical_issues=args.max_critical_issues,
        require_no_stage_failures=not args.allow_stage_failures,
        write_json_report=args.write_json,
    )
    summary = quality.get("summary", {})
    print("TRACE-Net IT operations console v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "critical_issue_count",
        "stage_fail_count",
        "warning_issue_count",
        "review_issue_count",
        "source_truth_mutation_issue_count",
        "raw_feedback_direct_to_llm_issue_count",
        "answer_permission_issue_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality['quality_path']}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
