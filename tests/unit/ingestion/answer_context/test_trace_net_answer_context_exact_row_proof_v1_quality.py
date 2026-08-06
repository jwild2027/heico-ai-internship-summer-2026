import json
from pathlib import Path

from tiff.trace_net_answer_context_exact_row_proof_v1 import check_answer_context_exact_row_proof_quality


def test_quality_check_passes(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "llm_exact_row_context_prompt": "x" * 600,
        "summary": {
            "exact_row_proof_record_count": 2,
            "citation_count": 2,
            "context_prompt_char_count": 600,
            "direct_exact_match_proven_count": 1,
            "direct_exact_match_candidate_count": 1,
            "violation_record_count": 0,
            "source_graph_leiden_expander_quality_status": "PASS",
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }), encoding="utf-8")
    result = check_answer_context_exact_row_proof_quality(
        report_path=report,
        min_records=1,
        min_citations=1,
        min_prompt_chars=500,
        min_direct_exact_proven=1,
        require_source_quality_pass=True,
        require_exact_row_prompt=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        write_json=True,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "trace_net_answer_context_exact_row_proof_v1_quality_check.json").exists()


def test_quality_check_fails_when_exact_required(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "llm_exact_row_context_prompt": "x" * 600,
        "summary": {"exact_row_proof_record_count": 1, "citation_count": 1, "context_prompt_char_count": 600, "direct_exact_match_proven_count": 0, "violation_record_count": 0}
    }), encoding="utf-8")
    result = check_answer_context_exact_row_proof_quality(report_path=report, min_direct_exact_proven=1)
    assert result["quality_status"] == "FAIL"
    assert "min_direct_exact_proven" in result["failures"]
