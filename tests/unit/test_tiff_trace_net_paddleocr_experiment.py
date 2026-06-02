import json
from pathlib import Path

from PIL import Image

from tiff.trace_net_paddleocr_experiment import (
    PaddleOcrExperimentOptions,
    PaddleOcrExperimentPaths,
    extract_part_numbers,
    load_tile_jobs,
    run_paddleocr_table_experiment,
)


def _write_plan(tmp_path: Path) -> Path:
    root = tmp_path / "table_extraction"
    tile_dir = root / "tiles" / "p001"
    tile_dir.mkdir(parents=True)
    for i in range(1, 3):
        Image.new("RGB", (120, 40), "white").save(tile_dir / f"tile_{i:03d}.png")
    plan = root / "table_tile_plan.jsonl"
    plan.write_text(json.dumps({"page_id": "p001", "status": "ok", "route": "table_crop_tile_repair_route_high"}) + "\n", encoding="utf-8")
    return plan


def test_load_tile_jobs_from_directory_convention(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path)
    jobs = load_tile_jobs(plan)
    assert len(jobs) == 2
    assert jobs[0]["page_id"] == "p001"
    assert jobs[0]["tile_id"] == "tile_001"


def test_mock_provider_writes_records_summary_and_graph(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path)
    paths = PaddleOcrExperimentPaths(tile_plan_path=plan, output_dir=tmp_path / "out")
    result = run_paddleocr_table_experiment(paths, PaddleOcrExperimentOptions(provider="mock"))
    summary = result["summary"]
    assert summary["status"] == "OK"
    assert summary["records"] == 2
    assert summary["ok_records"] == 2
    assert summary["part_number_records"] == 2
    assert paths.records_path.exists()
    assert paths.review_html_path.exists()
    assert paths.graph_nodes_path.exists()
    assert paths.graph_edges_path.exists()


def test_planned_provider_is_dependency_free(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path)
    paths = PaddleOcrExperimentPaths(tile_plan_path=plan, output_dir=tmp_path / "planned")
    result = run_paddleocr_table_experiment(paths, PaddleOcrExperimentOptions(provider="planned", max_tiles=1))
    assert result["summary"]["records"] == 1
    assert result["summary"]["planned_records"] == 1


def test_part_number_extraction() -> None:
    parts = extract_part_numbers("Part 120-37313-001 and AM03078-22 appear in this tile.")
    assert "120-37313-001" in parts
    assert "AM03078-22" in parts
