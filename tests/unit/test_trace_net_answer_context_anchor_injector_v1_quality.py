import json
from pathlib import Path

from tiff.trace_net_answer_context_anchor_injector_v1 import check_answer_context_anchor_injector_quality


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_quality_check_passes_expected_summary(tmp_path):
    report = _write(
        tmp_path / "report.json",
        {
            "quality_status": "PASS",
            "records": [{"citation_label": "E1"}],
            "summary": {
                "source_part_number_exact_retrieval_probe_quality_status": "PASS",
                "anchor_injection_ready": True,
                "direct_exact_anchor_count": 1,
                "direct_exact_anchor_page_count": 1,
                "citation_count": 1,
                "context_anchor_prompt_char_count": 700,
                "violation_record_count": 0,
                "human_review_required_count": 0,
                "unsafe_record_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "write_attempt_count": 0,
            },
        },
    )
    result = check_answer_context_anchor_injector_quality(
        report_path=report,
        min_records=1,
        min_direct_anchors=1,
        min_direct_anchor_pages=1,
        min_citations=1,
        min_prompt_chars=500,
        max_violation_records=0,
        require_source_quality_pass=True,
        require_anchor_injection_ready=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_check_fails_missing_direct_anchor(tmp_path):
    report = _write(
        tmp_path / "report.json",
        {
            "records": [],
            "summary": {
                "source_part_number_exact_retrieval_probe_quality_status": "PASS",
                "anchor_injection_ready": False,
                "direct_exact_anchor_count": 0,
                "direct_exact_anchor_page_count": 0,
                "citation_count": 0,
                "context_anchor_prompt_char_count": 0,
                "violation_record_count": 0,
                "human_review_required_count": 0,
                "unsafe_record_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "write_attempt_count": 0,
            },
        },
    )
    result = check_answer_context_anchor_injector_quality(
        report_path=report,
        min_direct_anchors=1,
        require_anchor_injection_ready=True,
    )
    assert result["quality_status"] == "FAIL"
    assert "min_direct_anchors" in result["failures"]
    assert "require_anchor_injection_ready" in result["failures"]


def test_quality_check_writes_json(tmp_path):
    report = _write(
        tmp_path / "report.json",
        {
            "records": [{"citation_label": "E1"}],
            "summary": {
                "source_part_number_exact_retrieval_probe_quality_status": "PASS",
                "anchor_injection_ready": True,
                "direct_exact_anchor_count": 1,
                "direct_exact_anchor_page_count": 1,
                "citation_count": 1,
                "context_anchor_prompt_char_count": 700,
                "violation_record_count": 0,
                "human_review_required_count": 0,
                "unsafe_record_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "write_attempt_count": 0,
            },
        },
    )
    result = check_answer_context_anchor_injector_quality(report_path=report, write_json=True)
    assert result["quality_status"] == "PASS"
    assert report.with_name("trace_net_answer_context_anchor_injector_v1_quality_check.json").exists()
