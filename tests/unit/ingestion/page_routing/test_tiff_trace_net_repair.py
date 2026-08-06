from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_repair import (
    TraceNetRepairOptions,
    TraceNetRepairPaths,
    build_trace_net_repair_plan,
    plan_repair_for_page,
    write_jsonl,
)


def _record(page_id: str, tier: str, page_role: str | None = None, image_class: str | None = None, **flags: bool) -> dict:
    rec = {
        "page_id": page_id,
        "status": "ok",
        "prompt_version": "visual_text_v2_2",
        "visual_text_cleanup_scores": {
            "trust_tier": tier,
            "usable_for_rag": tier in {"A", "B"},
            "requires_human_review": tier in {"C", "D"} or any(flags.values()),
            **flags,
        },
        "visual_text_scores_clean": dict(flags),
    }
    if page_role or image_class:
        rec["source"] = {"page_role": page_role, "image_class": image_class}
    return rec


def test_plan_repair_for_rag_safe_record() -> None:
    rec = _record("p001", "A")
    plan = plan_repair_for_page("p001", rec, {"trust_tier": "A", "rag_traits": ["include_visual_text"], "review_traits": []})

    assert plan.current_trust_tier == "A"
    assert plan.current_rag_trait == "include_visual_text"
    assert plan.primary_repair_route == "rag_include_route"
    assert plan.primary_repair_action == "no_repair_needed"
    assert plan.current_usable_for_rag is True


def test_plan_repair_routes_prompt_leakage_to_cleanup() -> None:
    rec = _record("p002", "D", prompt_template_leakage_risk=True, section_bleed_risk=True)
    plan = plan_repair_for_page("p002", rec, {"trust_tier": "D", "rag_traits": ["exclude_visual_text"], "review_traits": ["prompt_template_leakage", "section_bleed", "needs_human_review"]})

    assert plan.current_trust_tier == "D"
    assert plan.priority == "high"
    assert plan.primary_repair_route == "prompt_cleanup_repair_route"
    assert plan.primary_repair_action == "rerun_cleanup_salvage"
    assert "prompt_template_leakage" in plan.review_traits
    assert any(action.route == "human_review_route" for action in plan.action_queue)


def test_plan_repair_routes_table_missing_to_high_table_route() -> None:
    rec = _record("p003", "D", page_role="table", image_class="likely_table_or_grid", table_expected_but_not_extracted=True)
    plan = plan_repair_for_page("p003", rec, {"trust_tier": "D", "rag_traits": ["exclude_visual_text"], "review_traits": ["table_expected_but_not_extracted"]})

    assert plan.primary_repair_route == "table_crop_tile_repair_route_high"
    assert plan.primary_repair_action == "send_to_table_crop_tile_route"
    assert plan.recommended_settings["planned_prompt_version"] == "table_text_v1_planned"
    assert plan.recommended_settings["route_priority"] == "high"


def test_plan_repair_routes_parts_list_grid_to_medium_table_route() -> None:
    rec = _record("p003b", "C", page_role="parts_list", image_class="likely_table_or_grid", table_expected_but_not_extracted=True)
    plan = plan_repair_for_page("p003b", rec, {"trust_tier": "C", "rag_traits": ["exclude_visual_text"], "review_traits": ["table_expected_but_not_extracted"]})

    assert plan.primary_repair_route == "table_crop_tile_repair_route_medium"
    # Overall page priority remains high because the table-missing trait blocks RAG;
    # table_route_priority carries medium/high routing detail.
    assert plan.priority == "high"
    assert plan.table_route_priority == "medium"
    assert plan.recommended_settings["page_role"] == "parts_list"


def test_plan_repair_routes_weak_front_matter_table_flag_to_review_route() -> None:
    rec = _record("p003c", "C", page_role="front_matter", image_class="likely_figure_or_diagram", table_expected_but_not_extracted=True)
    plan = plan_repair_for_page("p003c", rec, {"trust_tier": "C", "rag_traits": ["exclude_visual_text"], "review_traits": ["table_expected_but_not_extracted"]})

    assert plan.primary_repair_route == "ocr_graph_validation_review_route"
    assert plan.primary_repair_action == "run_ocr_graph_validation"
    assert plan.recommended_settings["does_not_call_model"] is True


def test_build_trace_net_repair_plan_from_artifacts(tmp_path: Path) -> None:
    visual_dir = tmp_path / "visual_text"
    trust_dir = tmp_path / "trust_traits"
    output_dir = tmp_path / "trace_net"
    records = [
        _record("p001", "A"),
        _record("p002", "D", prompt_template_leakage_risk=True, section_bleed_risk=True),
        _record("p003", "D", page_role="table", image_class="likely_table_or_grid", table_expected_but_not_extracted=True),
        _record("p004", "C", hallucination_risk=True),
    ]
    write_jsonl(visual_dir / "visual_text_extraction_clean.jsonl", records)
    assertions = [
        {"page_id": "p001", "trait_type": "trust", "trait_key": "visual_text", "trait_value": "A"},
        {"page_id": "p001", "trait_type": "rag", "trait_key": "visual_text", "trait_value": "include_visual_text"},
        {"page_id": "p002", "trait_type": "trust", "trait_key": "visual_text", "trait_value": "D"},
        {"page_id": "p002", "trait_type": "rag", "trait_key": "visual_text", "trait_value": "exclude_visual_text"},
        {"page_id": "p002", "trait_type": "review", "trait_key": "visual_text", "trait_value": "prompt_template_leakage"},
        {"page_id": "p003", "trait_type": "trust", "trait_key": "visual_text", "trait_value": "D"},
        {"page_id": "p003", "trait_type": "review", "trait_key": "visual_text", "trait_value": "table_expected_but_not_extracted"},
        {"page_id": "p004", "trait_type": "trust", "trait_key": "visual_text", "trait_value": "C"},
        {"page_id": "p004", "trait_type": "review", "trait_key": "visual_text", "trait_value": "hallucination_risk"},
    ]
    write_jsonl(trust_dir / "trust_trait_assertions.jsonl", assertions)

    paths = TraceNetRepairPaths(visual_text_dir=visual_dir, trust_trait_dir=trust_dir, output_dir=output_dir)
    plan = build_trace_net_repair_plan(paths, TraceNetRepairOptions(expected_pages=4))
    summary = plan["summary"]

    assert plan["status"] == "OK"
    assert summary["records"] == 4
    assert summary["trust_tier_counts"] == {"A": 1, "C": 1, "D": 2}
    assert summary["auto_repair_candidate_records"] == 3
    assert summary["repair_route_counts"]["prompt_cleanup_repair_route"] == 1
    assert summary["repair_route_counts"]["table_crop_tile_repair_route_high"] == 1
    assert summary["table_repair_high_records"] == 1
    assert summary["repair_route_counts"]["ocr_graph_validation_review_route"] == 1
