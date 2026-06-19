from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_page_ink_route_evidence_v1 import (
    InkRouteEvidenceThresholds,
    analyze_image_ink,
    build_page_ink_route_evidence_report,
)


def _png_bytes(img: Image.Image) -> bytes:
    bio = BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


def _write_metadata_zip(path: Path) -> None:
    blank = Image.new("RGB", (220, 220), "white")

    table = Image.new("RGB", (220, 220), "white")
    d = ImageDraw.Draw(table)
    for y in [40, 80, 120, 160]:
        d.line((25, y, 195, y), fill="black", width=2)
    for x in [35, 95, 155, 195]:
        d.line((x, 30, x, 170), fill="black", width=2)

    diagram = Image.new("RGB", (220, 220), "white")
    d = ImageDraw.Draw(diagram)
    d.rectangle((30, 40, 190, 170), outline="black", width=5)
    d.ellipse((80, 75, 140, 135), outline="black", width=4)
    d.line((30, 40, 190, 170), fill="black", width=3)

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.xml", "<metadata></metadata>")
        for i, img in enumerate([blank, table, diagram], start=1):
            zf.writestr(f"{i:08d}.png", _png_bytes(img))


def _write_manifest(path: Path) -> None:
    cards = []
    for i in range(1, 4):
        cards.append({
            "page_id": f"t_p_test_p{i:06d}",
            "source_page_id": f"metadata_page_{i:06d}",
            "page_number": i,
            "primary_route": "blank_candidate" if i == 1 else "table" if i == 2 else "image_visual",
            "secondary_routes": [],
            "route_confidence": 0.9,
            "safe_for_routing": True,
        })
    path.write_text(json.dumps({
        "schema_version": "trace_net_page_route_manifest_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "page_route_cards": cards,
    }), encoding="utf-8")


def test_analyze_image_ink_detects_table_grid() -> None:
    img = Image.new("RGB", (220, 220), "white")
    d = ImageDraw.Draw(img)
    for y in [40, 80, 120, 160]:
        d.line((25, y, 195, y), fill="black", width=2)
    for x in [35, 95, 155, 195]:
        d.line((x, 30, x, 170), fill="black", width=2)

    metrics = analyze_image_ink(img, max_analysis_side=220, component_analysis_side=120)
    assert metrics["ink_primary_route"] == "table"
    assert metrics["horizontal_line_count"] >= 2
    assert metrics["vertical_line_count"] >= 2
    assert metrics["intersection_count"] > 0
    assert metrics["table_grid_likelihood"] >= 0.62


def test_build_page_ink_route_evidence_report_from_metadata_zip(tmp_path: Path) -> None:
    metadata_zip = tmp_path / "metadata.zip"
    manifest = tmp_path / "route_manifest.json"
    out = tmp_path / "out"
    _write_metadata_zip(metadata_zip)
    _write_manifest(manifest)

    report = build_page_ink_route_evidence_report(
        page_route_manifest=manifest,
        metadata_zip=metadata_zip,
        output_dir=out,
        max_analysis_side=220,
        component_analysis_side=120,
        thresholds=InkRouteEvidenceThresholds(
            min_ink_evidence_cards=3,
            min_source_page_ink_evidence_cards=3,
            min_image_analyzed_cards=3,
            max_image_read_error_cards=0,
            require_page_route_manifest_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    cards = report["ink_evidence_cards"]
    assert len(cards) == 3
    assert sum(1 for c in cards if c["image_analyzed"]) == 3
    assert cards[0]["ink_primary_route"] == "blank_candidate"
    assert cards[1]["ink_primary_route"] == "table"
    assert report["summary"]["answer_permission_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
