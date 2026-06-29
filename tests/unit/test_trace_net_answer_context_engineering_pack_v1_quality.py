import json
from pathlib import Path

from tiff.trace_net_answer_context_engineering_pack_v1 import check_quality


def test_quality_passes_for_valid_manifest(tmp_path):
    report = tmp_path / "manifest.json"
    payload = {
        "quality_status": "PASS",
        "summary": {
            "context_pack_record_count": 2,
            "retrieval_evidence_count": 2,
            "citation_count": 2,
            "direct_evidence_count": 1,
            "context_prompt_char_count": 500,
            "violation_record_count": 0,
            "source_raw_to_answer_quality_status": "PASS",
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "human_review_required_count": 0,
        },
        "llm_context_prompt": "x" * 500,
    }
    report.write_text(json.dumps(payload), encoding="utf-8")

    result = check_quality(
        report_path=report,
        write_json=True,
        min_records=2,
        min_retrieval_evidence=2,
        min_citations=2,
        min_direct_evidence=1,
        min_prompt_chars=200,
        require_source_quality_pass=True,
        require_context_prompt=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )

    assert result["quality_status"] == "PASS"
    assert (tmp_path / "trace_net_answer_context_engineering_pack_v1_quality_check.json").exists()


def test_quality_fails_for_violations(tmp_path):
    report = tmp_path / "manifest.json"
    report.write_text(json.dumps({"quality_status": "PASS", "summary": {"violation_record_count": 2}, "llm_context_prompt": ""}), encoding="utf-8")

    result = check_quality(report_path=report, max_violation_records=0, require_context_prompt=True)

    assert result["quality_status"] == "FAIL"
    assert "too many violation records" in result["failures"]
    assert "context prompt required" in result["failures"]
