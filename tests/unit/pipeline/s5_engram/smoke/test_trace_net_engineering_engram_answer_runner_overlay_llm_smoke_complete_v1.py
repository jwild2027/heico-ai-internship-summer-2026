import json
from pathlib import Path

from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_complete_v1 import check_overlay_llm_smoke_complete


def test_completeness_rejects_too_short_boundary_missing_answer(tmp_path: Path):
    answer = tmp_path / "answer.txt"
    answer.write_text("**Answer**\nThe", encoding="utf-8")
    manifest = tmp_path / "h25.json"
    manifest.write_text(json.dumps({
        "quality_status": "PASS",
        "smoke_records": [{
            "question_id": "q1",
            "grade": "PARTIAL",
            "answer_path": str(answer),
            "unsupported_claim_count": 0,
            "answer_permission": False,
        }],
        "summary": {"write_attempt_count": 0},
    }), encoding="utf-8")
    result = check_overlay_llm_smoke_complete(
        overlay_llm_smoke=manifest,
        min_records=1,
        min_answer_chars=120,
        require_good=True,
        require_boundary_language=True,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"
    failures = result["checked_records"][0]["completion_failures"]
    assert "answer_too_short" in failures
    assert "grade_not_good" in failures


def test_completeness_accepts_guarded_good_answer(tmp_path: Path):
    answer = tmp_path / "answer.txt"
    answer.write_text(
        "Answer: Not source-trace-ready because proof_context is missing. "
        "Evidence: Engram is guidance only and cannot prove source claims. "
        "Engineering confidence: LOW. Limits: no eligibility or interchangeability claim is made.",
        encoding="utf-8",
    )
    manifest = tmp_path / "h25.json"
    manifest.write_text(json.dumps({
        "quality_status": "PASS",
        "smoke_records": [{
            "question_id": "q1",
            "grade": "GOOD",
            "answer_path": str(answer),
            "unsupported_claim_count": 0,
            "answer_permission": False,
        }],
        "summary": {"write_attempt_count": 0},
    }), encoding="utf-8")
    result = check_overlay_llm_smoke_complete(
        overlay_llm_smoke=manifest,
        min_records=1,
        min_answer_chars=120,
        require_good=True,
        require_boundary_language=True,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "PASS"
