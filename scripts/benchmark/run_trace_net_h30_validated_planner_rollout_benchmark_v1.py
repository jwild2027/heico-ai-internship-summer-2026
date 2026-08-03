#!/usr/bin/env python3
"""Benchmark the Phase 4.5 planner-decision endpoint without retrieval."""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_validated_planner_rollout_benchmark_v1"

QUERIES = (
    "Find VS4956",
    "Locate E075221",
    "Search for 1002-F",
    "I only remember a part number that starts with MS49",
    "The P/N contains 50645",
    "Find ATA 25-21-00",
    "Describe the manual at a high level",
    "Find the locking ring near the seat",
    "Which assembly contains part 120-41824-003?",
    "Recover the OCR labels for part 120-41824-003 from the blurry scan",
    "Show figure 69 and identify its callouts",
    "Where is part 120-48024-001 listed?",
    "Find the removal procedure for the armrest",
    "What warnings apply before removing the seat assembly?",
    "Is part 120-41824-003 approved as a replacement for 120-48024-001?",
    "Compare the two manual references for the locking ring",
)


def post_json(base_url: str, api_key: str, query: str, timeout: int) -> Tuple[int, Dict[str, Any], float, str]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/trace-net/planner-decision",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
            return response.status, dict(value), round((time.perf_counter() - started) * 1000.0, 3), ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return exc.code, {}, round((time.perf_counter() - started) * 1000.0, 3), detail
    except Exception as exc:
        return 599, {}, round((time.perf_counter() - started) * 1000.0, 3), f"{type(exc).__name__}: {exc}"


def evaluate(
    query: str,
    status: int,
    response: Mapping[str, Any],
    error: str,
    latency_ms: float,
    expected_mode: Optional[str],
) -> Dict[str, Any]:
    failures: List[str] = []
    decision = dict(response.get("planner_execution") or {})
    shadow = dict(response.get("shadow_planner") or {})

    if status != 200:
        failures.append(f"http_status:{status}")
    if error:
        failures.append("transport_error")
    if response.get("retrieval_executed") is not False:
        failures.append("planner_decision_executed_retrieval")
    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed",
    ):
        if response.get(key) is not False:
            failures.append(f"unsafe_or_missing_false:{key}")
    if expected_mode and decision.get("rollout_mode") != expected_mode:
        failures.append(f"rollout_mode:{decision.get('rollout_mode')}!={expected_mode}")
    if decision.get("executor_owns_tunnel_selection") is not True:
        failures.append("executor_does_not_own_tunnels")
    if decision.get("planner_can_execute_tools") is not False:
        failures.append("planner_can_execute_tools")
    if decision.get("planner_can_select_evidence") is not False:
        failures.append("planner_can_select_evidence")

    return {
        "query": query,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "http_status": status,
        "latency_ms": latency_ms,
        "planner_call_status": decision.get("planner_call_status") or shadow.get("call_status"),
        "rollout_mode": decision.get("rollout_mode"),
        "rollout_phase": decision.get("rollout_phase"),
        "deterministic_route": decision.get("deterministic_route"),
        "selected_route": decision.get("selected_route"),
        "proposed_routes": decision.get("proposed_routes") or [],
        "planner_plan_adopted": bool(decision.get("planner_plan_adopted")),
        "route_changed": bool(decision.get("route_changed")),
        "deterministic_fallback_used": bool(decision.get("deterministic_fallback_used")),
        "decision_quality_status": decision.get("quality_status"),
        "decision_failures": decision.get("failures") or [],
        "canonical_bridge_used": bool(
            (decision.get("canonical_contract_bridge") or {}).get("used")
        ),
        "schema_repair_used": bool(shadow.get("schema_repair_used")),
        "error": error,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8118")
    parser.add_argument("--api-key", default="trace-net-cognitive-local")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--expect-mode", choices=("validate_only", "narrow", "broad", "mature"))
    parser.add_argument("--minimum-adoption-rate", type=float, default=0.0)
    parser.add_argument(
        "--output-dir",
        default="local_data/organization/trace_net/h30_validated_planner_rollout_benchmark_v1",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records_path = output / "records.jsonl"
    records: List[Dict[str, Any]] = []

    with records_path.open("w", encoding="utf-8") as handle:
        for index, query in enumerate(QUERIES, 1):
            print(f"[{index}/{len(QUERIES)}] {query}", flush=True)
            status, response, latency, error = post_json(
                args.base_url, args.api_key, query, args.timeout_seconds
            )
            row = evaluate(query, status, response, error, latency, args.expect_mode)
            records.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(
                f"[{index}/{len(QUERIES)}] {row['quality_status']} "
                f"adopted={int(row['planner_plan_adopted'])} "
                f"fallback={int(row['deterministic_fallback_used'])} "
                f"det={row['deterministic_route']} selected={row['selected_route']} "
                f"latency_ms={latency:.1f}",
                flush=True,
            )

    failed = [row for row in records if row["quality_status"] != "PASS"]
    adopted = [row for row in records if row["planner_plan_adopted"]]
    changed = [row for row in records if row["route_changed"]]
    fallback = [row for row in records if row["deterministic_fallback_used"]]
    bridge = [row for row in records if row["canonical_bridge_used"]]
    schema = [row for row in records if row["schema_repair_used"]]
    adoption_rate = len(adopted) / len(records) if records else 0.0
    gate_failures: List[str] = []
    if failed:
        gate_failures.append("infrastructure_or_safety_failures")
    if adoption_rate < args.minimum_adoption_rate:
        gate_failures.append(
            f"adoption_rate:{adoption_rate:.4f}<{args.minimum_adoption_rate:.4f}"
        )

    latencies = [float(row["latency_ms"]) for row in records]
    summary = {
        "module": MODULE,
        "quality_status": "PASS" if not gate_failures else "FAIL",
        "requested_record_count": len(QUERIES),
        "completed_record_count": len(records),
        "infrastructure_pass_count": len(records) - len(failed),
        "infrastructure_fail_count": len(failed),
        "planner_plan_adopted_count": len(adopted),
        "planner_plan_rejected_or_fallback_count": len(records) - len(adopted),
        "planner_adoption_rate": round(adoption_rate, 4),
        "route_changed_count": len(changed),
        "deterministic_fallback_count": len(fallback),
        "canonical_bridge_used_count": len(bridge),
        "schema_repair_used_count": len(schema),
        "deterministic_route_counts": dict(Counter(str(row.get("deterministic_route") or "none") for row in records)),
        "selected_route_counts": dict(Counter(str(row.get("selected_route") or "none") for row in records)),
        "decision_status_counts": dict(Counter(str(row.get("decision_quality_status") or "unknown") for row in records)),
        "planner_call_status_counts": dict(Counter(str(row.get("planner_call_status") or "unknown") for row in records)),
        "median_latency_ms": round(statistics.median(latencies), 3) if latencies else 0.0,
        "max_latency_ms": round(max(latencies), 3) if latencies else 0.0,
        "expected_mode": args.expect_mode,
        "minimum_adoption_rate": args.minimum_adoption_rate,
        "gate_failures": gate_failures,
        "records_path": str(records_path),
        "retrieval_executed": False,
        "executor_owns_tunnel_selection": True,
        "deterministic_fallback": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not gate_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
