from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_route_dispatch_coverage_audit_v1 import build_route_dispatch_coverage_audit_report
from tiff.trace_net_route_dispatch_coverage_audit_v1_quality import RouteDispatchCoverageAuditQualityThresholds


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_route_dispatch_coverage_audit_report_detects_allowed_and_violations(tmp_path: Path) -> None:
    dispatch = {
        "schema_version": "trace_net_route_dispatch_manifest_v1",
        "quality_status": "PASS",
        "route_dispatch_cards": [
            {
                "page_id": "p1",
                "page_number": 1,
                "primary_route": "table",
                "primary_dispatch_route": "table",
                "allowed_dispatch_routes": ["table"],
                "safe_for_routing": True,
                "table_processing_allowed": True,
            },
            {
                "page_id": "p2",
                "page_number": 2,
                "primary_route": "blank_candidate",
                "primary_dispatch_route": "blank_candidate",
                "allowed_dispatch_routes": ["blank_candidate"],
                "safe_for_routing": True,
                "blank_candidate_processing_allowed": True,
            },
        ],
    }
    detector = {
        "schema_version": "trace_net_artifact_detector_v1",
        "quality_status": "PASS",
        "page_artifact_cards": [
            {"page_id": "p1", "table_evidence_artifact_count": 2, "artifact_keys": ["table_line_geometry"]},
            {"page_id": "p2", "table_evidence_artifact_count": 1, "artifact_keys": ["table_bbox_resolver"]},
        ],
        "artifact_cards": [],
    }
    dispatch_path = tmp_path / "dispatch.json"
    detector_path = tmp_path / "detector.json"
    _write_json(dispatch_path, dispatch)
    _write_json(detector_path, detector)

    report = build_route_dispatch_coverage_audit_report(
        route_dispatch_manifest_path=dispatch_path,
        artifact_detector_path=detector_path,
        output_dir=tmp_path / "out",
        thresholds=RouteDispatchCoverageAuditQualityThresholds(
            min_dispatch_coverage_cards=2,
            min_audited_page_artifact_cards=2,
            require_route_dispatch_manifest_quality_pass=True,
            require_artifact_detector_quality_pass=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["dispatch_coverage_card_count"] == 2
    assert report["summary"]["route_dispatch_violation_card_count"] == 1
    cards = {card["page_id"]: card for card in report["route_dispatch_coverage_cards"]}
    assert cards["p1"]["route_dispatch_coverage_status"] == "PASS"
    assert "table_artifact_without_allowed_dispatch" in cards["p2"]["route_dispatch_violations"]


def test_missing_dispatch_card_is_unsafe_and_fails_quality(tmp_path: Path) -> None:
    dispatch_path = tmp_path / "dispatch.json"
    detector_path = tmp_path / "detector.json"
    _write_json(dispatch_path, {"schema_version": "trace_net_route_dispatch_manifest_v1", "quality_status": "PASS", "route_dispatch_cards": []})
    _write_json(detector_path, {"schema_version": "trace_net_artifact_detector_v1", "quality_status": "PASS", "page_artifact_cards": [{"page_id": "p1", "table_evidence_artifact_count": 1}]})

    report = build_route_dispatch_coverage_audit_report(
        route_dispatch_manifest_path=dispatch_path,
        artifact_detector_path=detector_path,
        output_dir=tmp_path / "out",
        thresholds=RouteDispatchCoverageAuditQualityThresholds(
            min_dispatch_coverage_cards=1,
            min_audited_page_artifact_cards=1,
            max_unsafe_audit_cards=0,
        ),
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["unsafe_audit_card_count"] == 1
