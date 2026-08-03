from __future__ import annotations

import importlib.util
import sys


SCRIPT = "scripts/operations/visual/serve_trace_net_router_proxy_v6_gated_visual_v1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("router_visual_composite", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["router_visual_composite"] = mod
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
        model="trace-net-router-proxy-v6-gated-visual-v1",
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
        model="trace-net-router-proxy-v6-gated-visual-v1",
        timeout_seconds=1,
        default_top_k=8,
        default_loose_top_k=8,
        visual_top_k=8,
        visual_min_score=0.001,
        visual_route_first=True,
        base_config=base_config,
        visual_endpoint=visual_endpoint,
    )


def test_composite_router_uses_gated_visual_before_base_router() -> None:
    mod = load_module()
    config = sample_config(mod)

    routed = mod.route_payload({"query": "Find the passenger seat assembly diagram with callouts"}, config)

    assert routed["quality_status"] == "PASS"
    assert routed["route"] == "gated_image_visual"
    assert routed["citation_count"] == 1
    assert routed["final_answer_allowed"] is False
    assert routed["answer_permission"] is False
    assert routed["review_only_docs_used_for_context_count"] == 0
    assert routed["gated_visual_context"]["citations"][0]["page_id"] == "p001"


def test_composite_router_falls_back_to_existing_v6_for_nonvisual_query(monkeypatch) -> None:
    mod = load_module()
    config = sample_config(mod)

    def fake_base_route(payload, base_config):
        return {
            "status": "TRACE_NET_GUIDED_DISCOVERY_ROUTER_PROXY_V6_DONE",
            "quality_status": "PASS",
            "router": "guided_discovery_router_proxy_v6",
            "route": "normal_ask",
            "route_reason": "fake normal fallback",
            "route_confidence": "medium",
            "weak_query": False,
            "partial_part_lookup": False,
            "question": mod.extract_question(payload),
            "downstream_response": {"content": "normal fallback"},
            "final_answer_allowed": False,
        }

    monkeypatch.setattr(mod.base_router, "route_payload", fake_base_route)

    routed = mod.route_payload({"query": "What is the torque limit"}, config)

    assert routed["route"] == "normal_ask"
    assert routed["composite_router"] == "trace_net_router_proxy_v6_gated_visual_v1"
    assert routed["visual_route_checked"] is True
    assert routed["visual_route_used"] is False
    assert routed["final_answer_allowed"] is False


def test_composite_router_openai_chat_visual_content() -> None:
    mod = load_module()
    config = sample_config(mod)

    routed = mod.route_payload(
        {
            "model": "trace-net-router-proxy-v6-gated-visual-v1",
            "messages": [{"role": "user", "content": "Show figure references for passenger seat assembly diagram"}],
        },
        config,
    )
    content = mod.chat_content_for_routed(routed)
    chat = mod.openai_chat_response("trace-net-router-proxy-v6-gated-visual-v1", content, routed)

    assert chat["choices"][0]["message"]["role"] == "assistant"
    assert "Answer permission: false" in chat["choices"][0]["message"]["content"]
    assert chat["trace_net_router"]["route"] == "gated_image_visual"
    assert chat["trace_net_router"]["final_answer_allowed"] is False
