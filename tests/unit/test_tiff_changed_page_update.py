from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.changed_page_update import (
    paths_might_refer_to_same_page,
    resolve_affected_pages,
    run_changed_page_backend_update,
)
from tiff.search_index import build_search_index


def make_export(root: Path, text: str = "120-37313-001 HOLDER, MAGAZINE 1") -> Path:
    manual = root / "t_p_120_1176"
    (manual / "pages").mkdir(parents=True)
    (manual / "ocr").mkdir(parents=True)
    (manual / "metadata.json").write_text('{"manual_id":"t_p_120_1176","publication_number":"T.P. 120/1176","ata_code":"25-21-00"}', encoding="utf-8")
    (manual / "manifest.json").write_text("{}", encoding="utf-8")
    (manual / "pages" / "000001_00000001.tif").write_bytes(b"fake-tiff")
    (manual / "ocr" / "000001_00000001.txt").write_text(text, encoding="utf-8")
    (manual / "ocr" / "000001_00000001.metadata.json").write_text(
        '{"page_label":"1056","page_type":"maintenance_manual_ipl","ata_code":"25-21-00"}',
        encoding="utf-8",
    )
    return root


def test_paths_match_raw_and_rescarta_staged_tiff_name():
    assert paths_might_refer_to_same_page(
        "local_data/sample_tiffs/00000001.tif",
        "local_data/rescarta_exports/t_p_120_1176/pages/000001_00000001.tif",
    )


def test_resolve_affected_pages_matches_staged_page(tmp_path: Path):
    export_root = make_export(tmp_path / "export")
    db_path = tmp_path / "search.db"
    build_search_index(export_root, db_path)

    matches, unmatched = resolve_affected_pages(db_path, ["local_data/sample_tiffs/00000001.tif"])

    assert unmatched == []
    assert [m.page_id for m in matches] == ["t_p_120_1176_p000001"]


def test_changed_page_update_refreshes_catalog_and_rag_chunks(tmp_path: Path):
    export_root = make_export(tmp_path / "export", "120-37313-001 HOLDER, MAGAZINE 1")
    db_path = tmp_path / "search.db"
    build_search_index(export_root, db_path)

    summary = run_changed_page_backend_update(
        db_path=db_path,
        export_root=export_root,
        changed_paths=["local_data/sample_tiffs/00000001.tif"],
    )

    assert summary.pages_updated == 1
    assert summary.clean_pages_updated == 1
    assert summary.catalog_rows_updated >= 1
    assert summary.canonical_parts_updated >= 1
    assert summary.rag_chunks_updated >= 1

    conn = sqlite3.connect(str(db_path))
    try:
        part = conn.execute(
            "SELECT canonical_nomenclature FROM part_catalog_clean WHERE part_number_normalized = ?",
            ("12037313001",),
        ).fetchone()
        assert part is not None
        assert part[0] == "HOLDER, MAGAZINE"
        chunks = conn.execute("SELECT count(*) FROM rag_chunks WHERE page_id = ?", ("t_p_120_1176_p000001",)).fetchone()[0]
        assert chunks >= 1
    finally:
        conn.close()
