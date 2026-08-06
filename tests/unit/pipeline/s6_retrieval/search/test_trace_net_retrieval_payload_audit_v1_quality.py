import json
from pathlib import Path

from tiff.trace_net_retrieval_payload_audit_v1 import check_quality


def test_quality_checker_passes(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "retrieval_payload_audit_record_count": 509,
            "route_separation_pass_count": 450,
            "qdrant_payload_count": 450,
            "opensearch_payload_count": 282,
            "violation_record_count": 0,
            "source_loader_contract_audit_quality_status": "PASS",
            "source_ocr_route_scan_pack_quality_status": "PASS",
            "human_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "blank_payload_violation_count": 0,
            "blocked_payload_violation_count": 0,
            "missing_lineage_payload_count": 0,
            "route_payload_mismatch_count": 0,
        },
    }), encoding="utf-8")
    result = check_quality(
        report_path=report,
        write_json=True,
        min_records=509,
        min_route_separation_pass=400,
        min_qdrant_payloads=400,
        min_opensearch_payloads=250,
        max_violation_records=0,
        require_source_quality_pass=True,
        require_no_human_review_required=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "trace_net_retrieval_payload_audit_v1_quality_check.json").exists()


def test_quality_checker_fails_on_payload_violation(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "retrieval_payload_audit_record_count": 509,
            "route_separation_pass_count": 450,
            "qdrant_payload_count": 450,
            "opensearch_payload_count": 282,
            "violation_record_count": 0,
            "blank_payload_violation_count": 1,
            "blocked_payload_violation_count": 0,
            "missing_lineage_payload_count": 0,
            "route_payload_mismatch_count": 0,
        },
    }), encoding="utf-8")
    result = check_quality(report_path=report, min_records=1, min_route_separation_pass=1, min_qdrant_payloads=1)
    assert result["quality_status"] == "FAIL"
    assert any("blank_payload_violation_count" in failure for failure in result["failures"])
