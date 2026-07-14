from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/build_trace_net_confirmed_image_gemma_structured_visual_cards_v1_1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("gemma_visual_cards_v1_1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gemma_visual_cards_v1_1"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_validate_filters_non_figure_refs_and_generic_callouts() -> None:
    mod = load_module()
    parsed = {
        "page_id": "x",
        "normalized_visual_page_type": "technical_diagram",
        "normalized_subject": "seat",
        "figure_refs": ["figure 3", "Armrest on the chair", "609", "figure 2 sheet 1"],
        "part_numbers": ["120-41824-003", "999-99999-999"],
        "visible_callouts": ["arrows", "part numbers", "Armrest", "3"],
        "visual_layout_summary": "layout",
        "uncertainty_notes": "uncertain",
        "retrieval_keywords": ["seat"],
        "evidence_use": "This card provides visual confirmation of a part.",
        "prohibited_claims": ["fit"],
        "confidence": "high",
    }
    out = mod.validate_structured_card(parsed, "x", ["120-41824-003"])

    assert out["figure_refs"] == ["figure 3", "figure 609", "figure 2 sheet 1"]
    assert out["part_numbers"] == ["120-41824-003"]
    assert out["visible_callouts"] == ["Armrest", "3"]
    assert "confirmation" not in out["evidence_use"].lower()
    assert "not final proof" in out["evidence_use"].lower()


def test_deterministic_structured_card_uses_retrieval_not_proof_language() -> None:
    mod = load_module()
    row = {
        "page_id": "t_p_120_1176_p000084",
        "visual_page_summary": {
            "visual_page_type": "technical_diagram_or_figure",
            "likely_diagram_subject": "visual page associated with part number(s): 120-41824-003",
            "figure_refs_clean": ["figure 2 sheet 1"],
            "part_numbers": ["120-41824-003"],
            "visual_observations": ["cleaned visible callouts: arrows | uncertainty: text is small"],
        },
        "llava_clean_observation": {
            "parsed": True,
            "diagram_subject_guess": "unknown",
            "visual_layout_description": "The page consists of technical diagrams with arrows.",
            "visible_callouts_or_labels_cleaned": ["arrows"],
            "visual_uncertainty": "Some text is blurry.",
        },
    }
    record = mod.build_record(
        row,
        call_ollama_gemma=False,
        ollama_base_url="http://127.0.0.1:11434",
        gemma_model="gemma4:26b",
        timeout_seconds=1.0,
    )
    card = record["structured_visual_card"]

    assert card["visible_callouts"] == []
    assert "not final proof" in card["evidence_use"].lower()
    assert record["safety_contract"]["final_answer_allowed"] is False


def test_quality_fails_if_proof_word_survives() -> None:
    mod = load_module()
    records = [
        {
            "structured_visual_card": {
                "evidence_use": "visual confirmation",
                "visible_callouts": [],
                "figure_refs": [],
            },
            "gemma_status": "not_requested",
            "runtime_counts": {"ollama_gemma_call_attempt": False},
            "safety_contract": {
                "answer_permission": False,
                "final_answer_allowed": False,
                "source_truth_mutation_allowed": False,
            },
        }
    ]
    summary = mod.build_summary(records, [], selected_page_count=1, min_record_count=1, require_gemma_success=False)
    assert summary["quality_status"] == "FAIL"
    assert summary["proof_word_evidence_use_count"] == 1
