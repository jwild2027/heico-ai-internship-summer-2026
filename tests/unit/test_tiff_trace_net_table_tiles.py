from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff.trace_net_table_tiles import (
    TABLE_ROUTE_HIGH,
    TABLE_ROUTE_MEDIUM,
    TraceNetTableTileOptions,
    TraceNetTableTilePaths,
    _parse_routes,
    build_and_write_table_tile_plan,
    select_repair_plan_rows,
)

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover
    Image = None
    ImageDraw = None


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _make_tiff(path: Path) -> None:
    if Image is None:
        pytest.skip("Pillow is required for this test")
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (800, 1100), "white")
    draw = ImageDraw.Draw(img)
    for y in range(80, 1020, 70):
        draw.line((50, y, 750, y), fill="black", width=2)
    for x in range(50, 760, 140):
        draw.line((x, 80, x, 1010), fill="black", width=2)
    draw.text((80, 40), "LIST OF EFFECTIVE PAGES", fill="black")
    img.save(path)


def test_parse_routes_aliases() -> None:
    assert _parse_routes("high") == (TABLE_ROUTE_HIGH,)
    assert _parse_routes("medium") == (TABLE_ROUTE_MEDIUM,)
    assert _parse_routes("high,medium") == (TABLE_ROUTE_HIGH, TABLE_ROUTE_MEDIUM)


def test_selected_routes_include_medium() -> None:
    opts = TraceNetTableTileOptions(routes=(TABLE_ROUTE_HIGH,), include_medium=True)
    assert TABLE_ROUTE_HIGH in opts.selected_routes()
    assert TABLE_ROUTE_MEDIUM in opts.selected_routes()


def test_select_repair_plan_rows_defaults_to_high() -> None:
    rows = [
        {"page_id": "p1", "primary_repair_route": TABLE_ROUTE_HIGH, "primary_repair_action": "send_to_table_crop_tile_route"},
        {"page_id": "p2", "primary_repair_route": TABLE_ROUTE_MEDIUM, "primary_repair_action": "send_to_table_crop_tile_route"},
        {"page_id": "p3", "primary_repair_route": "human_review_route", "primary_repair_action": "send_to_human_review"},
    ]
    selected = select_repair_plan_rows(rows, TraceNetTableTileOptions())
    assert [r["page_id"] for r in selected] == ["p1"]
    selected2 = select_repair_plan_rows(rows, TraceNetTableTileOptions(routes=(TABLE_ROUTE_HIGH,), include_medium=True))
    assert [r["page_id"] for r in selected2] == ["p1", "p2"]


def test_build_and_write_table_tile_plan_writes_tiles(tmp_path: Path) -> None:
    image_path = tmp_path / "source" / "page001.tif"
    _make_tiff(image_path)
    trace_dir = tmp_path / "trace_net"
    visual_dir = tmp_path / "visual_text"
    output_dir = tmp_path / "table_extraction"
    _write_jsonl(
        trace_dir / "trace_net_repair_plan.jsonl",
        [
            {
                "page_id": "p001",
                "primary_repair_route": TABLE_ROUTE_HIGH,
                "primary_repair_action": "send_to_table_crop_tile_route",
                "primary_repairer": "table_crop_tile",
                "source": {"tiff_path": str(image_path), "source_url": "http://example/page001"},
            }
        ],
    )
    _write_jsonl(visual_dir / "visual_text_extraction_clean.jsonl", [{"page_id": "p001", "tiff_path": str(image_path)}])

    paths = TraceNetTableTilePaths(trace_net_dir=trace_dir, visual_text_dir=visual_dir, output_dir=output_dir)
    result = build_and_write_table_tile_plan(paths, TraceNetTableTileOptions(tiles_per_page=4, max_image_edge=500))
    summary = result["summary"]
    assert summary["status"] == "OK"
    assert summary["records"] == 1
    assert summary["ok_records"] == 1
    assert summary["tile_images"] == 4
    records = result["records"]
    assert records[0]["tile_count"] == 4
    for tile in records[0]["tiles"]:
        assert Path(tile["path"]).exists()
    assert paths.review_html.exists()
    assert paths.graph_nodes.exists()
    assert paths.graph_edges.exists()


