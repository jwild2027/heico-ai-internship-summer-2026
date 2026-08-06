from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff.trace_net_table_extraction_bbox_overlay_export_v1 import (
    OverlayThresholds,
    build_table_extraction_bbox_overlay_export_report,
    parse_bbox,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parse_bbox_variants() -> None:
    assert parse_bbox([1, 2, 3, 4]) == {"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0}
    assert parse_bbox({"x": 1, "y": 2, "width": 3, "height": 4}) == {"x0": 1.0, "y0": 2.0, "x1": 4.0, "y1": 6.0}


def test_overlay_export_builds_png(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")

    image_path = tmp_path / "page.png"
    Image.new("RGB", (200, 200), "white").save(image_path)

    table_line_geometry = tmp_path / "line.json"
    write_json(table_line_geometry, {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "image_path": str(image_path),
                "table_extraction_bbox_source": "table_paddle_style_bbox_resolver",
                "table_extraction_bbox": [25, 30, 175, 160],
                "table_region_bbox": {"x0": 10, "y0": 20, "x1": 190, "y1": 180},
            }
        ],
    })

    report = build_table_extraction_bbox_overlay_export_report(
        table_line_geometry_path=table_line_geometry,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        thresholds=OverlayThresholds(),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["overlay_png_count"] == 1
    assert Path(report["overlay_records"][0]["overlay_png_path"]).exists()
