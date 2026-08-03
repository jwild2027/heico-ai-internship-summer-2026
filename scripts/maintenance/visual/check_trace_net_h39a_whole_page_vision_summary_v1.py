from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_h39a_whole_page_vision_summary_v1 import check_whole_page_vision_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net H39A whole-page vision summaries")
    parser.add_argument("--vision-summary", required=True)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-pass", type=int, default=1)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    args = parser.parse_args()
    result = check_whole_page_vision_summary(**vars(args))
    out = Path(args.vision_summary).with_name("trace_net_h39a_whole_page_vision_summary_v1_quality_check.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print("status=TRACE_NET_H39A_WHOLE_PAGE_VISION_SUMMARY_CHECKED")
    print(f"quality_status={result['quality_status']}")
    print(f"record_count={result['record_count']}")
    print(f"pass_count={result['pass_count']}")
    print(f"error_count={result['error_count']}")
    print(f"answer_permission_count={result['answer_permission_count']}")
    print(f"source_truth_mutation_allowed_count={result['source_truth_mutation_allowed_count']}")
    print(f"unsafe_finding_count={result['unsafe_finding_count']}")
    print(f"write_attempt_count={result['write_attempt_count']}")
    if result["quality_failures"]:
        print("quality_failures=" + ",".join(result["quality_failures"]))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
