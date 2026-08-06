from __future__ import annotations

import json
from pathlib import Path

from tiff.page_visual_object_quality import build_page_visual_object_quality, summarize_page_visual_object_audit


def sample_audit() -> dict:
    return {
        "summary": {
            "status": "OK",
            "pages_checked": 3,
            "pages_with_context": 3,
            "pages_without_context": 0,
            "pages_with_source_url": 3,
            "pages_with_ocr_text": 2,
            "pages_without_ocr_text": 1,
            "role_counts": {"figure": 1, "table": 1, "blank": 1},
            "figure_role_pages": 1,
            "table_role_pages": 1,
            "parts_list_role_pages": 0,
            "procedure_role_pages": 0,
            "blank_role_pages": 1,
            "likely_visual_pages": 2,
            "likely_figure_pages": 1,
            "likely_table_pages": 1,
            "pages_with_figure_refs": 1,
            "pages_with_sheet_refs": 1,
            "pages_with_table_refs": 1,
            "pages_with_illustration_refs": 2,
            "pages_with_image_terms": 0,
            "total_figure_refs": 4,
            "total_sheet_refs": 2,
            "total_table_refs": 3,
            "total_illustration_refs": 5,
            "total_part_refs": 7,
            "graph_page_context_nodes": 3,
            "graph_has_context_edges": 3,
            "graph_tagged_as_edges": 5,
            "graph_highlights_part_edges": 4,
            "warnings": ["one blank page"],
        },
        "rows": [],
    }


def test_summarize_page_visual_object_audit_ok() -> None:
    summary, checks = summarize_page_visual_object_audit(sample_audit(), max_pages_without_ocr_text=1)
    assert summary["page_visual_pages_checked"] == 3
    assert summary["page_visual_likely_visual_pages"] == 2
    assert summary["page_visual_graph_has_context_edges"] == 3
    assert all(check.ok for check in checks)


def test_build_page_visual_object_quality_missing_file(tmp_path: Path) -> None:
    report = build_page_visual_object_quality(tmp_path / "missing.json")
    assert report["status"] == "fail"
    assert report["summary"]["page_visual_audit_present"] is False


def test_build_page_visual_object_quality_from_file(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(sample_audit()), encoding="utf-8")
    report = build_page_visual_object_quality(audit_path, max_pages_without_ocr_text=1)
    assert report["status"] == "ok"
    assert report["summary"]["page_visual_table_role_pages"] == 1
