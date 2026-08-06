from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_answer import answer_question, build_rag_prompt, extractive_answer
from tiff.rag_chunks import build_rag_chunks
from tiff.rag_retriever import retrieve_rag_context


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
            '12 120-37313-001 MAGAZINE HOLDER 1', 0
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


def test_build_prompt_mentions_no_guessing(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_db(db_path)
    build_rag_chunks(db_path)
    retrieval = retrieve_rag_context(db_path, "What is 120-37313-001?", use_embeddings=False)
    messages = build_rag_prompt("What is 120-37313-001?", retrieval.sources)
    assert "Do not guess" in messages[0]["content"]
    assert "MAGAZINE HOLDER" in messages[1]["content"]


def test_extractive_answer_uses_part_catalog(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_db(db_path)
    build_rag_chunks(db_path)
    retrieval = retrieve_rag_context(db_path, "What is 120-37313-001?", use_embeddings=False)
    text = extractive_answer("What is 120-37313-001?", retrieval)
    assert "120-37313-001 is listed as MAGAZINE HOLDER" in text
    assert "page1.tif" in text


def test_answer_question_no_llm(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_db(db_path)
    build_rag_chunks(db_path)
    answer = answer_question(db_path, "What is 120-37313-001?", use_llm=False, use_embeddings=False)
    assert not answer.used_llm
    assert "MAGAZINE HOLDER" in answer.answer
    assert answer.sources
