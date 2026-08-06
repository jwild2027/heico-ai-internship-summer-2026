from __future__ import annotations

import importlib.util
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


def test_executor_owned_part_tunnels_include_phase4_3_resolution():
    planner = load(
        "phase456_planner",
        "src/trace_net/pipeline/s6_retrieval/routing/trace_net_h30_validated_planner_execution_v1.py",
    )
    exact = planner.ROUTE_TUNNELS["exact_identifier_lookup"]
    guided = planner.ROUTE_TUNNELS["guided_part_discovery"]

    assert "phase4_3_exact_source_resolution" in exact
    assert "phase4_3_candidate_source_resolution" in guided
    assert exact.index("phase4_3_exact_source_resolution") < exact.index(
        "qdrant_guidance"
    )
    assert guided.index("phase4_3_candidate_source_resolution") < guided.index(
        "qdrant_guidance"
    )


def test_planner_override_declares_phase4_3_candidate_tunnel():
    planner = load(
        "phase456_planner_override",
        "src/trace_net/pipeline/s6_retrieval/routing/trace_net_h30_validated_planner_execution_v1.py",
    )

    class FakeRoutePlan:
        def __init__(self, **kwargs: Any):
            self.__dict__.update(kwargs)

    deterministic = {
        "primary_route": "guided_part_discovery",
        "secondary_routes": [],
        "retrieval_tunnels": [
            "guided_candidate_discovery",
            "normal_source_resolution",
            "phase4_3_candidate_source_resolution",
            "qdrant_guidance",
        ],
        "authority_required": False,
        "repair_budget": 2,
        "rationale": ["deterministic"],
        "engram_policy": {},
        "working_memory": {},
    }
    decision = {
        "selected_route": "guided_part_discovery",
        "secondary_routes": [],
        "rollout_mode": "mature",
    }

    plan = planner._build_route_plan(
        {"RoutePlan": FakeRoutePlan},
        deterministic,
        decision,
    )
    assert plan.retrieval_tunnels == list(
        planner.ROUTE_TUNNELS["guided_part_discovery"]
    )
    assert "phase4_3_candidate_source_resolution" in plan.retrieval_tunnels


def test_native_writer_wrapper_restores_visible_followups_after_contract():
    cold = load(
        "phase456_cold",
        "src/trace_net/serving/adapters/trace_net_h30_cold_start_streaming_v1.py",
    )
    writer = load(
        "phase456_writer",
        "scripts/operations/writing/serve_trace_net_full_gemma_cognitive_v1.py",
    )

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

    assert result["writer_mode"] == "deterministic_fail_closed"
    assert result["gemma_status"] == "SKIPPED_NO_DIRECT_EVIDENCE"
    assert result["content"].startswith("## Answer")
    assert result["content"].count("Helpful follow-up questions:") == 1
    assert result["follow_up_questions_visible_count"] == 5
    assert result["follow_up_questions_visible"] is True
    for question in questions:
        assert result["content"].count(question) == 1
