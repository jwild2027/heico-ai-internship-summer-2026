import json
from pathlib import Path

from tiff.trace_net_part_number_exact_retrieval_probe_v1 import check_part_number_exact_retrieval_probe_quality


def test_quality_check_passes_with_thresholds(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "records": [{"citation_label": "E1"}],
                "summary": {
                    "exact_hit_count": 2,
                    "exact_page_count": 2,
                    "exact_direct_hit_count": 1,
                    "direct_exact_page_count": 1,
                    "context_seed_prompt_char_count": 800,
                    "violation_record_count": 0,
                    "source_quality_statuses": {"ocr_route_scan_pack": "PASS"},
                    "exact_retrieval_probe_ready": True,
                    "human_review_required_count": 0,
                    "manual_review_required_count": 0,
                    "unsafe_record_count": 0,
                    "answer_permission_count": 0,
                    "source_truth_mutation_allowed_count": 0,
                    "write_attempt_count": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    result = check_part_number_exact_retrieval_probe_quality(
        report_path=path,
        min_records=1,
        min_exact_hits=1,
        min_exact_pages=1,
        min_direct_exact_hits=1,
        min_direct_exact_pages=1,
        min_prompt_chars=500,
        max_violation_records=0,
        require_source_quality_pass=True,
        require_exact_retrieval_probe_ready=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_check_fails_when_direct_hits_missing(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "records": [],
                "summary": {
                    "exact_hit_count": 1,
                    "exact_page_count": 1,
                    "exact_direct_hit_count": 0,
                    "direct_exact_page_count": 0,
                    "context_seed_prompt_char_count": 800,
                    "violation_record_count": 0,
                    "source_quality_statuses": {"ocr_route_scan_pack": "PASS"},
                    "exact_retrieval_probe_ready": True,
                    "unsafe_record_count": 0,
                    "answer_permission_count": 0,
                    "source_truth_mutation_allowed_count": 0,
                    "write_attempt_count": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    result = check_part_number_exact_retrieval_probe_quality(report_path=path, min_direct_exact_hits=1)
    assert result["quality_status"] == "FAIL"
    assert "min_direct_exact_hits" in result["failures"]
