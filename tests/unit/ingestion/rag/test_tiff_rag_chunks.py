from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_chunks import build_rag_chunks, chunk_text_by_lines


def make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE pages (
            page_id TEXT PRIMARY KEY,
            manual_id TEXT,
            publication_number TEXT,
            ata_code TEXT,
            page_sequence INTEGER,
            page_label TEXT,
            page_type TEXT,
            title TEXT,
            tiff_path TEXT,
            ocr_text_path TEXT,
            rescarta_object_id TEXT,
            rescarta_page_id TEXT,
            ocr_text TEXT,
            is_blank INTEGER DEFAULT 0
        );
        CREATE TABLE part_mentions (
            mention_id TEXT PRIMARY KEY,
            part_number_display TEXT,
            part_number_normalized TEXT,
            manual_id TEXT,
            page_id TEXT,
            page_sequence INTEGER,
            ata_code TEXT,
            context TEXT,
            source TEXT
        );
        CREATE TABLE part_catalog (
            catalog_id TEXT PRIMARY KEY,
            part_number_display TEXT,
            part_number_normalized TEXT,
            nomenclature TEXT,
            item_number TEXT,
            quantity TEXT,
            figure_number TEXT,
            manual_id TEXT,
            page_id TEXT,
            page_sequence INTEGER,
            page_label TEXT,
            ata_code TEXT,
            source_tiff_path TEXT,
            source_ocr_path TEXT,
            evidence_text TEXT,
            confidence TEXT
        );
        INSERT INTO pages VALUES (
            'm1_p000001', 'm1', 'T.P. 120/1176', '25-21-00', 1, '1311',
            'maintenance_manual_ipl', 'IPL', 'page1.tif', 'page1.txt', 'm1', '000001',
            'ITEM PART NUMBER NOMENCLATURE QTY\n12 120-37313-001 MAGAZINE HOLDER 1\nfooter text', 0
        );
        INSERT INTO part_mentions VALUES (
            'pm1', '120-37313-001', '12037313001', 'm1', 'm1_p000001', 1, '25-21-00',
            '12 120-37313-001 MAGAZINE HOLDER 1', 'ocr'
        );
        INSERT INTO part_catalog VALUES (
            'pc1', '120-37313-001', '12037313001', 'MAGAZINE HOLDER', '12', '1', NULL,
            'm1', 'm1_p000001', 1, '1311', '25-21-00', 'page1.tif', 'page1.txt',
            '12 120-37313-001 MAGAZINE HOLDER 1', 'high'
        );
        """
    )
    conn.commit()
    conn.close()


def test_chunk_text_by_lines_preserves_content() -> None:
    chunks = chunk_text_by_lines("A\nB\nC\nD", max_chars=5, overlap_chars=0)
    assert chunks
    assert "A" in chunks[0]
    assert any("D" in c for c in chunks)


def test_build_rag_chunks_creates_fts_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_db(db_path)
    summary = build_rag_chunks(db_path, max_chars=200, overlap_chars=0)
    assert summary.pages_seen == 1
    assert summary.chunks_created == 1
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT chunk_text, part_numbers_json, nomenclatures_json FROM rag_chunks").fetchone()
    assert "MAGAZINE HOLDER" in row[0]
    assert "120-37313-001" in row[1]
    assert "MAGAZINE HOLDER" in row[2]
    fts_count = conn.execute("SELECT COUNT(*) FROM rag_chunk_fts WHERE rag_chunk_fts MATCH 'MAGAZINE'").fetchone()[0]
    assert fts_count == 1
    conn.close()
