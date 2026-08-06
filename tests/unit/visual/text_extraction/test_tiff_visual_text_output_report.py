from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_output_report import (
    VisualTextOutputPaths,
    build_html_review,
    build_markdown_review,
    build_visual_text_output_report,
    filter_records,
    format_terminal_report,
    parse_markdown_sections,
)


def _record(page_id: str, status: str = "ok") -> dict[str, object]:
    markdown = """# Page visual text
## Page type
parts_list

## Visual summary
The page contains a visible parts table and several callouts.

## Tables
| item | part |
|---|---|
| 1 | ABC-123 |

## Figures/diagrams
A diagram shows a bracket connected to a panel.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
- ABC-123
- CALLOUT 1

## Warnings/notes
No visible warning.

## Uncertain/unreadable
Some small text is unclear.
"""
    return {
        "page_id": page_id,
        "status": status,
        "provider": "ollama",
        "model": "llava:13b",
        "page_role": "parts_list",
        "image_classification": "likely_table_or_grid",
        "parents": {"ata_code": "25-21-00", "document_label": "T.P. 120/1176"},
        "source": {"source_url": "local://page", "tiff_path": "page.tif", "ocr_path": "page.txt"},
        "elapsed_seconds": 1.25,
        "visual_text_markdown": markdown,
        "visual_text_plain": "The page contains ABC-123.",
        "char_count": len(markdown),
    }


def test_parse_markdown_sections_extracts_expected_sections() -> None:
    sections = parse_markdown_sections(str(_record("p1")["visual_text_markdown"]))

    assert sections["Page type"] == "parts_list"
    assert "visible parts table" in sections["Visual summary"]
    assert "ABC-123" in sections["Labels/callouts/part numbers"]


def test_report_loads_jsonl_summary_and_formats_terminal(tmp_path: Path) -> None:
    records_path = tmp_path / "visual_text_extraction.jsonl"
    summary_path = tmp_path / "visual_text_extraction_summary.json"
    records = [_record("p000001"), _record("p000002")]
    records_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                "status": "OK",
                "provider": "ollama",
                "model": "llava:13b",
                "records": 2,
                "ok_records": 2,
                "error_records": 0,
                "pages_with_visual_text": 2,
                "visual_text_char_total": 1000,
            }
        ),
        encoding="utf-8",
    )

    report = build_visual_text_output_report(VisualTextOutputPaths(records_path=records_path, summary_path=summary_path))
    text = format_terminal_report(report, max_records=2)

    assert report.summary["status"] == "OK"
    assert len(report.records) == 2
    assert report.section_counts["Visual summary"] == 2
    assert "Visual text extraction outputs" in text
    assert "p000001" in text
    assert "ABC-123" in text


def test_filter_markdown_and_html_review(tmp_path: Path) -> None:
    report = build_visual_text_output_report(
        VisualTextOutputPaths(records_path=tmp_path / "missing.jsonl", summary_path=tmp_path / "missing_summary.json")
    )
    records = [_record("p000001"), _record("p000002", status="error")]
    filtered = filter_records(records, statuses=["ok"], search="ABC-123")
    md = build_markdown_review(report, filtered)
    html = build_html_review(report, records)

    assert [record["page_id"] for record in filtered] == ["p000001"]
    assert "# Visual Text Extraction Review" in md
    assert "p000001" in md
    assert "HEICO Visual Text Output Review" in html
    assert "data-search" in html
    assert "p000002" in html
