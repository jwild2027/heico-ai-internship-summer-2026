import json
from pathlib import Path

from tiff.trace_net_engineering_intent_answer_composer_v1 import (
    build_intent_answer_composer,
    check_intent_answer_composer,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _context_pack(tmp_path: Path, proof_context):
    path = tmp_path / "context" / "trace_net_engineering_answer_context_pack_v1.json"
    _write_json(path, {
        "quality_status": "PASS",
        "records": [{
            "question": "q",
            "guidance_context": [],
            "proof_context": proof_context,
            "answer_constraints": {
                "summary_guidance_policy": "v2 summaries may guide route planning and answer framing, but must not be used as proof"
            },
        }],
    })
    return path


def _runner(tmp_path: Path, question: str, task_type: str, context_pack: Path):
    path = tmp_path / "runner" / "trace_net_engineering_answer_runner_v1.json"
    _write_json(path, {
        "quality_status": "PASS",
        "answer_text": "Answer:\nGeneric old answer [V6] [O1].",
        "summary": {"question": question, "task_type": task_type},
        "stage_reports": {"engineering_answer_context_pack": str(context_pack)},
    })
    return path


def _proof():
    return [
        {
            "context_type": "visual_figure_link",
            "citation_label": "V6",
            "figure": "69",
            "page_number": 315,
            "part_number": "120-50645-005",
            "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
            "source_trace_ready": True,
        },
        {
            "context_type": "ocr_nomenclature",
            "citation_label": "O1",
            "figure": "69",
            "page_number": 316,
            "part_number": "120-50645-005",
            "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
            "line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF",
            "source_trace_ready": True,
        },
        {
            "context_type": "exact_part_evidence",
            "citation_label": "E1",
            "part_number": "120-50645-005",
            "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
            "source_trace_ready": True,
        },
        {
            "context_type": "visual_figure_link",
            "citation_label": "V7",
            "figure": "75",
            "page_number": 327,
            "part_number": "120-50645-011",
            "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
            "source_trace_ready": True,
        },
        {
            "context_type": "ocr_nomenclature",
            "citation_label": "O2",
            "figure": "75",
            "page_number": 328,
            "part_number": "120-50645-011",
            "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
            "source_trace_ready": True,
        },
    ]


def _build(tmp_path, question, task_type="visual_part_identification"):
    cp = _context_pack(tmp_path, _proof())
    runner = _runner(tmp_path, question, task_type, cp)
    return build_intent_answer_composer(
        runner=runner,
        output_dir=tmp_path / "out",
        min_answer_citations=1,
        min_source_trace_ready_citations=1,
        max_unsupported_claims=0,
        max_summary_used_as_proof=0,
        max_invalid_citations=0,
        max_llava_only_part_identity_claims=0,
        require_quality_pass=True,
    )


def test_troubleshooting_answer_explains_missing_nomenclature(tmp_path):
    result = _build(tmp_path, "Why was nomenclature missing from the visual route evidence?", "troubleshooting_question")
    answer = result["answer_text"].lower()
    assert result["quality_status"] == "PASS"
    assert result["summary"]["intent_answer_type"] == "troubleshooting_nomenclature"
    assert "missing" in answer
    assert "visual-link" in answer or "visual link" in answer
    assert "ocr-backed" in answer
    assert "recovered" in answer


def test_interchangeability_answer_leads_with_not_proven(tmp_path):
    result = _build(tmp_path, "Is 120-50645-005 interchangeable with 120-50645-011?", "comparison_question")
    answer = result["answer_text"].lower()
    assert result["quality_status"] == "PASS"
    assert result["summary"]["intent_answer_type"] == "unsupported_interchangeability"
    assert "cannot prove" in answer
    assert "120-50645-005" in answer
    assert "120-50645-011" in answer
    assert result["summary"]["unsupported_claim_count"] == 0


def test_installation_safety_answer_rejects_safety_claim(tmp_path):
    result = _build(tmp_path, "Does figure 69 prove installation safety?", "visual_part_identification")
    answer = result["answer_text"].lower()
    assert result["quality_status"] == "PASS"
    assert result["summary"]["intent_answer_type"] == "unsupported_installation_safety"
    assert answer.startswith("answer:\nno")
    assert "does not prove installation safety" in answer


def test_comparison_answer_mentions_both_figures(tmp_path):
    result = _build(tmp_path, "Compare figure 69 and figure 75.", "comparison_question")
    answer = result["answer_text"]
    assert result["quality_status"] == "PASS"
    assert result["summary"]["intent_answer_type"] == "comparison"
    assert "Figure 69" in answer
    assert "Figure 75" in answer
    assert "120-50645-005" in answer
    assert "120-50645-011" in answer


def test_check_intent_answer_composer_passes(tmp_path):
    result = _build(tmp_path, "What can TRACE-Net not prove about part number 120-50645-005?", "exact_part_lookup")
    composer_path = Path(result["paths"]["composer"])
    check = check_intent_answer_composer(
        composer=composer_path,
        output=tmp_path / "check" / "check.json",
        require_quality_pass=True,
        min_answer_citations=1,
        min_source_trace_ready_citations=1,
        max_unsupported_claims=0,
        max_summary_used_as_proof=0,
        max_invalid_citations=0,
        max_llava_only_part_identity_claims=0,
    )
    assert check["quality_status"] == "PASS"
