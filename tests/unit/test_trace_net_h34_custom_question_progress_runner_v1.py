import json
from pathlib import Path

from tiff.trace_net_h34_custom_question_progress_runner_v1 import (
    collect_evidence_cards,
    select_cards,
    build_custom_question_run,
)


def _write(path: Path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def test_collect_evidence_cards_extracts_routes(tmp_path):
    visual = _write(tmp_path / "visual.json", {"records": [{"figure_id": "69", "part_number": "120-50645-005", "page_number": 315, "text": "Figure 69 links to part 120-50645-005"}]})
    ocr = _write(tmp_path / "ocr.json", {"records": [{"line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY", "page_number": 316}]})
    cards = collect_evidence_cards({"visual": visual, "ocr": ocr})
    assert len(cards) >= 2
    assert {c.route for c in cards} == {"visual", "ocr"}
    assert any(c.part_number == "120-50645-005" for c in cards)


def test_select_cards_prefers_query_terms(tmp_path):
    exact = _write(tmp_path / "exact.json", {"records": [
        {"covered_part_number": "120-50645-005", "text": "covered_part_number 120-50645-005"},
        {"covered_part_number": "999-00000-000", "text": "covered_part_number 999-00000-000"},
    ]})
    cards = collect_evidence_cards({"exact": exact})
    selected = select_cards(cards, {"query_terms": ["120-50645-005"], "task_type": "exact_part_lookup"}, max_cards=1)
    assert selected[0].part_number == "120-50645-005"


def test_artifact_run_produces_progress_manifest(tmp_path):
    exact = _write(tmp_path / "exact.json", {"records": [{"covered_part_number": "120-50645-005", "text": "covered_part_number 120-50645-005"}]})
    visual = _write(tmp_path / "visual.json", {"records": [{"figure_id": "69", "part_number": "120-50645-005", "text": "Figure 69 links to part 120-50645-005"}]})
    manifest = build_custom_question_run(
        output_dir=tmp_path / "out",
        table_exact_search_adapter=exact,
        image_visual_evidence_pack=visual,
        llm_mode="artifact",
        max_questions=2,
        progress=False,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["question_count"] == 2
    assert manifest["summary"]["write_attempt_count"] == 0


def test_quiz_artifact_answer_is_not_same_as_lookup(tmp_path):
    exact = _write(tmp_path / "exact.json", {"records": [{"covered_part_number": "120-50645-005", "text": "covered_part_number 120-50645-005"}]})
    manifest = build_custom_question_run(
        output_dir=tmp_path / "out",
        table_exact_search_adapter=exact,
        llm_mode="artifact",
        max_questions=5,
        progress=False,
    )
    answers = [r["answer_preview"] for r in manifest["records"]]
    assert "quiz" in answers[-1].lower() or "question" in answers[-1].lower()
    assert answers[0] != answers[-1]
