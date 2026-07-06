from __future__ import annotations

import argparse
from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import check_qdrant_adapter_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Qdrant adapter artifact.")
    p.add_argument("--qdrant-adapter", required=True)
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--min-local-queries", type=int, default=0)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-all-layers", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    result = check_qdrant_adapter_manifest(**vars(args))
    print("status=" + result["status"])
    print("quality_status=" + result["quality_status"])
    print("qdrant_point_record_count=" + str(result["qdrant_point_record_count"]))
    print("local_retrieval_query_count=" + str(result["local_retrieval_query_count"]))
    print("qdrant_write_attempt_count=" + str(result["qdrant_write_attempt_count"]))
    print("qdrant_read_attempt_count=" + str(result["qdrant_read_attempt_count"]))
    print("unsafe_finding_count=" + str(result["unsafe_finding_count"]))
    print("answer_permission_count=" + str(result["answer_permission_count"]))
    print("write_attempt_count=" + str(result["write_attempt_count"]))
    if result.get("quality_failures"):
        print("quality_failures=" + str(result["quality_failures"]))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
