import json
from pathlib import Path

from tiff.trace_net_raw_to_answer_e2e_smoke_v1 import check_quality


def test_quality_passes_expected_report(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "all_stage_quality_pass": True,
            "stage_report_count": 9,
            "postgres_contract_ready_count": 509,
            "qdrant_contract_ready_count": 450,
            "opensearch_contract_ready_count": 282,
            "qdrant_payload_count": 450,
            "opensearch_payload_count": 282,
            "retrieval_evidence_count": 3,
            "citation_count": 3,
            "violation_record_count": 0,
            "missing_lineage_count": 0,
            "route_payload_mismatch_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "human_review_required_count": 0,
            "unsafe_record_count": 0,
            "dry_run_only": True,
            "live_write_enabled": False,
        },
    }), encoding="utf-8")
    result = check_quality(
        report_path=report,
        require_all_stage_quality_pass=True,
        require_dry_run_only=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_fails_missing_retrieval_evidence(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "FAIL",
        "summary": {
            "all_stage_quality_pass": True,
            "stage_report_count": 9,
            "postgres_contract_ready_count": 509,
            "qdrant_contract_ready_count": 450,
            "opensearch_contract_ready_count": 282,
            "qdrant_payload_count": 450,
            "opensearch_payload_count": 282,
            "retrieval_evidence_count": 0,
            "citation_count": 0,
            "violation_record_count": 0,
            "dry_run_only": True,
        },
    }), encoding="utf-8")
    result = check_quality(report_path=report)
    assert result["quality_status"] == "FAIL"
    assert any("retrieval_evidence" in item for item in result["failures"])


def test_quality_can_require_llm_success(tmp_path):
    report = tmp_path / "report.json"
    base_summary = {
        "all_stage_quality_pass": True,
        "stage_report_count": 9,
        "postgres_contract_ready_count": 509,
        "qdrant_contract_ready_count": 450,
        "opensearch_contract_ready_count": 282,
        "qdrant_payload_count": 450,
        "opensearch_payload_count": 282,
        "retrieval_evidence_count": 3,
        "citation_count": 3,
        "violation_record_count": 0,
        "missing_lineage_count": 0,
        "route_payload_mismatch_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
        "human_review_required_count": 0,
        "unsafe_record_count": 0,
        "dry_run_only": True,
        "live_write_enabled": False,
        "llm_status": "FALLBACK",
        "llm_answer_char_count": 0,
    }
    report.write_text(json.dumps({"quality_status": "PASS", "summary": base_summary}), encoding="utf-8")
    result = check_quality(report_path=report, require_llm_success=True)
    assert result["quality_status"] == "FAIL"
    assert any("llm_status" in item for item in result["failures"])

    base_summary["llm_status"] = "PASS"
    base_summary["llm_answer_char_count"] = 200
    report.write_text(json.dumps({"quality_status": "PASS", "summary": base_summary}), encoding="utf-8")
    result = check_quality(report_path=report, require_llm_success=True)
    assert result["quality_status"] == "PASS"
