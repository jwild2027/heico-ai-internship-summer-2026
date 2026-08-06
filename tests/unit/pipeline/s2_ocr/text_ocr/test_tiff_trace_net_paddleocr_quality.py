import json
from pathlib import Path

from PIL import Image

from tiff.trace_net_paddleocr_experiment import (
    PaddleOcrExperimentOptions,
    PaddleOcrExperimentPaths,
    build_quality_report,
    run_paddleocr_table_experiment,
)


def _make_run(tmp_path: Path) -> PaddleOcrExperimentPaths:
    root = tmp_path / "table_extraction"
    tile_dir = root / "tiles" / "p001"
    tile_dir.mkdir(parents=True)
    Image.new("RGB", (120, 40), "white").save(tile_dir / "tile_001.png")
    plan = root / "table_tile_plan.jsonl"
    plan.write_text(json.dumps({"page_id": "p001", "status": "ok", "route": "table_crop_tile_repair_route_high"}) + "\n", encoding="utf-8")
    paths = PaddleOcrExperimentPaths(tile_plan_path=plan, output_dir=tmp_path / "out")
    run_paddleocr_table_experiment(paths, PaddleOcrExperimentOptions(provider="mock"))
    return paths


def test_quality_passes_for_mock_run(tmp_path: Path) -> None:
    paths = _make_run(tmp_path)
    report = build_quality_report(paths, min_records=1, min_ok_records=1, max_error_records=0, min_part_number_records=1, min_html_table_records=1)
    assert report["status"] == "OK"


def test_quality_fails_when_min_records_too_high(tmp_path: Path) -> None:
    paths = _make_run(tmp_path)
    report = build_quality_report(paths, min_records=2, min_ok_records=1)
    assert report["status"] == "FAIL"
