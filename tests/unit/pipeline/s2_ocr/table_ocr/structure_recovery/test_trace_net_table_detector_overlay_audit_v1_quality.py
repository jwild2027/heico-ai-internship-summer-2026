import json
from pathlib import Path

from tiff.trace_net_table_detector_overlay_audit_v1 import Thresholds, write_json
from tiff.trace_net_table_detector_overlay_audit_v1_quality import build_quality_payload


def test_quality_passes_for_safe_report(tmp_path):
    report_path = tmp_path / "report.json"
    report = {
        "schema_version": "trace_net_table_detector_overlay_audit_v1",
        "summary": {
            "schema_version": "trace_net_table_detector_overlay_audit_v1",
            "audit_card_count": 2,
            "detector_disagreement_card_count": 1,
            "overlay_ready_card_count": 0,
            "unsafe_audit_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_quality_statuses": {"margin_detector_parity": "PASS", "table_bbox_resolver": "PASS"},
        },
        "audit_cards": [],
    }
    write_json(report_path, report)
    payload = build_quality_payload(
        report_path,
        Thresholds(
            min_audit_cards=1,
            min_detector_disagreement_cards=1,
            require_margin_detector_parity_quality_pass=True,
            require_table_bbox_resolver_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert payload["quality_status"] == "PASS"


def test_quality_fails_when_disagreement_threshold_unmet(tmp_path):
    report_path = tmp_path / "report.json"
    write_json(
        report_path,
        {
            "schema_version": "trace_net_table_detector_overlay_audit_v1",
            "summary": {
                "schema_version": "trace_net_table_detector_overlay_audit_v1",
                "audit_card_count": 1,
                "detector_disagreement_card_count": 0,
                "unsafe_audit_card_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "source_quality_statuses": {},
            },
        },
    )
    payload = build_quality_payload(report_path, Thresholds(min_detector_disagreement_cards=1))
    assert payload["quality_status"] == "FAIL"
    assert "min_detector_disagreement_cards_met" in payload["quality_fail_reasons"]
