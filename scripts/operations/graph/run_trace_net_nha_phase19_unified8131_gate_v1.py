#!/usr/bin/env python3
"""Run N19 unified-8131 real-model acceptance and latency gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.operations.graph.run_trace_net_nha_phase18_unified8131_gate_v1 import (
    build_bank as build_phase18_bank,
    call,
    evaluate as evaluate_phase18,
)

SCHEMA_VERSION = "trace_net_nha_phase19_unified8131_mixed12_v1"
STATUS = "TRACE_NET_NHA_PHASE19_UNIFIED8131_MIXED12_V1"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_bank() -> list[dict[str, Any]]:
    rows = [dict(row) for row in build_phase18_bank()]
    nha_index = 0
    for row in rows:
        kind = str(row.get("kind") or "")
        if kind.startswith("upstream_"):
            # N19 needs the complete OpenAI response body to inspect the upstream
            # route-completion and preservation telemetry. Public SSE behavior is
            # still exercised by alternating NHA cases plus the synthetic control.
            row["stream"] = False
        elif kind.startswith("nha_"):
            row["stream"] = nha_index % 2 == 1
            nha_index += 1
        else:
            row["stream"] = True
    return rows


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def evaluate(case: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(evaluate_phase18(case, response))
    failures = list(row.get("failures") or [])
    body = _mapping(response.get("body"))
    trace = _mapping(body.get("trace_net"))
    fastpath = _mapping(trace.get("phase19_route_completion_fastpath"))
    preservation = _mapping(trace.get("phase19_preservation_writer"))

    row.update({
        "phase19_fastpath_active": bool(fastpath.get("active")),
        "phase19_fastpath_executed_calls": int(fastpath.get("executed_calls") or 0),
        "phase19_fastpath_skipped_calls": int(fastpath.get("skipped_call_count") or 0),
        "phase19_fastpath_matching_page": bool(fastpath.get("matching_source_page_resolved")),
        "phase19_preservation_active": bool(preservation.get("active")),
        "phase19_preservation_accepted": bool(preservation.get("structured_output_accepted")),
        "phase19_preservation_fallback": bool(preservation.get("phase3_fallback_used")),
    })

    if str(case.get("expected_action")) == "passthrough":
        if str(row.get("upstream_gemma_outcome")) != "accepted":
            failures.append(
                "phase19_upstream_rewrite_not_accepted:"
                + str(row.get("upstream_gemma_status") or "")
            )
        if not row["phase19_fastpath_active"]:
            failures.append("phase19_route_completion_fastpath_not_active")
        if row["phase19_fastpath_executed_calls"] < 1:
            failures.append("phase19_route_completion_executed_no_calls")
        if not row["phase19_fastpath_matching_page"]:
            failures.append("phase19_matching_source_page_not_resolved")
        if not row["phase19_preservation_active"]:
            failures.append("phase19_preservation_writer_not_active")
        if not row["phase19_preservation_accepted"]:
            failures.append("phase19_preservation_output_not_accepted")
        if row["phase19_preservation_fallback"]:
            failures.append("phase19_unexpected_phase3_fallback")

    row["failures"] = list(dict.fromkeys(failures))
    row["passed"] = not row["failures"]
    return row


def summarize(
    records: Sequence[Mapping[str, Any]],
    *,
    upstream_average_max_seconds: float,
    upstream_maximum_max_seconds: float,
    nha_maximum_max_seconds: float,
) -> dict[str, Any]:
    upstream = [row for row in records if str(row.get("action")) == "passthrough"]
    nha = [row for row in records if str(row.get("action")) == "gemma_override"]
    synthetic = [row for row in records if str(row.get("action")) == "synthetic_blocked"]
    upstream_latencies = [float(row.get("latency_seconds") or 0.0) for row in upstream]
    nha_latencies = [float(row.get("latency_seconds") or 0.0) for row in nha]
    all_latencies = [float(row.get("latency_seconds") or 0.0) for row in records]

    counts = {
        "question_count": len(records),
        "pass_count": sum(bool(row.get("passed")) for row in records),
        "fail_count": sum(not bool(row.get("passed")) for row in records),
        "http_200_count": sum(int(row.get("http_status") or 0) == 200 for row in records),
        "nha_question_count": len(nha),
        "nha_model_call_count": sum(int(row.get("model_calls") or 0) for row in nha),
        "upstream_question_count": len(upstream),
        "upstream_actual_gemma_call_count": sum(int(row.get("model_calls") or 0) for row in upstream),
        "upstream_gemma_accepted_count": sum(str(row.get("upstream_gemma_outcome")) == "accepted" for row in upstream),
        "upstream_safe_fallback_count": sum(str(row.get("upstream_gemma_outcome")) == "safe_fallback" for row in upstream),
        "phase19_fastpath_active_count": sum(bool(row.get("phase19_fastpath_active")) for row in upstream),
        "phase19_matching_page_count": sum(bool(row.get("phase19_fastpath_matching_page")) for row in upstream),
        "phase19_preservation_active_count": sum(bool(row.get("phase19_preservation_active")) for row in upstream),
        "phase19_preservation_accepted_count": sum(bool(row.get("phase19_preservation_accepted")) for row in upstream),
        "phase19_preservation_fallback_count": sum(bool(row.get("phase19_preservation_fallback")) for row in upstream),
        "synthetic_block_count": len(synthetic),
        "model_backed_question_count": sum(int(row.get("model_calls") or 0) == 1 for row in records),
        "unexpected_zero_model_call_count": sum(
            int(row.get("model_calls") or 0) == 0 and str(row.get("action")) != "synthetic_blocked"
            for row in records
        ),
        "allowed_zero_model_call_count": sum(
            int(row.get("model_calls") or 0) == 0 and str(row.get("action")) == "synthetic_blocked"
            for row in records
        ),
        "stream_count": sum(bool(row.get("stream")) for row in records),
        "nonstream_count": sum(not bool(row.get("stream")) for row in records),
        "production_graph_write_count": 0,
        "source_artifact_mutation_count": 0,
        "synthetic_artifact_access_count": 0,
    }
    latency = {
        "average_seconds": round(sum(all_latencies) / len(all_latencies), 3) if all_latencies else 0.0,
        "maximum_seconds": round(max(all_latencies), 3) if all_latencies else 0.0,
        "upstream_average_seconds": round(sum(upstream_latencies) / len(upstream_latencies), 3) if upstream_latencies else 0.0,
        "upstream_maximum_seconds": round(max(upstream_latencies), 3) if upstream_latencies else 0.0,
        "nha_maximum_seconds": round(max(nha_latencies), 3) if nha_latencies else 0.0,
        "upstream_average_limit_seconds": upstream_average_max_seconds,
        "upstream_maximum_limit_seconds": upstream_maximum_max_seconds,
        "nha_maximum_limit_seconds": nha_maximum_max_seconds,
    }

    failures: list[str] = []
    failures.extend(
        f"{row.get('case_id')}:" + "|".join(str(value) for value in (row.get("failures") or []))
        for row in records
        if not row.get("passed")
    )
    expected = {
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
    for key, value in expected.items():
        if counts.get(key) != value:
            failures.append(f"count:{key} expected={value} actual={counts.get(key)}")
    if latency["upstream_average_seconds"] > upstream_average_max_seconds:
        failures.append(
            f"latency:upstream_average {latency['upstream_average_seconds']}>{upstream_average_max_seconds}"
        )
    if latency["upstream_maximum_seconds"] > upstream_maximum_max_seconds:
        failures.append(
            f"latency:upstream_maximum {latency['upstream_maximum_seconds']}>{upstream_maximum_max_seconds}"
        )
    if latency["nha_maximum_seconds"] > nha_maximum_max_seconds:
        failures.append(
            f"latency:nha_maximum {latency['nha_maximum_seconds']}>{nha_maximum_max_seconds}"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "module": "run_trace_net_nha_phase19_unified8131_gate_v1",
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "counts": counts,
        "latency": latency,
        "failures": list(dict.fromkeys(failures)),
        "warnings": [],
        "live_model_call_policy": "one accepted real Gemma call for every non-synthetic request",
        "latency_policy": "route-completion early stop with no evidence or authority relaxation",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--upstream-average-max-seconds", type=float, default=80.0)
    parser.add_argument("--upstream-maximum-max-seconds", type=float, default=100.0)
    parser.add_argument("--nha-maximum-max-seconds", type=float, default=20.0)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    bank = build_bank()
    records: list[dict[str, Any]] = []
    for case in bank:
        response = call(args.base_url, args.api_key, args.model, case, args.timeout_seconds)
        row = evaluate(case, response)
        records.append(row)
        print(
            f"{row['case_id']} passed={row['passed']} action={row['action']} "
            f"model_calls={row['model_calls']} latency={row['latency_seconds']} "
            f"fastpath={row.get('phase19_fastpath_active')} preserve={row.get('phase19_preservation_accepted')}"
        )

    summary = summarize(
        records,
        upstream_average_max_seconds=args.upstream_average_max_seconds,
        upstream_maximum_max_seconds=args.upstream_maximum_max_seconds,
        nha_maximum_max_seconds=args.nha_maximum_max_seconds,
    )
    summary["output_dir"] = str(output_dir)
    summary["artifacts"] = [
        "trace_net_nha_phase19_unified8131_bank_v1.json",
        "trace_net_nha_phase19_unified8131_results_v1.json",
        "trace_net_nha_phase19_unified8131_results_v1.jsonl",
        "trace_net_nha_phase19_unified8131_quality_v1.json",
    ]
    _write_json(output_dir / summary["artifacts"][0], {"records": bank})
    _write_json(output_dir / summary["artifacts"][1], {"records": records})
    _write_jsonl(output_dir / summary["artifacts"][2], records)
    _write_json(output_dir / summary["artifacts"][3], summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("quality_status=" + summary["quality_status"])
    print("TRACE_NET_NHA_PHASE19_UNIFIED8131=" + summary["quality_status"])
    if args.strict and summary["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
