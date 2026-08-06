from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tiff.trace_net_e2e_route_scoped_visual_context_builder_v35 import (
    build_visual_context,
    evaluate_quality,
    load_route_index,
)


def _write_tif(path: Path, color: int = 255) -> None:
    from PIL import Image, ImageDraw
    im = Image.new("L", (420, 220), color)
    d = ImageDraw.Draw(im)
    d.rectangle([160, 40, 360, 180], outline=0, width=3)
    d.ellipse([220, 70, 300, 150], outline=0, width=3)
    d.line([30, 30, 390, 30], fill=0, width=2)
    im.save(path)


def _make_bundle(tmp_path: Path) -> Path:
    p1 = tmp_path / "00000001.tif"
    p2 = tmp_path / "00000002.tif"
    _write_tif(p1)
    _write_tif(p2)
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<mets:mets xmlns:mets="http://www.loc.gov/METS/" xmlns:xlink="http://www.w3.org/1999/xlink" LABEL="Demo Manual" OBJID="demo/obj">
 <mets:fileSec><mets:fileGrp ID="FG0001">
  <mets:file ID="FID0001" MIMETYPE="image/tiff" SIZE="123"><mets:FLocat LOCTYPE="URL" xlink:href="file://./00000001.tif"/></mets:file>
  <mets:file ID="FID0002" MIMETYPE="image/tiff" SIZE="456"><mets:FLocat LOCTYPE="URL" xlink:href="file://./00000002.tif"/></mets:file>
 </mets:fileGrp></mets:fileSec>
</mets:mets>'''
    z = tmp_path / "metadata.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("metadata.xml", xml)
        zf.write(p1, "00000001.tif")
        zf.write(p2, "00000002.tif")
    return z


def test_load_route_index_accepts_flexible_route_manifest(tmp_path: Path) -> None:
    route = tmp_path / "route.json"
    route.write_text(json.dumps({"records": [{"page_id": "t_p_120_1176_p000001", "primary_route": "image_visual"}]}), encoding="utf-8")
    idx = load_route_index(route)
    assert idx["t_p_120_1176_p000001"]["routes"] == ["image_visual"]


def test_build_visual_context_from_bundle_and_route_manifest(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    route = tmp_path / "route.json"
    route.write_text(json.dumps({"records": [
        {"page_id": "t_p_120_1176_p000001", "primary_route": "image_visual"},
        {"page_id": "t_p_120_1176_p000002", "primary_route": "normal_text"},
    ]}), encoding="utf-8")
    report = build_visual_context(
        output_dir=tmp_path / "out",
        page_bundle_zip=bundle,
        route_dispatch_manifest=route,
        max_visual_pages=5,
    )
    assert report["source_page_count"] == 2
    assert report["route_index_page_count"] == 2
    assert report["image_visual_candidate_count"] >= 1
    assert report["visual_context_card_count"] == 1
    assert report["guidance_only_visual_context_count"] == 1
    assert Path(report["visual_context_cards_jsonl_path"]).exists()


def test_quality_checks_pass_for_report(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    route = tmp_path / "route.json"
    route.write_text(json.dumps({"records": [{"page_id": "t_p_120_1176_p000001", "route": "technical_drawing_candidate"}]}), encoding="utf-8")
    report = build_visual_context(output_dir=tmp_path / "out", page_bundle_zip=bundle, route_dispatch_manifest=route)
    checks = evaluate_quality(
        report,
        min_source_pages=2,
        min_route_candidates=2,
        min_image_visual_candidates=1,
        min_visual_context_cards=1,
        min_visual_prompt_contexts=1,
        min_guidance_only_visual_contexts=1,
        min_technical_geometry_cards=1,
        max_visual_proof_authority_violations=0,
        max_post_gate_issue_count=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_no_answer_permission=True,
    )
    assert all(c["passed"] for c in checks), checks
