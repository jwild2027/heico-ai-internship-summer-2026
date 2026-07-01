import json
from pathlib import Path

from tiff.trace_net_engineering_real_answer_smoke_test_v1 import (
    DEFAULT_QUESTIONS,
    _grade_record,
    _normalize_questions,
    _short_run_dir,
    check_real_answer_smoke_test,
)


def test_default_question_bank_has_30_diverse_questions():
    assert len(DEFAULT_QUESTIONS) == 30
    categories = {q["category"] for q in DEFAULT_QUESTIONS}
    for needed in ["figure_lookup", "exact_part_lookup", "comparison", "interchangeability", "installation_safety", "troubleshooting", "unknown_part"]:
        assert needed in categories


def test_short_run_dir_keeps_windows_paths_short(tmp_path):
    long_question = "Find part number 120-50645-005 and cite the source while also explaining every limitation in detail."
    d = _short_run_dir(tmp_path / "runs", 4, long_question, "exact_part_lookup")
    assert d.name.startswith("q04_part_")
    assert len(d.name) <= 20
    assert "120_50645" not in d.name


def test_grade_marks_bad_for_unsupported_claims():
    row = {"runner_passed": True, "unsupported_claim_count": 1, "source_trace_ready_citation_count": 3, "proof_context_count": 3}
    assert _grade_record(row, "answer") == "BAD"


def test_grade_marks_blocked_for_runner_failure():
    row = {"runner_passed": False, "unsupported_claim_count": 0, "summary_used_as_proof_count": 0, "invalid_answer_citation_count": 0}
    assert _grade_record(row, "") == "BLOCKED"


def test_check_manifest_passes_with_good_thresholds(tmp_path):
    manifest = tmp_path / "smoke.json"
    data = {
        "quality_status": "PASS",
        "summary": {
            "smoke_question_count": 30,
            "good_answer_count": 12,
            "good_or_partial_answer_count": 20,
            "bad_answer_count": 0,
            "unsupported_claim_count": 0,
            "summary_used_as_proof_count": 0,
            "invalid_answer_citation_count": 0,
            "llava_only_part_identity_claim_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        },
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    result = check_real_answer_smoke_test(
        manifest=manifest,
        min_smoke_questions=30,
        min_good_answers=10,
        min_good_or_partial_answers=20,
        max_bad_answers=0,
    )
    assert result["quality_status"] == "PASS"
