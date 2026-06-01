from __future__ import annotations

import json
from pathlib import Path

from tiff.page_image_recognition_quality import build_page_image_recognition_quality


def test_current_audit_shape_parses_readable_and_figure_counts(tmp_path: Path) -> None:
    audit = {
        "status": "OK",
        "counts": {
            "pages_checked": 509,
            "readable_images": 509,
            "missing_image_paths": 0,
            "missing_image_files": 0,
            "unreadable_images": 0,
            "blank_nearly_blank_pages": 14,
        },
        "image_recognition_signals": {
            "likely_visual_pages": 493,
            "likely_figure_diagram_pages": 493,
            "likely_table_grid_pages": 331,
            "avg_ink_ratio": 0.068,
            "total_large_components": 17735,
        },
        "classification_counts": {
            "likely_table_or_grid": 331,
            "likely_figure_or_diagram": 162,
            "likely_blank": 14,
            "likely_text_or_parts_list": 2,
        },
        "page_roles": {
            "parts_list": 290,
            "figure": 157,
            "procedure": 28,
            "blank": 14,
            "front_matter": 10,
            "table": 10,
        },
    }
    audit_path = tmp_path / "audit.json"
    nodes_path = tmp_path / "nodes.json"
    edges_path = tmp_path / "edges.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    nodes_path.write_text(json.dumps([{} for _ in range(513)]), encoding="utf-8")
    edges_path.write_text(json.dumps([{} for _ in range(1018)]), encoding="utf-8")

    report = build_page_image_recognition_quality(audit_path, graph_nodes_path=nodes_path, graph_edges_path=edges_path)
    summary = report["summary"]

    assert report["status"] == "OK"
    assert summary["page_image_readable_images"] == 509
    assert summary["page_image_likely_figure_pages"] == 493
    assert summary["page_image_likely_table_pages"] == 331
