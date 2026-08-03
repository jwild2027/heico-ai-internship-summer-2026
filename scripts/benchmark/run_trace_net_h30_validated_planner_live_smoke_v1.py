#!/usr/bin/env python3
"""Small live smoke for planner-led TRACE-Net retrieval and safety boundaries."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_validated_planner_live_smoke_v1"

QUERIES = (
    "Find VS4956",
    "Describe the manual at a high level",
    "Which assembly contains part 120-41824-003?",
    "Find the removal procedure for the armrest",
    "Is part 120-41824-003 approved as a replacement for 120-48024-001?",
)


def post(base_url: str, api_key: str, query: str, timeout: int) -> Tuple[int, Dict[str, Any], float, str]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/trace-net/ask",
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


def evaluate(query: str, status: int, response: Mapping[str, Any], latency: float, error: str) -> Dict[str, Any]:
    failures: List[str] = []
    execution = dict(response.get("planner_execution") or {})
    envelope = dict(response.get("evidence_envelope") or {})
    safety = dict(response.get("safety_contract") or envelope.get("safety_contract") or {})

    if status != 200:
        failures.append(f"http_status:{status}")
    if error:
        failures.append("transport_error")
    if not response.get("route"):
        failures.append("missing_effective_route")
    if "self_rag_critic" not in response:
        failures.append("missing_self_rag_critic")
    if "crag_repair_attempts" not in response:
        failures.append("missing_crag_trace")
    if "planner_execution" not in response:
        failures.append("missing_planner_execution_trace")
    if execution.get("executor_owns_tunnel_selection") is not True:
        failures.append("executor_does_not_own_tunnels")
    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed",
    ):
        if response.get(key) is not False:
            failures.append(f"unsafe_response:{key}")
        if key in safety and safety.get(key) is not False:
            failures.append(f"unsafe_contract:{key}")
    for key in ("postgres_write_attempt", "qdrant_write_attempt", "opensearch_write_attempt"):
        if safety.get(key) not in (None, False):
            failures.append(f"write_attempt:{key}")

    return {
        "query": query,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "http_status": status,
        "latency_ms": latency,
        "effective_route": response.get("route"),
        "rollout_mode": execution.get("rollout_mode"),
        "planner_plan_adopted": bool(execution.get("planner_plan_adopted")),
        "route_changed": bool(execution.get("route_changed")),
        "deterministic_fallback_used": bool(execution.get("deterministic_fallback_used")),
        "critic_quality_status": (response.get("self_rag_critic") or {}).get("quality_status"),
        "repair_count": len(response.get("crag_repair_attempts") or []),
        "citation_count": int(response.get("citation_count") or 0),
        "error": error,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8118")
    parser.add_argument("--api-key", default="trace-net-cognitive-local")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--minimum-adopted", type=int, default=0)
    parser.add_argument(
        "--output",
        default="local_data/organization/trace_net/h30_validated_planner_live_smoke_v1.json",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    records: List[Dict[str, Any]] = []
    for index, query in enumerate(QUERIES, 1):
        print(f"[{index}/{len(QUERIES)}] {query}", flush=True)
        status, response, latency, error = post(args.base_url, args.api_key, query, args.timeout_seconds)
        row = evaluate(query, status, response, latency, error)
        records.append(row)
        print(
            f"[{index}/{len(QUERIES)}] {row['quality_status']} "
            f"route={row['effective_route']} adopted={int(row['planner_plan_adopted'])} "
            f"fallback={int(row['deterministic_fallback_used'])} latency_ms={latency:.1f}",
            flush=True,
        )

    failed = [row for row in records if row["quality_status"] != "PASS"]
    adopted = [row for row in records if row["planner_plan_adopted"]]
    gate_failures: List[str] = []
    if failed:
        gate_failures.append("live_record_failures")
    if len(adopted) < args.minimum_adopted:
        gate_failures.append(f"adopted_count:{len(adopted)}<{args.minimum_adopted}")
    result = {
        "module": MODULE,
        "quality_status": "PASS" if not gate_failures else "FAIL",
        "record_count": len(records),
        "pass_count": len(records) - len(failed),
        "fail_count": len(failed),
        "planner_plan_adopted_count": len(adopted),
        "minimum_adopted": args.minimum_adopted,
        "gate_failures": gate_failures,
        "records": records,
        "self_rag_required": True,
        "crag_trace_required": True,
        "executor_owned_tunnels": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if not gate_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
