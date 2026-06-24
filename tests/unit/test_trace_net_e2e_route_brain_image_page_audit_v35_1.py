from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from tiff.trace_net_e2e_route_brain_image_page_audit_v35_1 import (
    build_route_brain_audit,
    evaluate_quality,
    load_route_index,
)


def _make_zip(path: Path, pages: int = 5) -> None:
    files = []
    for i in range(1, pages + 1):
        files.append(f'''<file ID="file{i}" MIMETYPE="image/tiff" SIZE="10000"><FLocat xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="file://./{i:08d}.tif"/></file>''')
    xml = "<mets LABEL=\"sample\" OBJID=\"obj\"><fileSec>" + "".join(files) + "</fileSec></mets>"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.xml", xml)
        for i in range(1, pages + 1):
            zf.writestr(f"{i:08d}.tif", b"fake-tiff")


def _write_routes(path: Path) -> None:
    data = {
        "records": [
            {"page_id": "t_p_120_1176_p000001", "primary_route": "image_visual"},
            {"page_id": "t_p_120_1176_p000002", "primary_route": "normal_text"},
            {"page_id": "t_p_120_1176_p000003", "primary_route": "table"},
            {"page_id": "t_p_120_1176_p000004", "primary_route": "blank_candidate"},
            {"page_id": "t_p_120_1176_p000005", "primary_route": "normal_text", "route_policies": {"image_visual": {"route": "image_visual", "status": "secondary_review_candidate_allowed"}}},
        ]
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_manual(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["page_number", "page_id", "filename", "manual_screen_category", "notes"])
        w.writeheader()
        w.writerow({"page_number": 2, "page_id": "t_p_120_1176_p000002", "filename": "00000002.tif", "manual_screen_category": "diagram_image_page", "notes": "manual"})
        w.writerow({"page_number": 5, "page_id": "t_p_120_1176_p000005", "filename": "00000005.tif", "manual_screen_category": "diagram_image_page", "notes": "manual"})


def test_route_index_does_not_stringify_nested_route_policy(tmp_path: Path):
    routes = tmp_path / "routes.json"
    _write_routes(routes)
    index, malformed = load_route_index(routes)
    assert malformed == 0
    assert "image_visual" in index["t_p_120_1176_p000005"]["routes"]
    assert all(not r.startswith("{") for v in index.values() for r in v["routes"])


def test_build_route_brain_audit_counts_and_repairs(tmp_path: Path):
    z = tmp_path / "metadata.zip"
    routes = tmp_path / "routes.json"
    manual = tmp_path / "manual.csv"
    out = tmp_path / "out"
    _make_zip(z)
    _write_routes(routes)
    _write_manual(manual)
    report = build_route_brain_audit(
        output_dir=out,
        page_bundle_zip=z,
        route_dispatch_manifest=routes,
        manual_screened_diagram_pages_csv=manual,
        page_id_prefix="t_p_120_1176",
    )
    assert report["source_page_count"] == 5
    assert report["actual_diagram_page_count"] == 2
    assert report["corrected_image_visual_count"] == 2
    assert report["overbroad_image_visual_candidate_count"] == 1
    assert report["missed_diagram_page_count"] == 1
    assert Path(report["actual_diagram_pages_jsonl_path"]).exists()


def test_quality_passes(tmp_path: Path):
    z = tmp_path / "metadata.zip"
    routes = tmp_path / "routes.json"
    manual = tmp_path / "manual.csv"
    out = tmp_path / "out"
    _make_zip(z)
    _write_routes(routes)
    _write_manual(manual)
    report = build_route_brain_audit(
        output_dir=out,
        page_bundle_zip=z,
        route_dispatch_manifest=routes,
        manual_screened_diagram_pages_csv=manual,
        page_id_prefix="t_p_120_1176",
    )
    status, checks = evaluate_quality(
        report,
        min_source_pages=5,
        min_route_candidates=5,
        min_manual_screened_diagram_pages=2,
        expected_actual_diagram_pages=2,
        max_image_visual_candidates_after_correction=2,
        min_overbroad_image_visual_candidates=1,
        max_malformed_route_values=0,
        require_no_answer_permission=True,
    )
    assert status == "PASS", checks
