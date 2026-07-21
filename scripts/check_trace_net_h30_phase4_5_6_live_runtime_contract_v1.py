#!/usr/bin/env python3
"""Check Phase 4.5.6 live mature runtime contracts."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    planner = load(
        "phase456_check_planner",
        "scripts/trace_net_h30_validated_planner_execution_v1.py",
    )
    cold = load(
        "phase456_check_cold",
        "scripts/trace_net_h30_cold_start_streaming_v1.py",
    )
    writer = load(
        "phase456_check_writer",
        "scripts/serve_trace_net_full_gemma_cognitive_v1.py",
    )

    exact = planner.ROUTE_TUNNELS["exact_identifier_lookup"]
    guided = planner.ROUTE_TUNNELS["guided_part_discovery"]

    questions = [
        "What additional part number characters do you remember after the prefix 123?",
        "Do you know the manufacturer, vendor, or supplier?",
        "What component, function, or assembly is the part associated with?",
        "Do you know the ATA chapter or aircraft system?",
        "Do you remember a figure, diagram, IPL table, item number, or page?",
    ]
    cognitive_result = {
        "route": "guided_part_discovery",
        "content": (
            "TRACE-Net found candidate evidence, not a final identification:\n"
            "- 1234567\n"
            "Candidate results are guidance only until resolved to direct source evidence."
        ),
        "follow_up_questions": questions,
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [{"candidate_value": "1234567"}],
        },
        "citation_count": 0,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }

    class FakeRuntime:
        def health(self):
            return {"quality_status": "PASS"}

    def fake_http_json(*args, **kwargs):
        return 200, dict(cognitive_result)

    def fake_contract(result):
        updated = dict(result)
        updated["content"] = "## Answer\n\n" + str(result.get("content") or "")
        return updated

    module = {
        "Runtime": FakeRuntime,
        "make_handler": lambda runtime: object,
        "http_json": fake_http_json,
        "direct_evidence": lambda result: [],
        "validate_answer": lambda *args, **kwargs: {
            "quality_status": "PASS",
            "failures": [],
            "accepted": True,
        },
        "build_prompt": lambda *args, **kwargs: "",
        "extract_latest_user": lambda payload: "I only know the part starts with 123",
        "error_payload": lambda *args, **kwargs: {},
        "openai_response": lambda *args, **kwargs: {},
        "MODEL_ID": "trace-net-gemma4-cognitive-rag-v1",
        "MODULE": "fake_writer",
        "clean_engineer_text": lambda text: text,
        "apply_engineer_answer_contract": fake_contract,
        "append_follow_up_questions": writer.append_follow_up_questions,
    }
    cold.install_gemma_latency_support(module)

    runtime = FakeRuntime()
    runtime.cognitive_base_url = "http://127.0.0.1:8118"
    runtime.cognitive_api_key = "key"
    runtime.gemma_base_url = "http://127.0.0.1:11434/v1"
    runtime.gemma_model = "gemma4:26b"
    runtime.timeout = 10

    result = runtime.process(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "I only know the part starts with 123",
                }
            ]
        }
    )

    checks = {
        "exact_executor_declares_phase4_3_resolution": (
            "phase4_3_exact_source_resolution" in exact
        ),
        "guided_executor_declares_phase4_3_resolution": (
            "phase4_3_candidate_source_resolution" in guided
        ),
        "native_wrapper_followups_visible": (
            result.get("follow_up_questions_visible") is True
        ),
        "native_wrapper_visible_count_five": (
            result.get("follow_up_questions_visible_count") == 5
        ),
        "native_wrapper_appends_once": (
            str(result.get("content") or "").count(
                "Helpful follow-up questions:"
            ) == 1
        ),
        "candidate_writer_still_skips_gemma": (
            result.get("gemma_status") == "SKIPPED_NO_DIRECT_EVIDENCE"
        ),
        "answer_permission_false": result.get("answer_permission") is False,
        "source_truth_mutation_false": (
            result.get("source_truth_mutation_allowed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    output = {
        "module": "check_trace_net_h30_phase4_5_6_live_runtime_contract_v1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "checks": checks,
        "exact_tunnels": list(exact),
        "guided_tunnels": list(guided),
        "follow_up_questions_visible_count": result.get(
            "follow_up_questions_visible_count"
        ),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }
    print(json.dumps(output, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
