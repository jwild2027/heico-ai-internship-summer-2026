import json
from pathlib import Path

from tiff.trace_net_engineering_answer_context_pack_v1 import (
    build_engineering_answer_context_pack,
    check_engineering_answer_context_pack,
)


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _planner(tmp_path: Path, guidance_pages=None):
    return _write(tmp_path / "planner.json", {
        "quality_status": "PASS",
        "records": [{
            "question": "What does figure 69 show?",
            "task_type": "visual_part_identification",
            "engineering_intent": "identify visual figure using proof",
            "entities": {"figures": ["69"], "part_numbers": [], "items": [], "part_families": [], "topics": ["figure"]},
            "required_routes": ["image_or_diagram", "table_ocr_proof", "raw_ocr_nomenclature", "image_route_quality_gate"],
            "optional_routes": ["graph_leiden_neighbors"],
            "proof_requirements": ["visual figure/page evidence", "OCR/table nomenclature evidence"],
            "forbidden_claims": ["summary-only figure proof", "interchangeability"],
            "guidance_pages": guidance_pages or [],
            "summary_guidance_policy": "v2 summaries may guide route planning and answer framing, but must not be used as proof",
            "answer_style": "engineering_brain",
        }],
    })


def _image_pack(tmp_path: Path):
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


def _ocr_pack(tmp_path: Path):
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


def test_builds_context_pack_with_guidance_separate_from_proof(tmp_path):
    planner = _planner(tmp_path, guidance_pages=[{
        "page_id": "t_p_120_1176_p000018",
        "page_number": 18,
        "summary_text": "Generic figure page guidance",
        "detected_figures": ["2"],
        "source_trace_ready": True,
    }])
    result = build_engineering_answer_context_pack(
        engineering_query_planner=planner,
        image_visual_evidence_pack=_image_pack(tmp_path),
        raw_ocr_nomenclature_extractor=_ocr_pack(tmp_path),
        output_dir=tmp_path / "out",
        min_proof_context=2,
        min_source_trace_ready=2,
    )
    assert result["quality_status"] == "PASS"
    s = result["summary"]
    assert s["guidance_context_count"] == 1
    assert s["proof_context_count"] >= 2
    assert s["summary_used_as_proof_count"] == 0
    record = result["records"][0]
    assert record["guidance_context"][0]["guidance_only"] is True
    assert all(p["proof_eligible"] for p in record["proof_context"])


def test_figure_69_gets_visual_and_ocr_proof(tmp_path):
    result = build_engineering_answer_context_pack(
        engineering_query_planner=_planner(tmp_path),
        image_visual_evidence_pack=_image_pack(tmp_path),
        raw_ocr_nomenclature_extractor=_ocr_pack(tmp_path),
        output_dir=tmp_path / "out",
        min_proof_context=2,
        min_source_trace_ready=2,
    )
    proof = result["records"][0]["proof_context"]
    types = {p["context_type"] for p in proof}
    assert "visual_figure_link" in types
    assert "ocr_nomenclature" in types
    assert any(p.get("nomenclature") == "DOUBLE PASSENGER SEAT ASSY" for p in proof)


def test_fails_when_proof_context_missing(tmp_path):
    result = build_engineering_answer_context_pack(
        engineering_query_planner=_planner(tmp_path),
        output_dir=tmp_path / "out",
        min_proof_context=1,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "FAIL"
    assert result["summary"]["proof_context_count"] == 0


def test_check_context_pack_passes(tmp_path):
    result = build_engineering_answer_context_pack(
        engineering_query_planner=_planner(tmp_path),
        image_visual_evidence_pack=_image_pack(tmp_path),
        raw_ocr_nomenclature_extractor=_ocr_pack(tmp_path),
        output_dir=tmp_path / "out",
        min_proof_context=2,
        min_source_trace_ready=2,
    )
    check = check_engineering_answer_context_pack(
        context_pack=tmp_path / "out" / "trace_net_engineering_answer_context_pack_v1.json",
        output=tmp_path / "check.json",
        require_quality_pass=True,
        min_proof_context=2,
        min_source_trace_ready=2,
    )
    assert check["quality_status"] == "PASS"


def test_answer_constraints_forbid_summary_only_proof(tmp_path):
    result = build_engineering_answer_context_pack(
        engineering_query_planner=_planner(tmp_path),
        image_visual_evidence_pack=_image_pack(tmp_path),
        raw_ocr_nomenclature_extractor=_ocr_pack(tmp_path),
        output_dir=tmp_path / "out",
        min_proof_context=2,
        min_source_trace_ready=2,
    )
    constraints = result["records"][0]["answer_constraints"]
    assert any("summary" in x.lower() for x in constraints["may_not_claim"])
    assert "engineering_brain" == constraints["answer_style"]


def _exact_part_planner(tmp_path: Path):
    return _write(tmp_path / "exact_planner.json", {
        "quality_status": "PASS",
        "records": [{
            "question": "Find part number 120-50645-005 and cite the source.",
            "task_type": "exact_part_lookup",
            "engineering_intent": "identify or locate an exact part number using source-traced evidence",
            "entities": {"figures": [], "part_numbers": ["120-50645-005"], "items": [], "part_families": [], "topics": []},
            "required_routes": ["exact_part_number", "table_ocr_proof", "graph_leiden_neighbors", "answer_quality_gate"],
            "optional_routes": [],
            "proof_requirements": ["source-trace-ready citation"],
            "forbidden_claims": ["interchangeability", "effectivity"],
            "guidance_pages": [],
            "summary_guidance_policy": "v2 summaries may guide route planning and answer framing, but must not be used as proof",
            "answer_style": "engineering_brain",
        }],
    })


def _exact_table_pack(tmp_path: Path):
    return _write(tmp_path / "exact_table.json", {
        "quality_status": "PASS",
        "records": [{
            "page_id": "t_p_120_1176_p000316",
            "page_number": 316,
            "table_id": "table_316",
            "row_index": 4,
            "field_name": "ipl_part_number",
            "normalized_value": "120-50645-005",
            "source_trace_ready": True,
            "citation_ready": True,
        }]
    })


def test_exact_part_lookup_builds_exact_part_proof_context(tmp_path):
    result = build_engineering_answer_context_pack(
        engineering_query_planner=_exact_part_planner(tmp_path),
        raw_ocr_nomenclature_extractor=_ocr_pack(tmp_path),
        table_route_evidence_packager=_exact_table_pack(tmp_path),
        table_exact_search_adapter=_exact_table_pack(tmp_path),
        output_dir=tmp_path / "out_exact",
        min_proof_context=2,
        min_source_trace_ready=2,
    )
    assert result["quality_status"] == "PASS"
    proof = result["records"][0]["proof_context"]
    types = {p["context_type"] for p in proof}
    assert "exact_part_evidence" in types
    assert "ocr_nomenclature" in types
    assert result["summary"]["exact_part_context_count"] >= 1
    assert all(p.get("guidance_only") is False for p in proof)
