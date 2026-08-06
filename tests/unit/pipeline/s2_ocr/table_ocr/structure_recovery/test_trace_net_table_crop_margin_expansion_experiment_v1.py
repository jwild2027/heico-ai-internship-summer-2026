from pathlib import Path

from tiff.trace_net_table_crop_margin_expansion_experiment_v1 import (
    bbox_from_record,
    build_report,
    classify_signal,
    clamp_bbox,
    morphology_score,
    Thresholds,
)


def test_bbox_and_clamp():
    bbox = bbox_from_record({"table_region_bbox": {"x0": 10, "y0": 20, "x1": 50, "y1": 80}})
    assert bbox is not None
    assert bbox["width"] == 40
    expanded = clamp_bbox(bbox, 100, 100, 25)
    assert expanded["x0"] == 0
    assert expanded["y0"] == 0
    assert expanded["x1"] == 75
    assert expanded["y1"] == 100


def test_signal_and_score():
    assert classify_signal(4, 3, 8) == "GRID"
    assert classify_signal(1, 1, 0) == "PARTIAL_GRID"
    assert classify_signal(1, 0, 0) == "WEAK_LINE_SIGNAL"
    assert morphology_score(4, 3, 8, "GRID") > morphology_score(1, 0, 0, "WEAK_LINE_SIGNAL")


def test_build_report_without_image_still_safe(tmp_path: Path):
    line_path = tmp_path / "line.json"
    bbox_path = tmp_path / "bbox.json"
    line_path.write_text(
        '{"quality_status":"PASS","table_geometry_cards":[{"page_id":"p1","table_id":"t1","table_type":"parts_list_table","horizontal_line_count":1,"vertical_line_count":0,"intersection_count":0,"resolved_image_path":"missing.tif"}]}',
        encoding="utf-8",
    )
    bbox_path.write_text(
        '{"quality_status":"PASS","table_bbox_cards":[{"page_id":"p1","table_id":"t1","bbox_source":"explicit_table_bbox","table_region_bbox":{"x0":0,"y0":0,"x1":100,"y1":100}}]}',
        encoding="utf-8",
    )
    report = build_report(
        table_line_geometry_path=line_path,
        table_bbox_resolver_path=bbox_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        margin_pixels=[0, 10],
        thresholds=Thresholds(min_diagnostic_cards=1, min_margin_candidate_cards=0, min_successful_image_cards=0, require_table_line_geometry_quality_pass=True, require_table_bbox_resolver_quality_pass=True, require_no_answer_permission=True),
    )
    assert report["quality_status"] == "PASS"
    card = report["diagnostic_cards"][0]
    assert card["can_answer_directly"] is False
    assert "resolved_image_missing_for_margin_experiment" in card["review_flags"]
