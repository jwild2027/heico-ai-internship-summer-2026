from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT = Path("scripts/serve_trace_net_router_proxy_v6_gemma_visual_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("router_gemma_visual_v1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["router_gemma_visual_v1"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeVisualEndpoint:
    docs = [{"page_id": "p1"}]
    rejected_docs = []

    def context_for_query(self, question, *, top_k=8, min_score=0.001):
        if "diagram" in question.lower() or "figure" in question.lower():
            return {
                "route_name": "gemma_confirmed_image_visual",
                "route_triggered": True,
                "context_pack_status": "gemma_visual_context_candidates_found",
                "citation_count": 1,
                "citations": [{"page_id": "p1"}],
            }
        return {
            "route_name": "gemma_confirmed_image_visual",
            "route_triggered": False,
            "context_pack_status": "visual_route_not_triggered",
            "citation_count": 0,
            "citations": [],
        }


def sample_config(mod):
    return mod.CompositeConfig(
        host="127.0.0.1",
        port=8017,
        normal_base_url="http://127.0.0.1:8014",
        guided_base_url="http://127.0.0.1:8016",
        model="trace-net-router-proxy-v6-gemma-visual-v1",
        timeout_seconds=1,
        default_top_k=8,
        default_loose_top_k=8,
        visual_top_k=8,
        visual_min_score=0.001,
        visual_route_first=True,
        base_config=None,
        visual_endpoint=FakeVisualEndpoint(),
    )


def test_visual_query_uses_gemma_visual_route() -> None:
    mod = load_module()
    routed = mod.route_payload({"query": "Find the passenger seat assembly diagram"}, sample_config(mod))

    assert routed["route"] == "gemma_confirmed_image_visual"
    assert routed["citation_count"] == 1
    assert routed["answer_permission"] is False


def test_partial_part_bypasses_visual() -> None:
    mod = load_module()
    routed = mod.route_payload({"query": "I only know the part starts with 24"}, sample_config(mod))

    assert routed["partial_part_lookup"] is True
    assert routed["partial_part_visual_bypass"] is True
    assert routed["visual_route_used"] is False
    assert routed["answer_permission"] is False


def test_exact_part_nonvisual_falls_back() -> None:
    mod = load_module()
    routed = mod.route_payload({"query": "Find part number 120-41824-003"}, sample_config(mod))

    assert routed["route"] != "gemma_confirmed_image_visual"
    assert routed["visual_route_used"] is False
