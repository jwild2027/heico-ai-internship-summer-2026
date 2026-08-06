#!/usr/bin/env python3
from __future__ import annotations

import argparse

from src.trace_net.engram.trace_net_h30_engram_canonical_registry_v1 import (
    write_quality_check,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check the TRACE-Net canonical Engram rule registry."
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = write_quality_check(args.registry, args.output)
    summary = result.get("summary", {})

    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(
        "canonical_rule_count="
        f"{summary.get('canonical_rule_count', 0)}"
    )
    print(
        "duplicate_rule_id_count="
        f"{summary.get('duplicate_rule_id_count', 0)}"
    )
    print(
        "duplicate_normalized_meaning_count="
        f"{summary.get('duplicate_normalized_meaning_count', 0)}"
    )
    print(
        "answer_permission_count="
        f"{summary.get('answer_permission_count', 0)}"
    )
    print(
        "source_truth_count="
        f"{summary.get('source_truth_count', 0)}"
    )
    print(
        "write_attempt_count="
        f"{summary.get('write_attempt_count', 0)}"
    )
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
