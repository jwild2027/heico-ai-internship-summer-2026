from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_tile_text_refiner_quality import (
    TableTileTextRefinerQualityOptions,
    TableTileTextRefinerQualityPaths,
    build_table_tile_text_refiner_quality,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_quality_passes_when_index_labels_are_filtered(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    summary = {
        "status": "OK",
        "records": 2,
        "pages": 1,
        "ok_records": 2,
        "error_records": 0,
        "records_with_canonical_parts": 1,
        "records_with_catalog_supported_parts": 1,
        "records_with_filtered_non_part_tokens": 1,
        "graph_nodes": 3,
        "graph_edges": 2,
    }
    (out_dir / "table_tile_text_refined_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    write_jsonl(
        out_dir / "table_tile_text_refined_records.jsonl",
        [
            {
                "canonical_part_numbers": ["120-50645-009"],
                "index_labels": ["25-Numerical"],
            },
            {
                "canonical_part_numbers": [],
                "index_labels": ["25-Vendors"],
            },
        ],
    )
    report = build_table_tile_text_refiner_quality(
        TableTileTextRefinerQualityPaths(output_dir=out_dir),
        TableTileTextRefinerQualityOptions(min_records=2, min_catalog_supported_records=1),
    )
    assert report["status"] == "OK"
    assert report["summary"]["table_tile_text_refined_index_labels_in_canonical_parts"] == 0


def test_quality_fails_when_index_label_remains_in_canonical(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    summary = {
        "status": "OK",
        "records": 1,
        "pages": 1,
        "ok_records": 1,
        "error_records": 0,
        "records_with_canonical_parts": 1,
        "records_with_catalog_supported_parts": 0,
        "records_with_filtered_non_part_tokens": 1,
        "graph_nodes": 2,
        "graph_edges": 1,
    }
    (out_dir / "table_tile_text_refined_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    write_jsonl(
        out_dir / "table_tile_text_refined_records.jsonl",
        [{"canonical_part_numbers": ["25-Numerical"], "index_labels": ["25-Numerical"]}],
    )
    report = build_table_tile_text_refiner_quality(
        TableTileTextRefinerQualityPaths(output_dir=out_dir),
        TableTileTextRefinerQualityOptions(min_records=1, max_index_labels_in_canonical_parts=0),
    )
    assert report["status"] == "FAIL"
