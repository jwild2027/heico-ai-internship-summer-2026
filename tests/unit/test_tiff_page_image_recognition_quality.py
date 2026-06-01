from __future__ import annotations

import json
from pathlib import Path

from tiff.page_image_recognition_quality import build_page_image_recognition_quality_report, summarize_page_image_recognition_audit


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_summarizes_audit_and_graph_overlay(tmp_path: Path) -> None:
    nodes = tmp_path / "nodes.json"
    edges = tmp_path / "edges.json"
    _write_json(nodes, [{"id": "a"}])
    _write_json(edges, [{"source": "p", "target": "a"}])
    audit = {
        "status": "OK",
        "counts": {
            "pages_checked": 3,
            "readable_images": 3,
            "missing_image_paths": 0,
            "missing_image_files": 0,
            "unreadable_images": 0,
            "blank_nearly_blank_pages": 1,
        },
        "image_recognition_signals": {
            "likely_visual_pages": 2,
            "likely_figure_or_diagram_pages": 1,
            "likely_table_or_grid_pages": 1,
            "avg_ink_ratio": 0.05,
            "total_large_components": 10,
        },
        "classification_counts": {
            "likely_table_or_grid": 1,
            "likely_figure_or_diagram": 1,
            "likely_blank": 1,
        },
        "page_roles": {"parts_list": 1, "figure": 1, "blank": 1},
        "graph_overlay": {"nodes": str(nodes), "edges": str(edges)},
    }
    summary = summarize_page_image_recognition_audit(audit)
    assert summary["page_image_pages_checked"] == 3
    assert summary["page_image_readable_images"] == 3
    assert summary["page_image_classified_pages"] == 3
    assert summary["page_image_role_pages"] == 3
    assert summary["page_image_graph_overlay_nodes"] == 1
    assert summary["page_image_graph_overlay_edges"] == 1


def test_quality_report_passes_for_good_audit(tmp_path: Path) -> None:
    nodes = tmp_path / "nodes.json"
    edges = tmp_path / "edges.json"
    _write_json(nodes, [{"id": "a"}])
    _write_json(edges, [{"source": "p", "target": "a"}])
    audit_path = tmp_path / "audit.json"
    _write_json(
        audit_path,
        {
            "status": "OK",
            "counts": {"pages_checked": 2, "readable_images": 2, "blank_nearly_blank_pages": 0},
            "image_recognition_signals": {"likely_visual_pages": 2, "likely_figure_or_diagram_pages": 1, "likely_table_or_grid_pages": 1, "avg_ink_ratio": 0.1, "total_large_components": 3},
            "classification_counts": {"likely_table_or_grid": 1, "likely_figure_or_diagram": 1},
            "page_roles": {"parts_list": 1, "figure": 1},
            "graph_overlay": {"nodes": str(nodes), "edges": str(edges)},
        },
    )
    report = build_page_image_recognition_quality_report(audit_path=audit_path)
    assert report.status == "OK"
    assert all(check.status == "OK" for check in report.checks)


def test_quality_report_fails_for_missing_audit(tmp_path: Path) -> None:
    report = build_page_image_recognition_quality_report(audit_path=tmp_path / "missing.json")
    assert report.status == "FAIL"
    assert any(check.name == "page_image_audit_present" for check in report.checks)
