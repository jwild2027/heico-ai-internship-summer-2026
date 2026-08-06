
from tiff.trace_net_h38_diversity_task_runner_v1 import (
    artifact_answer,
    run_diversity_task_runner,
    unsafe_forbidden_claims,
)


def test_h38b_negated_installation_safety_is_safe():
    answer = "This does not prove interchangeability, effectivity, fit, replacement approval, or installation safety."
    assert unsafe_forbidden_claims(answer) == []


def test_h38b_negated_quiz_boundary_is_safe():
    answer = "No. TRACE-Net cannot prove interchangeability, fit, or installation safety from the selected evidence [V1]."
    assert unsafe_forbidden_claims(answer) == []


def test_h38b_artifact_quiz_has_cannot_prove_boundary():
    rec = {
        "task_type": "quiz_generation",
        "selected_cards": [
            {"evidence_label": "V1", "route": "visual", "page": "1", "figure": "1", "part_number": "111-11111-111", "nomenclature": "AAA"},
            {"evidence_label": "O1", "route": "ocr", "page": "2", "figure": "2", "part_number": "222-22222-222", "nomenclature": "BBB"},
            {"evidence_label": "T1", "route": "table", "page": "3", "figure": "3", "part_number": "333-33333-333", "nomenclature": "CCC"},
            {"evidence_label": "E1", "route": "exact", "page": "4", "figure": "4", "part_number": "444-44444-444", "nomenclature": "DDD"},
            {"evidence_label": "O2", "route": "ocr", "page": "5", "figure": "5", "part_number": "555-55555-555", "nomenclature": "EEE"},
        ],
    }
    ans = artifact_answer(rec)
    assert "cannot prove interchangeability" in ans
    assert unsafe_forbidden_claims(ans) == []


def test_h38b_artifact_runner_now_passes_fixture(tmp_path):
    import json

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
    planner = tmp_path / "planner.json"
    planner.write_text(json.dumps({"quality_status": "PASS", "plan_records": records}), encoding="utf-8")

    result = run_diversity_task_runner(
        diversity_planner=planner,
        output_dir=tmp_path / "out",
        llm_mode="artifact",
        min_good_answers=4,
        min_contract_pass=4,
        max_fallback_used=0,
        progress=False,
    )
    assert result["summary"]["good_answer_count"] >= 4
    assert result["summary"]["contract_pass_count"] >= 4
    assert result["summary"]["unsupported_claim_count"] == 0
