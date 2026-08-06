from __future__ import annotations

from tiff.visual_text_extraction import (
    build_visual_text_prompt,
    normalize_visual_text_markdown,
    score_visual_text_markdown,
)
from tiff.visual_text_extraction_quality import build_visual_text_extraction_quality, VisualTextQualityPaths
import json
from pathlib import Path


def _card() -> dict:
    return {
        "page_id": "t_p_120_1176_p000001",
        "parents": {"document_label": "T.P. 120/1176", "ata_code": "25-21-00"},
        "source": {"source_url": "http://localhost:8080/rescarta/t_p_120_1176/000001"},
        "context": {"summary": "routing context only"},
        "parts": [{"part_number": "120-12345-001"}],
        "direct_traits": {"page_role": "parts_list", "image_classification": "likely_table_or_grid"},
    }


def test_v2_4_prompt_is_compact_and_avoids_template_phrases() -> None:
    prompt = build_visual_text_prompt(_card(), prompt_version="visual_text_v2_4", ocr_assist_text="OCR text here")
    assert "# Page visual text" in prompt
    assert "## Transcribed visible text" in prompt
    assert "bullet list of exact visible" not in prompt.lower()
    assert "if none visible" not in prompt.lower()
    assert "visible warnings, cautions, notes" not in prompt.lower()
    assert "page_id=t_p_120_1176_p000001" in prompt


def test_v2_4_scores_as_v2_4() -> None:
    md = """# Page visual text
## Page type
text
## Visible title/header
Passenger Seats
## Transcribed visible text
- PASSENGER SEATS
## Visual summary
Title page for passenger seats.
## OCR/context assist notes
NONE
## Tables
NONE
## Figures/diagrams
NONE
## Charts/graphs
NONE
## Labels/callouts/part numbers
NONE
## Warnings/notes
NONE
## Uncertain/unreadable
NONE
## Model caution
Derived visual context only; verify critical facts against source TIFF/OCR evidence.
"""
    normalized = normalize_visual_text_markdown(md, prompt_version="visual_text_v2_4")
    scores = score_visual_text_markdown(normalized, prompt_version="visual_text_v2_4")
    assert scores["prompt_version"] == "visual_text_v2_4"
    assert scores["required_sections_present"] is True


def test_quality_can_require_v2_4(tmp_path: Path) -> None:
    out = tmp_path
    record = {
        "page_id": "p1",
        "status": "ok",
        "char_count": 500,
        "visual_text_scores": {"prompt_version": "visual_text_v2_4", "required_sections_present": True},
    }
    (out / "visual_text_extraction.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (out / "visual_text_corpus.md").write_text("# corpus\ntext", encoding="utf-8")
    (out / "visual_text_graph_nodes.json").write_text(json.dumps([{}, {}]), encoding="utf-8")
    (out / "visual_text_graph_edges.json").write_text(json.dumps([{}]), encoding="utf-8")
    summary = {
        "status": "OK",
        "records": 1,
        "ok_records": 1,
        "planned_records": 0,
        "error_records": 0,
        "pages_with_visual_text": 1,
        "visual_text_char_total": 500,
        "visual_text_avg_chars": 500.0,
        "visual_text_v2_records": 1,
        "visual_text_v2_4_records": 1,
        "visual_text_required_sections_records": 1,
    }
    (out / "visual_text_extraction_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    report = build_visual_text_extraction_quality(
        VisualTextQualityPaths(output_dir=out),
        require_v2=True,
        require_v2_4=True,
        min_records=1,
        min_required_section_records=1,
        allow_planned=False,
    )
    assert report["status"] == "OK"
