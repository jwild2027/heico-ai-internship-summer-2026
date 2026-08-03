from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_h38c_diversity_task_repair_runner_v1 import check_repair_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net H38C diversity task repair runner")
    parser.add_argument("--repair-run", required=True)
    parser.add_argument("--min-records", type=int, default=5)
    parser.add_argument("--min-good-answers", type=int, default=4)
    parser.add_argument("--min-contract-pass", type=int, default=4)
    parser.add_argument("--max-fallback-used", type=int, default=0)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    args = parser.parse_args()
    result = check_repair_run(**vars(args))
    out = Path(args.repair_run).with_name("trace_net_h38c_diversity_task_repair_runner_v1_quality_check.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print("status=TRACE_NET_H38C_DIVERSITY_TASK_REPAIR_RUN_CHECKED")
    print(f"quality_status={result['quality_status']}")
    print(f"question_count={result['question_count']}")
    print(f"good_answer_count={result['good_answer_count']}")
    print(f"contract_pass_count={result['contract_pass_count']}")
    print(f"fallback_used_count={result['fallback_used_count']}")
    print(f"repair_used_count={result['repair_used_count']}")
    print(f"bad_answer_count={result['bad_answer_count']}")
    print(f"unsupported_claim_count={result['unsupported_claim_count']}")
    print(f"unsafe_finding_count={result['unsafe_finding_count']}")
    print(f"answer_permission_count={result['answer_permission_count']}")
    print(f"write_attempt_count={result['write_attempt_count']}")
    if result["quality_failures"]:
        print("quality_failures=" + ",".join(result["quality_failures"]))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
