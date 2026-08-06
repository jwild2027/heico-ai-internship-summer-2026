#!/usr/bin/env python3
"""Check strict N20 real-Gemma 100-question NHA benchmark artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

REQUIRED_COUNTS = {
    "question_count": 100,
    "pass_count": 100,
    "fail_count": 0,
    "http_200_count": 100,
    "model_call_count": 100,
    "gemma_writer_accepted_count": 100,
    "answer_key_pass_count": 100,
    "deterministic_fallback_count": 0,
    "unique_query_count": 100,
    "stream_count": 50,
    "nonstream_count": 50,
    "production_synthetic_access_count": 0,
    "production_graph_write_count": 0,
    "source_artifact_mutation_count": 0,
}


def check(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir).resolve()
    quality_path = root / "trace_net_nha_phase20_gemma100_quality_v1.json"
    results_path = root / "trace_net_nha_phase20_gemma100_results_v1.json"
    answer_key_path = root / "trace_net_nha_phase20_gemma100_answer_key_v1.json"
    missing = [str(path) for path in (quality_path, results_path, answer_key_path) if not path.is_file()]
    failures: list[str] = []
    if missing:
        failures.extend("missing:" + value for value in missing)
        return {"quality_status": "FAIL", "failures": failures, "counts": {}}

    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    results_payload = json.loads(results_path.read_text(encoding="utf-8"))
    answer_key = json.loads(answer_key_path.read_text(encoding="utf-8"))
    results = [dict(row) for row in (results_payload.get("records") or []) if isinstance(row, Mapping)]
    counts = dict(quality.get("counts") or {})
    if quality.get("quality_status") != "PASS":
        failures.append("quality_artifact_not_pass")
    for key, expected in REQUIRED_COUNTS.items():
        if int(counts.get(key) or 0) != expected:
            failures.append(f"count:{key} expected={expected} actual={counts.get(key)}")
    if int(counts.get("unique_relationship_count") or 0) < 40:
        failures.append("unique_relationship_count_below_40")
    if int(counts.get("unique_template_count") or 0) < 20:
        failures.append("unique_template_count_below_20")
    if len(results) != 100:
        failures.append(f"result_count:{len(results)}!=100")
    if int(answer_key.get("case_count") or 0) != 100:
        failures.append("answer_key_case_count_not_100")
    for row in results:
        if not row.get("passed"):
            failures.append(str(row.get("case_id") or "unknown") + ":failed")
        if int(row.get("model_call_count") or 0) != 1:
            failures.append(str(row.get("case_id") or "unknown") + ":model_call_count")
        if row.get("writer_source") != "gemma" or not row.get("gemma_writer_accepted"):
            failures.append(str(row.get("case_id") or "unknown") + ":writer_not_accepted")
        if row.get("deterministic_fallback_used"):
            failures.append(str(row.get("case_id") or "unknown") + ":fallback_used")

    return {
        "schema_version": "trace_net_nha_phase20_gemma100_check_v1",
        "module": "check_trace_net_nha_phase20_gemma100_v1",
        "status": "TRACE_NET_NHA_PHASE20_GEMMA100_CHECK_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": list(dict.fromkeys(failures)),
        "warnings": list(quality.get("warnings") or []),
        "counts": counts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = check(args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("TRACE_NET_NHA_PHASE20_GEMMA100_CHECK=PASS" if result["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE20_GEMMA100_CHECK=FAIL")
    if args.strict and result["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE20_GEMMA100_CHECK=FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
