#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_artifact_dirty_planner_v1 import (
    PlannerThresholds,
    check_dirty_planner_quality,
    print_quality_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Artifact Dirty Planner v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-planner-records", type=int, default=1)
    parser.add_argument("--min-dirty-artifacts", type=int, default=1)
    parser.add_argument("--max-dependency-cycles", type=int, default=0)
    parser.add_argument("--require-registry-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    thresholds = PlannerThresholds(
        min_planner_records=args.min_planner_records,
        min_dirty_artifacts=args.min_dirty_artifacts,
        max_dependency_cycle_count=args.max_dependency_cycles,
        require_registry_quality_pass=args.require_registry_quality_pass,
    )
    payload = check_dirty_planner_quality(
        report_path=args.report_path,
        thresholds=thresholds,
        write_json_report=args.write_json,
    )
    print_quality_summary(payload)
    return 0 if payload.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
