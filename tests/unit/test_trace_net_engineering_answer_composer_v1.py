import json
from pathlib import Path

from tiff.trace_net_engineering_answer_composer_v1 import (
    build_engineering_answer_composer,
    check_engineering_answer_composer,
    compose_engineering_answer,
    quality_gate_answer,
)


def _context_pack(tmp_path: Path) -> Path:
    data = {
        "status": "TRACE_NET_ENGINEERING_ANSWER_CONTEXT_PACK_BUILT",
        "quality_status": "PASS",
        "records": [
            {
                "question": "What does figure 69 show?",
                "task_type": "visual_part_identification",
                "guidance_context": [],
                "proof_context": [
                    {
                        "context_type": "visual_figure_link",
                        "citation_label": "V6",
                        "page_number": 315,
                        "figure": "69",
                        "part_number": "120-50645-005",
                        "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                        "nomenclature_confidence": "HIGH",
                        "source_trace_ready": True,
                        "guidance_only": False,
                        "proof_eligible": True,
                    },
                    {
                        "context_type": "ocr_nomenclature",
                        "citation_label": "O1",
                        "page_number": 316,
                        "figure": "69",
                        "part_number": "120-50645-005",
                        "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                        "nomenclature_confidence": "HIGH",
                        "line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF",
                        "source_trace_ready": True,
                        "guidance_only": False,
                        "proof_eligible": True,
                    },
                    {
                        "context_type": "table_ocr_proof",
                        "citation_label": "T1",
                        "part_number": "120-50645-005",
                        "source_trace_ready": True,
                        "guidance_only": False,
                        "proof_eligible": True,
                    },
                ],
                "answer_constraints": {
                    "answer_style": "engineering_brain",
                    "may_not_claim": ["interchangeability", "effectivity", "installation safety"],
                    "summary_guidance_policy": "v2 summaries may guide route planning and answer framing, but must not be used as proof",
                },
            }
        ],
    }
    path = tmp_path / "context_pack.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_compose_uses_visual_and_ocr_nomenclature(tmp_path):
    pack = json.loads(_context_pack(tmp_path).read_text())
    record = pack["records"][0]
    answer = compose_engineering_answer(record)
    text = answer["answer_text"]
    assert "Figure 69" in text
    assert "120-50645-005" in text
    assert "DOUBLE PASSENGER SEAT ASSY" in text
    assert "[V6]" in text
    assert "[O1]" in text
    assert answer["summary_used_as_proof_count"] == 0


def test_quality_gate_passes_clean_engineering_answer(tmp_path):
    pack = json.loads(_context_pack(tmp_path).read_text())
    record = pack["records"][0]
    answer = compose_engineering_answer(record)
    gate = quality_gate_answer(answer, record, min_answer_citations=2, min_source_trace_ready_citations=2)
    assert gate["quality_status"] == "PASS"
    assert gate["unsupported_claim_count"] == 0
    assert gate["llava_only_part_identity_claim_count"] == 0


def test_build_writes_outputs_and_passes(tmp_path):
    context = _context_pack(tmp_path)
    result = build_engineering_answer_composer(
        context_pack=context,
        output_dir=tmp_path / "composer",
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
        max_unsupported_claims=0,
        max_summary_used_as_proof=0,
        max_invalid_citations=0,
        max_llava_only_part_identity_claims=0,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "composer" / "trace_net_engineering_answer_composer_v1.json").exists()
    assert result["summary"]["source_trace_ready_citation_count"] >= 2


def test_check_composer_passes(tmp_path):
    context = _context_pack(tmp_path)
    build_engineering_answer_composer(
        context_pack=context,
        output_dir=tmp_path / "composer",
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
    )
    checked = check_engineering_answer_composer(
        composer=tmp_path / "composer" / "trace_net_engineering_answer_composer_v1.json",
        output=tmp_path / "check.json",
        require_quality_pass=True,
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
    )
    assert checked["quality_status"] == "PASS"


def test_quality_gate_rejects_unsupported_positive_claim(tmp_path):
    pack = json.loads(_context_pack(tmp_path).read_text())
    record = pack["records"][0]
    answer = compose_engineering_answer(record)
    answer["answer_text"] += "\nThis proves interchangeability."
    gate = quality_gate_answer(answer, record)
    assert gate["quality_status"] == "FAIL"
    assert gate["unsupported_claim_count"] >= 1


def test_exact_part_lookup_composer_uses_exact_and_ocr_context(tmp_path):
    data = {
        "quality_status": "PASS",
        "records": [{
            "question": "Find part number 120-50645-005 and cite the source.",
            "task_type": "exact_part_lookup",
            "guidance_context": [],
            "proof_context": [
                {
                    "context_type": "exact_part_evidence",
                    "citation_label": "E1",
                    "page_number": 316,
                    "field_name": "ipl_part_number",
                    "value": "120-50645-005",
                    "part_number": "120-50645-005",
                    "source_trace_ready": True,
                    "guidance_only": False,
                    "proof_eligible": True,
                },
                {
                    "context_type": "ocr_nomenclature",
                    "citation_label": "O1",
                    "page_number": 316,
                    "part_number": "120-50645-005",
                    "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                    "nomenclature_confidence": "HIGH",
                    "line_text": "120-50645-005 DOUBLE PASSENGER SEAT ASSY",
                    "source_trace_ready": True,
                    "guidance_only": False,
                    "proof_eligible": True,
                },
            ],
            "answer_constraints": {"answer_style": "engineering_brain"},
        }],
    }
    path = tmp_path / "exact_context.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = build_engineering_answer_composer(
        context_pack=path,
        output_dir=tmp_path / "exact_composer",
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
    )
    assert result["quality_status"] == "PASS"
    text = result["answer_text"]
    assert "Part number 120-50645-005 is present" in text
    assert "DOUBLE PASSENGER SEAT ASSY" in text
    assert "[E1]" in text and "[O1]" in text
