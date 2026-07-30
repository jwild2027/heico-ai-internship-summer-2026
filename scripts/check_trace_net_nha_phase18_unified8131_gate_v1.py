#!/usr/bin/env python3
"""Independently check the N18 unified 8131 mixed real-model gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

EXPECTED = {
    "question_count": 12,
    "pass_count": 12,
    "fail_count": 0,
    "http_200_count": 12,
    "nha_question_count": 6,
    "nha_model_call_count": 6,
    "upstream_question_count": 5,
    "upstream_actual_gemma_call_count": 5,
    "synthetic_block_count": 1,
    "model_backed_question_count": 11,
    "unexpected_zero_model_call_count": 0,
    "allowed_zero_model_call_count": 1,
    "stream_count": 6,
    "nonstream_count": 6,
    "production_graph_write_count": 0,
    "source_artifact_mutation_count": 0,
    "synthetic_artifact_access_count": 0,
}


def check(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    quality_path = root / "trace_net_nha_phase18_unified8131_quality_v1.json"
    result_path = root / "trace_net_nha_phase18_unified8131_results_v1.json"
    failures: list[str] = []
    if not quality_path.exists():
        failures.append("missing_quality_artifact")
        quality: Mapping[str, Any] = {}
    else:
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
    if not result_path.exists():
        failures.append("missing_results_artifact")
        records = []
    else:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        records = payload.get("records") if isinstance(payload, Mapping) else []
        records = records if isinstance(records, list) else []
    if quality.get("quality_status") != "PASS":
        failures.append("quality_artifact_not_pass")
    counts = quality.get("counts") if isinstance(quality.get("counts"), Mapping) else {}
    for key, expected in EXPECTED.items():
        if counts.get(key) != expected:
            failures.append(f"count:{key} expected={expected} actual={counts.get(key)}")
    if len(records) != 12:
        failures.append(f"record_count:{len(records)}!=12")
    if any(not bool(row.get("passed")) for row in records if isinstance(row, Mapping)):
        failures.append("failed_record_present")
    return {
        "schema_version": "trace_net_nha_phase18_unified8131_check_v1",
        "module": "check_trace_net_nha_phase18_unified8131_gate_v1",
        "status": "TRACE_NET_NHA_PHASE18_UNIFIED8131_CHECK_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": [],
        "counts": dict(counts),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    result = check(args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("TRACE_NET_NHA_PHASE18_UNIFIED8131_CHECK=" + result["quality_status"])
    return 1 if args.strict and result["quality_status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
