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
