import json
from pathlib import Path

from tiff.trace_net_engineering_runner_expanded_eval_set_v1 import (
    DEFAULT_EXPANDED_QUESTIONS,
    _collect_summary,
    _evaluate_quality,
    check_engineering_runner_expanded_eval_set,
)


def test_default_expanded_questions_cover_lookup_debug_and_safety():
    joined = "\n".join(DEFAULT_EXPANDED_QUESTIONS).lower()
    assert "figure 69" in joined
    assert "120-50645-005" in joined
    assert "nomenclature" in joined
    assert "interchangeable" in joined
    assert "installation safety" in joined
    assert len(DEFAULT_EXPANDED_QUESTIONS) >= 10


def test_collect_summary_preserves_h6_counts():
    h6 = {
        "summary": {
            "runner_pass_count": 6,
            "runner_fail_count": 1,
            "summary_used_as_proof_count": 0,
            "unsupported_claim_count": 0,
            "source_trace_ready_citation_count": 18,
        },
        "records": [
            {"question": "What does figure 69 show?", "runner_passed": True, "task_type": "visual_part_identification"},
            {"question": "Is it interchangeable?", "runner_passed": False, "task_type": "general_engineering_question"},
        ],
    }
    s = _collect_summary(h6)
    assert s["runner_pass_count"] == 6
    assert s["expanded_question_count"] == 2
    assert s["failing_question_count"] == 1
    assert "visual_part_identification" in s["task_types"]


def test_evaluate_quality_fails_when_runner_passes_too_low():
    failures = _evaluate_quality(
        {"expanded_question_count": 12, "runner_pass_count": 5},
        min_expanded_questions=12,
        min_runner_passes=6,
    )
    assert any("runner_pass_count" in f for f in failures)


def test_check_expanded_eval_set_passes(tmp_path):
    manifest = tmp_path / "expanded.json"
    output = tmp_path / "check.json"
    manifest.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "expanded_question_count": 12,
            "runner_pass_count": 8,
            "unsupported_claim_count": 0,
            "summary_used_as_proof_count": 0,
            "invalid_answer_citation_count": 0,
            "llava_only_part_identity_claim_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        },
    }), encoding="utf-8")
    result = check_engineering_runner_expanded_eval_set(
        expanded_eval_set=manifest,
        output=output,
        require_quality_pass=True,
        min_expanded_questions=12,
        min_runner_passes=6,
    )
    assert result["quality_status"] == "PASS"
    assert output.exists()


def test_check_expanded_eval_set_blocks_summary_proof(tmp_path):
    manifest = tmp_path / "expanded.json"
    output = tmp_path / "check.json"
    manifest.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "expanded_question_count": 12,
            "runner_pass_count": 8,
            "summary_used_as_proof_count": 1,
        },
    }), encoding="utf-8")
    result = check_engineering_runner_expanded_eval_set(
        expanded_eval_set=manifest,
        output=output,
        min_expanded_questions=12,
        min_runner_passes=6,
        max_summary_used_as_proof=0,
    )
    assert result["quality_status"] == "FAIL"
    assert any("summary_used_as_proof_count" in f for f in result["failures"])
