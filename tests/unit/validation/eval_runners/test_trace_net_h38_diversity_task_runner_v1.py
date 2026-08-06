import json
from pathlib import Path

from tiff.trace_net_h38_diversity_task_runner_v1 import (
    build_prompt,
    run_diversity_task_runner,
    check_diversity_task_run,
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


def test_build_prompt_contains_diversity_rules(tmp_path):
    data = json.loads(_planner(tmp_path).read_text(encoding="utf-8"))
    prompt = build_prompt(data["plan_records"][-1])
    assert "exactly 5 technician quiz questions" in prompt
    assert "[V1]" in prompt
    assert "source_extractor_quality_pass" in prompt


def test_validate_quiz_rejects_metadata_item(tmp_path):
    data = json.loads(_planner(tmp_path).read_text(encoding="utf-8"))
    answer = "1. What is source_extractor_quality_pass?\\nAnswer Key\\n1. source_extractor_quality_pass [V1]"
    v = validate_answer(data["plan_records"][-1], answer, False, 1500)
    assert "metadata_quiz_item" in v["findings"]


def test_artifact_run_passes(tmp_path):
    result = run_diversity_task_runner(
        diversity_planner=_planner(tmp_path),
        output_dir=tmp_path / "out",
        llm_mode="artifact",
        min_good_answers=4,
        min_contract_pass=4,
        max_fallback_used=0,
        progress=False,
    )
    assert result["summary"]["fallback_used_count"] == 0
    assert result["summary"]["good_answer_count"] >= 4
    assert (tmp_path / "out" / "trace_net_h38_diversity_task_runner_v1.json").exists()


def test_check_run(tmp_path):
    result = run_diversity_task_runner(
        diversity_planner=_planner(tmp_path),
        output_dir=tmp_path / "out",
        llm_mode="artifact",
        min_good_answers=4,
        min_contract_pass=4,
        progress=False,
    )
    check = check_diversity_task_run(
        tmp_path / "out" / "trace_net_h38_diversity_task_runner_v1.json",
        min_records=5,
        min_good_answers=4,
        min_contract_pass=4,
        require_quality_pass=False,
    )
    assert check["quality_status"] == "PASS"
