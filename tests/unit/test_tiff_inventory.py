from __future__ import annotations

from pathlib import Path

import pytest

from tiff.inventory import build_tiff_inventory_record, inventory_directory


PIL = pytest.importorskip("PIL.Image")


def test_build_tiff_inventory_record(tmp_path: Path):
    image_path = tmp_path / "DWG-12345_REV-C_SHEET-1.tif"
    image = PIL.new("1", (100, 50), color=1)
    image.save(image_path, format="TIFF", dpi=(300, 300))

    record = build_tiff_inventory_record(image_path, source_root=tmp_path)

    assert record.file_name == "DWG-12345_REV-C_SHEET-1.tif"
    assert record.extension == ".tif"
    assert record.file_size_bytes > 0
    assert record.sha256 is not None
    assert len(record.sha256) == 64
    assert record.page_count == 1
    assert record.width_px == 100
    assert record.height_px == 50
    assert record.relative_path == "DWG-12345_REV-C_SHEET-1.tif"


def test_inventory_directory_finds_tiff_files_only(tmp_path: Path):
    image_path = tmp_path / "a.tiff"
    image = PIL.new("L", (10, 10), color=255)
    image.save(image_path, format="TIFF")
    (tmp_path / "ignore.txt").write_text("not a tiff", encoding="utf-8")

    records = inventory_directory(tmp_path, hash_files=False)

    assert len(records) == 1
    assert records[0].file_name == "a.tiff"
    assert records[0].sha256 is None
