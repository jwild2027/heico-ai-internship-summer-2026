from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_human_review_queue_v1 import quality_report


def test_quality_report_passes_safe_queue(tmp_path: Path) -> None:
    report = {
        "summary": {
            "review_task_count": 2,
            "high_priority_review_task_count": 1,
            "missing_page_id_count": 0,
            "unsafe_review_task_count": 0,
            "review_task_can_answer_directly_count": 0,
            "review_task_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "it_console_quality_status": "PASS",
        }
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    quality = quality_report(
        report_path=path,
        min_review_tasks=1,
        min_high_priority_review_tasks=1,
        require_it_console_quality_pass=True,
    )
    assert quality["status"] == "PASS"


def test_quality_report_fails_if_review_task_can_answer(tmp_path: Path) -> None:
    report = {
        "summary": {
            "review_task_count": 2,
            "high_priority_review_task_count": 1,
            "missing_page_id_count": 0,
            "unsafe_review_task_count": 0,
            "review_task_can_answer_directly_count": 1,
            "review_task_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
        }
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    quality = quality_report(report_path=path)
    assert quality["status"] == "FAIL"
    assert quality["checks"]["review_task_can_answer_directly_count_zero"] is False


def test_quality_report_writes_json(tmp_path: Path) -> None:
    report = {
        "summary": {
            "review_task_count": 1,
            "high_priority_review_task_count": 1,
            "missing_page_id_count": 0,
            "unsafe_review_task_count": 0,
            "review_task_can_answer_directly_count": 0,
            "review_task_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
        }
    }
    path = tmp_path / "trace_net_human_review_queue_v1.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    quality = quality_report(report_path=path, write_json_report=True)
    assert quality["status"] == "PASS"
    assert (tmp_path / "trace_net_human_review_queue_v1_quality.json").exists()
