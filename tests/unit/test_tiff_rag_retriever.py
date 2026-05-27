from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_chunks import build_rag_chunks
from tiff.rag_retriever import cosine_similarity, deserialize_embedding, retrieve_rag_context, serialize_embedding


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
        INSERT INTO pages VALUES (
            'm1_p000002', 'm1', 'T.P. 120/1176', '25-21-00', 2, '1312',
            'maintenance_manual_ipl', 'IPL', 'page2.tif', 'page2.txt', 'm1', '000002',
            'oxygen bottle bracket installation text', 0
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


def test_embedding_serialization_and_cosine() -> None:
    blob = serialize_embedding([1, 0, 1])
    assert deserialize_embedding(blob) == [1.0, 0.0, 1.0]
    assert round(cosine_similarity([1, 0], [1, 0]), 6) == 1.0
    assert round(cosine_similarity([1, 0], [0, 1]), 6) == 0.0


def test_retrieve_part_catalog_first(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_db(db_path)
    build_rag_chunks(db_path)
    result = retrieve_rag_context(db_path, "What is 120-37313-001?", use_embeddings=False)
    assert result.sources
    first = result.sources[0]
    assert first.source_type == "part_catalog"
    assert first.part_nomenclature == "MAGAZINE HOLDER"
    assert first.tiff_path == "page1.tif"


def test_retrieve_keyword_chunk(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_db(db_path)
    build_rag_chunks(db_path)
    result = retrieve_rag_context(db_path, "oxygen bottle", use_embeddings=False)
    assert result.sources
    assert any("oxygen" in s.chunk_text.lower() for s in result.sources)
