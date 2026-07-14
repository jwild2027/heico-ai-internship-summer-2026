from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/build_trace_net_confirmed_image_llava_observations_v1_2.py")


def load_module():
    spec = importlib.util.spec_from_file_location("llava_observations_v1_2", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llava_observations_v1_2"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_prompt_blocks_prompt_leak_and_generic_callouts() -> None:
    mod = load_module()
    card = {
        "page_id": "t_p_120_1176_p000499",
        "visual_page_summary": {
            "visual_page_type": "technical_diagram_or_figure",
            "likely_diagram_subject": "unknown",
            "figure_refs_clean": ["figure 609"],
            "part_numbers": ["120-00000-001"],
        },
    }

    prompt = mod.llava_prompt(card).lower()

    assert "do not copy these instructions" in prompt
    assert "visible_callouts_or_labels must be a json array of short strings" in prompt
    assert "do not put generic sentences" in prompt
    assert "write exactly \"unknown\"" in prompt


def test_cleanup_filters_prompt_leak_and_generic_sentence() -> None:
    mod = load_module()
    raw = """{
      "visual_page_type": "technical_diagram_or_figure",
      "diagram_subject_guess": "aircraft structure",
      "visible_callouts_or_labels": [
        "25",
        "Callouts on the diagram include part numbers, measurements, and possibly some indications about orientation or assembly.",
        "Item 5",
        "120-29069-001"
      ],
      "page_header_or_boilerplate_text": "TRACE-Net's visual observation specialist for scanned aircraft technical-manual pages.",
      "figure_title_or_sheet_text_if_clearly_visible": "Figure title or sheet text is not visible or clear in this image.",
      "retrieval_keywords": ["technical drawing"]
    }"""

    clean = mod.cleanup_llava_observation(raw)

    assert clean["parsed"] is True
    assert clean["diagram_subject_guess"] == "unknown"
    assert clean["figure_title_or_sheet_text_if_clearly_visible"] == ""
    assert "Item 5" in clean["visible_callouts_or_labels_cleaned"]
    assert "120-29069-001" in clean["visible_callouts_or_labels_cleaned"]
    assert "25" in clean["filtered_out_possible_header_or_boilerplate_labels"]
    assert clean["filtered_out_prompt_leak_values"]
    assert clean["filtered_out_generic_callout_sentences"]


def test_cleanup_keeps_real_small_item_numbers_but_not_header_tokens() -> None:
    mod = load_module()
    raw = """{
      "diagram_subject_guess": "unknown",
      "visible_callouts_or_labels": ["1", "2", "3", "25", "21", "00", "377"],
      "figure_title_or_sheet_text_if_clearly_visible": "Figure 26 Sheet 1"
    }"""

    clean = mod.cleanup_llava_observation(raw)

    assert "1" in clean["visible_callouts_or_labels_cleaned"]
    assert "2" in clean["visible_callouts_or_labels_cleaned"]
    assert "25" in clean["filtered_out_possible_header_or_boilerplate_labels"]
    assert "377" in clean["filtered_out_possible_header_or_boilerplate_labels"]
    assert clean["figure_title_or_sheet_text_if_clearly_visible"] == "Figure 26 Sheet 1"
