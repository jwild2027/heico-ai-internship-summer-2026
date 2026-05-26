from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PIL import Image

from scripts.batch_scan_tiffs_to_json import iter_tiff_files, report_output_path, scan_folder_to_json


def _make_tiff(path: Path, size: tuple[int, int] = (120, 80)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("1", size, 1).save(path)


def test_iter_tiff_files_is_recursive_and_filters_extensions(tmp_path: Path) -> None:
    _make_tiff(tmp_path / "a.tif")
    _make_tiff(tmp_path / "nested" / "b.tiff")
    (tmp_path / "ignore.txt").write_text("not a tiff", encoding="utf-8")

    paths = list(iter_tiff_files(tmp_path, recursive=True))

    assert [p.name for p in paths] == ["a.tif", "b.tiff"]


def test_report_output_path_preserves_relative_folders(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "out"
    tiff_path = input_dir / "nested" / "a.tif"

    result = report_output_path(tiff_path, input_dir=input_dir, output_dir=output_dir)

    assert result == output_dir / "nested" / "a.tif.scan.json"


def test_scan_folder_to_json_writes_reports_and_sqlite(tmp_path: Path) -> None:
    input_dir = tmp_path / "sample_tiffs"
    output_dir = tmp_path / "json_scans"
    db_path = tmp_path / "db" / "tiff_scans.db"
    _make_tiff(input_dir / "DWG-100_REV-A_SHEET-1-OF-1.tif")
    _make_tiff(input_dir / "manual" / "00000018.tif")

    result = scan_folder_to_json(
        input_dir=input_dir,
        output_dir=output_dir,
        db_path=db_path,
        hash_file=False,
        run_ocr=False,
        recursive=True,
    )

    assert result.total_discovered == 2
    assert result.total_succeeded == 2
    assert result.total_failed == 0
    assert (output_dir / "DWG-100_REV-A_SHEET-1-OF-1.tif.scan.json").exists()
    assert (output_dir / "manual" / "00000018.tif.scan.json").exists()

    report = json.loads((output_dir / "DWG-100_REV-A_SHEET-1-OF-1.tif.scan.json").read_text(encoding="utf-8"))
    assert report["file"]["file_name"] == "DWG-100_REV-A_SHEET-1-OF-1.tif"

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM tiff_files").fetchone()[0]
    assert count == 2
