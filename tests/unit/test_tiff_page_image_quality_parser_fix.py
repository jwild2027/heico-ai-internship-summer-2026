import json
import subprocess
import sys
from pathlib import Path


def test_page_image_quality_parser_accepts_counts_shape(tmp_path: Path) -> None:
    audit = {
        "status": "OK",
        "counts": {
            "pages_checked": 2,
            "readable_images": 2,
            "missing_image_paths": 0,
            "missing_image_files": 0,
            "unreadable_images": 0,
            "blank_nearly_blank_pages": 0,
        },
        "image_recognition_signals": {
            "likely_visual_pages": 2,
            "likely_figure_diagram_pages": 1,
            "likely_table_grid_pages": 1,
            "avg_ink_ratio": 0.1,
            "median_ink_ratio": 0.1,
            "total_large_components": 3,
        },
        "classification_counts": {"likely_table_or_grid": 1, "likely_figure_or_diagram": 1},
        "page_roles": {"figure": 1, "parts_list": 1},
    }
    audit_path = tmp_path / "audit.json"
    nodes_path = tmp_path / "nodes.json"
    edges_path = tmp_path / "edges.json"
    out_path = tmp_path / "quality.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    nodes_path.write_text(json.dumps([{"id": "n1"}]), encoding="utf-8")
    edges_path.write_text(json.dumps([{"id": "e1"}]), encoding="utf-8")

    rc = subprocess.call([
        sys.executable,
        "scripts/maintenance/ingestion/check_page_image_recognition_quality.py",
        "--audit-json",
        str(audit_path),
        "--graph-nodes",
        str(nodes_path),
        "--graph-edges",
        str(edges_path),
        "--json-output",
        str(out_path),
        "--write-json",
    ])
    assert rc == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["summary"]["page_image_readable_images"] == 2
    assert data["status"] == "OK"
