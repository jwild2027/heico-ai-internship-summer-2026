from __future__ import annotations

import importlib.util
import sys


SCRIPT = "scripts/operations/visual/serve_trace_net_router_proxy_v6_gated_visual_v1_1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("router_visual_composite_v1_1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["router_visual_composite_v1_1"] = mod
    spec.loader.exec_module(mod)
    return mod


def sample_config(mod):
    docs = [
        {
            "document_id": "doc1",
            "page_id": "p001",
            "search_ready": True,
            "review_only": False,
            "visual_route": "image_visual",
            "visual_subtype": "confirmed_diagram_dominant",
            "visual_summaries": ["Technical drawing showing passenger seat assembly callouts."],
            "identifiers": {
                "figure_refs": ["figure 601"],
                "part_numbers": ["120-12345-001"],
            },
            "search_text": "passenger seat assembly diagram callout figure 601 part 120-12345-001",
        }
    ]
    review = [
        {
            "document_id": "review1",
            "page_id": "p999",
            "search_ready": False,
            "review_only": True,
            "visual_route": "visual_candidate_review",
            "search_text": "review only passenger seat assembly",
        }
    ]
    base_config = mod.base_router.ServerConfig(
        host="127.0.0.1",
        port=8017,
        normal_base_url="http://127.0.0.1:8014",
        guided_base_url="http://127.0.0.1:8016",
        model="trace-net-router-proxy-v6-gated-visual-v1-1",
        timeout_seconds=1,
        default_top_k=8,
        default_loose_top_k=8,
    )
    visual_endpoint = mod.visual_live.VisualEndpoint(docs=docs, review_docs=review, top_k=8, min_score=0.001)
    return mod.CompositeConfig(
        host="127.0.0.1",
        port=8017,
        normal_base_url="http://127.0.0.1:8014",
        guided_base_url="http://127.0.0.1:8016",
        model="trace-net-router-proxy-v6-gated-visual-v1-1",
        timeout_seconds=1,
        default_top_k=8,
        default_loose_top_k=8,
        visual_top_k=8,
        visual_min_score=0.001,
        visual_route_first=True,
        base_config=base_config,
        visual_endpoint=visual_endpoint,
    )


def test_visual_query_still_uses_gated_visual() -> None:
    mod = load_module()
    config = sample_config(mod)

    routed = mod.route_payload({"query": "Find the passenger seat assembly diagram with callouts"}, config)

    assert routed["quality_status"] == "PASS"
    assert routed["route"] == "gated_image_visual"
    assert routed["citation_count"] == 1
    assert routed["answer_permission"] is False
    assert routed["gated_visual_context"]["citations"][0]["page_id"] == "p001"


def test_partial_part_lookup_bypasses_visual_and_uses_base_router(monkeypatch) -> None:
    mod = load_module()
    config = sample_config(mod)

    def fake_base_route(payload, base_config):
        return {
            "status": "TRACE_NET_GUIDED_DISCOVERY_ROUTER_PROXY_V6_DONE",
            "quality_status": "PASS",
            "router": "guided_discovery_router_proxy_v6",
            "route": "guided_discovery",
            "route_reason": "partial part lookup",
            "route_confidence": "high",
            "weak_query": True,
            "partial_part_lookup": True,
            "question": mod.extract_question(payload),
            "downstream_response": {"content": "guided fallback"},
            "final_answer_allowed": False,
            "answer_permission": False,
        }

    monkeypatch.setattr(mod.base_router, "route_payload", fake_base_route)

    routed = mod.route_payload({"query": "I only know the part starts with 24"}, config)

    assert routed["route"] == "guided_discovery"
    assert routed["partial_part_lookup"] is True
    assert routed["partial_part_visual_bypass"] is True
    assert routed["visual_route_used"] is False
    assert routed["answer_permission"] is False


def test_plain_nonvisual_falls_back_to_base_router(monkeypatch) -> None:
    mod = load_module()
    config = sample_config(mod)

    def fake_base_route(payload, base_config):
        return {
            "status": "TRACE_NET_GUIDED_DISCOVERY_ROUTER_PROXY_V6_DONE",
            "quality_status": "PASS",
            "router": "guided_discovery_router_proxy_v6",
            "route": "normal_ask",
            "route_reason": "normal fallback",
            "route_confidence": "medium",
            "weak_query": False,
            "partial_part_lookup": False,
            "question": mod.extract_question(payload),
            "downstream_response": {"content": "normal fallback"},
            "final_answer_allowed": False,
            "answer_permission": False,
        }

    monkeypatch.setattr(mod.base_router, "route_payload", fake_base_route)

    routed = mod.route_payload({"query": "What is the torque limit"}, config)

    assert routed["route"] == "normal_ask"
    assert routed["visual_route_used"] is False
    assert routed["answer_permission"] is False


def test_forced_visual_can_still_use_visual_for_partial_part_query() -> None:
    mod = load_module()
    config = sample_config(mod)

    routed = mod.route_payload({"query": "I only know the part starts with 24", "mode": "visual"}, config)

    assert routed["route"] == "gated_image_visual"
    assert routed["answer_permission"] is False
