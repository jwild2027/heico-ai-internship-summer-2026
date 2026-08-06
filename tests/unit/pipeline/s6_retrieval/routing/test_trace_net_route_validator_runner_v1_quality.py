import json
from pathlib import Path

from tiff.trace_net_route_validator_runner_v1 import check_quality


def test_quality_checker_passes_expected_manifest(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    report = out / "trace_net_route_validator_runner_v1.json"
    for name in [
        "trace_net_route_validator_runner_v1_records.csv",
        "trace_net_route_validator_runner_v1_validated_records.csv",
        "trace_net_route_validator_runner_v1_unresolved_records.csv",
        "trace_net_route_validator_runner_v1_records.jsonl",
    ]:
        (out / name).write_text("x", encoding="utf-8")
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "source_four_route_resolver_quality_status": "PASS",
            "validator_record_count": 509,
            "validated_route_count": 300,
            "validator_gated_unresolved_count": 10,
            "qdrant_embedding_allowed_count": 250,
            "opensearch_index_allowed_count": 200,
            "invalid_validated_route_count": 0,
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
    result = check_quality(
        report_path=report,
        min_records=509,
        min_validated=100,
        min_unresolved=1,
        min_qdrant_allowed=100,
        min_opensearch_allowed=1,
        require_source_quality_pass=True,
        require_no_human_review_required=True,
        require_decision_files=True,
        require_four_validated_routes_only=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_checker_fails_low_validated_count(tmp_path):
    report = tmp_path / "trace_net_route_validator_runner_v1.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "source_four_route_resolver_quality_status": "PASS",
            "validator_record_count": 509,
            "validated_route_count": 2,
            "validator_gated_unresolved_count": 0,
            "invalid_validated_route_count": 0,
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "unsafe_record_count": 0,
        },
    }), encoding="utf-8")
    result = check_quality(report_path=report, min_records=509, min_validated=100)
    assert result["quality_status"] == "FAIL"
    assert any("validated_route_count" in failure for failure in result["failures"])
