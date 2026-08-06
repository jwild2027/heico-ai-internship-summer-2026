from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_cleanup import (
    VisualTextCleanupPaths,
    build_clean_summary,
    cleanup_visual_text_record,
    read_jsonl,
    run_visual_text_cleanup,
)


def _record(page_id: str = "t_p_120_1176_p000001", markdown: str | None = None) -> dict:
    if markdown is None:
        markdown = """
# Page visual text

## Page type
parts_list

## Visible title/header
Effective pages list

## Transcribed visible text
- 40-1FL

## Visual summary
This page is a list of effective pages.

## OCR/context assist notes
No OCR/context-only notes reported.

## Tables
No readable table detected.

## Figures/diagrams
No readable figure or diagram detected.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
- 40-1FL

## Warnings/notes
No visible warnings, cautions, notes, revision notes, or procedural notes detected.

## Uncertain/unreadable
No uncertain or unreadable visual regions reported.

## Model caution
Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.
"""
    return {
        "page_id": page_id,
        "status": "ok",
        "provider": "ollama",
        "model": "llava:13b",
        "page_role": "parts_list",
        "image_classification": "likely_table_or_grid",
        "prompt_version": "visual_text_v2_2",
        "ocr_assist_preview": "40-1FL",
        "known_parts": [],
        "visual_text_markdown": markdown,
        "visual_text_scores": {},
        "char_count": len(markdown),
    }


def test_cleanup_detects_and_removes_prompt_template_leakage() -> None:
    record = _record(
        markdown="""
# Page visual text

## Page type
parts_list

## Visible title/header
No readable title or header detected.

## Transcribed visible text
20-IFL

## Visual summary
This page is a list of effective pages.

## OCR/context assist notes
No OCR/context-only notes reported.

## Tables
No readable table detected.

## Figures/diagrams
No readable figure or diagram detected.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
bullet list of exact visible labels, callouts, item numbers, part numbers, quantities, references. If none visible, say so.

## Warnings/notes
visible warnings, cautions, notes, revision notes, or procedural notes. If none visible, say so.

## Uncertain/unreadable
No uncertain or unreadable visual regions reported.

## Model caution
Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.
"""
    )
    cleaned = cleanup_visual_text_record(record)
    scores = cleaned["visual_text_cleanup_scores"]
    assert scores["prompt_template_repaired"] is True
    assert scores["prompt_template_leakage_risk"] is False
    assert scores["trust_tier"] != "D"
    assert "bullet list of exact visible" not in cleaned["visual_text_markdown_clean"].lower()
    assert "if none visible, say so" not in cleaned["visual_text_markdown_clean"].lower()


def test_cleanup_detects_section_bleed_and_moves_inline_sections() -> None:
    record = _record(
        markdown="""
# Page visual text

## Page type
unknown

## Visible title/header
No readable title or header detected.

## Transcribed visible text
- 1002-F Visual summary: This page appears to be a parts list. Tables: No readable table detected. Labels/callouts/part numbers: - 1002-F

## Visual summary
No additional visual summary available.

## OCR/context assist notes
No OCR/context-only notes reported.

## Tables
No readable table detected.

## Figures/diagrams
No readable figure or diagram detected.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
No readable labels, callouts, item numbers, part numbers, or references detected.

## Warnings/notes
No visible warnings, cautions, notes, revision notes, or procedural notes detected.

## Uncertain/unreadable
No uncertain or unreadable visual regions reported.

## Model caution
Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.
"""
    )
    cleaned = cleanup_visual_text_record(record)
    scores = cleaned["visual_text_cleanup_scores"]
    assert scores["section_bleed_repaired"] is True
    assert scores["section_bleed_risk"] is False
    assert "Visual summary: This page" not in cleaned["visual_text_markdown_clean"]
    assert "This page appears to be a parts list" in cleaned["visual_text_markdown_clean"]
    assert "1002-F" in cleaned["visual_text_markdown_clean"]


def test_cleanup_summary_counts_trust_and_table_missing() -> None:
    clean_records = [cleanup_visual_text_record(_record())]
    summary = build_clean_summary(clean_records)
    assert summary["records"] == 1
    assert summary["table_expected_records"] == 1
    assert summary["table_expected_missing_records"] == 1
    assert summary["requires_human_review_records"] == 0
    assert summary["trust_tier_counts"].get("A") == 1


def test_run_visual_text_cleanup_writes_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "visual_text"
    output_dir.mkdir()
    records_path = output_dir / "visual_text_extraction.jsonl"
    records_path.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    paths = VisualTextCleanupPaths(output_dir=output_dir)

    result = run_visual_text_cleanup(paths)

    assert result["summary"]["records"] == 1
    assert paths.clean_records.exists()
    assert paths.clean_summary.exists()
    assert paths.review_flags.exists()
    assert paths.clean_corpus_md.exists()
    assert paths.clean_review_html.exists()
    written = read_jsonl(paths.clean_records)
    assert written[0]["cleanup_version"] == "visual_text_v2_3_1_cleanup"
