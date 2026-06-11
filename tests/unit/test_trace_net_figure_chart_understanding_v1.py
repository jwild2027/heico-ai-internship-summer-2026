from __future__ import annotations

import json
from pathlib import Path

from tiff import trace_net_figure_chart_understanding_v1 as mod


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def sample_page_registry() -> dict:
    return {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000048",
                "page_number": 48,
                "page_traits": ["source_trace_present", "figure_chart_or_diagram_signal", "part_or_catalog_signal"],
                "detected_elements": [
                    {"element_type": "figure_chart_or_diagram", "status": "candidate"},
                    {"element_type": "part_catalog", "status": "available"},
                ],
                "recommended_extraction_routes": ["visual_region_route", "visual_catalog_compare_route"],
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_number": 2,
                "page_traits": ["source_trace_present", "ocr_text_present"],
                "detected_elements": [{"element_type": "source_text"}],
                "recommended_extraction_routes": ["source_text_route"],
            },
        ],
    }


def test_extract_visual_refs_finds_figures_parts_and_items() -> None:
    refs = mod.extract_visual_refs("Figure 97 sheet 2 item 14 part 120-46137-001 callout 5")
    assert "Figure 97 sheet 2" in refs["figure_refs"][0]
    assert "item 14" in [x.lower() for x in refs["item_refs"]]
    assert "120-46137-001" in refs["part_numbers"]
    assert "5" in refs["callout_labels"]


def test_classify_visual_type_parts_diagram() -> None:
    visual_type = mod.classify_visual_type("figure 97 double passenger seat structure parts list 120-46137-001")
    assert visual_type == "parts_diagram_or_illustrated_parts_list"


def test_build_report_keeps_visual_records_retrieval_only(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    image_audit = tmp_path / "image.json"
    visual = tmp_path / "visual.jsonl"
    candidates = tmp_path / "candidates.json"
    table = tmp_path / "table.json"

    write_json(registry, sample_page_registry())
    write_json(
        image_audit,
        {
            "records": [
                {
                    "page_id": "t_p_120_1176_p000048",
                    "role": "parts_list",
                    "classification": "likely_table_or_grid",
                    "likely_figure_or_diagram": True,
                    "likely_table_grid": True,
                }
            ]
        },
    )
    write_jsonl(visual, [{"page_id": "t_p_120_1176_p000048", "clean_text": "Figure 97 item 14 120-46137-001"}])
    write_json(candidates, {"records": [{"page_id": "t_p_120_1176_p000048", "citation_id": "cite:source_text:p48"}]})
    write_json(table, {"records": [{"page_id": "t_p_120_1176_p000048", "rows": []}]})

    report = mod.build_figure_chart_understanding_report(
        page_registry_path=registry,
        image_recognition_audit_path=image_audit,
        visual_text_records_path=visual,
        embedding_candidates_path=candidates,
        table_cell_normalizer_path=table,
        output_dir=tmp_path / "out",
        quality_config={
            "min_visual_records": 1,
            "min_visual_candidate_pages": 1,
            "min_figure_diagram_records": 1,
            "min_visual_regions": 1,
            "min_retrieval_only_records": 1,
            "min_graph_attachment_plans": 1,
        },
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["visual_understanding_record_count"] == 1
    record = report["records"][0]
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False
    assert record["answer_support_candidate"] is False
    assert record["requires_catalog_compare"] is True
    assert record["linked_part_candidates"] == ["120-46137-001"]
    assert Path(report["report_path"]).exists()


def test_user_visible_leak_marker_fails_quality(tmp_path: Path) -> None:
    summary = {
        "source_page_registry_count": 1,
        "visual_understanding_record_count": 1,
        "visual_candidate_page_count": 1,
        "figure_diagram_record_count": 1,
        "chart_record_count": 0,
        "parts_diagram_record_count": 1,
        "visual_text_record_backed_count": 1,
        "visual_region_count": 1,
        "callout_candidate_count": 0,
        "linked_part_candidate_count": 0,
        "records_requiring_catalog_compare_count": 1,
        "records_needing_human_review_count": 1,
        "records_with_graph_attachment_plan_count": 1,
        "visual_retrieval_only_count": 1,
        "visual_answer_allowed_count": 0,
        "unverified_visual_claim_count": 0,
        "unsafe_visual_evidence_count": 1,
        "missing_page_id_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    quality = mod.evaluate_quality(summary, {"min_visual_records": 1})
    assert quality["status"] == "FAIL"
