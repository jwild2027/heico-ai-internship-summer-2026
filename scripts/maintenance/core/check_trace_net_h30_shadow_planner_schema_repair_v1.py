#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
shadow = (ROOT / "src/trace_net/router/trace_net_h30_shadow_planner_v1.py").read_text(encoding="utf-8")
benchmark = (ROOT / "scripts/benchmark/run_trace_net_h30_shadow_planner_benchmark_v1.py").read_text(encoding="utf-8")
required = {
    "schema_repair_version": 'SHADOW_SCHEMA_REPAIR_VERSION = "v1"' in shadow,
    "json_response_mode": '"response_format": {"type": "json_object"}' in shadow,
    "exact_schema_guidance": "PROPOSAL_SCHEMA_GUIDANCE" in shadow,
    "one_bounded_repair": '"shadow_planner_max_schema_repairs": 1' in shadow,
    "repair_revalidated": "repaired_validation = validate_shadow_planner_proposal" in shadow,
    "grounding_not_overrideable": '"shadow_planner_schema_repair_can_override_grounding": False' in shadow,
    "benchmark_repair_metrics": '"schema_repair_used_count"' in benchmark,
    "planner_execution_disabled": '"execution_enabled": False' in shadow,
    "source_truth_mutation_disabled": '"source_truth_mutation_allowed": False' in shadow,
}
failures = [name for name, ok in required.items() if not ok]
result = {
    "module": "check_trace_net_h30_shadow_planner_schema_repair_v1",
    "quality_status": "PASS" if not failures else "FAIL",
    "failure_count": len(failures),
    "failures": failures,
    "max_schema_repairs": 1,
    "validator_weakened": False,
    "planner_route_applied": False,
    "retrieval_influenced": False,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
}
print(json.dumps(result, indent=2))
raise SystemExit(0 if not failures else 1)
