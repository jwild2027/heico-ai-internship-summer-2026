from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_calibrated_cascade_route_brain_v35_3 import build_calibrated_route_brain, quality_checks


def _write_features(path: Path) -> None:
    rows = [
        {"schema_version": "test", "page_id": "p1", "page_number": 1, "filename": "1.tif", "manual_label": "diagram", "manual_diagram_page": True, "predicted_primary_route": "image_visual", "fishnet_uncertain": False, "route_scores": {"image_visual": 0.90, "normal_text": 0.20, "table": 0.10, "blank_candidate": 0.0}, "feature_summary": {"ink_density": 0.07, "edge_density": 0.2}},
        {"schema_version": "test", "page_id": "p2", "page_number": 2, "filename": "2.tif", "manual_label": "non_diagram", "manual_diagram_page": False, "predicted_primary_route": "normal_text", "fishnet_uncertain": False, "route_scores": {"image_visual": 0.30, "normal_text": 0.80, "table": 0.10, "blank_candidate": 0.0}, "feature_summary": {"ink_density": 0.12, "edge_density": 0.1}},
        {"schema_version": "test", "page_id": "p3", "page_number": 3, "filename": "3.tif", "manual_label": "diagram", "manual_diagram_page": True, "predicted_primary_route": "table", "fishnet_uncertain": True, "route_scores": {"image_visual": 0.50, "normal_text": 0.20, "table": 0.56, "blank_candidate": 0.0}, "feature_summary": {"ink_density": 0.08, "edge_density": 0.2}},
    ]
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_build_calibrated_route_brain(tmp_path: Path):
    features = tmp_path / "features.jsonl"
    _write_features(features)
    out = tmp_path / "out"
    report = build_calibrated_route_brain(feature_audit_report=None, feature_records_jsonl=features, output_dir=out)
    assert report["source_page_count"] == 3
    assert report["route_decision_count"] == 3
    assert report["actual_diagram_page_count"] == 2
    assert Path(report["decisions_jsonl_path"]).exists()
    assert Path(report["fishnet_review_queue_jsonl_path"]).exists()
    assert report["diagram_recall"] >= 0.5
    decisions = [json.loads(x) for x in Path(report["decisions_jsonl_path"]).read_text().splitlines()]
    assert decisions[2]["fishnet_action"] == "dual_route_table_and_visual"
    assert "image_visual" in decisions[2]["secondary_routes"]


def test_quality_checks_pass(tmp_path: Path):
    features = tmp_path / "features.jsonl"
    _write_features(features)
    report = build_calibrated_route_brain(feature_audit_report=None, feature_records_jsonl=features, output_dir=tmp_path / "out")
    class Args:
        min_source_pages = 3
        min_route_decisions = 3
        min_actual_diagram_pages = 2
        min_diagram_recall = 0.5
        min_diagram_precision = 0.5
        max_false_negative_diagram_count = 1
        min_fishnet_review_queue_count = 1
        max_answer_permission_count = 0
        max_source_truth_mutation_allowed = 0
        require_no_answer_permission = True
    checks = quality_checks(report, Args())
    assert all(c["passed"] for c in checks)


def test_secondary_image_route_stays_review_not_visual_context(tmp_path):
    features = tmp_path / "features.jsonl"
    rows = [
        {"schema_version": "test", "page_id": "p1", "page_number": 1, "filename": "1.tif", "manual_label": "non_diagram", "manual_diagram_page": False, "predicted_primary_route": "normal_text", "fishnet_uncertain": True, "route_scores": {"image_visual": 0.55, "normal_text": 0.70, "table": 0.10, "blank_candidate": 0.0}, "feature_summary": {"ink_density": 0.10, "edge_density": 0.20}},
    ]
    with features.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    out = tmp_path / "out"
    report = build_calibrated_route_brain(feature_audit_report=None, feature_records_jsonl=features, output_dir=out)
    decision = report["sample_decisions"][0]
    assert decision["fishnet_visual_review_candidate"] is True
    assert decision["visual_context_eligible"] is False
    assert decision["predicted_visual"] is False
    assert "image_visual" not in decision["dispatch_routes"]
