import json
from pathlib import Path

from tiff.trace_net_engineering_query_planner_v1 import (
    build_engineering_query_planner,
    check_engineering_query_planner,
    classify_task,
    extract_entities,
)


def _index(tmp_path: Path) -> Path:
    p = tmp_path / "index.json"
    p.write_text(json.dumps({
        "status": "TRACE_NET_V2_SUMMARY_GUIDANCE_INDEX_BUILT",
        "quality_status": "PASS",
        "summary": {"summary_record_count": 3},
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
                "page_id": "t_p_120_1176_p000328",
                "page_number": 328,
                "summary_text": "Illustrated parts list page for Figure 75 showing double passenger seat assembly.",
                "detected_figures": ["75"],
                "detected_part_numbers": ["120-50645-011"],
                "detected_topics": ["illustrated parts list", "double passenger seat", "figure"],
                "manual_section_hint": "illustrated_parts_list",
                "guidance_only": True,
                "source_trace_ready": True,
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "summary_text": "This page appears to be a parts list or applicability section from a maintenance manual.",
                "detected_figures": [],
                "detected_part_numbers": [],
                "detected_topics": ["illustrated parts list", "maintenance manual"],
                "manual_section_hint": "maintenance_manual",
                "guidance_only": True,
                "source_trace_ready": True,
            },
        ],
    }), encoding="utf-8")
    return p


def test_extract_entities_and_visual_classification():
    entities = extract_entities("What does figure 69 show?")
    assert entities["figures"] == ["69"]
    assert classify_task("What does figure 69 show?", entities) == "visual_part_identification"


def test_build_visual_plan_uses_guidance_and_forbids_summary_proof(tmp_path):
    manifest = build_engineering_query_planner(
        question="What does figure 69 show?",
        v2_summary_guidance_index=_index(tmp_path),
        output_dir=tmp_path / "planner",
        min_planner_records=1,
        min_required_routes=1,
    )
    assert manifest["quality_status"] == "PASS"
    record = manifest["records"][0]
    assert record["task_type"] == "visual_part_identification"
    assert "image_or_diagram" in record["required_routes"]
    assert "raw_ocr_nomenclature" in record["required_routes"]
    assert record["can_answer_from_summaries_only"] is False
    assert any(g["page_number"] == 316 for g in record["guidance_pages"])
    assert "summary-only figure proof" in record["forbidden_claims"]


def test_exact_part_plan_routes_to_exact_part(tmp_path):
    manifest = build_engineering_query_planner(
        question="Find part number 120-50645-005 and cite the source.",
        v2_summary_guidance_index=_index(tmp_path),
        output_dir=tmp_path / "planner",
    )
    record = manifest["records"][0]
    assert record["task_type"] == "exact_part_lookup"
    assert record["entities"]["part_numbers"] == ["120-50645-005"]
    assert "exact_part_number" in record["required_routes"]
    assert record["answer_permission"] is False


def test_troubleshooting_plan_diagnostic_routes(tmp_path):
    manifest = build_engineering_query_planner(
        question="Why is the image route adapter failing while writing JSON?",
        v2_summary_guidance_index=_index(tmp_path),
        output_dir=tmp_path / "planner",
    )
    record = manifest["records"][0]
    assert record["task_type"] == "troubleshooting_question"
    assert "diagnostic_context" in record["required_routes"]
    assert "error log or artifact status" in record["proof_requirements"]


def test_check_planner_passes(tmp_path):
    manifest = build_engineering_query_planner(
        question="What does figure 69 show?",
        v2_summary_guidance_index=_index(tmp_path),
        output_dir=tmp_path / "planner",
    )
    result = check_engineering_query_planner(
        planner=tmp_path / "planner" / "trace_net_engineering_query_planner_v1.json",
        output=tmp_path / "check.json",
        require_quality_pass=True,
        min_planner_records=1,
        min_required_routes=1,
    )
    assert result["quality_status"] == "PASS"


