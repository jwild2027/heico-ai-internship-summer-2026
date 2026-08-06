from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_candidate_scan import (
    TABLE_ROUTE_HIGH,
    TABLE_ROUTE_MEDIUM,
    ROUTE_SKIP,
    TableCandidateScanOptions,
    TableCandidateScanPaths,
    build_and_write_table_candidate_scan,
    graph_table_score,
    image_layout_score,
)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_table_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in range(80, 900, 80):
        draw.line((60, y, 740, y), fill="black", width=3)
    for x in range(60, 741, 170):
        draw.line((x, 80, x, 900), fill="black", width=3)
    for row, y in enumerate(range(110, 850, 80)):
        draw.text((80, y), f"120-{row:05d}-001", fill="black")
        draw.text((300, y), "PART NAME", fill="black")
    img.save(path)


def make_figure_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((180, 200, 620, 700), outline="black", width=8)
    draw.line((400, 100, 400, 900), fill="black", width=6)
    draw.text((200, 760), "SEAT BACKREST", fill="black")
    img.save(path)


def test_graph_table_score_blocks_figure() -> None:
    row = {"page_id": "p1", "page_role": "figure", "image_classification": "likely_figure_or_diagram"}
    score = graph_table_score(row)
    assert score["score"] < 0
    assert score["has_figure_trait"] is True


def test_image_layout_score_detects_grid(tmp_path: Path) -> None:
    table = tmp_path / "table.png"
    fig = tmp_path / "figure.png"
    make_table_image(table)
    make_figure_image(fig)
    table_score = image_layout_score(str(table), max_edge=800)
    fig_score = image_layout_score(str(fig), max_edge=800)
    assert table_score["score"] > fig_score["score"]
    assert table_score["metrics"]["horizontal_rules"] >= 2


def test_build_all_page_candidate_scan_writes_repair_plan(tmp_path: Path) -> None:
    table = tmp_path / "table.png"
    figure = tmp_path / "figure.png"
    make_table_image(table)
    make_figure_image(figure)
    entity_dir = tmp_path / "entity"
    export_dir = tmp_path / "export"
    image_dir = tmp_path / "image"
    out_dir = tmp_path / "out"
    write_json(
        entity_dir / "page_character_cards.json",
        [
            {
                "page_id": "p_table",
                "page_role": "table",
                "image_classification": "likely_table_or_grid",
                "tiff_path": str(table),
                "source_url": "http://source/table",
            },
            {
                "page_id": "p_figure",
                "page_role": "figure",
                "image_classification": "likely_figure_or_diagram",
                "tiff_path": str(figure),
                "source_url": "http://source/figure",
            },
        ],
    )
    write_json(export_dir / "page_index.json", [])
    write_json(image_dir / "page_image_recognition_audit.json", {"records": []})
    paths = TableCandidateScanPaths(entity_trait_dir=entity_dir, export_dir=export_dir, image_recognition_dir=image_dir, output_dir=out_dir)
    result = build_and_write_table_candidate_scan(paths, TableCandidateScanOptions(expect_pages=2, min_layout_score=2))
    summary = result["summary"]
    assert summary["records"] == 2
    assert summary["candidate_records"] >= 1
    rows = [json.loads(line) for line in paths.repair_plan_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(row["page_id"] == "p_table" for row in rows)
    assert all(row["page_id"] != "p_figure" for row in rows if row.get("primary_repair_route") != ROUTE_SKIP)
