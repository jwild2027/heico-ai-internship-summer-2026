#!/usr/bin/env python3
"""Independently check the NHA N16 live Gemma-20 artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-count", type=int, default=20)
    parser.add_argument("--expected-gemma-overrides", type=int, default=18)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.output_dir).resolve()
    quality_path = root / "trace_net_nha_phase16_gemma20_quality_v1.json"
    results_path = root / "trace_net_nha_phase16_gemma20_results_v1.json"
    failures = []
    if not quality_path.exists():
        failures.append("missing_quality_artifact")
        quality = {}
    else:
        quality = read_json(quality_path)
    if not results_path.exists():
        failures.append("missing_results_artifact")
        records = []
    else:
        payload = read_json(results_path)
        records = payload.get("records") if isinstance(payload, Mapping) else []
        if not isinstance(records, list):
            records = []

    counts = quality.get("counts") if isinstance(quality, Mapping) else {}
    expected = {
        "question_count": args.expected_count,
        "pass_count": args.expected_count,
        "fail_count": 0,
        "http_200_count": args.expected_count,
        "gemma_override_count": args.expected_gemma_overrides,
        "gemma_override_pass_count": args.expected_gemma_overrides,
        "gemma_call_count": args.expected_gemma_overrides,
        "gemma_writer_accepted_count": args.expected_gemma_overrides,
        "deterministic_fallback_count": 0,
        "self_rag_pass_count": args.expected_gemma_overrides,
        "engram_skill_present_count": args.expected_gemma_overrides,
        "engram_atoms_present_count": args.expected_gemma_overrides,
        "synthetic_block_count": 1,
        "passthrough_control_count": 1,
        "stream_count": 10,
        "nonstream_count": 10,
        "production_graph_write_count": 0,
        "source_artifact_mutation_count": 0,
        "synthetic_artifact_access_count": 0,
    }
    for key, value in expected.items():
        if int((counts or {}).get(key) or 0) != value:
            failures.append(f"count:{key} expected={value} actual={(counts or {}).get(key)}")
    if len(records) != args.expected_count:
        failures.append(f"record_count expected={args.expected_count} actual={len(records)}")
    for row in records:
        if not isinstance(row, Mapping):
            failures.append("result_not_object")
            continue
        if not row.get("passed"):
            failures.append(f"failed_case:{row.get('case_id')}")
    if str(quality.get("quality_status") or "") != "PASS":
        failures.append("quality_artifact_not_pass")

    output = {
        "schema_version": "trace_net_nha_phase16_gemma20_check_v1",
        "module": "check_trace_net_nha_phase16_gemma20_v1",
        "status": "TRACE_NET_NHA_PHASE16_GEMMA20_CHECK_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": list(dict.fromkeys(failures)),
        "warnings": [],
        "counts": counts or {},
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    if args.strict and failures:
        raise SystemExit("TRACE_NET_NHA_PHASE16_GEMMA20_CHECK=FAIL")
    print("TRACE_NET_NHA_PHASE16_GEMMA20_CHECK=PASS" if not failures else "TRACE_NET_NHA_PHASE16_GEMMA20_CHECK=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
