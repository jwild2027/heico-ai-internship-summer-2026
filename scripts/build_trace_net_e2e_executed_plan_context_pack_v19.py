from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from tiff.trace_net_e2e_executed_plan_context_pack_v19 import (
    add_common_quality_args,
    build_and_write,
    print_report_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E executed-plan context packs v19.")
    parser.add_argument("--dynamic-plan-executor", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--high-degree-threshold", type=int, default=10)
    parser.add_argument("--max-pages-per-community", type=int, default=25)
    parser.add_argument("--quality", action="store_true")
    add_common_quality_args(parser)
    args = parser.parse_args()

    report = build_and_write(
        args.dynamic_plan_executor,
        args.output_dir,
        top_k=args.top_k,
        high_degree_threshold=args.high_degree_threshold,
        max_pages_per_community=args.max_pages_per_community,
        quality_args=args if args.quality else None,
    )
    print_report_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
