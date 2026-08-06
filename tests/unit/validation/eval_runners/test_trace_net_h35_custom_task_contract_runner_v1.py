import json
from pathlib import Path

from tiff.trace_net_h35_custom_task_contract_runner_v1 import (
    build_contract_records,
    build_custom_task_contract_run,
    check_custom_task_contract_run,
    load_evidence_cards,
    select_evidence_for_task,
)


def _write(path: Path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def test_contracts_include_quiz_requirements():
    contracts = build_contract_records(5)
    quiz = [c for c in contracts if c["task_type"] == "quiz_generation"][0]
    assert quiz["contract"]["min_quiz_questions"] == 5
    assert quiz["contract"]["min_unique_evidence_labels"] >= 4
    assert "answer key" in quiz["contract"]["must_include"]


def test_load_and_select_evidence(tmp_path):
    visual = _write(tmp_path / "visual.json", {"records": [
        {"page": 315, "figure": "69", "part_number": "120-50645-005", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"},
        {"page": 327, "figure": "75", "part_number": "120-50645-011", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"},
    ]})
    ocr = _write(tmp_path / "ocr.json", {"records": [
        {"line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY", "linked_part_number": "120-50645-005", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"}
    ]})
    cards = load_evidence_cards(visual, ocr, None, None)
    assert len(cards) >= 3
    task = build_contract_records(1)[0]
    selected = select_evidence_for_task(cards, task, max_cards=3)
    assert any(c.part_number == "120-50645-005" for c in selected)


def test_artifact_run_passes_with_synthetic_evidence(tmp_path):
    visual = _write(tmp_path / "visual.json", {"records": [
        {"page": 315, "figure": "69", "part_number": "120-50645-005", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"},
        {"page": 327, "figure": "75", "part_number": "120-50645-011", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"},
        {"page": 382, "figure": "91", "part_number": "120-29068-003"},
    ]})
    ocr = _write(tmp_path / "ocr.json", {"records": [
        {"line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY", "linked_part_number": "120-50645-005", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"},
        {"line_text": "75 - | 120-50645-011 DOUBLE PASSENGER SEAT ASSY", "linked_part_number": "120-50645-011", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"},
    ]})
    table = _write(tmp_path / "table.json", {"records": [{"covered_part_number": "120-50645-005"}]})
    result = build_custom_task_contract_run(
        output_dir=tmp_path / "out",
        image_visual_evidence_pack=visual,
        raw_ocr_nomenclature_extractor=ocr,
        table_route_evidence_packager=table,
        llm_mode="artifact",
        max_questions=5,
        max_cards_per_question=6,
        min_good_answers=1,
        min_contract_pass=1,
        max_fallback_used=0,
        progress=False,
    )
    assert result["summary"]["fallback_used_count"] == 0
    assert result["summary"]["good_answer_count"] >= 1
    assert Path(tmp_path / "out" / "trace_net_h35_custom_task_contract_runner_v1.json").exists()


def test_check_detects_fallback(tmp_path):
    manifest = {
        "quality_status": "FAIL",
        "summary": {
            "good_answer_count": 5,
            "contract_pass_count": 5,
            "fallback_used_count": 1,
            "answer_permission_count": 0,
            "unsafe_finding_count": 0,
            "write_attempt_count": 0,
        },
        "records": [{"question_id": str(i)} for i in range(5)],
    }
    p = tmp_path / "m.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    result = check_custom_task_contract_run(p, max_fallback_used=0)
    assert result["quality_status"] == "FAIL"
    assert "fallback_used_count_above_max" in result["quality_failures"]
