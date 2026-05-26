from pathlib import Path

from tiff.search_index import (
    build_search_index,
    extract_part_mentions,
    normalize_part_number,
    search_db,
)


def make_fake_export(root: Path) -> Path:
    manual_dir = root / "t_p_120_1176"
    pages_dir = manual_dir / "pages"
    ocr_dir = manual_dir / "ocr"
    pages_dir.mkdir(parents=True)
    ocr_dir.mkdir(parents=True)

    (manual_dir / "metadata.json").write_text(
        '{"manual_id":"t_p_120_1176","publication_number":"T.P. 120/1176",'
        '"title":"EMBRAER Maintenance Manual with Illustrated Parts List",'
        '"ata_code":"25-21-00"}',
        encoding="utf-8",
    )
    (manual_dir / "manifest.json").write_text('{"page_count":2}', encoding="utf-8")

    (pages_dir / "000001_00000001.tif").write_bytes(b"fake-tiff-1")
    (pages_dir / "000002_00000002.tif").write_bytes(b"fake-tiff-2")

    (ocr_dir / "000001_00000001.txt").write_text(
        "This IPL page mentions part number 120-50648-533 for the oxygen bottle bracket.",
        encoding="utf-8",
    )
    (ocr_dir / "000001_00000001.metadata.json").write_text(
        '{"page_type":"maintenance_manual_ipl","page_label":"371"}',
        encoding="utf-8",
    )
    (ocr_dir / "000002_00000002.txt").write_text(
        "Contents page with ATA 25-21-00 and emergency equipment stowage.",
        encoding="utf-8",
    )
    (ocr_dir / "000002_00000002.metadata.json").write_text(
        '{"page_type":"manual_contents_page","page_label":"i"}',
        encoding="utf-8",
    )
    return manual_dir


def test_normalize_part_number():
    assert normalize_part_number("120-50648-533") == "12050648533"
    assert normalize_part_number("120 50648 533") == "12050648533"
    assert normalize_part_number("pn: ab-123") == "PNAB123"


def test_extract_part_mentions_skips_ata_code():
    mentions = extract_part_mentions("ATA 25-21-00 and part 120-50648-533 are here")
    normalized = {m["normalized"] for m in mentions}
    assert "252100" not in normalized
    assert "12050648533" in normalized


def test_build_and_search_index(tmp_path):
    export_root = tmp_path / "rescarta_exports"
    make_fake_export(export_root)
    db_path = tmp_path / "tiff_search.db"

    summary = build_search_index(export_root, db_path)
    assert summary.manuals == 1
    assert summary.pages == 2
    assert summary.part_mentions >= 1

    part_results = search_db(db_path, "120-50648-533", limit=5)
    assert part_results
    assert part_results[0].match_source == "part-number"
    assert part_results[0].page_label == "371"
    assert part_results[0].tiff_path.endswith("000001_00000001.tif")

    keyword_results = search_db(db_path, "emergency equipment", limit=5, mode="keyword")
    assert keyword_results
    assert keyword_results[0].page_label == "i"
