from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_answer import answer_question, build_structured_part_answer
from tiff.rag_retriever import retrieve_rag_context


def make_clean_catalog_db(path: Path) -> None:
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
        CREATE TABLE part_catalog_clean (
            part_number_normalized TEXT PRIMARY KEY,
            part_number_display TEXT NOT NULL,
            canonical_nomenclature TEXT NOT NULL,
            source_count INTEGER NOT NULL,
            variant_count INTEGER NOT NULL,
            best_catalog_id TEXT,
            best_page_id TEXT,
            best_page_sequence INTEGER,
            best_page_label TEXT,
            best_ata_code TEXT,
            source_tiff_path TEXT,
            source_ocr_path TEXT,
            evidence_text TEXT,
            confidence TEXT,
            variants_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO pages VALUES (
            'p0', 'm1', 'T.P. 120/1176', '11-00-66', 42, '1021',
            'maintenance_manual_ipl', 'IPL', 'page1021.tif', 'page1021.txt', 'm1', '000042',
            'reference to 120-37313-001', 0
        );
        INSERT INTO pages VALUES (
            'p1', 'm1', 'T.P. 120/1176', '25-21-00', 83, '1056',
            'maintenance_manual_ipl', 'IPL', 'page1056.tif', 'page1056.txt', 'm1', '000083',
            '12 120-37313-001 HOLDER, MAGAZINE 1', 0
        );
        INSERT INTO pages VALUES (
            'p2', 'm1', 'T.P. 120/1176', '25-21-00', 86, '1059',
            'maintenance_manual_ipl', 'IPL', 'page1059.tif', 'page1059.txt', 'm1', '000086',
            '120-37313-001 appears again', 0
        );
        INSERT INTO part_mentions VALUES (
            'pm0', '120-37313-001', '12037313001', 'm1', 'p0', 42, '11-00-66',
            'reference to 120-37313-001', 'ocr'
        );
        INSERT INTO part_mentions VALUES (
            'pm1', '120-37313-001', '12037313001', 'm1', 'p1', 83, '25-21-00',
            '12 120-37313-001 HOLDER, MAGAZINE 1', 'ocr'
        );
        INSERT INTO part_mentions VALUES (
            'pm2', '120-37313-001', '12037313001', 'm1', 'p2', 86, '25-21-00',
            '120-37313-001 appears again', 'ocr'
        );
        INSERT INTO part_catalog_clean VALUES (
            '12037313001', '120-37313-001', 'HOLDER, MAGAZINE', 6, 4,
            'pc1', 'p1', 83, '1056', '25-21-00', 'page1056.tif', 'page1056.txt',
            '12 120-37313-001 HOLDER, MAGAZINE 1', 'high',
            '["HOLDER, MAGAZINE", "HOLDER, MAGAZINE... VS4956"]', CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()


def test_part_lookup_uses_deterministic_grouped_answer(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_clean_catalog_db(db_path)

    answer = answer_question(
        db_path,
        "What is part number 120-37313-001?",
        use_llm=True,
        use_embeddings=False,
    )

    assert not answer.used_llm
    assert "120-37313-001 is listed as HOLDER, MAGAZINE." in answer.answer
    assert "Primary nomenclature source:" in answer.answer
    assert "Additional pages where this part number appears:" in answer.answer
    assert "page1056.tif" in answer.answer
    assert "additional appearance pages" in answer.answer
    assert "all local sources" not in answer.answer.lower()


def test_retrieval_dedupes_same_page_part_mention(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_clean_catalog_db(db_path)

    retrieval = retrieve_rag_context(
        db_path,
        "What is part number 120-37313-001?",
        use_embeddings=False,
        top_k=6,
    )
    page_source_types = [(s.page_id, s.source_type) for s in retrieval.sources]

    assert ("p1", "part_catalog_clean") in page_source_types
    assert ("p1", "part_mentions") not in page_source_types
    assert ("p0", "part_mentions") in page_source_types
    assert ("p2", "part_mentions") in page_source_types


def test_structured_part_answer_separates_primary_from_mentions(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_clean_catalog_db(db_path)
    retrieval = retrieve_rag_context(db_path, "120-37313-001", use_embeddings=False)

    text = build_structured_part_answer("120-37313-001", retrieval)

    assert text is not None
    assert text.index("Primary nomenclature source:") < text.index("Additional pages where this part number appears:")
    assert "Page 1056" in text
    assert "Page 1021" in text
