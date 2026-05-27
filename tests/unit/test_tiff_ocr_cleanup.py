from pathlib import Path
import sqlite3

from tiff.ocr_cleanup import (
    clean_ocr_text,
    clean_part_nomenclature,
    rebuild_clean_part_catalog_pipeline,
    run_ocr_cleanup,
)
from tiff.rag_retriever import retrieve_rag_context


def test_clean_part_nomenclature_removes_dot_leaders_and_effectivity_codes():
    assert clean_part_nomenclature("HOLDER, MAGAZINE... VWS4956") == "HOLDER, MAGAZINE"
    assert clean_part_nomenclature("HOLDER, MAGAZINE........0..0..:EEEE WS4956") == "HOLDER, MAGAZINE"


def test_clean_ocr_text_preserves_part_number_and_removes_region_labels():
    cleaned, removed = clean_ocr_text(
        "[bottom_right_title_block] [T].[P]. [120]/[1176]\n"
        "+ + + + +\n"
        "12 120-37313-001 HOLDER, MAGAZINE........0..0..:EEEE WS4956 1"
    )
    assert "bottom_right_title_block" not in cleaned
    assert "T.P. 120/1176" in cleaned
    assert "120-37313-001" in cleaned
    assert removed >= 1


def _make_minimal_search_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE schema_info (key TEXT PRIMARY KEY, value TEXT);
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
                thumbnail_path TEXT,
                rescarta_object_id TEXT,
                rescarta_page_id TEXT,
                ocr_text TEXT,
                is_blank INTEGER,
                metadata_json TEXT
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
            """
        )
        ocr_text = "12 120-37313-001 HOLDER, MAGAZINE........0..0..:EEEE WS4956 1"
        conn.execute(
            """
            INSERT INTO pages (
                page_id, manual_id, publication_number, ata_code, page_sequence,
                page_label, page_type, title, tiff_path, ocr_text_path,
                rescarta_object_id, rescarta_page_id, ocr_text, is_blank, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "m_p000083",
                "m",
                "T.P. 120/1176",
                "25-21-00",
                83,
                "1056",
                "maintenance_manual_ipl",
                None,
                "page083.tif",
                "page083.txt",
                "m",
                "000083",
                ocr_text,
                0,
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO part_mentions (
                mention_id, part_number_display, part_number_normalized,
                manual_id, page_id, page_sequence, ata_code, context, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pm1",
                "120-37313-001",
                "12037313001",
                "m",
                "m_p000083",
                83,
                "25-21-00",
                ocr_text,
                "ocr",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_rebuild_clean_part_catalog_pipeline_creates_canonical_name(tmp_path):
    db_path = tmp_path / "search.db"
    _make_minimal_search_db(db_path)
    summary = rebuild_clean_part_catalog_pipeline(db_path)
    assert summary.pages_cleaned == 1
    assert summary.canonical_parts == 1

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT canonical_nomenclature, source_count FROM part_catalog_clean WHERE part_number_normalized = ?",
            ("12037313001",),
        ).fetchone()
        assert row == ("HOLDER, MAGAZINE", 1)
    finally:
        conn.close()


def test_rag_retriever_prefers_clean_catalog_source(tmp_path):
    db_path = tmp_path / "search.db"
    _make_minimal_search_db(db_path)
    rebuild_clean_part_catalog_pipeline(db_path)

    result = retrieve_rag_context(db_path, "What is part number 120-37313-001?", use_embeddings=False)
    assert result.sources
    assert result.sources[0].source_type == "part_catalog_clean"
    assert result.sources[0].part_nomenclature == "HOLDER, MAGAZINE"
