from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/operations/visual/serve_trace_net_router_proxy_v6_gemma_visual_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("router_gemma_visual_v1_fix", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["router_gemma_visual_v1_fix"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeVisualEndpoint:
    docs = [{"page_id": "p1"}]
    rejected_docs = []

    def context_for_query(self, question, *, top_k=8, min_score=0.001):
        return {
            "route_name": "gemma_confirmed_image_visual",
            "route_triggered": False,
            "context_pack_status": "visual_route_not_triggered",
            "citation_count": 0,
            "citations": [],
        }


class ExplodingBaseRouter:
    @staticmethod
    def route_payload(payload, config):
        raise AssertionError("base router should not be called when base_config is None")


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


def test_none_base_config_uses_stub_fallback(monkeypatch) -> None:
    mod = load_module()
    monkeypatch.setattr(mod, "base_router", ExplodingBaseRouter)

    routed = mod.route_payload({"query": "Find part number 120-41824-003"}, sample_config(mod))

    assert routed["route"] == "normal_ask"
    assert routed["visual_route_used"] is False
    assert routed["answer_permission"] is False


def test_none_base_config_partial_uses_stub_fallback(monkeypatch) -> None:
    mod = load_module()
    monkeypatch.setattr(mod, "base_router", ExplodingBaseRouter)

    routed = mod.route_payload({"query": "I only know the part starts with 24"}, sample_config(mod))

    assert routed["partial_part_lookup"] is True
    assert routed["partial_part_visual_bypass"] is True
    assert routed["visual_route_used"] is False
    assert routed["answer_permission"] is False
