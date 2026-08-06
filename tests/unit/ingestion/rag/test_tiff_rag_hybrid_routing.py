from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_chunks import build_rag_chunks
from tiff.rag_retriever import RagSource, retrieve_rag_context
from tiff.rag_router import classify_query


def make_hybrid_db(path: Path) -> None:
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
            'cat', 'm1', 'T.P. 120/1176', '25-21-00', 10, '1056',
            'maintenance_manual_ipl', 'IPL', 'cat.tif', 'cat.txt', 'm1', '000010',
            '120-37313-001 HOLDER, MAGAZINE', 0
        );
        INSERT INTO pages VALUES (
            'mention', 'm1', 'T.P. 120/1176', '25-21-00', 11, '1057',
            'maintenance_manual_ipl', 'IPL', 'mention.tif', 'mention.txt', 'm1', '000011',
            'additional mention of 120-37313-001', 0
        );
        INSERT INTO pages VALUES (
            'keyword', 'm1', 'T.P. 120/1176', '25-21-00', 12, '1058',
            'maintenance_manual_ipl', 'IPL', 'keyword.tif', 'keyword.txt', 'm1', '000012',
            'magazine holder parts are listed in the passenger seat section', 0
        );
        INSERT INTO part_mentions VALUES (
            'pm1', '120-37313-001', '12037313001', 'm1', 'mention', 11, '25-21-00',
            'additional mention of 120-37313-001', 'ocr'
        );
        INSERT INTO part_catalog_clean VALUES (
            '12037313001', '120-37313-001', 'HOLDER, MAGAZINE', 2, 1,
            'pc1', 'cat', 10, '1056', '25-21-00', 'cat.tif', 'cat.txt',
            '120-37313-001 HOLDER, MAGAZINE', 'high', '["HOLDER, MAGAZINE"]', CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()


def test_router_keeps_lookups_structured_but_summaries_hybrid() -> None:
    part = classify_query("What is part number 120-37313-001?")
    assert part.answer_mode == "part_lookup"
    assert part.retrieval_mode == "structured"
    assert part.allow_structured_answer

    locate = classify_query("Where is magazine holder shown?")
    assert locate.answer_mode == "nomenclature_locate"
    assert locate.retrieval_mode == "structured"
    assert locate.allow_structured_answer

    summary = classify_query("Summarize the sources related to magazine holder parts.")
    assert summary.answer_mode == "nomenclature_summary"
    assert summary.retrieval_mode == "hybrid"
    assert not summary.allow_structured_answer
    assert summary.should_try_embeddings


def test_hybrid_summary_uses_catalog_mentions_keywords_and_vectors(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "search.db"
    make_hybrid_db(db_path)
    build_rag_chunks(db_path)

    def fake_vector_sources(*args, **kwargs):
        return [
            RagSource(
                source_id="vector:seat-context",
                source_type="vector",
                page_id="vector_page",
                manual_id="m1",
                chunk_text="semantic context for magazine holder installed near passenger seat",
                score=0.77,
                publication_number="T.P. 120/1176",
                ata_code="25-21-00",
                page_sequence=99,
                page_label="1099",
                tiff_path="vector.tif",
                ocr_text_path="vector.txt",
            )
        ], True, []

    monkeypatch.setattr("tiff.rag_retriever.retrieve_embedding_sources", fake_vector_sources)

    retrieval = retrieve_rag_context(
        db_path,
        "Summarize the sources related to magazine holder parts.",
        use_embeddings=True,
        top_k=4,
    )

    source_types = [source.source_type for source in retrieval.sources]
    assert "nomenclature_catalog_clean" in source_types
    assert "part_mentions" in source_types
    assert any(source_type.startswith("keyword") for source_type in source_types)
    assert "vector" in source_types
    assert retrieval.used_embeddings
    assert retrieval.retrieval_mode == "hybrid"
