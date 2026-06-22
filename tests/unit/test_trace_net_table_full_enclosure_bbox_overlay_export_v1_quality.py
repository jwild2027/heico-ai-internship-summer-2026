from tiff.trace_net_table_full_enclosure_bbox_overlay_export_v1 import evaluate_quality


def args(**overrides):
    defaults = {
        "require_table_full_enclosure_bbox_reconstructor_quality_pass": True,
        "min_source_records": 2,
        "min_overlay_records": 2,
        "min_image_available_records": 2,
        "min_overlay_pngs": 2,
        "min_contact_sheets": 1,
        "min_final_bbox_ready_overlays": 2,
        "min_full_enclosure_reconstructed_overlays": 1,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_no_answer_permission": True,
    }
    defaults.update(overrides)
    return type("Args", (), defaults)()


def payload(**summary_overrides):
    summary = {
        "source_table_full_enclosure_bbox_reconstructor_quality_status": "PASS",
        "source_record_count": 2,
        "overlay_record_count": 2,
        "image_available_record_count": 2,
        "overlay_png_written_count": 2,
        "contact_sheet_written_count": 1,
        "final_bbox_ready_overlay_count": 2,
        "full_enclosure_reconstructed_overlay_count": 1,
        "full_page_bbox_overlay_count": 1,
        "unsafe_table_full_enclosure_overlay_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    summary.update(summary_overrides)
    return {
        "schema_version": "trace_net_table_full_enclosure_bbox_overlay_export_v1",
        "status": "TABLE_FULL_ENCLOSURE_BBOX_OVERLAY_EXPORT_BUILT",
        "summary": summary,
    }


def test_quality_passes_for_good_payload():
    quality = evaluate_quality(payload(), args=args())
    assert quality["quality_status"] == "PASS"


def test_quality_fails_when_overlay_pngs_missing():
    quality = evaluate_quality(payload(overlay_png_written_count=1), args=args())
    assert quality["quality_status"] == "FAIL"
    assert "min_overlay_pngs_met" in quality["quality_fail_reasons"]
