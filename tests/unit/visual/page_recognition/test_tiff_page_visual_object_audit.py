from __future__ import annotations

import json
from pathlib import Path

from tiff.page_visual_object_audit import audit_page_visual_objects, load_page_contexts, load_page_records


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_visual_object_audit_counts_roles_and_refs(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    context_dir = tmp_path / "context"
    graph_dir = tmp_path / "graph"
    ocr_dir = tmp_path / "ocr"
    _write(ocr_dir / "p1.txt", "FIGURE 12 SHEET 1 OF 2\n120-37313-001 HOLDER, MAGAZINE\nILLUSTRATED PARTS LIST")
    _write(ocr_dir / "p2.txt", "TABLE 3 MATERIAL LIST\nFASTENER DATA")
    _write(ocr_dir / "p3.txt", "")
    page_index = {
        "pages": [
            {"page_id": "p1", "ocr_text_path": str(ocr_dir / "p1.txt"), "source_image_path": "p1.tif", "source_url": "http://source/p1", "page_label": "12"},
            {"page_id": "p2", "ocr_text_path": str(ocr_dir / "p2.txt"), "source_image_path": "p2.tif", "source_url": "http://source/p2", "page_label": "13"},
            {"page_id": "p3", "ocr_text_path": str(ocr_dir / "p3.txt"), "source_image_path": "p3.tif", "source_url": "http://source/p3", "page_label": "14"},
        ]
    }
    _write(export_dir / "page_index.json", json.dumps(page_index))
    contexts = {
        "contexts": [
            {"page_id": "p1", "page_role": "figure", "short_summary": "Figure page for a magazine holder.", "topics": ["figure", "parts list"], "important_parts": ["120-37313-001"]},
            {"page_id": "p2", "page_role": "table", "short_summary": "Table page with material data.", "topics": ["table"]},
            {"page_id": "p3", "page_role": "blank", "short_summary": "Blank page.", "topics": []},
        ]
    }
    _write(context_dir / "page_contexts.json", json.dumps(contexts))
    graph_summary = {"node_types": {"page_context": 3}, "edge_types": {"HAS_CONTEXT": 3, "TAGGED_AS": 3, "HIGHLIGHTS_PART": 1}}
    _write(graph_dir / "graph_summary.json", json.dumps(graph_summary))

    records = load_page_records(export_dir)
    assert len(records) == 3
    loaded_contexts = load_page_contexts(context_dir / "page_contexts.json")
    assert sorted(loaded_contexts) == ["p1", "p2", "p3"]

    summary, rows = audit_page_visual_objects(
        export_dir=export_dir,
        context_file=context_dir / "page_contexts.json",
        graph_summary=graph_dir / "graph_summary.json",
        repo_root=tmp_path,
        sample_limit=10,
    )
    assert summary.status == "OK"
    assert summary.pages_checked == 3
    assert summary.figure_role_pages == 1
    assert summary.table_role_pages == 1
    assert summary.blank_role_pages == 1
    assert summary.pages_with_figure_refs >= 1
    assert summary.pages_with_sheet_refs >= 1
    assert summary.pages_with_table_refs >= 1
    assert summary.likely_figure_pages >= 1
    assert summary.likely_table_pages >= 1
    assert summary.graph_page_context_nodes == 3
    p1 = next(row for row in rows if row.page_id == "p1")
    assert p1.highlighted_parts == ["120-37313-001"]
    assert p1.likely_visual_page is True


def test_missing_context_is_reported(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    _write(export_dir / "page_index.json", json.dumps({"pages": [{"page_id": "p1", "source_url": "http://s"}]}))
    summary, _rows = audit_page_visual_objects(export_dir=export_dir, context_file=tmp_path / "missing.json", graph_summary=None, repo_root=tmp_path)
    assert summary.pages_checked == 1
    assert summary.pages_without_context == 1
    assert any("context" in warning.lower() for warning in summary.warnings)
