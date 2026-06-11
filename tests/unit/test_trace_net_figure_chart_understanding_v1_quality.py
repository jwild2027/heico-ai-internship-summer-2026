from __future__ import annotations

import json
from pathlib import Path

from tiff import trace_net_figure_chart_understanding_v1 as mod


def test_quality_passes_for_safe_visual_report(tmp_path: Path) -> None:
    report = {
        "summary": {
            "source_page_registry_count": 509,
            "visual_understanding_record_count": 493,
            "visual_candidate_page_count": 493,
            "figure_diagram_record_count": 493,
            "chart_record_count": 0,
            "parts_diagram_record_count": 290,
            "visual_text_record_backed_count": 25,
            "visual_region_count": 493,
            "callout_candidate_count": 100,
            "linked_part_candidate_count": 50,
            "records_requiring_catalog_compare_count": 290,
            "records_needing_human_review_count": 493,
            "records_with_graph_attachment_plan_count": 493,
            "visual_retrieval_only_count": 493,
            "visual_answer_allowed_count": 0,
            "unverified_visual_claim_count": 0,
            "unsafe_visual_evidence_count": 0,
            "missing_page_id_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    quality = mod.quality_report_from_path(
        path,
        {
            "require_page_registry_count": 509,
            "min_visual_records": 100,
            "min_visual_candidate_pages": 100,
            "min_figure_diagram_records": 100,
            "min_visual_regions": 100,
            "min_retrieval_only_records": 100,
            "min_graph_attachment_plans": 100,
        },
        write_json_file=True,
    )
    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()


def test_quality_fails_if_visual_can_answer() -> None:
    summary = {
        "source_page_registry_count": 1,
        "visual_understanding_record_count": 1,
        "visual_candidate_page_count": 1,
        "figure_diagram_record_count": 1,
        "visual_region_count": 1,
        "records_with_graph_attachment_plan_count": 1,
        "visual_retrieval_only_count": 0,
        "visual_answer_allowed_count": 1,
        "unverified_visual_claim_count": 1,
        "unsafe_visual_evidence_count": 0,
        "missing_page_id_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    quality = mod.evaluate_quality(summary, {"min_visual_records": 1, "min_retrieval_only_records": 0})
    assert quality["status"] == "FAIL"
