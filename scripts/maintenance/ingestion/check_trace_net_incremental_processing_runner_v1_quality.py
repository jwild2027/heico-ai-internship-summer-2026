from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_incremental_processing_runner_v1 import quality_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net incremental processing runner v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-processing-steps", type=int, default=0)
    parser.add_argument("--require-no-full-rescan", action="store_true")
    parser.add_argument("--max-unchanged-page-reprocess", type=int)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    result = quality_report(
        args.report_path,
        require_page_count=args.require_page_count,
        min_processing_steps=args.min_processing_steps,
        require_no_full_rescan=args.require_no_full_rescan,
        max_unchanged_page_reprocess=args.max_unchanged_page_reprocess,
        write_json_report=args.write_json,
    )
    print("TRACE-Net incremental processing runner v1 quality")
    print(f" Status: {result['status']}")
    for key in [
        "execution_mode",
        "page_count",
        "dirty_page_count",
        "affected_page_count",
        "planned_job_count",
        "processing_step_count",
        "processing_batch_count",
        "no_op_processed",
        "full_rescan_required",
        "unchanged_page_reprocess_count",
        "external_command_execution_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {result.get(key)}")
    if args.write_json:
        print(f" quality_path: {result.get('quality_path')}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
