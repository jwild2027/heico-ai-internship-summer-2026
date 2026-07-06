from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_engram_crag_repair_v1 import check_crag_repair_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram CRAG repair artifact v1")
    parser.add_argument("--crag-repair", required=True)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-crag-pass-or-no-repair", type=int, default=1)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-repair-attempts", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    args = parser.parse_args()
    result = check_crag_repair_manifest(**vars(args))
    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("critic_record_count=" + str(result.get("critic_record_count")))
    print("crag_pass_or_no_repair_count=" + str(result.get("crag_pass_or_no_repair_count")))
    print("repair_recommended_count=" + str(result.get("repair_recommended_count")))
    print("repair_attempt_count=" + str(result.get("repair_attempt_count")))
    print("unsafe_finding_count=" + str(result.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(result.get("answer_permission_count")))
    print("write_attempt_count=" + str(result.get("write_attempt_count")))
    if result.get("quality_failures"):
        print("quality_failures=" + repr(result.get("quality_failures")))
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
