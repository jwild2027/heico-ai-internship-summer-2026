from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.trace_net.ingestion.batch_scan_tiffs_to_json import scan_folder_to_json
from scripts.maintenance.ingestion.summarize_tiff_db import summarize_db


def _make_tiff(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("1", (80, 60), 1).save(path)


def test_summarize_db_returns_counts(tmp_path: Path) -> None:
    input_dir = tmp_path / "sample_tiffs"
    output_dir = tmp_path / "json_scans"
    db_path = tmp_path / "db" / "tiff_scans.db"
    _make_tiff(input_dir / "DWG-100_REV-A.tif")

    scan_folder_to_json(
        input_dir=input_dir,
        output_dir=output_dir,
        db_path=db_path,
        hash_file=False,
        run_ocr=False,
    )

    summary = summarize_db(db_path)

    assert summary["counts"]["files"] == 1
    assert summary["counts"]["scan_reports"] == 1
    assert summary["recent_records"][0]["file_name"] == "DWG-100_REV-A.tif"
