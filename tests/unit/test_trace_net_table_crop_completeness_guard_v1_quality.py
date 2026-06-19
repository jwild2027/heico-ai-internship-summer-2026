from tiff.trace_net_table_crop_completeness_guard_v1_quality import build_quality_report


def test_quality_report_passes_safe_summary():
    report = {
        "schema_version": "trace_net_table_crop_completeness_guard_v1",
        "summary": {
            "crop_completeness_card_count": 2,
            "unsafe_crop_completeness_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_quality_statuses": {
                "table_line_geometry": "PASS",
                "table_bbox_resolver": "PASS",
                "overlay_review_pack": "PASS",
            },
        },
    }
    quality = build_quality_report(
        report,
        thresholds={
            "min_completeness_cards": 1,
            "max_unsafe_completeness_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_bbox_resolver_quality_pass": True,
            "require_overlay_review_pack_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert quality["quality_status"] == "PASS"
    assert quality["checks"]["no_answer_permission"] is True


def test_quality_report_fails_missing_cards():
    report = {
        "schema_version": "trace_net_table_crop_completeness_guard_v1",
        "summary": {
            "crop_completeness_card_count": 0,
            "unsafe_crop_completeness_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_quality_statuses": {},
        },
    }
    quality = build_quality_report(report, thresholds={"min_completeness_cards": 1})
    assert quality["quality_status"] == "FAIL"
    assert "min_completeness_cards_met" in quality["quality_fail_reasons"]
