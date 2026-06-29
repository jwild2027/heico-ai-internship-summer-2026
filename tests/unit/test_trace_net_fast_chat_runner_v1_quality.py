import json
from pathlib import Path

from tiff.trace_net_fast_chat_runner_v1 import check_fast_chat_runner_quality


def test_quality_checker_passes_ready_report(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"summary": {
        "stage_count": 3,
        "answer_citation_count": 3,
        "valid_answer_citation_count": 3,
        "direct_exact_answer_record_count": 8,
        "figure_item_answer_record_count": 0,
        "part_family_answer_record_count": 0,
        "part_family_part_number_count": 0,
        "invalid_answer_citation_count": 0,
        "violation_record_count": 0,
        "source_context_quality_status": "PASS",
        "fast_chat_runner_ready": True,
        "multi_route_quality_gate_passed": True,
        "webui_answer_ready": True,
        "query_type": "exact_part_number",
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
    }}), encoding="utf-8")
    result = check_fast_chat_runner_quality(
        report_path=str(report),
        min_stage_reports=3,
        min_citations=1,
        min_valid_citations=1,
        min_direct_exact_records=8,
        require_source_quality_pass=True,
        require_fast_chat_ready=True,
        require_multi_route_quality_pass=True,
        require_webui_answer_ready=True,
        require_exact_part_query=True,
        require_no_human_review_required=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_checker_fails_unready_webui(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"summary": {"stage_count": 1, "webui_answer_ready": False}}), encoding="utf-8")
    result = check_fast_chat_runner_quality(report_path=str(report), require_webui_answer_ready=True)
    assert result["quality_status"] == "FAIL"
