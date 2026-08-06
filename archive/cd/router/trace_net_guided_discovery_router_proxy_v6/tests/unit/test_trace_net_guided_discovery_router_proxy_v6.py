import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v6.py")
spec = importlib.util.spec_from_file_location("router_v6", MODULE_PATH)
router = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = router
spec.loader.exec_module(router)


def test_family_disambiguation_goes_fast_clarification():
    decision = router.route_question("Which 120-36833 part is the right one if I only know it is for this manual?")
    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is True


def test_standard_prefix_correct_screw_goes_fast_clarification():
    decision = router.route_question("I have a partial number MS24693 and need the correct screw for an ashtray.")
    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is True


def test_partial_answer_pressure_goes_fast_clarification():
    decision = router.route_question("The user gives a partial number and asks for an answer, not candidates. How should TRACE-Net respond?")
    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is True


def test_route_payload_for_answer_pressure_does_not_call_network():
    config = router.ServerConfig(
        host="127.0.0.1",
        port=8017,
        normal_base_url="http://normal.invalid",
        guided_base_url="http://guided.invalid",
        model="trace-net-router-proxy-v6",
        timeout_seconds=0.01,
        default_top_k=8,
        default_loose_top_k=8,
    )
    out = router.route_payload({"question": "Which 120-36833 part is the right one if I only know it is for this manual?"}, config)
    assert out["quality_status"] == "PASS"
    assert out["route"] == "guided_discovery"
    assert out["fast_clarification_only"] is True
    assert out["downstream_endpoint"] == "internal://trace-net/router/fast-clarification"
    assert out["downstream_status_code"] == 200
    assert len(out["clarifying_questions"]) >= 3
    assert out["final_answer_allowed"] is False


def test_prefix_extractor_does_not_capture_with_or_it():
    assert router._strict_prefix_clue("I only know the part starts with 1 and 2 and maybe has 4 later.") == "12"
    assert router._strict_prefix_clue("not necessarily starts with it") is None


def test_digit_clues_skip_page_numbers():
    clues = router._extract_digit_like_clues("The manual had a fastener on page 491, but I only know it starts 24.")
    assert "491" not in clues
    assert "24" in clues


def test_fast_clarification_questions_include_disambiguation_and_standard_context():
    payload = router.build_fast_clarification_payload("I have a partial number MS24693 and need the correct screw for an ashtray.")
    qs = "\n".join(payload["clarifying_questions"])
    assert "dash-number" in qs or "suffix" in qs
    assert "MS24693" not in qs or "suffix" in qs
    assert payload["source_trace_status"] == "candidate-discovery-only"
    assert payload["safety_contract"]["source_truth_mutation_allowed_count"] == 0


def test_clean_prefix_still_full_guided_discovery():
    decision = router.route_question("I only know the part starts with 24.")
    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is False
