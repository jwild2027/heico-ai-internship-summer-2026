import json
from pathlib import Path

from tiff.trace_net_engineering_real_answer_smoke_review_v1 import build_smoke_review, check_smoke_review


def _write_smoke(tmp_path: Path, records):
    p = tmp_path / "smoke" / "trace_net_engineering_real_answer_smoke_test_v1.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "runner_pass_count": sum(1 for r in records if r.get("runner_passed")),
        "runner_fail_count": sum(1 for r in records if not r.get("runner_passed")),
        "intent_answer_used_count": sum(1 for r in records if r.get("intent_answer_used")),
        "answer_citation_count": sum(int(r.get("answer_citation_count", 0)) for r in records),
        "valid_answer_citation_count": sum(int(r.get("valid_answer_citation_count", 0)) for r in records),
        "source_trace_ready_citation_count": sum(int(r.get("source_trace_ready_citation_count", 0)) for r in records),
        "unsupported_claim_count": sum(int(r.get("unsupported_claim_count", 0)) for r in records),
        "summary_used_as_proof_count": sum(int(r.get("summary_used_as_proof_count", 0)) for r in records),
        "invalid_answer_citation_count": 0,
        "llava_only_part_identity_claim_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
    }
    p.write_text(json.dumps({"quality_status": "PASS", "summary": summary, "records": records}), encoding="utf-8")
    return p


def test_review_counts_grades_and_weak_categories(tmp_path):
    records = [
        {"question_id": "q01", "question": "What does figure 69 show?", "category": "figure_lookup", "grade": "GOOD", "runner_passed": True, "quality_status": "PASS", "answer_citation_count": 3, "source_trace_ready_citation_count": 3},
        {"question_id": "q02", "question": "What evidence supports Figure 69?", "category": "evidence_support", "grade": "PARTIAL", "runner_passed": True, "quality_status": "PASS", "answer_citation_count": 3, "source_trace_ready_citation_count": 3},
        {"question_id": "q03", "question": "Unknown part", "category": "unknown_part", "grade": "BLOCKED", "runner_passed": False, "quality_status": "FAIL"},
    ]
    smoke = _write_smoke(tmp_path, records)
    review = build_smoke_review(
        smoke_test=smoke,
        output_dir=tmp_path / "out" / "review",
        min_smoke_questions=3,
        min_good_answers=1,
        min_good_or_partial_answers=2,
        max_bad_answers=0,
        require_quality_pass=True,
    )
    s = review["summary"]
    assert review["quality_status"] == "PASS"
    assert s["good_answer_count"] == 1
    assert s["partial_answer_count"] == 1
    assert s["blocked_answer_count"] == 1
    assert s["weak_answer_count"] == 2
    assert {r["category"] for r in review["weak_records"]} == {"evidence_support", "unknown_part"}


def test_review_fails_bad_threshold(tmp_path):
    smoke = _write_smoke(tmp_path, [
        {"question_id": "q01", "question": "bad", "category": "route_explanation", "grade": "BAD", "runner_passed": True, "quality_status": "PASS"}
    ])
    review = build_smoke_review(smoke_test=smoke, output_dir=tmp_path / "out", max_bad_answers=0)
    assert review["quality_status"] == "FAIL"
    assert any("bad_answer_count" in f for f in review["quality_gate"]["failures"])


def test_check_review_reuses_thresholds(tmp_path):
    smoke = _write_smoke(tmp_path, [
        {"question_id": "q01", "question": "good", "category": "figure_lookup", "grade": "GOOD", "runner_passed": True, "quality_status": "PASS"}
    ])
    review = build_smoke_review(smoke_test=smoke, output_dir=tmp_path / "review", min_good_answers=1, require_quality_pass=True)
    result = check_smoke_review(
        review=tmp_path / "review" / "trace_net_engineering_real_answer_smoke_review_v1.json",
        output=tmp_path / "checks" / "check.json",
        min_smoke_questions=1,
        min_good_answers=1,
        require_quality_pass=True,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "checks" / "check.json").exists()


def test_csv_files_are_written_to_nested_dirs(tmp_path):
    smoke = _write_smoke(tmp_path, [
        {"question_id": "q01", "question": "partial", "category": "summary_limit", "grade": "PARTIAL", "runner_passed": True, "quality_status": "PASS"}
    ])
    review = build_smoke_review(smoke_test=smoke, output_dir=tmp_path / "a" / "very" / "nested" / "out")
    paths = review["paths"]
    assert Path(paths["records_csv"]).exists()
    assert Path(paths["weak_records_csv"]).exists()


def test_recommendations_are_category_specific(tmp_path):
    smoke = _write_smoke(tmp_path, [
        {"question_id": "q01", "question": "Can v2 summaries alone prove it?", "category": "summary_limit", "grade": "PARTIAL", "runner_passed": True, "quality_status": "PASS"}
    ])
    review = build_smoke_review(smoke_test=smoke, output_dir=tmp_path / "out")
    assert "v2 summaries" in review["weak_records"][0]["recommendation"]
