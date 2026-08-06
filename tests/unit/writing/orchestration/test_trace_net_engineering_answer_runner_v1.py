import json
from pathlib import Path

from tiff.trace_net_engineering_answer_runner_v1 import (
    build_engineering_answer_runner,
    check_engineering_answer_runner,
)


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _index(tmp_path: Path) -> Path:
    return _write(tmp_path / "v2_index.json", {
        "status": "TRACE_NET_V2_SUMMARY_GUIDANCE_INDEX_BUILT",
        "quality_status": "PASS",
        "summary": {"summary_record_count": 2},
        "records": [
            {
                "page_id": "t_p_120_1176_p000316",
                "page_number": 316,
                "summary_text": "Illustrated parts list page for Figure 69 showing double passenger seat assembly.",
                "detected_figures": ["69"],
                "detected_part_numbers": ["120-50645-005"],
                "detected_topics": ["illustrated parts list", "double passenger seat", "figure"],
                "manual_section_hint": "illustrated_parts_list",
                "guidance_only": True,
                "source_trace_ready": True,
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "summary_text": "Generic IPL applicability page.",
                "detected_figures": [],
                "detected_part_numbers": [],
                "detected_topics": ["illustrated parts list"],
                "manual_section_hint": "illustrated_parts_list",
                "guidance_only": True,
                "source_trace_ready": True,
            },
        ],
    })


def _image_pack(tmp_path: Path) -> Path:
    return _write(tmp_path / "image_pack.json", {
        "quality_status": "PASS",
        "records": [{
            "citation_label": "V6",
            "linked": True,
            "page_id": "t_p_120_1176_p000315",
            "page_number": 315,
            "figure": "69",
            "callout": "",
            "linked_part_number": "120-50645-005",
            "linked_description": "DOUBLE PASSENGER SEAT ASSY",
            "linked_nomenclature": "DOUBLE PASSENGER SEAT ASSY",
            "linked_nomenclature_confidence": "HIGH",
            "proof_source": "trusted_ocr_table_figure_item_evidence",
            "source_trace_ready": True,
            "citation_ready": True,
            "limitations": ["does not prove interchangeability"],
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }],
    })


def _ocr_pack(tmp_path: Path) -> Path:
    return _write(tmp_path / "ocr_nom.json", {
        "quality_status": "PASS",
        "records": [{
            "source_visual_citation_label": "V6",
            "figure": "69",
            "linked_part_number": "120-50645-005",
            "selected_nomenclature": "DOUBLE PASSENGER SEAT ASSY",
            "selected_nomenclature_confidence": "HIGH",
            "selected_ocr_page_number": 316,
            "selected_ocr_page_id": "t_p_120_1176_p000316",
            "selected_extraction_rule": "same_line_after_part",
            "selected_line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF",
            "source_trace_ready": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }],
    })


def test_runner_chains_planner_context_pack_and_composer(tmp_path):
    result = build_engineering_answer_runner(
        question="What does figure 69 show?",
        v2_summary_guidance_index=_index(tmp_path),
        image_visual_evidence_pack=_image_pack(tmp_path),
        raw_ocr_nomenclature_extractor=_ocr_pack(tmp_path),
        output_dir=tmp_path / "runner",
        min_proof_context=2,
        min_source_trace_ready=2,
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
        require_quality_pass=True,
        require_engineering_answer_ready=True,
    )
    assert result["quality_status"] == "PASS"
    s = result["summary"]
    assert s["stage_pass_count"] == 3
    assert s["proof_context_count"] >= 2
    assert s["source_trace_ready_citation_count"] >= 2
    assert s["summary_used_as_proof_count"] == 0
    assert "DOUBLE PASSENGER SEAT ASSY" in result["answer_text"]
    assert (tmp_path / "runner" / "planner" / "trace_net_engineering_query_planner_v1.json").exists()
    assert (tmp_path / "runner" / "context_pack" / "trace_net_engineering_answer_context_pack_v1.json").exists()
    assert (tmp_path / "runner" / "composer" / "trace_net_engineering_answer_composer_v1.json").exists()


def test_check_runner_passes(tmp_path):
    build_engineering_answer_runner(
        question="What does figure 69 show?",
        v2_summary_guidance_index=_index(tmp_path),
        image_visual_evidence_pack=_image_pack(tmp_path),
        raw_ocr_nomenclature_extractor=_ocr_pack(tmp_path),
        output_dir=tmp_path / "runner",
        min_proof_context=2,
        min_source_trace_ready=2,
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
    )
    checked = check_engineering_answer_runner(
        runner=tmp_path / "runner" / "trace_net_engineering_answer_runner_v1.json",
        output=tmp_path / "check.json",
        require_quality_pass=True,
        require_engineering_answer_ready=True,
        min_stage_passes=3,
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
    )
    assert checked["quality_status"] == "PASS"


def test_runner_fails_when_proof_artifacts_missing(tmp_path):
    result = build_engineering_answer_runner(
        question="What does figure 69 show?",
        v2_summary_guidance_index=_index(tmp_path),
        output_dir=tmp_path / "runner",
        min_proof_context=1,
        min_source_trace_ready=1,
        min_answer_citations=1,
        min_source_trace_ready_citations=1,
        require_quality_pass=True,
        require_engineering_answer_ready=True,
    )
    assert result["quality_status"] == "FAIL"
    assert result["summary"]["stage_quality_statuses"]["engineering_query_planner"] == "PASS"
    assert result["summary"]["stage_quality_statuses"]["engineering_answer_context_pack"] == "FAIL"


def test_runner_preserves_safety_contract(tmp_path):
    result = build_engineering_answer_runner(
        question="What does figure 69 show?",
        v2_summary_guidance_index=_index(tmp_path),
        image_visual_evidence_pack=_image_pack(tmp_path),
        raw_ocr_nomenclature_extractor=_ocr_pack(tmp_path),
        output_dir=tmp_path / "runner",
        min_proof_context=2,
        min_source_trace_ready=2,
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
    )
    s = result["summary"]
    assert s["answer_permission_count"] == 0
    assert s["source_truth_mutation_allowed_count"] == 0
    assert s["write_attempt_count"] == 0
    assert result["safety_contract"]["answer_permission"] is False
