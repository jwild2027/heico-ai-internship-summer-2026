from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.changed_page_backend import (
    delete_page_scoped_backend_rows,
    read_changed_tiffs,
    run_changed_page_backend_update,
    tiff_paths_match,
    update_search_index_for_changed_pages,
)
from tiff.search_index import build_search_index


def _write_export(root: Path, page1_text: str = "001 120-37313-001 HOLDER, MAGAZINE 1") -> Path:
    manual = root / "t_p_120_1176"
    (manual / "pages").mkdir(parents=True)
    (manual / "ocr").mkdir(parents=True)
    (manual / "metadata.json").write_text(
        '{"manual_id":"t_p_120_1176","publication_number":"T.P. 120/1176","ata_code":"25-21-00"}',
        encoding="utf-8",
    )
    (manual / "manifest.json").write_text("{}", encoding="utf-8")
    (manual / "pages" / "000001_00000001.tif").write_bytes(b"tiff1")
    (manual / "pages" / "000002_00000002.tif").write_bytes(b"tiff2")
    (manual / "ocr" / "000001_00000001.txt").write_text(page1_text, encoding="utf-8")
    (manual / "ocr" / "000001_00000001.metadata.json").write_text(
        '{"page_label":"1056","ata_code":"25-21-00","page_type":"maintenance_manual_ipl"}',
        encoding="utf-8",
    )
    (manual / "ocr" / "000002_00000002.txt").write_text("002 120-36843-001 HOLDER, MAGAZINE 1", encoding="utf-8")
    (manual / "ocr" / "000002_00000002.metadata.json").write_text(
        '{"page_label":"1082","ata_code":"25-21-00","page_type":"maintenance_manual_ipl"}',
        encoding="utf-8",
    )
    return manual


def test_tiff_paths_match_rescarta_suffix_style():
    assert tiff_paths_match(
        "local_data/sample_tiffs/00000083.tif",
        "local_data/rescarta_exports/t_p_120_1176/pages/000083_00000083.tif",
    )
    assert tiff_paths_match(
        "C:/data/00000083.tif",
        "local_data/rescarta_exports/t_p_120_1176/pages/000083_00000083.tif",
    )
    assert not tiff_paths_match("00000083.tif", "000099_00000099.tif")


def test_read_changed_tiffs_ignores_blank_lines_and_comments(tmp_path: Path):
    changed = tmp_path / "changed.txt"
    changed.write_text("\n# comment\n'a.tif'\n\"b.tif\"\n", encoding="utf-8")
    assert read_changed_tiffs(changed) == ("a.tif", "b.tif")


def test_incremental_search_update_changes_only_matching_page(tmp_path: Path):
    export_root = tmp_path / "exports"
    manual = _write_export(export_root)
    db_path = tmp_path / "search.db"
    build_search_index(export_root, db_path, reset=True)

    # Change only page 1 in the staging export.
    (manual / "ocr" / "000001_00000001.txt").write_text("001 120-37313-001 HOLDER, UPDATED 1", encoding="utf-8")
    changed_list = tmp_path / "changed.txt"
    changed_list.write_text(str(manual / "pages" / "000001_00000001.tif"), encoding="utf-8")

    summary = update_search_index_for_changed_pages(
        export_root=export_root,
        db_path=db_path,
        changed_list_path=changed_list,
    )
    assert summary.affected_pages == 1
    assert summary.search_pages_updated == 1
    assert summary.part_mentions_updated >= 1

    conn = sqlite3.connect(str(db_path))
    try:
        page1 = conn.execute("SELECT ocr_text FROM pages WHERE page_id = 't_p_120_1176_p000001'").fetchone()[0]
        page2 = conn.execute("SELECT ocr_text FROM pages WHERE page_id = 't_p_120_1176_p000002'").fetchone()[0]
    finally:
        conn.close()
    assert "UPDATED" in page1
    assert "120-36843-001" in page2


def test_delete_page_scoped_backend_rows_removes_only_requested_page(tmp_path: Path):
    db_path = tmp_path / "search.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE pages(page_id TEXT PRIMARY KEY);
            CREATE TABLE part_mentions(mention_id TEXT PRIMARY KEY, page_id TEXT);
            CREATE TABLE part_catalog(catalog_id TEXT PRIMARY KEY, page_id TEXT);
            CREATE TABLE rag_chunks(chunk_id TEXT PRIMARY KEY, page_id TEXT);
            CREATE TABLE rag_embeddings(chunk_id TEXT, model TEXT, embedding_json TEXT, dim INTEGER);
            INSERT INTO pages VALUES ('p1'), ('p2');
            INSERT INTO part_mentions VALUES ('m1','p1'), ('m2','p2');
            INSERT INTO part_catalog VALUES ('c1','p1'), ('c2','p2');
            INSERT INTO rag_chunks VALUES ('r1','p1'), ('r2','p2');
            INSERT INTO rag_embeddings VALUES ('r1','bge','[]',0), ('r2','bge','[]',0);
            """
        )
        counts = delete_page_scoped_backend_rows(conn, ["p1"])
        conn.commit()
        assert counts.part_mentions == 1
        assert counts.part_catalog == 1
        assert counts.rag_embeddings == 1
        assert conn.execute("SELECT count(*) FROM pages WHERE page_id='p2'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM part_mentions WHERE page_id='p2'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM rag_embeddings WHERE chunk_id='r2'").fetchone()[0] == 1
    finally:
        conn.close()


def test_changed_page_backend_update_returns_unmatched_files(tmp_path: Path):
    export_root = tmp_path / "exports"
    _write_export(export_root)
    db_path = tmp_path / "search.db"
    build_search_index(export_root, db_path, reset=True)
    changed_list = tmp_path / "changed.txt"
    changed_list.write_text("missing_99999999.tif", encoding="utf-8")

    summary = run_changed_page_backend_update(
        export_root=export_root,
        db_path=db_path,
        changed_list_path=changed_list,
    )
    assert summary.affected_pages == 0
    assert summary.unmatched_changed_files == ["missing_99999999.tif"]
