import importlib.util
import json
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "serve_trace_net_guided_discovery_router_proxy_v2.py"
spec = importlib.util.spec_from_file_location("router_proxy", SCRIPT)
router = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = router
spec.loader.exec_module(router)


def cfg():
    return router.ServerConfig(
        host="127.0.0.1",
        port=8017,
        normal_base_url="http://normal.local",
        guided_base_url="http://guided.local",
        model="trace-net-router-proxy-v2",
        timeout_seconds=1.0,
        default_top_k=8,
        default_loose_top_k=8,
    )


def test_detects_partial_part_prefix_lookup():
    decision = router.route_question("I am looking for a part that starts with numbers 2 and 4 but I do not have the rest")
    assert decision.route == "guided_discovery"
    assert decision.partial_part_lookup is True
    assert decision.weak_query is True


def test_normal_question_routes_to_normal_ask():
    decision = router.route_question("Find part number 120-36833-001")
    assert decision.route == "normal_ask"
    assert decision.partial_part_lookup is False


def test_forced_mode_overrides_auto_detection():
    assert router.route_question("Find part number 120-36833-001", "guided").route == "guided_discovery"
    assert router.route_question("I only know a part starts with 24", "normal").route == "normal_ask"


def test_extract_question_from_chat_messages():
    payload = {"messages": [{"role": "system", "content": "x"}, {"role": "user", "content": "hello"}]}
    assert router.extract_question(payload) == "hello"




def test_normal_request_includes_query_and_user_message_for_8014_schema():
    req = router.build_normal_request({"question": "Find part number 120-36833-001"}, "Find part number 120-36833-001")
    assert req["query"] == "Find part number 120-36833-001"
    assert req["question"] == "Find part number 120-36833-001"
    assert req["messages"] == [{"role": "user", "content": "Find part number 120-36833-001"}]


def test_normal_request_preserves_existing_chat_message():
    payload = {"messages": [{"role": "user", "content": "Find part number 120-36833-001"}]}
    req = router.build_normal_request(payload, "Find part number 120-36833-001")
    assert req["query"] == "Find part number 120-36833-001"
    assert req["messages"] == payload["messages"]

def test_route_payload_to_guided_surfaces_ui_fields():
    guided_response = {
        "status": "TRACE_NET_GUIDED_CANDIDATE_DISCOVERY_ENDPOINT_V1_DONE",
        "quality_status": "PASS",
        "intent": "partial_part_prefix_lookup",
        "known_clues": {"part_prefix": "24"},
        "missing_clues": ["manufacturer_or_company"],
        "clarifying_questions": ["Do you know the manufacturer?"],
        "strict_prefix_candidates": [{"candidate_part_number": "244CS-3-2", "nomenclature": "AR - FASTENER"}],
        "loose_candidates": [],
        "candidate_routes": [],
        "strict_prefix_candidate_count": 1,
        "loose_candidate_count": 0,
        "source_trace_status": "candidate-discovery-only",
        "final_answer_allowed": False,
    }
    with mock.patch.object(router, "http_post_json", return_value=(200, guided_response)) as post:
        out = router.route_payload({"question": "part starts with 24"}, cfg())
    assert out["quality_status"] == "PASS"
    assert out["route"] == "guided_discovery"
    assert out["strict_prefix_candidates"][0]["candidate_part_number"] == "244CS-3-2"
    assert out["final_answer_allowed"] is False
    assert post.call_args.args[0].endswith("/api/trace-net/guided-discovery")


def test_route_payload_to_normal_ask():
    normal_response = {"status": "ok", "answer": "citation-backed draft", "final_answer_allowed": False}
    with mock.patch.object(router, "http_post_json", return_value=(200, normal_response)) as post:
        out = router.route_payload({"question": "Find part number 120-36833-001"}, cfg())
    assert out["quality_status"] == "PASS"
    assert out["route"] == "normal_ask"
    assert out["downstream_response"]["answer"] == "citation-backed draft"
    assert post.call_args.args[0].endswith("/api/trace-net/ask")
    sent = post.call_args.args[1]
    assert sent["query"] == "Find part number 120-36833-001"
    assert sent["messages"][0]["content"] == "Find part number 120-36833-001"


def test_guided_chat_content_is_readable():
    content = router.guided_payload_to_chat_content(
        {
            "known_clues": {"part_prefix": "24"},
            "clarifying_questions": ["Do you know the ATA?"],
            "strict_prefix_candidates": [
                {
                    "candidate_part_number": "244CS-3-2",
                    "nomenclature": "AR - FASTENER",
                    "page_id": "t_p_120_1176_p000491",
                    "confidence": "high",
                    "why_matched": "part starts with prefix 24",
                }
            ],
            "loose_candidates": [],
            "final_answer_allowed": False,
        }
    )
    assert "not a final part identification" in content
    assert "244CS-3-2" in content
    assert "Final answer allowed: false" in content


def test_openai_chat_response_shape():
    decision = router.RouteDecision("guided_discovery", "test", "high", True, True)
    resp = router.openai_chat_response("m", "hello", {"x": 1}, decision)
    assert resp["object"] == "chat.completion"
    assert resp["choices"][0]["message"]["content"] == "hello"
    assert resp["trace_net_router"]["route"] == "guided_discovery"