def test_graph_table_gate_blocks_figure_page_card(tmp_path: Path) -> None:
    image_path = tmp_path / "source" / "figure001.tif"
    _make_tiff(image_path)
    trace_dir = tmp_path / "trace_net"
    visual_dir = tmp_path / "visual_text"
    entity_dir = tmp_path / "entity_traits"
    output_dir = tmp_path / "table_extraction"
    _write_jsonl(
        trace_dir / "trace_net_repair_plan.jsonl",
        [
            {
                "page_id": "pfig",
                "primary_repair_route": TABLE_ROUTE_MEDIUM,
                "primary_repair_action": "send_to_table_crop_tile_route",
                "source": {"tiff_path": str(image_path)},
            }
        ],
    )
    _write_jsonl(visual_dir / "visual_text_extraction_clean.jsonl", [{"page_id": "pfig", "tiff_path": str(image_path)}])
    (entity_dir).mkdir(parents=True, exist_ok=True)
    (entity_dir / "page_character_cards.json").write_text(
        json.dumps(
            [
                {
                    "page_id": "pfig",
                    "context": {"page_role": "figure"},
                    "signals": {"image_classification": "likely_figure_or_diagram"},
                    "traits": ["context:page_role=figure", "image_recognition:classification=likely_figure_or_diagram"],
                }
            ]
        ),
        encoding="utf-8",
    )
    paths = TraceNetTableTilePaths(
        trace_net_dir=trace_dir,
        visual_text_dir=visual_dir,
        entity_trait_dir=entity_dir,
        output_dir=output_dir,
    )
    result = build_and_write_table_tile_plan(
        paths,
        TraceNetTableTileOptions(routes=(TABLE_ROUTE_MEDIUM,), tiles_per_page=4, max_image_edge=500),
    )
    summary = result["summary"]
    assert summary["route_candidate_pages"] == 1
    assert summary["records"] == 0
    assert summary["ok_records"] == 0
    assert summary["table_graph_gate_skipped_records"] == 1
    skipped = result["skipped_by_table_graph_gate"]
    assert skipped[0]["page_id"] == "pfig"
    assert skipped[0]["table_graph_gate"]["decision"] == "skip"
    assert skipped[0]["table_graph_gate"]["figure_signal"] is True


def test_graph_table_gate_allows_table_page_card(tmp_path: Path) -> None:
    image_path = tmp_path / "source" / "table001.tif"
    _make_tiff(image_path)
    trace_dir = tmp_path / "trace_net"
    visual_dir = tmp_path / "visual_text"
    entity_dir = tmp_path / "entity_traits"
    output_dir = tmp_path / "table_extraction"
    _write_jsonl(
        trace_dir / "trace_net_repair_plan.jsonl",
        [
            {
                "page_id": "ptable",
                "primary_repair_route": TABLE_ROUTE_HIGH,
                "primary_repair_action": "send_to_table_crop_tile_route",
                "source": {"tiff_path": str(image_path)},
            }
        ],
    )
    _write_jsonl(visual_dir / "visual_text_extraction_clean.jsonl", [{"page_id": "ptable", "tiff_path": str(image_path)}])
    entity_dir.mkdir(parents=True, exist_ok=True)
    (entity_dir / "page_character_cards.json").write_text(
        json.dumps(
            [
                {
                    "page_id": "ptable",
                    "context": {"page_role": "table"},
                    "signals": {"image_classification": "likely_table_or_grid"},
                    "traits": ["context:page_role=table", "image_recognition:classification=likely_table_or_grid"],
                }
            ]
        ),
        encoding="utf-8",
    )
    paths = TraceNetTableTilePaths(
        trace_net_dir=trace_dir,
        visual_text_dir=visual_dir,
        entity_trait_dir=entity_dir,
        output_dir=output_dir,
    )
    result = build_and_write_table_tile_plan(
        paths,
        TraceNetTableTileOptions(routes=(TABLE_ROUTE_HIGH,), tiles_per_page=4, max_image_edge=500),
    )
    summary = result["summary"]
    assert summary["status"] == "OK"
    assert summary["ok_records"] == 1
    assert summary["tile_images"] == 4
    assert result["records"][0]["table_gate_decision"] == "allow"
    assert result["records"][0]["table_gate_score"] >= 2


def test_table_graph_gate_skips_figure_or_engineering_drawing() -> None:
    rows = [
        {
            "page_id": "drawing_page",
            "primary_repair_route": TABLE_ROUTE_MEDIUM,
            "review_traits": ["table_expected_but_not_extracted"],
            "route_metadata": {"page_role": "figure", "image_class": "likely_figure_or_diagram"},
        },
        {
            "page_id": "table_page",
            "primary_repair_route": TABLE_ROUTE_MEDIUM,
            "review_traits": ["table_expected_but_not_extracted"],
            "route_metadata": {"page_role": "parts_list", "image_class": "likely_table_or_grid"},
        },
    ]
    opts = TraceNetTableTileOptions(routes=(TABLE_ROUTE_HIGH,), include_medium=True)
    selected = select_repair_plan_rows(rows, opts, clean_records={})
    assert [r["page_id"] for r in selected] == ["table_page"]
    gate = selected[0]["table_graph_gate"]
    assert gate["decision"] == "allow"


def test_table_graph_gate_can_be_disabled_for_legacy_behavior() -> None:
    rows = [
        {
            "page_id": "drawing_page",
            "primary_repair_route": TABLE_ROUTE_MEDIUM,
            "review_traits": ["table_expected_but_not_extracted"],
            "route_metadata": {"page_role": "figure", "image_class": "likely_figure_or_diagram"},
        }
    ]
    opts = TraceNetTableTileOptions(routes=(TABLE_ROUTE_HIGH,), include_medium=True, table_graph_gate=False)
    selected = select_repair_plan_rows(rows, opts, clean_records={})
    assert [r["page_id"] for r in selected] == ["drawing_page"]
