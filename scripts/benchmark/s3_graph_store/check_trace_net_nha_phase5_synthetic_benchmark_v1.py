#!/usr/bin/env python3
"""Check TRACE-Net NHA phase N5 synthetic benchmark artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trace_net.graph.trace_net_nha_phase5_synthetic_benchmark_v1 import (
    EXPECTED_QUESTION_COUNT,
    EXPECTED_SCENARIO_COUNT,
    _records,
    _read_json,
    build_graph_overlay,
    validate_phase5,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase0-3-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-scenario-count", type=int, default=EXPECTED_SCENARIO_COUNT)
    parser.add_argument("--expected-question-count", type=int, default=EXPECTED_QUESTION_COUNT)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    phase0 = Path(args.phase0_3_dir).resolve()
    output = Path(args.output_dir).resolve()
    inventory = _records(_read_json(phase0 / "trace_net_nha_page_inventory_v1.json"))
    scenarios = _records(_read_json(output / "trace_net_nha_synthetic_scenarios_v1.json"))
    relationships = _records(_read_json(output / "trace_net_nha_synthetic_relationships_v1.json"))
    assignments = _records(_read_json(output / "trace_net_nha_synthetic_page_assignments_v1.json"))
    questions = _records(_read_json(output / "trace_net_nha_synthetic_question_bank_v1.json"))
    graph = _read_json(output / "trace_net_nha_synthetic_graph_overlay_v1.json")
    result = validate_phase5(
        inventory, scenarios, relationships, assignments, questions, graph,
        expected_scenario_count=args.expected_scenario_count,
        expected_question_count=args.expected_question_count,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict and result["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE5_CHECK=FAIL")
    print("TRACE_NET_NHA_PHASE5_CHECK=PASS" if result["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE5_CHECK=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
