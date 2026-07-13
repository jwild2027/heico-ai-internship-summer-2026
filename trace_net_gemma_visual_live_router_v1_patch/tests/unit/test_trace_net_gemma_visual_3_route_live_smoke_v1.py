from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path("scripts/run_trace_net_gemma_visual_3_route_live_smoke_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("gemma_visual_smoke_v1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gemma_visual_smoke_v1"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_validate_visual_record() -> None:
    mod = load_module()
    spec = {
        "name": "visual_exact_part_diagram",
        "query": "Find diagram for part number 120-41824-003",
        "expected_visual": True,
        "min_citations": 1,
        "expected_page_id": "t_p_120_1176_p000084",
    }
    response = {
        "route": "gemma_confirmed_image_visual",
        "visual_route_used": True,
        "citation_count": 1,
        "citations": [{"page_id": "t_p_120_1176_p000084"}],
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    }
    record = mod.validate_record(spec, response)
    assert record["quality_status"] == "PASS"


def test_validate_rejects_unexpected_visual() -> None:
    mod = load_module()
    spec = {"name": "normal_exact_part", "query": "Find part number 120-41824-003", "expected_visual": False}
    response = {
        "route": "gemma_confirmed_image_visual",
        "visual_route_used": True,
        "citation_count": 1,
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    }
    record = mod.validate_record(spec, response)
    assert record["quality_status"] == "FAIL"
    assert "unexpected_visual_route" in record["failures"]
