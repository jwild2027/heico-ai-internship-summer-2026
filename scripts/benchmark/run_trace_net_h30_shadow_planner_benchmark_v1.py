#!/usr/bin/env python3
"""Run a focused benchmark against the Phase 4.4 planner-only endpoint."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_shadow_planner_benchmark_v1"

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


def post_plan(base_url: str, api_key: str, query: str, timeout: int) -> Tuple[int, Dict[str, Any], float, str]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/trace-net/shadow-plan",
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


def evaluate(query: str, status: int, response: Mapping[str, Any], error: str, latency: float) -> Dict[str, Any]:
    failures: List[str] = []
    validation = dict(response.get("validation") or {})
    comparison = dict(response.get("comparison") or {})
    proposal = dict(response.get("proposal") or {})

    if status != 200:
        failures.append(f"http_status:{status}")
    if error:
        failures.append("transport_error")
    if response.get("call_status") != "PASS":
        failures.append(f"planner_call_status:{response.get('call_status')}")
    if response.get("planner_route_applied") is not False:
        failures.append("planner_route_applied")
    if response.get("retrieval_influenced") is not False:
        failures.append("planner_retrieval_influenced")
    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed",
    ):
        if response.get(key) is not False:
            failures.append(f"unsafe_or_missing_false:{key}")

    return {
        "query": query,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "http_status": status,
        "latency_ms": latency,
        "call_status": response.get("call_status"),
        "validation_status": validation.get("quality_status"),
        "proposal_accepted": bool(validation.get("accepted")),
        "schema_repair_attempted": bool(response.get("schema_repair_attempted")),
        "schema_repair_used": bool(response.get("schema_repair_used")),
        "schema_repair_call_status": response.get("schema_repair_call_status"),
        "deterministic_route": comparison.get("deterministic_route"),
        "planner_route": comparison.get("planner_primary_route"),
        "route_disagreement": bool(comparison.get("route_disagreement")),
        "identifier_mode_disagreement": bool(comparison.get("identifier_mode_disagreement")),
        "proposal": proposal,
        "validation": validation,
        "comparison": comparison,
        "error": error,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8118")
    parser.add_argument("--api-key", default="trace-net-cognitive-local")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/h30_shadow_planner_benchmark_v1")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records_path = output / "records.jsonl"
    records = []

    with records_path.open("w", encoding="utf-8") as handle:
        for index, query in enumerate(QUERIES, 1):
            print(f"[{index}/{len(QUERIES)}] {query}", flush=True)
            status, response, latency, error = post_plan(args.base_url, args.api_key, query, args.timeout_seconds)
            row = evaluate(query, status, response, error, latency)
            records.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(
                f"[{index}/{len(QUERIES)}] {row['quality_status']} "
                f"accepted={int(row['proposal_accepted'])} "
                f"repair={int(row['schema_repair_used'])} "
                f"det={row['deterministic_route']} planner={row['planner_route']} "
                f"latency_ms={latency:.1f}",
                flush=True,
            )

    failed = [row for row in records if row["quality_status"] != "PASS"]
    accepted = [row for row in records if row["proposal_accepted"]]
    disagreements = [row for row in records if row["route_disagreement"]]
    repair_attempted = [row for row in records if row["schema_repair_attempted"]]
    repair_used = [row for row in records if row["schema_repair_used"]]
    summary = {
        "module": MODULE,
        "quality_status": "PASS" if not failed and len(records) == len(QUERIES) else "FAIL",
        "requested_record_count": len(QUERIES),
        "completed_record_count": len(records),
        "infrastructure_pass_count": len(records) - len(failed),
        "infrastructure_fail_count": len(failed),
        "proposal_accepted_count": len(accepted),
        "proposal_rejected_count": len(records) - len(accepted),
        "planner_acceptance_rate": round(len(accepted) / len(records), 4) if records else 0.0,
        "route_disagreement_count": len(disagreements),
        "schema_repair_attempted_count": len(repair_attempted),
        "schema_repair_used_count": len(repair_used),
        "schema_repair_success_rate": round(len(repair_used) / len(repair_attempted), 4) if repair_attempted else 0.0,
        "deterministic_route_counts": dict(Counter(str(row.get("deterministic_route") or "unknown") for row in records)),
        "planner_route_counts": dict(Counter(str(row.get("planner_route") or "none") for row in records)),
        "validation_status_counts": dict(Counter(str(row.get("validation_status") or "unknown") for row in records)),
        "median_latency_ms": sorted(row["latency_ms"] for row in records)[len(records) // 2] if records else 0.0,
        "records_path": str(records_path),
        "proposal_only": True,
        "planner_execution_enabled": False,
        "planner_route_applied": False,
        "retrieval_influenced": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
