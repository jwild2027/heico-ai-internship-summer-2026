import json
from pathlib import Path

from tiff.trace_net_leiden_navigation_metadata_bridge_v1 import (
    BridgeThresholds,
    build_navigation_metadata_bridge,
    check_bridge_quality,
)


def _source(path: Path) -> Path:
    payload = {
        "quality_status": "PASS",
        "status": "LEIDEN_REPRESENTATIVE_LABELS_REFINED",
        "summary": {},
        "community_profile_records": [
            {
                "community_id": "c1",
                "refined_label": "Part family community 120-46137",
                "page_count": 1,
                "representative_page_ids": ["p1"],
                "representative_part_numbers": ["120-46137-001"],
                "navigation_intent": "part_family_navigation",
                "navigation_confidence": "HIGH_NAVIGATION_CONFIDENCE",
                "dominant_evidence_category": "table_evidence",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_check_bridge_quality_passes_existing_report(tmp_path):
    report = build_navigation_metadata_bridge(
        label_tightening_path=_source(tmp_path / "source.json"),
        output_dir=tmp_path / "out",
        thresholds=BridgeThresholds(min_community_records=1, min_retrieval_hints=1, min_page_navigation_hints=1),
    )
    quality = check_bridge_quality(
        report_path=report["report_path"],
        thresholds=BridgeThresholds(
            min_community_records=1,
            min_retrieval_hints=1,
            min_page_navigation_hints=1,
            require_no_answer_permission=True,
        ),
        write_json_report=True,
    )
    assert quality["quality_status"] == "PASS"
    quality_path = Path(report["quality_path"])
    assert quality_path.exists()
    saved = json.loads(quality_path.read_text(encoding="utf-8"))
    assert saved["quality_status"] == "PASS"


def test_check_bridge_quality_fails_threshold(tmp_path):
    report = build_navigation_metadata_bridge(
        label_tightening_path=_source(tmp_path / "source.json"),
        output_dir=tmp_path / "out",
    )
    quality = check_bridge_quality(
        report_path=report["report_path"],
        thresholds=BridgeThresholds(min_community_records=99),
    )
    assert quality["quality_status"] == "FAIL"
    assert "community_navigation_record_count_below_minimum" in quality["summary"]["quality_issues"]


def test_zero_safety_counters_are_reported(tmp_path):
    report = build_navigation_metadata_bridge(
        label_tightening_path=_source(tmp_path / "source.json"),
        output_dir=None,
        write_files=False,
    )
    summary = report["summary"]
    for key in [
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        assert summary[key] == 0
