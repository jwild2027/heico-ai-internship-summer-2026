#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Independently check the NHA live-20 output directory.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-count", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(args.output_dir).resolve()
    required = [
        root / "trace_net_nha_phase10_live20_bank_v1.json",
        root / "trace_net_nha_phase10_live20_results_v1.json",
        root / "trace_net_nha_phase10_live20_quality_v1.json",
        root / "trace_net_nha_phase10_live20_summary_v1.json",
    ]
    failures = [f"missing:{path.name}" for path in required if not path.exists()]
    results = []
    quality = {}
    if not failures:
        results = json.loads(required[1].read_text(encoding="utf-8"))["records"]
        quality = json.loads(required[2].read_text(encoding="utf-8"))
        if len(results) != args.expected_count:
            failures.append(f"result_count expected={args.expected_count} actual={len(results)}")
        if any(not row.get("passed") for row in results):
            failures.append("one_or_more_live20_records_failed")
        if quality.get("quality_status") != "PASS":
            failures.append("quality_artifact_not_pass")
        counts = quality.get("counts") or {}
        for key in ("pass_count", "http_200_count", "action_match_count"):
            if int(counts.get(key) or 0) != args.expected_count:
                failures.append(f"{key} expected={args.expected_count} actual={counts.get(key)}")
        if int(counts.get("synthetic_artifact_access_count") or 0) != 0:
            failures.append("synthetic_artifact_accessed")
    result = {
        "schema_version": "trace_net_nha_phase9_12_release_v1",
        "module": "check_trace_net_nha_phase10_live20_v1",
        "status": "TRACE_NET_NHA_PHASE10_LIVE20_CHECK_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": [],
        "counts": quality.get("counts") or {},
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict and failures:
        raise SystemExit("TRACE_NET_NHA_PHASE10_LIVE20_CHECK=FAIL")
    print("TRACE_NET_NHA_PHASE10_LIVE20_CHECK=PASS" if not failures else "TRACE_NET_NHA_PHASE10_LIVE20_CHECK=WARN")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
