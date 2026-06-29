import json
from pathlib import Path

from tiff.trace_net_four_route_operational_resolver_v1 import build_four_route_operational_resolver, check_quality


def test_quality_checker_passes_expected_manifest(tmp_path):
    source = tmp_path / "resolver.json"
    source.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [
            {"page_number": 1, "primary_route": "detailed_parts_list", "route_confidence_band": "high", "route_confidence_score": 94, "auto_resolved": True},
            {"page_number": 2, "primary_route": "review_required", "candidate_routes": ["table_or_index"], "route_confidence_band": "low", "validator_required": True},
        ],
    }), encoding="utf-8")
    payload = build_four_route_operational_resolver(route_confidence_resolver=source, output_dir=tmp_path / "out", quality=True)
    report = tmp_path / "out" / "trace_net_four_route_operational_resolver_v1.json"
    result = check_quality(
        report_path=report,
        min_records=2,
        min_auto_resolved=1,
        min_validator_required=1,
        min_multi_route_required=1,
        require_source_quality_pass=True,
        require_four_operational_routes_only=True,
        require_no_human_review_required=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        max_unsafe=0,
    )
    assert payload["quality_status"] == "PASS"
    assert result["quality_status"] == "PASS"


def test_quality_checker_fails_unknown_subtype(tmp_path):
    report = tmp_path / "bad.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "operational_record_count": 1,
            "auto_resolved_operational_route_count": 0,
            "validator_required_count": 1,
            "multi_route_required_count": 1,
            "source_route_confidence_resolver_quality_status": "PASS",
            "invalid_operational_route_count": 0,
            "unknown_subtype_count": 1,
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }), encoding="utf-8")
    result = check_quality(report_path=report, max_unknown_subtypes=0)
    assert result["quality_status"] == "FAIL"
