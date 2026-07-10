from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/build_trace_net_confirmed_image_llava_observations_v1_1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("llava_observations_v1_1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llava_observations_v1_1"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_prompt_tells_llava_not_to_echo_header_tokens() -> None:
    mod = load_module()
    card = {
        "page_id": "t_p_120_1176_p000084",
        "visual_page_summary": {
            "visual_page_type": "technical_diagram_or_figure",
            "likely_diagram_subject": "unknown",
            "figure_refs_clean": ["figure 2 sheet 1"],
            "part_numbers": ["120-41824-003"],
            "visible_callouts_clean": ["25", "21", "00", "377"],
        },
    }

    prompt = mod.llava_prompt(card).lower()

    assert "do not list page headers" in prompt
    assert "25, 21, 00, 06, 12, and 377" in prompt
    assert "unknown" in prompt
    assert "visible_callouts_clean" not in prompt


def test_cleanup_separates_header_tokens_from_callouts() -> None:
    mod = load_module()
    raw = """```json
    {
      "visual_page_type": "technical_diagram_or_figure",
      "diagram_subject_guess": "unknown",
      "visible_callouts_or_labels": ["25", "21", "00", "140", "Item 5", "377", "120-29069-001"],
      "figure_title_or_sheet_text_if_clearly_visible": "Figure 107 sheet 1",
      "retrieval_keywords": ["seat", "diagram"]
    }
    ```"""

    clean = mod.cleanup_llava_observation(raw)

    assert clean["parsed"] is True
    assert "25" in clean["filtered_out_possible_header_or_boilerplate_labels"]
    assert "377" in clean["filtered_out_possible_header_or_boilerplate_labels"]
    assert "Item 5" in clean["visible_callouts_or_labels_cleaned"]
    assert "120-29069-001" in clean["visible_callouts_or_labels_cleaned"]


def test_cleanup_handles_non_json_raw_output() -> None:
    mod = load_module()
    clean = mod.cleanup_llava_observation("This page appears to be a technical drawing.")

    assert clean["parsed"] is False
    assert clean["visible_callouts_or_labels_cleaned"] == []
