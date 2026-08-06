import json
from pathlib import Path

from tiff.trace_net_part_family_fast_answer_composer_v1 import check_part_family_fast_answer_composer_quality


def test_part_family_quality_pass(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "part_family_answer_record_count": 3,
            "answer_citation_count": 4,
            "valid_answer_citation_count": 4,
            "part_family_part_number_count": 3,
            "invalid_answer_citation_count": 0,
            "violation_record_count": 0,
            "source_context_quality_status": "PASS",
            "part_family_fast_answer_ready": True,
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        }
    }), encoding="utf-8")
    result = check_part_family_fast_answer_composer_quality(
        report_path=report,
        min_records=1,
        min_citations=1,
        min_valid_citations=1,
        min_family_part_numbers=2,
        require_source_quality_pass=True,
        require_part_family_answer_ready=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"
