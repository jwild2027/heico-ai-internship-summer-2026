import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v5.py")
spec = importlib.util.spec_from_file_location("router_v5", MODULE_PATH)
router = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = router
spec.loader.exec_module(router)


def test_contains_digits_page_hint_fast_clarification():
    decision = router.route_question("The part had 36833 in it and I think it was on the first few pages.")
    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is True
    assert decision.weak_query is True


def test_ring_locking_contains_digits_fast_clarification():
    decision = router.route_question("I saw a ring locking part and the number had 48024 somewhere.")
    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is True


def test_clean_prefix_still_full_guided_discovery():
    decision = router.route_question("I only know the part starts with 24.")
    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is False


def test_fast_clarification_payload_has_three_questions_and_safety():
    payload = router.build_fast_clarification_payload("The part had 36833 in it and I think it was on the first few pages.")
    assert payload["quality_status"] == "PASS"
    assert payload["final_answer_allowed"] is False
    assert payload["source_trace_status"] == "candidate-discovery-only"
    assert payload["fast_clarification_only"] is True
    assert len(payload["clarifying_questions"]) >= 3
    assert payload["safety_contract"]["source_truth_mutation_allowed_count"] == 0


def test_route_payload_fast_clarification_does_not_call_network():
    config = router.ServerConfig(
        host="127.0.0.1",
        port=8017,
        normal_base_url="http://normal.invalid",
        guided_base_url="http://guided.invalid",
        model="trace-net-router-proxy-v5",
        timeout_seconds=0.01,
        default_top_k=8,
        default_loose_top_k=8,
    )
    out = router.route_payload({"question": "I saw a ring locking part and the number had 48024 somewhere."}, config)
    assert out["quality_status"] == "PASS"
    assert out["route"] == "guided_discovery"
    assert out["fast_clarification_only"] is True
    assert out["downstream_endpoint"] == "internal://trace-net/router/fast-clarification"
    assert out["downstream_status_code"] == 200
    assert len(out["clarifying_questions"]) >= 3


def test_openai_chat_content_for_fast_clarification_mentions_no_final_answer():
    payload = router.build_fast_clarification_payload("The part had 36833 in it and I think it was on the first few pages.")
    content = router.guided_payload_to_chat_content(payload)
    assert "before running expensive candidate discovery" in content
    assert "Final answer allowed: false" in content
    assert content.count("?") >= 3


def test_safety_claim_routes_to_fast_clarification():
    decision = router.route_question("Can 120-41824-003 be used instead of 120-41824-007?")
    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is True