def test_specific_figure_query_does_not_fill_with_generic_guidance(tmp_path):
    p = tmp_path / "index_generic.json"
    p.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"summary_record_count": 2},
        "records": [
            {
                "page_id": "t_p_120_1176_p000020",
                "page_number": 20,
                "summary_text": "This page describes the format of an illustrated parts list.",
                "detected_figures": [],
                "detected_part_numbers": [],
                "detected_topics": ["illustrated parts list", "table"],
                "manual_section_hint": "illustrated_parts_list",
                "guidance_only": True,
                "source_trace_ready": True,
            },
            {
                "page_id": "t_p_120_1176_p000021",
                "page_number": 21,
                "summary_text": "This page describes organization of parts within a maintenance manual.",
                "detected_figures": [],
                "detected_part_numbers": [],
                "detected_topics": ["illustrated parts list", "maintenance manual"],
                "manual_section_hint": "illustrated_parts_list",
                "guidance_only": True,
                "source_trace_ready": True,
            },
        ],
    }), encoding="utf-8")
    manifest = build_engineering_query_planner(
        question="What does figure 69 show?",
        v2_summary_guidance_index=p,
        output_dir=tmp_path / "planner",
        min_planner_records=1,
        min_required_routes=1,
    )
    record = manifest["records"][0]
    assert record["task_type"] == "visual_part_identification"
    assert record["guidance_pages"] == []
    assert manifest["summary"]["selected_guidance_page_count"] == 0


def test_specific_part_query_only_uses_exact_part_guidance(tmp_path):
    manifest = build_engineering_query_planner(
        question="Find part number 120-50645-005 and cite the source.",
        v2_summary_guidance_index=_index(tmp_path),
        output_dir=tmp_path / "planner",
    )
    record = manifest["records"][0]
    assert record["task_type"] == "exact_part_lookup"
    assert [g["page_number"] for g in record["guidance_pages"]] == [316]
    assert record["guidance_pages"][0]["guidance_reasons"][0] == "part_hint:120-50645-005"

def test_engineer_clarification_profile_extracts_engine_nha_doc_types():
    from tiff.trace_net_engineering_query_planner_v1 import build_plan_record

    record = build_plan_record(
        "please locate engine IPC/SB/CMM for the 2312M87G01-sealFace? "
        "NHA: 2330M... -Gearbox assy-access, 2330m...-Modeule Assy-Access gearbox "
        "engine: GEnx-2b67B",
        {"records": [], "summary": {"summary_record_count": 0}},
    )

    profile = record["engineer_clarification_profile"]
    clues = profile["extracted_engineer_clues"]

    assert "2312M87G01" in clues["part_number_candidates"]
    assert "2330M" in clues["partial_identifier_candidates"]
    assert "2330M" in clues["nha_candidates"]
    assert set(["IPC", "SB", "CMM"]).issubset(set(clues["requested_doc_types"]))
    assert any(x.upper().startswith("GENX-2B67B") for x in clues["engine_candidates"])
    assert "multiple_document_types_requested" in profile["risk_flags"]
    assert "partial_identifier_requires_clarification" in profile["risk_flags"]
    assert profile["answer_permission"] is False
    assert profile["source_truth_mutation_allowed"] is False


def test_engineer_clarification_profile_flags_eligibility_not_mention_only():
    from tiff.trace_net_engineering_query_planner_v1 import build_plan_record

    record = build_plan_record(
        "Looking for elegibility documents for PN DF250040-501 Paper towel dispenser. "
        "Likely used on a mixed fleet of A319-321 and boeing 737-787",
        {"records": [], "summary": {"summary_record_count": 0}},
    )

    profile = record["engineer_clarification_profile"]
    clues = profile["extracted_engineer_clues"]

    assert "DF250040-501" in clues["part_number_candidates"]
    assert "A319-321" not in clues["part_number_candidates"]
    assert profile["memory_layer"] == "working_memory"
    assert "procedural_memory" in profile["secondary_memory_layers"]
    assert "critic_memory" in profile["secondary_memory_layers"]
    assert profile["proof_role"] == "guidance_only"
    assert profile["can_be_used_as_proof"] is False
    assert "paper towel dispenser" in [x.lower() for x in clues["part_description_candidates"]]
    assert set(["A319", "A320", "A321"]).issubset(set(clues["fleet_candidates"]))
    assert "B737" in clues["fleet_candidates"]
    assert "B787" in clues["fleet_candidates"]
    assert "25" in clues["ata_candidates"]
    assert clues["eligibility_or_applicability_intent"] is True
    assert "eligibility_requires_authority_not_mention_only" in profile["risk_flags"]
    assert any("eligibility" in q.lower() for q in profile["clarifying_questions"])
    assert profile["can_answer_directly"] is False
    assert profile["can_prove_claims"] is False
