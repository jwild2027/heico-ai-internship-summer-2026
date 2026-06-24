from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_e2e_cascade_route_feature_audit_v35_2 import build_feature_audit, quality_checks


def _make_zip(path: Path) -> None:
    tmp = path.parent / "imgs"
    tmp.mkdir()
    for i in range(1, 5):
        im = Image.new("L", (200, 260), 255)
        d = ImageDraw.Draw(im)
        if i == 1:
            # text-ish page
            for y in range(40, 200, 18):
                d.line((20, y, 170, y), fill=0, width=2)
        elif i == 2:
            # table-ish page
            for y in range(30, 230, 25):
                d.line((20, y, 180, y), fill=0, width=2)
            for x in range(20, 190, 40):
                d.line((x, 30, x, 230), fill=0, width=2)
        elif i == 3:
            # diagram-ish page
            d.ellipse((55, 55, 150, 150), outline=0, width=3)
            d.line((40, 190, 180, 70), fill=0, width=3)
            d.line((20, 230, 190, 230), fill=0, width=2)
        else:
            pass
        img_path = tmp / f"{i:08d}.tif"
        im.save(img_path)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.xml", "<metadata />")
        for img in sorted(tmp.glob("*.tif")):
            zf.write(img, img.name)


def _manual_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["page_number", "page_id", "filename", "manual_screen_category"])
        w.writeheader()
        w.writerow({"page_number": 3, "page_id": "t_p_120_1176_p000003", "filename": "00000003.tif", "manual_screen_category": "diagram_image_page"})


def test_build_feature_audit(tmp_path: Path):
    bundle = tmp_path / "metadata.zip"
    labels = tmp_path / "manual.csv"
    out = tmp_path / "out"
    _make_zip(bundle)
    _manual_csv(labels)
    report = build_feature_audit(
        page_bundle_zip=bundle,
        route_dispatch_manifest=None,
        manual_screened_diagram_pages=labels,
        output_dir=out,
        page_id_prefix="t_p_120_1176",
    )
    assert report["source_page_count"] == 4
    assert report["feature_record_count"] == 4
    assert report["actual_diagram_page_count"] == 1
    assert report["feature_column_count"] >= 10
    assert Path(report["feature_records_jsonl_path"]).exists()
    rows = [json.loads(x) for x in Path(report["feature_records_jsonl_path"]).read_text().splitlines()]
    assert rows[2]["manual_diagram_page"] is True
    assert "route_scores" in rows[0]


def test_quality_checks_pass(tmp_path: Path):
    bundle = tmp_path / "metadata.zip"
    labels = tmp_path / "manual.csv"
    out = tmp_path / "out"
    _make_zip(bundle)
    _manual_csv(labels)
    report = build_feature_audit(
        page_bundle_zip=bundle,
        route_dispatch_manifest=None,
        manual_screened_diagram_pages=labels,
        output_dir=out,
        page_id_prefix="t_p_120_1176",
    )
    class Args:
        min_source_pages = 4
        min_feature_records = 4
        min_manual_screened_diagram_pages = 1
        expected_actual_diagram_pages = 1
        min_feature_columns = 10
        min_confusion_matrix_total = 4
        min_label_coverage = 4
        max_answer_permission_count = 0
        max_source_truth_mutation_allowed = 0
        require_no_answer_permission = True
    checks = quality_checks(report, Args())
    assert all(c["passed"] for c in checks)
