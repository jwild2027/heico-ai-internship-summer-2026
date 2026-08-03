from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/build/visual/build_trace_net_confirmed_image_gemma_structured_visual_cards_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("gemma_visual_cards_v1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gemma_visual_cards_v1"] = mod
    spec.loader.exec_module(mod)
    return mod


def sample_row():
    return {
        "module": "trace_net_confirmed_image_page_summary_v1_2",
        "page_id": "t_p_120_1176_p000084",
        "source_visual_route": "image_visual",
        "source_visual_subtype": "confirmed_diagram_dominant",
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
            "figure_title_or_sheet_text_if_clearly_visible": "",
            "visible_callouts_or_labels_cleaned": ["arrows"],
            "visual_uncertainty": "Some text is blurry.",
            "retrieval_keywords": ["technical diagram", "part number"],
        },
        "model_layers": {"llava_clean_payload_loaded": True},
    }


def test_deterministic_structured_card_preserves_source_parts() -> None:
    mod = load_module()
    card = mod.deterministic_structured_card(sample_row())

    assert card["page_id"] == "t_p_120_1176_p000084"
    assert card["part_numbers"] == ["120-41824-003"]
    assert "figure 2 sheet 1" in card["figure_refs"]
    assert "arrows" in card["visible_callouts"]
    assert "fit" in card["prohibited_claims"]


def test_validate_rejects_gemma_invented_part_numbers() -> None:
    mod = load_module()
    parsed = {
        "page_id": "x",
        "normalized_visual_page_type": "technical_diagram",
        "normalized_subject": "seat",
        "figure_refs": ["figure 1"],
        "part_numbers": ["120-41824-003", "999-99999-999"],
        "visible_callouts": ["item 1"],
        "visual_layout_summary": "layout",
        "uncertainty_notes": "uncertain",
        "retrieval_keywords": ["seat"],
        "evidence_use": "retrieval only",
        "prohibited_claims": ["fit"],
        "confidence": "high",
    }
    out = mod.validate_structured_card(parsed, "x", ["120-41824-003"])

    assert out["part_numbers"] == ["120-41824-003"]
    assert "999-99999-999" not in out["part_numbers"]
    assert {"fit", "interchangeability", "effectivity", "approval", "eligibility", "installation"}.issubset(set(out["prohibited_claims"]))


def test_build_record_without_gemma_keeps_safety_false() -> None:
    mod = load_module()
    record = mod.build_record(
        sample_row(),
        call_ollama_gemma=False,
        ollama_base_url="http://127.0.0.1:11434",
        gemma_model="gemma4:26b",
        timeout_seconds=1.0,
    )

    assert record["gemma_status"] == "not_requested"
    assert record["structured_visual_card"]["page_id"] == "t_p_120_1176_p000084"
    assert record["safety_contract"]["answer_permission"] is False
    assert record["safety_contract"]["source_truth_mutation_allowed"] is False
