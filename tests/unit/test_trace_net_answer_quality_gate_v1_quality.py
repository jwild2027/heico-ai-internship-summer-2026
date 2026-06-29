import json
from pathlib import Path

from tiff.trace_net_answer_quality_gate_v1 import check_answer_quality_gate_report


def _report(quality_status="PASS", violations=0):
    return {
        "quality_status": quality_status,
        "answer_text": "Part 120-29073-001 is found [E1].",
        "summary": {
            "source_context_quality_status": "PASS",
            "context_record_count": 1,
            "answer_citation_count": 1,
            "valid_answer_citation_count": 1,
            "invalid_answer_citation_count": 0,
            "direct_proof_citation_count": 1,
            "query_part_numbers": ["120-29073-001"],
            "unsupported_factual_sentence_count": 0,
            "unsupported_interchangeability_claim_count": 0,
            "graph_or_leiden_overstatement_count": 0,
            "violation_record_count": violations,
            "answer_quality_gate_passed": quality_status == "PASS",
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
        },
    }


def test_quality_check_pass(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()), encoding="utf-8")
    payload = check_answer_quality_gate_report(
        report_path=path,
        require_source_quality_pass=True,
        require_answer_quality_pass=True,
        require_direct_proof_citation=True,
        require_query_part_mentioned=True,
        require_no_unsupported_interchangeability=True,
        require_no_graph_proof_overstatement=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        max_violation_records=0,
    )
    assert payload["quality_status"] == "PASS"


def test_quality_check_fails_on_violations(tmp_path):
    path = tmp_path / "report.json"
    bad = _report(quality_status="FAIL", violations=1)
    bad["summary"]["answer_quality_gate_passed"] = False
    path.write_text(json.dumps(bad), encoding="utf-8")
    payload = check_answer_quality_gate_report(
        report_path=path,
        require_answer_quality_pass=True,
        max_violation_records=0,
    )
    assert payload["quality_status"] == "FAIL"
    assert payload["failures"]
