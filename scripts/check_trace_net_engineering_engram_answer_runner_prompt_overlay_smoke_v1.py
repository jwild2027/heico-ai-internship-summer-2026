from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import check_answer_runner_prompt_overlay_smoke_manifest


def main() -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net H24 Engram answer-runner prompt overlay smoke.")
    p.add_argument("--overlay-smoke", required=True)
    p.add_argument("--min-overlay-records", type=int, default=5)
    p.add_argument("--min-matched-bridge-records", type=int, default=5)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    args = p.parse_args()
    result = check_answer_runner_prompt_overlay_smoke_manifest(
        overlay_smoke=args.overlay_smoke,
        min_overlay_records=args.min_overlay_records,
        min_matched_bridge_records=args.min_matched_bridge_records,
        require_quality_pass=args.require_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("overlay_record_count=" + str(s.get("overlay_record_count")))
    print("target_question_count=" + str(s.get("target_question_count")))
    print("matched_bridge_record_count=" + str(s.get("matched_bridge_record_count")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    if result.get("quality_failures"):
        print("quality_failures=" + str(result.get("quality_failures")))
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
