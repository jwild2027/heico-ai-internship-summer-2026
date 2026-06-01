from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_extraction import (
    build_visual_text_prompt,
    normalize_visual_text_markdown,
    parse_visual_text_sections,
    score_visual_text_markdown,
)
from tiff.visual_text_extraction_quality import VisualTextQualityPaths, build_visual_text_extraction_quality


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _card(tmp_path: Path) -> dict[str, object]:
    return {
        "page_id": "t_p_120_1176_p000027",
        "parents": {"document_label": "T.P. 120/1176", "ata_code": "25-21-00"},
        "context": {"page_role": "parts_list", "summary": "Existing context should not be copied."},
        "signals": {"image_classification": "likely_table_or_grid"},
        "source": {
            "source_url": "http://localhost:8080/rescarta/t_p_120_1176/000027",
            "tiff_path": str(tmp_path / "page.tif"),
            "ocr_path": str(tmp_path / "page.txt"),
        },
        "parts": [{"part_number": "120-12345-001"}],
    }


def test_v22_prompt_blocks_metadata_leakage_without_refusal_language(tmp_path: Path) -> None:
    prompt = build_visual_text_prompt(
        _card(tmp_path),
        prompt_version="visual_text_v2_2",
        ocr_assist_text="OCR says 120-12345-001 BRACKET",
    )

    lowered = prompt.lower()
    assert "you can read and describe the supplied page image" in lowered
    assert "do not apologize" in lowered
    assert "never copy these routing fields" in lowered
    assert "ocr/context assist notes" in lowered
    assert "return exactly this markdown structure" in lowered


def test_v22_parser_handles_setext_style_sections() -> None:
    raw = """Page visual text
================
Page type
----------
parts_list
Visible title/header
--------------------
NUMERICAL INDEX
Transcribed visible text
------------------------
- 120-12345-001 BRACKET
Visual summary
--------------
A parts-list index page.
OCR/context assist notes
------------------------
No OCR/context-only notes reported.
Tables
------
No readable table detected.
Figures/diagrams
----------------
No readable figure or diagram detected.
Charts/graphs
-------------
No readable chart or graph detected.
Labels/callouts/part numbers
----------------------------
- 120-12345-001
Warnings/notes
--------------
No visible warnings.
Uncertain/unreadable
--------------------
No uncertain regions.
Model caution
-------------
Verify source.
"""
    normalized = normalize_visual_text_markdown(raw, prompt_version="visual_text_v2_2")
    sections = parse_visual_text_sections(normalized)
    scores = score_visual_text_markdown(normalized, prompt_version="visual_text_v2_2")

    assert sections["Page type"] == "parts_list"
    assert "120-12345-001" in sections["Transcribed visible text"]
    assert sections["Visual summary"] == "A parts-list index page."
    assert scores["prompt_version"] == "visual_text_v2_2"
    assert scores["required_sections_present"] is True
    assert scores["has_part_numbers"] is True
    assert scores["too_summary_heavy"] is False


def test_v22_scores_refusal_like_output() -> None:
    raw = """# Page visual text
## Page type
unknown
## Visible title/header
No readable title or header detected.
## Transcribed visible text
No additional readable text transcribed from the image.
## Visual summary
I'm unable to transcribe text from images. If you have a specific question, feel free to ask.
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
No visible warnings.
## Uncertain/unreadable
No uncertain regions.
## Model caution
Verify source.
"""
    scores = score_visual_text_markdown(raw, prompt_version="visual_text_v2_2")

    assert scores["refusal_like"] is True
    assert scores["hallucination_risk"] is True


def test_quality_gate_can_require_v22_and_limit_refusals(tmp_path: Path) -> None:
    paths = VisualTextQualityPaths(output_dir=tmp_path)
    summary = {
        "status": "OK",
        "provider": "ollama",
        "model": "llava:13b",
        "total_page_cards": 1,
        "selected_pages": 1,
        "records": 1,
        "ok_records": 1,
        "planned_records": 0,
        "error_records": 0,
        "pages_with_visual_text": 1,
        "visual_text_char_total": 1000,
        "visual_text_avg_chars": 1000.0,
        "prompt_version": "visual_text_v2_2",
        "visual_text_v2_records": 1,
        "visual_text_v2_2_records": 1,
        "visual_text_required_sections_records": 1,
        "visual_text_refusal_like_records": 1,
    }
    _write_json(paths.summary_path, summary)
    _write_jsonl(paths.records_path, [{"page_id": "p1", "status": "ok", "char_count": 1000}])
    paths.corpus_md_path.write_text("# Page visual text\ncontent", encoding="utf-8")
    _write_json(paths.graph_nodes_path, {"nodes": [{"id": "e"}, {"id": "v"}]})
    _write_json(paths.graph_edges_path, {"edges": [{"source": "p1", "target": "v"}]})

    report = build_visual_text_extraction_quality(
        paths,
        allow_planned=False,
        require_v2=True,
        require_v2_2=True,
        min_required_section_records=1,
        max_refusal_like_records=0,
    )

    assert report["status"] == "FAIL"
    assert any(check["name"] == "visual_text_refusal_like" and not check["ok"] for check in report["checks"])
