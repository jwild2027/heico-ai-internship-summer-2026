from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_cleanup import (
    VisualTextCleanupPaths,
    build_clean_quality_report,
    clean_visual_text_record,
    postprocess_visual_text_outputs,
)


def _record(page_id: str, markdown: str, *, role: str = "parts_list", image: str = "likely_table_or_grid") -> dict:
    return {
        "page_id": page_id,
        "status": "ok",
        "provider": "ollama",
        "model": "llava:13b",
        "prompt_version": "visual_text_v2_2",
        "page_role": role,
        "image_classification": image,
        "ocr_assist_preview": "120-36833-501 20-IFL Effective Pages",
        "known_parts": [{"part_number": "120-36833-501"}],
        "visual_text_markdown": markdown,
        "visual_text_scores": {"prompt_version": "visual_text_v2_2"},
    }


def test_cleanup_splits_section_bleed_and_flags_before_cleanup() -> None:
    markdown = """# Page visual text

## Page type
parts_list

## Transcribed visible text
120-36833-501 Visual summary: This is a parts list page. Tables: No readable table detected. Labels/callouts/part numbers: 120-36833-501

## Model caution
Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.
"""
    cleaned = clean_visual_text_record(_record("p1", markdown))
    flags = cleaned["visual_text_cleanup"]["flags"]
    sections = cleaned["visual_text_sections_clean"]
    assert flags["section_bleed_before_cleanup"] is True
    assert flags["section_bleed_after_cleanup"] is False
    assert "This is a parts list" in sections["Visual summary"]
    assert sections["Labels/callouts/part numbers"].strip() == "120-36833-501"
    assert flags["visible_part_numbers_supported_by_ocr"] == ["120-36833-501"]


def test_cleanup_detects_prompt_template_leakage_and_tier_d() -> None:
    markdown = """# Page visual text

## Page type
parts_list

## Labels/callouts/part numbers
bullet list of exact visible labels, callouts, item numbers, part numbers, quantities, references. If none visible, say so.

## Warnings/notes
visible warnings, cautions, notes, revision notes, or procedural notes. If none visible, say so.
"""
    cleaned = clean_visual_text_record(_record("p2", markdown))
    flags = cleaned["visual_text_cleanup"]["flags"]
    assert flags["prompt_template_leakage"] is True
    assert flags["trust_tier"] == "D"
    assert "bullet list of exact" not in cleaned["visual_text_markdown"].lower()


def test_postprocess_writes_clean_artifacts_and_quality_passes(tmp_path: Path) -> None:
    records_path = tmp_path / "visual_text_extraction.jsonl"
    good_md = """# Page visual text

## Page type
figure

## Visible title/header
Passenger Seat

## Transcribed visible text
120-36833-501

## Visual summary
A passenger seat figure with readable title text.

## OCR/context assist notes
No OCR/context-only notes reported.

## Tables
No readable table detected.

## Figures/diagrams
Seat figure is visible.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
120-36833-501

## Warnings/notes
No visible warnings.

## Uncertain/unreadable
No uncertain regions.

## Model caution
Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.
"""
    records_path.write_text(json.dumps(_record("p3", good_md, role="figure", image="likely_figure_or_diagram")) + "\n", encoding="utf-8")
    paths = VisualTextCleanupPaths(output_dir=tmp_path, records_path=records_path)
    result = postprocess_visual_text_outputs(paths)
    assert paths.clean_records_path.exists()
    assert paths.review_html_path.exists()
    assert result["summary"]["records"] == 1
    report = build_clean_quality_report(paths, min_records=1, max_prompt_template_leakage_records=0, max_metadata_leakage_records=0, max_refusal_like_records=0, max_trust_tier_d_records=0)
    assert report["status"] == "OK"
