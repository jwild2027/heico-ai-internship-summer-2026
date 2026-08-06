import json
from pathlib import Path

from tiff.trace_net_h37_diversity_evidence_planner_v1 import (
    build_diversity_evidence_planner,
    check_diversity_evidence_planner,
    collect_evidence_cards,
    select_diverse_cards,
)


def _write(path: Path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_collect_evidence_cards_extracts_fields(tmp_path):
    visual = _write(tmp_path / "visual.json", {
        "records": [
            {"citation_label": "V1", "page_id": "p000001", "figure": "1", "linked_part_number": "111-11111-111", "nomenclature": "AAA"},
        ]
    })
    ocr = _write(tmp_path / "ocr.json", {
        "records": [
            {"citation_label": "O1", "ocr_page_id": "p000002", "line_text": "2 - | 222-22222-222 BBB .... REF"},
        ]
    })
    cards = collect_evidence_cards(image_visual_evidence_pack=visual, raw_ocr_nomenclature_extractor=ocr)
    assert len(cards) >= 2
    assert {c["route"] for c in cards} >= {"visual", "ocr"}
    assert any(c["part_number"] == "222-22222-222" for c in cards)


def test_select_diverse_cards_limits_same_nomenclature():
    cards = []
    for i in range(6):
        cards.append({"evidence_label": f"V{i}", "route": "visual", "page": str(i), "figure": str(i), "part_number": f"120-00000-00{i}", "nomenclature": "SAME", "quality_score": 10})
    cards.append({"evidence_label": "O1", "route": "ocr", "page": "10", "figure": "10", "part_number": "999-99999-999", "nomenclature": "DIFFERENT", "quality_score": 7})
    task = {"task_type": "quiz_generation", "query_text": "quiz", "min_unique_routes": 2, "min_unique_pages": 3, "min_unique_part_numbers": 3, "min_unique_figures": 3, "max_same_nomenclature": 2}
    selected = select_diverse_cards(cards, task, max_cards=5)
    same_count = sum(1 for c in selected if c.get("nomenclature") == "SAME")
    assert same_count <= 2
    assert len({c["route"] for c in selected}) >= 2


def test_build_planner_passes_with_diverse_fixture(tmp_path):
    visual = _write(tmp_path / "visual.json", {"records": [
        {"citation_label": "V1", "page": "1", "figure": "1", "linked_part_number": "111-11111-111", "nomenclature": "AAA"},
        {"citation_label": "V2", "page": "2", "figure": "2", "linked_part_number": "222-22222-222", "nomenclature": "BBB"},
        {"citation_label": "V3", "page": "3", "figure": "3", "linked_part_number": "333-33333-333", "nomenclature": "CCC"},
    ]})
    ocr = _write(tmp_path / "ocr.json", {"records": [
        {"citation_label": "O1", "page": "1", "line_text": "1 | 111-11111-111 AAA .... REF"},
        {"citation_label": "O2", "page": "2", "line_text": "2 | 222-22222-222 BBB .... REF"},
        {"citation_label": "O3", "page": "3", "line_text": "3 | 333-33333-333 CCC .... REF"},
    ]})
    contract = _write(tmp_path / "contract.json", {"quality_status": "PASS", "records": [
        {"question_id": "q1", "task_type": "part_lookup", "question": "Find 111-11111-111"},
        {"question_id": "q2", "task_type": "representative_page_explanation", "question": "Pick page"},
        {"question_id": "q3", "task_type": "multi_page_summary", "question": "Summarize pages"},
        {"question_id": "q4", "task_type": "nomenclature_lookup", "question": "Lookup nomenclature"},
        {"question_id": "q5", "task_type": "quiz_generation", "question": "Make quiz"},
    ]})
    result = build_diversity_evidence_planner(
        contract_run=contract,
        image_visual_evidence_pack=visual,
        raw_ocr_nomenclature_extractor=ocr,
        output_dir=tmp_path / "out",
        min_plan_records=5,
        min_diversity_pass=4,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["diversity_pass_count"] >= 4
    assert (tmp_path / "out" / "trace_net_h37_diversity_overlay_map_v1.json").exists()


def test_check_planner(tmp_path):
    manifest = {
        "quality_status": "PASS",
        "summary": {
            "plan_record_count": 5,
            "diversity_pass_count": 5,
            "review_count": 0,
            "answer_permission_count": 0,
            "unsafe_finding_count": 0,
            "write_attempt_count": 0,
        }
    }
    p = _write(tmp_path / "planner.json", manifest)
    result = check_diversity_evidence_planner(p, min_plan_records=5, min_diversity_pass=5, require_quality_pass=True, require_no_answer_permission=True)
    assert result["quality_status"] == "PASS"
