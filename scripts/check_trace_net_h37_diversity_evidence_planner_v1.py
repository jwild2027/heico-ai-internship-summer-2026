from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_h37_diversity_evidence_planner_v1 import check_diversity_evidence_planner


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net H37 diversity evidence planner")
    parser.add_argument("--diversity-planner", required=True)
    parser.add_argument("--min-plan-records", type=int, default=5)
    parser.add_argument("--min-diversity-pass", type=int, default=4)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    args = parser.parse_args()

    result = check_diversity_evidence_planner(**vars(args))
    p = Path(args.diversity_planner)
    out = p.with_name("trace_net_h37_diversity_evidence_planner_v1_quality_check.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print("status=TRACE_NET_H37_DIVERSITY_EVIDENCE_PLANNER_CHECKED")
    print(f"quality_status={result['quality_status']}")
    print(f"plan_record_count={result['plan_record_count']}")
    print(f"diversity_pass_count={result['diversity_pass_count']}")
    print(f"review_count={result['review_count']}")
    print(f"unsafe_finding_count={result['unsafe_finding_count']}")
    print(f"answer_permission_count={result['answer_permission_count']}")
    print(f"write_attempt_count={result['write_attempt_count']}")
    if result["quality_failures"]:
        print("quality_failures=" + ",".join(result["quality_failures"]))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
