from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_incident_review_bridge_v1 import quality_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Incident Review Bridge v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-incidents", type=int, default=1)
    parser.add_argument("--min-review-tasks", type=int, default=1)
    parser.add_argument("--min-high-priority-tasks", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    try:
        quality = quality_report(
            args.report_path,
            min_incidents=args.min_incidents,
            min_review_tasks=args.min_review_tasks,
            min_high_priority_tasks=args.min_high_priority_tasks,
            write_json_report=args.write_json,
        )
    except Exception as exc:
        print(f"TRACE-Net incident review bridge quality check failed: {exc}")
        return 1
    print("TRACE-Net incident review bridge v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "incident_count",
        "review_task_count",
        "critical_priority_review_task_count",
        "high_priority_review_task_count",
        "unsafe_review_task_count",
        "review_task_can_answer_directly_count",
        "review_task_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        print(f" {key}: {quality.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality['quality_path']}")
    return 0 if quality["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
