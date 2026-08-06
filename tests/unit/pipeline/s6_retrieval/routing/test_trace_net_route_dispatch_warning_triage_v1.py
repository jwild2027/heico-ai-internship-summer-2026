from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_route_dispatch_warning_triage_v1 import build_route_dispatch_warning_triage_report
from tiff.trace_net_route_dispatch_warning_triage_v1_quality import RouteDispatchWarningTriageQualityThresholds


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_route_dispatch_warning_triage_classifies_known_warnings(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    _write_json(audit_path, {
        "schema_version": "trace_net_route_dispatch_coverage_audit_v1",
        "quality_status": "PASS",
        "summary": {
            "quality_status": "PASS",
            "route_dispatch_warning_card_count": 2,
            "route_dispatch_violation_card_count": 0,
        },
        "route_dispatch_coverage_cards": [
            {
                "page_id": "p1",
                "page_number": 1,
                "primary_dispatch_route": "blank_candidate",
                "allowed_dispatch_routes": ["blank_candidate"],
                "blank_candidate_processing_allowed": True,
                "route_dispatch_coverage_status": "WARNING",
                "route_dispatch_warnings": ["blank_candidate_has_heavy_processing_evidence"],
                "artifact_evidence_category_counts": {"table": 1},
            },
            {
                "page_id": "p2",
                "page_number": 2,
                "primary_dispatch_route": "table",
                "allowed_dispatch_routes": ["table"],
                "route_dispatch_coverage_status": "WARNING",
                "route_dispatch_warnings": [
                    "ocr_text_artifact_without_explicit_text_dispatch",
                    "retrieval_answer_artifact_without_explicit_text_dispatch",
                ],
                "artifact_evidence_category_counts": {"ocr_text": 1, "retrieval_answer": 1},
            },
        ],
    })
    report = build_route_dispatch_warning_triage_report(
        route_dispatch_coverage_audit_path=audit_path,
        output_dir=tmp_path / "out",
        thresholds=RouteDispatchWarningTriageQualityThresholds(
            min_warning_triage_cards=3,
            require_route_dispatch_coverage_audit_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["warning_triage_card_count"] == 3
    assert report["summary"]["blank_heavy_processing_triage_count"] == 1
    assert report["summary"]["ocr_text_dispatch_policy_triage_count"] == 1
    assert report["summary"]["retrieval_answer_legacy_overlap_triage_count"] == 1
    assert {card["warning_family"] for card in report["warning_triage_cards"]} == {
        "blank_candidate_heavy_processing",
        "ocr_text_dispatch_policy",
        "retrieval_answer_legacy_overlap",
    }


def test_route_dispatch_warning_triage_records_unresolved_violations(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    _write_json(audit_path, {
        "schema_version": "trace_net_route_dispatch_coverage_audit_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS", "route_dispatch_violation_card_count": 1},
        "route_dispatch_coverage_cards": [
            {
                "page_id": "p1",
                "page_number": 1,
                "route_dispatch_coverage_status": "VIOLATION",
                "route_dispatch_violations": ["table_artifact_without_allowed_dispatch"],
                "route_dispatch_warnings": ["ocr_text_artifact_without_explicit_text_dispatch"],
            }
        ],
    })
    report = build_route_dispatch_warning_triage_report(
        route_dispatch_coverage_audit_path=audit_path,
        output_dir=tmp_path / "out",
        thresholds=RouteDispatchWarningTriageQualityThresholds(min_warning_triage_cards=1),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["unresolved_violation_triage_count"] == 1
    assert report["unresolved_violation_triage_cards"][0]["route_dispatch_violations"] == ["table_artifact_without_allowed_dispatch"]
