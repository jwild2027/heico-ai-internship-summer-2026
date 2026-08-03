#!/usr/bin/env python3
"""Independently check N19 unified-8131 quality artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED = {
    "question_count": 12,
    "pass_count": 12,
    "fail_count": 0,
    "http_200_count": 12,
    "nha_question_count": 6,
    "nha_model_call_count": 6,
    "upstream_question_count": 5,
    "upstream_actual_gemma_call_count": 5,
    "upstream_gemma_accepted_count": 5,
    "upstream_safe_fallback_count": 0,
    "phase19_fastpath_active_count": 5,
    "phase19_matching_page_count": 5,
    "phase19_preservation_active_count": 5,
    "phase19_preservation_accepted_count": 5,
    "phase19_preservation_fallback_count": 0,
    "synthetic_block_count": 1,
    "model_backed_question_count": 11,
    "unexpected_zero_model_call_count": 0,
    "allowed_zero_model_call_count": 1,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(args.output_dir)
    quality = json.loads((root / "trace_net_nha_phase19_unified8131_quality_v1.json").read_text(encoding="utf-8"))
    results = json.loads((root / "trace_net_nha_phase19_unified8131_results_v1.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    counts = quality.get("counts") or {}
    for key, expected in EXPECTED.items():
        if counts.get(key) != expected:
            failures.append(f"count:{key} expected={expected} actual={counts.get(key)}")
    if quality.get("quality_status") != "PASS":
        failures.append("quality_artifact_not_pass")
    if len(results.get("records") or []) != 12:
        failures.append("result_record_count_not_12")
    if quality.get("failures"):
        failures.extend("quality:" + str(value) for value in quality.get("failures") or [])

    output = {
        "schema_version": "trace_net_nha_phase19_unified8131_check_v1",
        "module": "check_trace_net_nha_phase19_unified8131_gate_v1",
        "status": "TRACE_NET_NHA_PHASE19_UNIFIED8131_CHECK_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": list(dict.fromkeys(failures)),
        "warnings": quality.get("warnings") or [],
        "counts": counts,
        "latency": quality.get("latency") or {},
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print("TRACE_NET_NHA_PHASE19_UNIFIED8131_CHECK=" + output["quality_status"])
    if args.strict and output["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
