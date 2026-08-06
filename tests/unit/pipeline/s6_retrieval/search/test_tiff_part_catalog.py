from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.part_catalog import (
    build_part_catalog,
    clean_nomenclature,
    best_nomenclature_from_lines,
    query_part_catalog,
)
from tiff.search_index import build_search_index, search_db
from tiff.search_web_ui import SearchRequest, render_page


def _make_export(root: Path) -> Path:
    manual = root / "t_p_120_1176"
    (manual / "ocr").mkdir(parents=True)
    (manual / "pages").mkdir(parents=True)
    (manual / "metadata.json").write_text(
        '{"manual_id":"t_p_120_1176","publication_number":"T.P. 120/1176","ata_code":"25-21-00"}',
        encoding="utf-8",
    )
    (manual / "manifest.json").write_text("{}", encoding="utf-8")
    (manual / "pages" / "000001_00000001.tif").write_bytes(b"fake")
    (manual / "ocr" / "000001_00000001.metadata.json").write_text(
        '{"page_type":"maintenance_manual_ipl","page_label":"1311","title":"IPL TABLE"}',
        encoding="utf-8",
    )
    (manual / "ocr" / "000001_00000001.txt").write_text(
        "ITEM PART NUMBER NOMENCLATURE QTY\n"
        "12 120-37313-001 MAGAZINE HOLDER 1\n"
        "13 120-36843-001 BROCHURE HOLDER ASSY 2\n"
        "[bottom_right_title_block] 25-21-00 Page 1311 T.P. 120/1176",
        encoding="utf-8",
    )
    return root


def test_clean_nomenclature_removes_qty() -> None:
    name, qty = clean_nomenclature("MAGAZINE HOLDER 1")
    assert name == "MAGAZINE HOLDER"
    assert qty == "1"


def test_best_nomenclature_from_lines_same_line() -> None:
    name, item, qty, _fig, confidence, evidence = best_nomenclature_from_lines(
        ["12 120-37313-001 MAGAZINE HOLDER 1"],
        "12037313001",
    )
    assert name == "MAGAZINE HOLDER"
    assert item == "12"
    assert qty == "1"
    assert confidence == "high"
    assert "120-37313-001" in evidence


def test_build_part_catalog_and_enrich_search_results(tmp_path: Path) -> None:
    export_root = _make_export(tmp_path / "exports")
    db_path = tmp_path / "tiff_search.db"
    build_search_index(export_root, db_path)
    summary = build_part_catalog(db_path)

    assert summary.catalog_entries >= 2
    assert summary.high_confidence >= 2

    rows = query_part_catalog(db_path, "120-37313-001")
    assert rows
    assert rows[0].nomenclature == "MAGAZINE HOLDER"

    results = search_db(db_path, "120-37313-001", mode="part", limit=5)
    assert results
    assert results[0].part_nomenclature == "MAGAZINE HOLDER"
    assert "MAGAZINE HOLDER" in render_page(SearchRequest(query="120-37313-001", mode="part"), results, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        catalog_count = conn.execute("SELECT count(*) FROM part_catalog").fetchone()[0]
    finally:
        conn.close()
    assert catalog_count >= 2
