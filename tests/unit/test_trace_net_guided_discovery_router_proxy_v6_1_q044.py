from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROUTER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "serve_trace_net_guided_discovery_router_proxy_v6.py"


def _load_router_module():
    module_name = "trace_net_router_proxy_v6_q044"
    spec = importlib.util.spec_from_file_location(module_name, ROUTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Python 3.14 dataclasses resolve string annotations through sys.modules
    # while @dataclass executes. Register the module before exec_module.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_q044_loose_contains_exact_policy_routes_to_fast_guided_clarification():
    router = _load_router_module()
    question = "I want to know if a loose contains match should be treated as exact."

    decision = router.route_question(question)

    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is True
    assert decision.partial_part_lookup is True


def test_q044_clarifying_questions_match_expected_policy_themes():
    router = _load_router_module()
    question = "I want to know if a loose contains match should be treated as exact."

    questions = router.build_fast_clarification_questions(question)
    lowered = "\n".join(questions).lower()

    assert len(questions) >= 3
    assert "what exact clue and candidate are being compared" in lowered
    assert "start with the clue" in lowered
    assert "only contain" in lowered
    assert "source evidence" in lowered
    assert "promoting" in lowered


def test_q044_route_payload_stays_read_only_and_does_not_call_normal_ask():
    router = _load_router_module()
    config = router.ServerConfig(
        host="127.0.0.1",
        port=8017,
        normal_base_url="http://127.0.0.1:8014",
        guided_base_url="http://127.0.0.1:8016",
        model="trace-net-router-proxy-v6",
        timeout_seconds=1.0,
        default_top_k=8,
        default_loose_top_k=8,
    )

    response = router.route_payload(
        {
            "model": "trace-net-router-proxy-v6",
            "messages": [
                {
                    "role": "user",
                    "content": "I want to know if a loose contains match should be treated as exact.",
                }
            ],
        },
        config,
    )

    assert response["quality_status"] == "PASS"
    assert response["route"] == "guided_discovery"
    assert response["fast_clarification_only"] is True
    assert response["downstream_endpoint"] == "internal://trace-net/router/fast-clarification"
    assert response["final_answer_allowed"] is False
    safety = response.get("safety_contract", {})
    assert response.get(
        "source_truth_mutation_allowed_count",
        safety.get("source_truth_mutation_allowed_count", 0),
    ) == 0
    assert response.get(
        "postgres_write_attempt_count",
        safety.get("postgres_write_attempt_count", 0),
    ) == 0
    assert response.get(
        "qdrant_write_attempt_count",
        safety.get("qdrant_write_attempt_count", 0),
    ) == 0
    assert response.get(
        "opensearch_write_attempt_count",
        safety.get("opensearch_write_attempt_count", 0),
    ) == 0
    assert len(response["clarifying_questions"]) >= 3


def test_clear_strict_prefix_query_still_uses_full_guided_discovery_not_fast_clarification():
    router = _load_router_module()
    question = "Find part candidates that start with 24."

    decision = router.route_question(question)

    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is False


def test_exact_part_lookup_still_routes_to_normal_ask():
    router = _load_router_module()
    question = "Find part number 120-36833-001."

    decision = router.route_question(question)

    assert decision.route == "normal_ask"
    assert decision.fast_clarification_only is False


def test_q044_runtime_shim_is_defined_before_main_guard():
    """Server runtime must execute the q044 shim before entering blocking main()."""
    text = ROUTER_PATH.read_text(encoding="utf-8")
    shim_idx = text.find("# A routing-policy question about whether a loose contains match can be treated")
    main_idx = text.rfind('\nif __name__ == "__main__":')
    if main_idx < 0:
        main_idx = text.rfind("\nif __name__ == '__main__':")

    assert shim_idx >= 0
    assert main_idx >= 0
    assert shim_idx < main_idx

