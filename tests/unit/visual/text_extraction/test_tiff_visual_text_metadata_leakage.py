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


def test_v21_prompt_explicitly_separates_metadata_from_visible_text(tmp_path: Path) -> None:
    prompt = build_visual_text_prompt(
        _card(tmp_path),
        prompt_version="visual_text_v2_1",
        ocr_assist_text="OCR assist says 120-12345-001 BRACKET",
    )

    lowered = prompt.lower()
    assert "strict visual text extraction v2.1" in lowered
    assert "metadata/context below is not visible page text" in lowered
    assert "ocr/context assist notes" in lowered
    assert "never copy page_id" in lowered
    assert "do not include metadata" in lowered


def test_v21_normalizer_adds_ocr_context_section() -> None:
    markdown = """# Page visual text
## Page type
parts_list

## Transcribed visible text
- Direct visible text only.
"""
    normalized = normalize_visual_text_markdown(markdown, prompt_version="visual_text_v2_1")
    sections = parse_visual_text_sections(normalized)

    assert "OCR/context assist notes" in sections
    assert sections["OCR/context assist notes"] == "No OCR/context-only notes reported."
    assert "Visual summary" in sections
    assert score_visual_text_markdown(normalized)["required_sections_present"] is True


def test_metadata_leakage_score_flags_context_in_visible_sections_but_not_notes() -> None:
    leaked = """# Page visual text
## Page type
parts_list

## Visible title/header
No readable title or header detected.

## Transcribed visible text
- current page role: parts_list
- source URL/path hint: http://localhost:8080/rescarta/t_p_120_1176/000027

## Visual summary
A parts list page.

## OCR/context assist notes
No OCR/context-only notes reported.

## Tables
No readable table detected.

## Figures/diagrams
No readable figure or diagram detected.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
- image classification: likely_table_or_grid

## Warnings/notes
No visible warnings.

## Uncertain/unreadable
No uncertain regions.

## Model caution
Verify source.
"""
    scores = score_visual_text_markdown(leaked)
    assert scores["metadata_leakage_risk"] is True
    assert "source_url" in scores["metadata_leakage_markers"]
    assert "page_role_hint" in scores["metadata_leakage_markers"]
    assert "image_classification_hint" in scores["metadata_leakage_markers"]

    clean = leaked.replace(
        "- current page role: parts_list\n- source URL/path hint: http://localhost:8080/rescarta/t_p_120_1176/000027",
        "- Passenger seat parts list",
    ).replace(
        "- image classification: likely_table_or_grid",
        "- 120-12345-001",
    ).replace(
        "No OCR/context-only notes reported.",
        "Context-only note: current page role was parts_list; source URL/path hint was present.",
    )
    clean_scores = score_visual_text_markdown(clean)
    assert clean_scores["metadata_leakage_risk"] is False
    assert clean_scores["metadata_leakage_marker_count"] == 0
    assert clean_scores["has_ocr_context_notes"] is True


def test_quality_gate_can_limit_metadata_leakage_records(tmp_path: Path) -> None:
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
        "prompt_version": "visual_text_v2_1",
        "visual_text_v2_records": 1,
        "visual_text_required_sections_records": 1,
        "visual_text_metadata_leakage_records": 1,
        "visual_text_metadata_leakage_marker_total": 3,
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
        min_required_section_records=1,
        max_metadata_leakage_records=0,
    )

    assert report["status"] == "FAIL"
    assert any(check["name"] == "visual_text_metadata_leakage" and not check["ok"] for check in report["checks"])
