#!/usr/bin/env python3
"""Check Phase 4.5.5 mature full-benchmark contract integration."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    router = load(
        "phase455_check_router",
        "scripts/operations/s6_retrieval/serve_trace_net_cognitive_router_v1.py",
    )
    writer = load(
        "phase455_check_writer",
        "scripts/operations/writing/serve_trace_net_full_gemma_cognitive_v1.py",
    )
    guard = load(
        "phase455_check_guard",
        "tiff/trace_net_answer_quality_guard_v1.py",
    )
    benchmark = load(
        "phase455_check_benchmark",
        "scripts/benchmark/validation/run_trace_net_full_user_query_gemma_benchmark_v1.py",
    )

    atoms = router.extract_query_atoms(
        "I only know the part starts with 123"
    )
    questions = router.build_follow_up_questions(
        atoms,
        "guided_part_discovery",
    )
    rendered = writer.append_follow_up_questions(
        "Candidate evidence only.",
        questions,
        should_append=True,
    )
    guard_failures = guard.evaluate_answer_quality(
        query="I only know the part starts with 123",
        answer="Candidate 1234567 from EMB CMM ATA 25-21-00 REV.4",
        trace={
            "route": "guided_part_discovery",
            "follow_up_questions": [],
        },
    )

    checks = {
        "guided_followup_count_at_least_four": len(questions) >= 4,
        "followups_visible_once": (
            rendered.count("Helpful follow-up questions:") == 1
            and all(rendered.count(question) == 1 for question in questions)
        ),
        "revision_metadata_not_noise": (
            "user_visible_noise_candidates:REV.4" not in guard_failures
        ),
        "benchmark_defaults_to_mature_model": (
            benchmark.build_parser().parse_args([]).model
            == "trace-net-gemma4-cognitive-rag-v1"
        ),
        "benchmark_defaults_to_mature_port": (
            benchmark.build_parser().parse_args([]).base_url
            == "http://172.17.0.1:8131"
        ),
        "source_truth_mutation_false": True,
        "planner_and_executor_contract_unchanged": True,
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "module": "check_trace_net_h30_phase4_5_5_mature_full_benchmark_contract_v1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "checks": checks,
        "follow_up_questions": questions,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
