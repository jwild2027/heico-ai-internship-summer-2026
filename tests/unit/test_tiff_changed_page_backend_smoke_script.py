from pathlib import Path

from scripts.benchmark.ingestion.smoke_test_changed_page_backend_mode import extract_changed_list_count, find_first_tiff


def test_extract_changed_list_count():
    assert extract_changed_list_count("Changed list count: 17\n") == 17
    assert extract_changed_list_count("no count here") is None


def test_find_first_tiff(tmp_path: Path):
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    target = nested / "000001.tif"
    target.write_bytes(b"fake")
    assert find_first_tiff(root) == target
