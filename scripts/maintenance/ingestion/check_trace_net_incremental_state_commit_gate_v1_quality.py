from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_incremental_state_commit_gate_v1 import quality_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net incremental state commit gate v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--require-no-full-rescan", action="store_true")
    parser.add_argument("--max-unchanged-page-reprocess", type=int)
    parser.add_argument("--require-commit-allowed", action="store_true")
    parser.add_argument("--require-commit-blocked-for-pending", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    result = quality_report(
        args.report_path,
        require_page_count=args.require_page_count,
        require_no_full_rescan=args.require_no_full_rescan,
        max_unchanged_page_reprocess=args.max_unchanged_page_reprocess,
        require_commit_allowed=args.require_commit_allowed,
        require_commit_blocked_for_pending=args.require_commit_blocked_for_pending,
        write_json_report=args.write_json,
    )
    print("TRACE-Net incremental state commit gate v1 quality")
    print(f" Status: {result['status']}")
    for key in [
        "page_count",
        "dirty_page_count",
        "affected_page_count",
        "planned_job_count",
        "processing_step_count",
        "state_commit_decision",
        "state_commit_required",
        "state_commit_allowed",
        "state_commit_performed",
        "pending_execution_step_count",
        "blocked_commit_check_count",
        "failed_execution_step_count",
        "full_rescan_required",
        "unchanged_page_reprocess_count",
        "state_commit_write_attempt_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {result.get(key)}")
    if args.write_json:
        print(f" quality_path: {result.get('quality_path')}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
