#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

SOURCE = Path(__file__).with_name("run_trace_net_cognitive_route_smoke_v1.py")
text = SOURCE.read_text(encoding="utf-8")

checks = {
    "helper_present": "def evaluate_live_result(" in text,
    "execution_modes_bounded": 'EXECUTION_MODES = {"narrow", "broad", "mature"}' in text,
    "decision_must_pass": 'decision_status == "PASS"' in text,
    "adoption_required": 'planner_map.get("planner_plan_adopted") is True' in text,
    "route_applied_required": 'planner_map.get("planner_route_applied") is True' in text,
    "retrieval_influence_required": 'planner_map.get("retrieval_influenced") is True' in text,
    "fallback_rejected": 'not planner_map.get("deterministic_fallback_used")' in text,
    "failures_rejected": "and not planner_failures" in text,
    "selected_matches_effective": "and selected_route == actual_route" in text,
    "unexplained_changes_disallowed": '"unexplained_route_changes_allowed": False' in text,
    "source_truth_mutation_required_false": "result.get(\"source_truth_mutation_allowed\") is False" in text,
}
failures = [name for name, passed in checks.items() if not passed]
result = {
    "module": "check_trace_net_h30_planner_aware_route_smoke_v1",
    "quality_status": "PASS" if not failures else "FAIL",
    "failure_count": len(failures),
    "failures": failures,
    "checks": checks,
    "planner_route_changes_require_validated_adoption": True,
    "source_truth_mutation_allowed": False,
}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if not failures else 1)
