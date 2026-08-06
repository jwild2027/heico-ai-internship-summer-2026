from tiff.trace_net_table_extraction_bbox_overlay_export_v1 import OverlayThresholds, build_quality


def test_overlay_export_quality_passes() -> None:
    summary = {
        "overlay_record_count": 2,
        "overlay_png_count": 2,
        "missing_extraction_bbox_count": 0,
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "table_line_geometry_quality_status": "PASS",
    }
    assert build_quality(summary, OverlayThresholds())["status"] == "PASS"


def test_overlay_export_quality_fails_missing_bbox() -> None:
    summary = {
        "overlay_record_count": 2,
        "overlay_png_count": 1,
        "missing_extraction_bbox_count": 1,
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "table_line_geometry_quality_status": "PASS",
    }
    assert build_quality(summary, OverlayThresholds())["status"] == "FAIL"
