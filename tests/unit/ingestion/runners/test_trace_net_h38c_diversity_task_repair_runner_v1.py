import json
from pathlib import Path

from tiff.trace_net_h38c_diversity_task_repair_runner_v1 import (
    _count_quiz_questions,
    run_repair_runner,
    unsafe_forbidden_claims,
    validate_answer,
)


def _planner(tmp_path: Path) -> Path:
    cards = [
        {"evidence_label": "V1", "route": "visual", "page": "1", "figure": "1", "part_number": "111-11111-111", "nomenclature": "AAA", "preview": "visual aaa"},
        {"evidence_label": "O1", "route": "ocr", "page": "2", "figure": "2", "part_number": "222-22222-222", "nomenclature": "BBB", "preview": "ocr bbb"},
        {"evidence_label": "T1", "route": "table", "page": "3", "figure": "3", "part_number": "333-33333-333", "nomenclature": "CCC", "preview": "table ccc"},
        {"evidence_label": "E1", "route": "exact", "page": "4", "figure": "4", "part_number": "444-44444-444", "nomenclature": "DDD", "preview": "exact ddd"},
        {"evidence_label": "O2", "route": "ocr", "page": "5", "figure": "5", "part_number": "555-55555-555", "nomenclature": "EEE", "preview": "ocr eee"},
    ]
    records = []
    for i, task in enumerate(["part_lookup", "representative_page_explanation", "multi_page_summary", "nomenclature_lookup", "quiz_generation"], 1):
        records.append({
            "question_id": f"q{i}",
            "task_type": task,
            "query_text": f"question {i}",
            "selected_cards": cards,
            "selected_evidence_labels": [c["evidence_label"] for c in cards],
            "selected_routes": sorted({c["route"] for c in cards}),
            "selected_pages": sorted({c["page"] for c in cards}),
            "selected_part_numbers": sorted({c["part_number"] for c in cards}),
            "selected_figures": sorted({c["figure"] for c in cards}),
        })
    p = tmp_path / "planner.json"
    p.write_text(json.dumps({"quality_status": "PASS", "plan_records": records}), encoding="utf-8")
    return p


def test_h38c_negation_catches_nor_can_confirm():
    answer = "It does not provide evidence regarding replacement, nor can it confirm its installation safety, effectivity, or interchangeability with other parts."
    assert unsafe_forbidden_claims(answer) == []


def test_h38c_counts_inline_quiz_questions():
    answer = "Quiz 1. First? 2. Second? 3. Third? 4. Limits? 5. Fifth? Answer Key: 1. A [V1]"
    assert _count_quiz_questions(answer) == 5


def test_h38c_validate_quiz_metadata_fails():
    rec = {"task_type": "quiz_generation", "selected_cards": [{"evidence_label": "V1", "route": "visual"}]}
    answer = "1. What is LLaVA? 2. A? 3. B? 4. C? 5. D? Answer Key: 1. Visual authority model [V1]"
    v = validate_answer(rec, answer, False, 1500)
    assert "metadata_or_internal_quiz_item" in v["findings"]


def test_h38c_artifact_runner_passes(tmp_path):
    result = run_repair_runner(
        diversity_planner=_planner(tmp_path),
        output_dir=tmp_path / "out",
        llm_mode="artifact",
        min_good_answers=4,
        min_contract_pass=4,
        progress=False,
    )
    assert result["summary"]["good_answer_count"] >= 4
    assert result["summary"]["contract_pass_count"] >= 4
    assert result["summary"]["unsupported_claim_count"] == 0
