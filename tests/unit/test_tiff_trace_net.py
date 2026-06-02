from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net import TraceNetOptions, TraceNetPaths, build_and_write_trace_net_plan, build_page_signals, plan_page_route


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_plan_page_route_routes_tables_to_table_extractor() -> None:
    signals = {
        "page_id": "p1",
        "role": "table",
        "image_classes": ["likely_table_or_grid"],
        "traits": [],
        "visual_status": "ok",
        "visual_prompt_version": "visual_text_v2_2",
        "visual_scores": {
            "required_sections_present": True,
            "has_table_rows": False,
            "trust_tier": "C",
        },
    }

    route = plan_page_route(signals)

    assert route.route == "table_grid"
    assert route.recommended_extractor == "grit_table_crop_tile_route"
    assert route.fishnet_enabled is True
    assert "table_expected_missing" in route.reasons
    assert route.priority == "high"


def test_plan_page_route_figures_to_callout_extractor() -> None:
    signals = {
        "page_id": "p2",
        "role": "figure",
        "image_classes": ["likely_figure_or_diagram"],
        "traits": [],
        "visual_status": "ok",
        "visual_prompt_version": "visual_text_v2_2",
        "visual_scores": {"trust_tier": "B", "has_figure_description": True},
    }

    route = plan_page_route(signals)

    assert route.route == "figure_diagram"
    assert route.recommended_extractor == "vision_figure_callout_route"
    assert route.usable_for_rag is True


def test_build_and_write_trace_net_plan_from_artifacts(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    trait_dir = tmp_path / "traits"
    visual_dir = tmp_path / "visual"
    output_dir = tmp_path / "trace_net"
    paths = TraceNetPaths(export_dir=export_dir, trait_dir=trait_dir, visual_text_dir=visual_dir, output_dir=output_dir)

    _write_json(
        paths.page_index_path,
        {
            "p1": {"page_id": "p1", "role": "front_matter", "source_url": "x", "tiff_path": "p1.tif"},
            "p2": {"page_id": "p2", "role": "table", "source_url": "x", "tiff_path": "p2.tif"},
            "p3": {"page_id": "p3", "role": "figure", "source_url": "x", "tiff_path": "p3.tif"},
            "p4": {"page_id": "p4", "role": "blank", "source_url": "x", "tiff_path": "p4.tif"},
        },
    )
    _write_json(
        paths.page_cards_path,
        [
            {"page_id": "p2", "direct_traits": ["visual:likely_table_or_grid"]},
            {"page_id": "p3", "direct_traits": ["visual:likely_figure_or_diagram"]},
        ],
    )
    _write_jsonl(
        paths.clean_records_path,
        [
            {"page_id": "p1", "status": "ok", "prompt_version": "visual_text_v2_2", "scores": {"trust_tier": "B"}},
            {"page_id": "p2", "status": "ok", "prompt_version": "visual_text_v2_2", "scores": {"trust_tier": "C", "has_table_rows": False}},
            {"page_id": "p3", "status": "ok", "prompt_version": "visual_text_v2_2", "scores": {"trust_tier": "B", "has_figure_description": True}},
            {"page_id": "p4", "status": "ok", "prompt_version": "visual_text_v2_2", "scores": {"trust_tier": "B"}},
        ],
    )

    plan = build_and_write_trace_net_plan(paths, TraceNetOptions(expected_pages=4))

    assert plan["status"] == "OK"
    summary = plan["summary"]
    assert summary["records"] == 4
    assert summary["route_counts"]["table_grid"] == 1
    assert summary["route_counts"]["figure_diagram"] == 1
    assert summary["route_counts"]["blank"] == 1
    assert paths.plan_path.exists()
    assert paths.plan_jsonl_path.exists()
    assert paths.graph_nodes_path.exists()
    assert paths.graph_edges_path.exists()
    assert paths.review_md_path.exists()
