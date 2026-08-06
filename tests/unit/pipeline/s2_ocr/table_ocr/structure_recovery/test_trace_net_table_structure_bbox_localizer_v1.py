import json
from pathlib import Path

from tiff.trace_net_table_structure_bbox_localizer_v1 import (
    build_report,
    make_structure_record,
    normalize_bbox,
    validate_visual_candidate,
)


def visual_record(*, visual_box=None, quality=True, applied=True, multi=False):
    return {
        "visual_bbox_localizer_id": "vis1",
        "page_id": "p1",
        "table_id": "normtable1",
        "input_bbox": {"x0": 100, "y0": 100, "x1": 2100, "y1": 3100, "width": 2000, "height": 3000, "coordinate_system": "pixels"},
        "localized_table_bbox": visual_box or {"x0": 140, "y0": 120, "x1": 2050, "y1": 2920, "width": 1910, "height": 2800, "coordinate_system": "pixels"},
        "localized_bbox_source": "visual_dark_pixel_line_refined" if applied else "input_bbox_fallback",
        "table_localization_quality_pass": quality,
        "visual_refinement_applied": applied,
        "multi_column_vertical_merge_applied": multi,
        "multi_column_vertical_cluster_count": 2 if multi else 1,
        "horizontal_line_run_count": 12,
        "vertical_line_run_count": 10,
        "row_band_run_count": 22,
        "column_band_run_count": 18,
    }


def scoped_record():
    return {
        "scoped_table_record_id": "scope1",
        "page_id": "p1",
        "table_id": "table1",
        "scoped_row_count": 60,
        "scoped_cell_count": 240,
        "scoped_value_record_count": 240,
        "bbox_scoped_extraction_ready": True,
    }


def test_structure_gate_accepts_complete_visual_candidate():
    visual = visual_record(multi=True)
    input_box = normalize_bbox(visual["input_bbox"])
    loc_box = normalize_bbox(visual["localized_table_bbox"])
    ok, flags, diag = validate_visual_candidate(visual, scoped_record(), input_box, loc_box)
    assert ok is True
    assert diag["structure_visual_candidate_accepted"] is True
    assert "visual_candidate_cuts_table_columns" not in flags


def test_structure_gate_rejects_narrow_partial_column_candidate():
    visual = visual_record(
        visual_box={"x0": 600, "y0": 120, "x1": 1050, "y1": 2950, "width": 450, "height": 2830, "coordinate_system": "pixels"},
        multi=True,
    )
    input_box = normalize_bbox(visual["input_bbox"])
    loc_box = normalize_bbox(visual["localized_table_bbox"])
    ok, flags, diag = validate_visual_candidate(visual, scoped_record(), input_box, loc_box)
    assert ok is False
    assert "visual_candidate_cuts_table_columns" in flags
    assert diag["structure_visual_candidate_rejected"] is True


def test_structure_gate_rejects_too_short_for_many_rows():
    visual = visual_record(
        visual_box={"x0": 140, "y0": 120, "x1": 2050, "y1": 500, "width": 1910, "height": 380, "coordinate_system": "pixels"},
        multi=True,
    )
    ok, flags, _ = validate_visual_candidate(visual, scoped_record(), normalize_bbox(visual["input_bbox"]), normalize_bbox(visual["localized_table_bbox"]))
    assert ok is False
    assert "visual_candidate_too_short_for_row_count" in flags


def test_make_record_falls_back_to_input_when_visual_is_partial():
    visual = visual_record(
        visual_box={"x0": 600, "y0": 120, "x1": 1050, "y1": 2950, "width": 450, "height": 2830, "coordinate_system": "pixels"},
        multi=True,
    )
    record = make_structure_record(visual, scoped_record(), "page_id_single_scoped_record")
    assert record["structure_selected_bbox_source"] == "conservative_input_bbox_fallback"
    assert record["structure_visual_candidate_rejected"] is True
    assert record["structure_selected_table_bbox"]["width"] == 2000


def test_build_report_writes_outputs(tmp_path: Path):
    visual_payload = {
        "quality_status": "PASS",
        "table_visual_bbox_localizer_records": [visual_record(), visual_record(visual_box={"x0": 600, "y0": 120, "x1": 1050, "y1": 2950, "width": 450, "height": 2830, "coordinate_system": "pixels"}, multi=True) | {"page_id": "p2"}],
    }
    scoped_payload = {
        "quality_status": "PASS",
        "scoped_table_records": [scoped_record(), scoped_record() | {"page_id": "p2", "table_id": "table2"}],
    }
    visual_path = tmp_path / "visual.json"
    scoped_path = tmp_path / "scoped.json"
    visual_path.write_text(json.dumps(visual_payload), encoding="utf-8")
    scoped_path.write_text(json.dumps(scoped_payload), encoding="utf-8")
    report = build_report(
        table_visual_bbox_localizer_path=visual_path,
        table_bbox_scoped_cell_extraction_path=scoped_path,
        output_dir=tmp_path / "out",
        thresholds={
            "min_source_visual_records": 2,
            "min_structure_records": 2,
            "min_selected_bbox_records": 2,
            "min_visual_bbox_rejected_records": 1,
            "max_unsafe_records": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_visual_bbox_localizer_quality_pass": True,
            "require_table_bbox_scoped_cell_extraction_quality_pass": True,
            "require_all_records_selected_bbox_ready": True,
        },
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["structure_record_count"] == 2
    assert report["summary"]["structure_visual_bbox_rejected_count"] == 1
    assert (tmp_path / "out" / "trace_net_table_structure_bbox_localizer_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_table_structure_bbox_localizer_v1_quality.json").exists()
