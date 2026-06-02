from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_tile_text_quality import TableTileTextQualityPaths, build_table_tile_text_quality


def test_table_tile_text_quality_passes_for_valid_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    summary = {
        "status": "OK",
        "records": 2,
        "ok_records": 2,
        "error_records": 0,
        "tile_text_char_total": 100,
        "part_number_records": 1,
        "graph_nodes": 3,
        "graph_edges": 2,
    }
    (output_dir / "table_tile_text_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (output_dir / "table_tile_text_records.jsonl").write_text(json.dumps({"status": "ok"}) + "\n" + json.dumps({"status": "ok"}) + "\n", encoding="utf-8")

    report = build_table_tile_text_quality(
        TableTileTextQualityPaths(output_dir=output_dir),
        min_records=2,
        min_ok_records=2,
        max_error_records=0,
        min_text_chars=1,
        min_part_number_records=1,
    )
    assert report["status"] == "OK"


def test_table_tile_text_quality_fails_when_too_few_records(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "table_tile_text_summary.json").write_text(json.dumps({"status": "OK", "records": 0}), encoding="utf-8")
    (output_dir / "table_tile_text_records.jsonl").write_text("", encoding="utf-8")
    report = build_table_tile_text_quality(TableTileTextQualityPaths(output_dir=output_dir), min_records=1)
    assert report["status"] == "FAIL"
