from __future__ import annotations

from pathlib import Path

from tiff.trace_net_table_tiles import TraceNetTableTilePaths, build_table_tile_quality, write_jsonl, _write_json


def test_build_table_tile_quality_ok(tmp_path: Path) -> None:
    out = tmp_path / "table_extraction"
    paths = TraceNetTableTilePaths(output_dir=out)
    summary = {
        "status": "OK",
        "records": 2,
        "selected_pages": 2,
        "ok_records": 2,
        "error_records": 0,
        "missing_image_path_records": 0,
        "missing_image_file_records": 0,
        "tile_images": 12,
        "full_preprocessed_images": 2,
    }
    _write_json(paths.summary, summary)
    _write_json(paths.tile_plan, {"summary": summary, "records": []})
    write_jsonl(paths.tile_plan_jsonl, [{"page_id": "p1"}, {"page_id": "p2"}])
    _write_json(paths.graph_nodes, [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}])
    _write_json(paths.graph_edges, [{"source": "a", "target": "b"}, {"source": "c", "target": "d"}])

    report = build_table_tile_quality(paths, min_records=2, expect_pages=2, min_ok_records=2, min_tile_images=12)
    assert report["status"] == "OK"
    assert report["summary"]["table_tile_ok_records"] == 2


def test_build_table_tile_quality_fails_on_missing_records(tmp_path: Path) -> None:
    out = tmp_path / "table_extraction"
    paths = TraceNetTableTilePaths(output_dir=out)
    _write_json(paths.summary, {"status": "FAIL", "records": 0, "selected_pages": 0, "ok_records": 0, "tile_images": 0})
    report = build_table_tile_quality(paths, min_records=1, min_ok_records=1, min_tile_images=1)
    assert report["status"] == "FAIL"
    assert any(not c["ok"] for c in report["checks"])
