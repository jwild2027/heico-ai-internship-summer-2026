from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/build_trace_net_confirmed_image_page_summary_v1_2.py")


def load_module():
    spec = importlib.util.spec_from_file_location("confirmed_image_summary_v1_2", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["confirmed_image_summary_v1_2"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_filter_real_part_numbers_removes_noise_and_ata() -> None:
    mod = load_module()
    values = [
        "OCR/TABLE/FIGURE-ITEM",
        "VISUAL/OCR",
        "REVIEW-ONLY",
        "25-21-00",
        "120-41824-003",
        "120-41824-0",
        "120-41824-001/501",
        "MS24693-C5",
    ]
    assert mod.filter_real_part_numbers(values) == [
        "120-41824-003",
        "120-41824-001/501",
        "MS24693-C5",
    ]


def test_cleaned_llava_payload_drives_subject_not_raw_json() -> None:
    mod = load_module()
    doc = {
        "document_id": "doc::p019",
        "page_id": "t_p_120_1176_p000019",
        "visual_route": "image_visual",
        "visual_subtype": "confirmed_diagram_dominant",
        "summary": "parts_diagram_or_illustrated_parts_list",
        "figure_refs": ["figure 3"],
        "part_numbers": ["25-21-00", "OCR/TABLE/FIGURE-ITEM"],
        "callouts": [],
    }
    llava = {
        "page_id": "t_p_120_1176_p000019",
        "llava_status": "ollama_llava_observation_created",
        "llava_visual_observation": "```json {\"diagram_subject_guess\":\"Chair with a backrest and armrests\"} ```",
        "llava_observation_cleaned": {
            "parsed": True,
            "diagram_subject_guess": "Chair with a backrest and armrests",
            "visual_layout_description": "A technical drawing of a chair with armrests.",
            "figure_title_or_sheet_text_if_clearly_visible": "Figure 3",
            "visible_callouts_or_labels_cleaned": ["Figure 3"],
            "visual_uncertainty": "Small text is unclear.",
        },
    }
    card = mod.build_summary_card(
        doc,
        llava_observation=llava,
        call_ollama_llava=False,
        call_ollama_gemma=False,
        image_roots=[],
        ollama_base_url="http://127.0.0.1:11434",
        llava_model="llava:13b",
        gemma_model="gemma4:26b",
        ollama_timeout_seconds=1.0,
    )
    summary = card["visual_page_summary"]
    assert summary["likely_diagram_subject"] == "Chair with a backrest and armrests"
    assert not summary["likely_diagram_subject"].startswith("```")
    assert "figure 3" in summary["figure_refs_clean"]
    assert summary["part_numbers"] == []
    assert card["model_layers"]["llava_clean_payload_loaded"] is True


def test_unknown_llava_subject_does_not_become_raw_json_subject() -> None:
    mod = load_module()
    doc = {
        "document_id": "doc::p004",
        "page_id": "t_p_120_1176_p000004",
        "visual_route": "image_visual",
        "visual_subtype": "confirmed_diagram_dominant",
        "summary": "parts_diagram_or_illustrated_parts_list",
        "figure_refs": [],
        "part_numbers": [],
        "callouts": [],
    }
    llava = {
        "page_id": "t_p_120_1176_p000004",
        "llava_status": "ollama_llava_observation_created",
        "llava_visual_observation": "```json {\"diagram_subject_guess\":\"unknown\", \"visual_layout_description\":\"A technical drawing.\"} ```",
        "llava_observation_cleaned": {
            "parsed": True,
            "diagram_subject_guess": "unknown",
            "visual_layout_description": "A technical drawing.",
            "visible_callouts_or_labels_cleaned": [],
            "visual_uncertainty": "Subject unclear.",
        },
    }
    card = mod.build_summary_card(
        doc,
        llava_observation=llava,
        call_ollama_llava=False,
        call_ollama_gemma=False,
        image_roots=[],
        ollama_base_url="http://127.0.0.1:11434",
        llava_model="llava:13b",
        gemma_model="gemma4:26b",
        ollama_timeout_seconds=1.0,
    )
    subject = card["visual_page_summary"]["likely_diagram_subject"]
    assert subject == "confirmed image/diagram page; subject not explicitly identified"
    assert "```" not in subject
