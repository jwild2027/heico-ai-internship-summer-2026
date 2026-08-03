import sqlite3
from pathlib import Path

from PIL import Image

from scripts.build.ingestion.scan_changed_tiffs import read_path_list, resolve_listed_path, scan_changed_tiffs


def make_tiff(path: Path, color: int = 255) -> None:
    img = Image.new("1", (64, 32), color=color)
    img.save(path, format="TIFF")


def test_read_path_list_ignores_blanks_and_comments(tmp_path):
    file_list = tmp_path / "changed.txt"
    file_list.write_text("\n# comment\na.tif\n\n b.tiff \n", encoding="utf-8")
    assert read_path_list(file_list) == ["a.tif", "b.tiff"]


def test_resolve_relative_path_against_source_root(tmp_path):
    root = tmp_path / "root"
    assert resolve_listed_path("a/b.tif", source_root=root) == root / "a/b.tif"


def test_empty_changed_list_writes_summary_without_scanning(tmp_path):
    file_list = tmp_path / "changed.txt"
    file_list.write_text("", encoding="utf-8")
    summary = tmp_path / "summary.json"

    result = scan_changed_tiffs(
        file_list=file_list,
        output_dir=tmp_path / "json",
        db_path=None,
        summary_output=summary,
    )

    assert result.total_listed == 0
    assert result.total_attempted == 0
    assert result.total_succeeded == 0
    assert summary.exists()


def test_scan_one_changed_tiff_to_json_and_sqlite(tmp_path):
    root = tmp_path / "sample"
    root.mkdir()
    tiff_path = root / "00000001.tif"
    make_tiff(tiff_path)

    file_list = tmp_path / "changed.txt"
    file_list.write_text("00000001.tif\n", encoding="utf-8")

    db_path = tmp_path / "scan.db"
    result = scan_changed_tiffs(
        file_list=file_list,
        output_dir=tmp_path / "json",
        db_path=db_path,
        source_root=root,
        run_ocr=False,
    )

    assert result.total_listed == 1
    assert result.total_attempted == 1
    assert result.total_succeeded == 1
    assert (tmp_path / "json" / "00000001.tif.scan.json").exists()

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM tiff_files").fetchone()[0]
    finally:
        conn.close()
    assert count == 1
