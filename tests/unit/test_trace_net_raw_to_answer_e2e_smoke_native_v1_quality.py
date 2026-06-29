import json
from tiff import trace_net_raw_to_answer_e2e_smoke_native_v1 as mod


def test_check_quality_pass(tmp_path):
    report = tmp_path / mod.REPORT_NAME
    payload = {
        "quality_status": "PASS",
        "summary": {
            "stage_report_count": 9,
            "postgres_contract_ready_count": 509,
            "qdrant_contract_ready_count": 450,
            "opensearch_contract_ready_count": 282,
            "qdrant_payload_count": 450,
            "opensearch_payload_count": 282,
            "retrieval_evidence_count": 8,
            "citation_count": 8,
            "violation_record_count": 0,
            "all_stage_quality_pass": True,
            "dry_run_only": True,
            "human_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "llm_status": "PASS",
            "llm_answer_char_count": 128,
        },
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    result = mod.check_quality(
        report_path=report,
        require_all_stage_quality_pass=True,
        require_dry_run_only=True,
        require_no_human_review_required=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        require_llm_success=True,
    )
    assert result["quality_status"] == "PASS"


def test_check_quality_fails_low_evidence(tmp_path):
    report = tmp_path / mod.REPORT_NAME
    payload = {"quality_status": "PASS", "summary": {"stage_report_count": 9, "retrieval_evidence_count": 0}}
    report.write_text(json.dumps(payload), encoding="utf-8")
    result = mod.check_quality(report_path=report, min_retrieval_evidence=1)
    assert result["quality_status"] == "FAIL"
