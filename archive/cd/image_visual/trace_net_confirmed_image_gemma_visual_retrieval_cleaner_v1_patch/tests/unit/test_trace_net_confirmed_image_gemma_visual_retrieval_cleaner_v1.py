from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path("scripts/benchmark/visual/build_trace_net_confirmed_image_gemma_visual_retrieval_cleaner_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("visual_cleaner_v1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["visual_cleaner_v1"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_clean_structured_card_removes_prompt_leak_keywords() -> None:
    mod = load_module()
    card = {
        "normalized_visual_page_type": "technical_diagram_or_figure",
        "normalized_subject": "visual page associated with part number(s): 120-41824-007",
        "figure_refs": ["figure 5", "Armrest on the chair"],
        "part_numbers": ["120-41824-007"],
        "visible_callouts": ["arrows", "120-41824-007"],
        "visual_layout_summary": "Technical diagram.",
        "uncertainty_notes": "Safety note: Do not prove fit/interchangeability/effectivity/approval/installation. Do not replace OCR.",
        "retrieval_keywords": [
            "TRACE-Net's visual observation specialist",
            "scanned aircraft technical-manual pages",
            "Tecnam Aircraft",
            "Type Certificate Data Sheet",
            "figure 5",
        ],
        "evidence_use": "This card provides visual confirmation of a part.",
        "prohibited_claims": ["fit"],
        "confidence": "high",
    }
    out = mod.clean_structured_card(card)

    blob = str(out)
    assert "TRACE-Net" not in blob
    assert "Tecnam" not in blob
    assert out["figure_refs"] == ["figure 5"]
    assert out["visible_callouts"] == ["120-41824-007"]
    assert "not final proof" in out["evidence_use"].lower()
    assert "confirmation" not in out["evidence_use"].lower()


def test_quality_fails_on_prompt_leak() -> None:
    mod = load_module()
    records = [{
        "structured_visual_card": {
            "retrieval_keywords": ["TRACE-Net's visual observation specialist"],
            "evidence_use": "retrieval only. This is not final proof.",
            "visible_callouts": [],
            "figure_refs": [],
        },
        "safety_contract": {
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        },
    }]
    summary = mod.quality_summary(records, [], min_record_count=1)
    assert summary["quality_status"] == "FAIL"
    assert summary["prompt_leak_record_count"] == 1


def test_clean_record_forces_safety_false() -> None:
    mod = load_module()
    row = {
        "page_id": "p1",
        "structured_visual_card": {
            "figure_refs": ["609"],
            "part_numbers": [],
            "visible_callouts": ["arrows"],
            "evidence_use": "retrieval only",
        },
        "safety_contract": {
            "answer_permission": True,
            "final_answer_allowed": True,
            "source_truth_mutation_allowed": True,
        },
    }
    out = mod.clean_record(row)

    assert out["structured_visual_card"]["figure_refs"] == ["figure 609"]
    assert out["structured_visual_card"]["visible_callouts"] == []
    assert out["safety_contract"]["answer_permission"] is False
    assert out["safety_contract"]["final_answer_allowed"] is False
    assert out["safety_contract"]["source_truth_mutation_allowed"] is False
