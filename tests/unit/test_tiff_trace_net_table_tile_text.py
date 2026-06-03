from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_tile_text import (
    TableTileTextOptions,
    TableTileTextPaths,
    extract_part_like_strings,
    filter_part_numbers,
    run_table_tile_text_extraction,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_part_number_extraction_filters_ata_codes() -> None:
    part_like = extract_part_like_strings("ATA 25-21-00 part 120-37313-001 and AM03078-22")
    parts = filter_part_numbers(part_like)
    assert "25-21-00" not in parts
    assert "120-37313-001" in parts
    assert "AM03078-22" in parts


def test_page_ocr_provider_splits_page_ocr_into_tile_records(tmp_path: Path) -> None:
    table_dir = tmp_path / "table"
    export_dir = tmp_path / "export"
    output_dir = tmp_path / "out"
    ocr_path = tmp_path / "ocr" / "p1.txt"
    ocr_path.parent.mkdir(parents=True)
    ocr_path.write_text("HEADER\nITEM 1 120-37313-001 HOLDER MAGAZINE\nITEM 2 AM03078-22 ASHTRAY\nFOOTER\n", encoding="utf-8")

    _write_jsonl(
        table_dir / "table_tile_plan.jsonl",
        [
            {
                "page_id": "p1",
                "status": "ok",
                "repair_route": "table_crop_tile_repair_route_high",
                "repair_priority": "high",
                "source_url": "source://p1",
                "tiff_path": "p1.tif",
                "tile_count": 2,
                "tiles": [
                    {"tile_id": "p1_tile_001", "tile_index": 1, "path": "tile_001.png"},
                    {"tile_id": "p1_tile_002", "tile_index": 2, "path": "tile_002.png"},
                ],
            }
        ],
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "page_index.json").write_text(json.dumps({"p1": {"page_id": "p1", "ocr_path": str(ocr_path)}}), encoding="utf-8")
    (export_dir / "part_tree.json").write_text(json.dumps({"120-37313-001": {}, "AM03078-22": {}}), encoding="utf-8")

    result = run_table_tile_text_extraction(
        TableTileTextPaths(export_dir=export_dir, table_dir=table_dir, output_dir=output_dir),
        TableTileTextOptions(provider="page_ocr"),
    )

    summary = result["summary"]
    assert summary["status"] == "OK"
    assert summary["records"] == 2
    assert summary["ok_records"] == 2
    assert summary["part_number_records"] >= 1
    assert summary["catalog_supported_part_number_records"] >= 1
    assert (output_dir / "table_tile_text_records.jsonl").exists()
    assert (output_dir / "table_tile_text_review.html").exists()


def test_mock_provider_is_dependency_free(tmp_path: Path) -> None:
    table_dir = tmp_path / "table"
    output_dir = tmp_path / "out"
    _write_jsonl(
        table_dir / "table_tile_plan.jsonl",
        [
            {
                "page_id": "p2",
                "status": "ok",
                "tile_count": 1,
                "tiles": [{"tile_id": "p2_tile_001", "tile_index": 1, "path": "tile.png"}],
            }
        ],
    )
    result = run_table_tile_text_extraction(
        TableTileTextPaths(table_dir=table_dir, output_dir=output_dir, export_dir=tmp_path / "missing"),
        TableTileTextOptions(provider="mock"),
    )
    assert result["summary"]["records"] == 1
    assert result["summary"]["ok_records"] == 1
    assert result["summary"]["part_number_records"] == 1
