from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path("scripts/serve_trace_net_openwebui_unified_rag_v2.py")


def load():
    spec = importlib.util.spec_from_file_location("unified_followup_v1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["unified_followup_v1"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_descriptive_hinge_uses_guided_route():
    mod = load()
    assert mod.route_kind("I would like a part that is a hinge") == "guided_discovery"


def test_local_router_clarification_payload_has_contextual_questions():
    mod = load()
    decision = mod.analyze_query("I would like a part that is a hinge")
    payload = mod.router_clarification_payload("I would like a part that is a hinge", decision)
    assert payload["quality_status"] == "PASS"
    assert payload["candidate_routes"] == []
    text = " ".join(payload["clarifying_questions"]).lower()
    assert "part-number" in text or "part number" in text
    assert "manufacturer" in text or "company" in text
    assert payload["final_answer_allowed"] is False
