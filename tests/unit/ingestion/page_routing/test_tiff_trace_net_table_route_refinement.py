from __future__ import annotations

from tiff.trace_net_repair import classify_table_repair_route, plan_repair_for_page


def _record(page_id: str, tier: str = "C", *, role: str = "", image_class: str = "", title: str = "") -> dict:
    return {
        "page_id": page_id,
        "status": "ok",
        "page_role": role,
        "image_class": image_class,
        "visible_title": title,
        "visual_text_cleanup_scores": {
            "trust_tier": tier,
            "usable_for_rag": False,
            "requires_human_review": True,
            "table_expected_but_not_extracted": True,
        },
        "visual_text_scores_clean": {"table_expected_but_not_extracted": True},
    }


def test_table_refinement_high_for_real_table_grid_page() -> None:
    rec = _record("p_table", role="table", image_class="likely_table_or_grid")
    traits = {"table_expected_but_not_extracted"}

    route, action, priority, settings = classify_table_repair_route(rec, traits)
    plan = plan_repair_for_page(
        "p_table",
        rec,
        {"trust_tier": "C", "rag_traits": ["exclude_visual_text"], "review_traits": sorted(traits)},
    )

    assert route == "table_crop_tile_repair_route_high"
    assert action == "send_to_table_crop_tile_route"
    assert priority == "high"
    assert settings["route_priority"] == "high"
    assert plan.primary_repair_route == "table_crop_tile_repair_route_high"
    assert plan.table_route_priority == "high"


def test_table_refinement_medium_for_parts_list_grid_page() -> None:
    rec = _record("p_parts", role="parts_list", image_class="likely_table_or_grid")
    traits = {"table_expected_but_not_extracted"}

    route, _action, priority, settings = classify_table_repair_route(rec, traits)
    plan = plan_repair_for_page(
        "p_parts",
        rec,
        {"trust_tier": "C", "rag_traits": ["exclude_visual_text"], "review_traits": sorted(traits)},
    )

    assert route == "table_crop_tile_repair_route_medium"
    assert priority == "medium"
    assert settings["route_priority"] == "medium"
    assert plan.primary_repair_route == "table_crop_tile_repair_route_medium"
    assert plan.table_route_priority == "medium"


def test_table_refinement_avoids_table_route_for_figure_page() -> None:
    rec = _record("p_fig", role="figure", image_class="likely_figure_or_diagram")
    traits = {"table_expected_but_not_extracted"}

    plan = plan_repair_for_page(
        "p_fig",
        rec,
        {"trust_tier": "C", "rag_traits": ["exclude_visual_text"], "review_traits": sorted(traits)},
    )

    assert plan.primary_repair_route == "ocr_graph_validation_review_route"
    assert plan.primary_repair_action == "run_ocr_graph_validation"
    assert plan.table_route_priority == "not_table"


def test_table_refinement_low_review_for_weak_front_matter_table_flag() -> None:
    rec = _record("p_front", role="front_matter", image_class="likely_table_or_grid")
    traits = {"table_expected_but_not_extracted"}

    plan = plan_repair_for_page(
        "p_front",
        rec,
        {"trust_tier": "C", "rag_traits": ["exclude_visual_text"], "review_traits": sorted(traits)},
    )

    assert plan.primary_repair_route == "table_candidate_review_route"
    assert plan.primary_repair_action == "review_table_candidate_before_extraction"
    assert plan.table_route_priority == "low"


def test_table_refinement_preserves_generic_fallback_without_metadata() -> None:
    rec = {
        "page_id": "p_no_meta",
        "status": "ok",
        "visual_text_cleanup_scores": {
            "trust_tier": "D",
            "usable_for_rag": False,
            "requires_human_review": True,
            "table_expected_but_not_extracted": True,
        },
        "visual_text_scores_clean": {"table_expected_but_not_extracted": True},
    }
    traits = {"table_expected_but_not_extracted"}

    plan = plan_repair_for_page(
        "p_no_meta",
        rec,
        {"trust_tier": "D", "rag_traits": ["exclude_visual_text"], "review_traits": sorted(traits)},
    )

    assert plan.primary_repair_route == "table_crop_tile_repair_route"
    assert plan.table_route_priority in {"generic", "high"}
