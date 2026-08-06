from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_answer import answer_question
from tiff.rag_retriever import (
    classify_query_intent,
    nomenclature_match_score,
    retrieve_rag_context,
)


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
        CREATE TABLE rag_chunks (
            chunk_id TEXT PRIMARY KEY,
            manual_id TEXT,
            page_id TEXT,
            chunk_index INTEGER,
            chunk_text TEXT,
            publication_number TEXT,
            ata_code TEXT,
            page_sequence INTEGER,
            page_label TEXT,
            page_type TEXT,
            title TEXT,
            tiff_path TEXT,
            ocr_text_path TEXT,
            rescarta_object_id TEXT,
            rescarta_page_id TEXT
        );
        CREATE TABLE rag_embeddings (
            chunk_id TEXT,
            model TEXT,
            dim INTEGER,
            embedding_json TEXT,
            PRIMARY KEY (chunk_id, model)
        );
        """
    )
    rows = [
        (
            "cat_1",
            "m1",
            "T.P. 120/1176",
            "25-21-00",
            1056,
            "1056",
            "maintenance_manual_ipl",
            "IPL",
            "cat_1.tif",
            "cat_1.txt",
            "m1",
            "000083",
            "120-37313-001 HOLDER, MAGAZINE",
            0,
        ),
        (
            "mention_1",
            "m1",
            "T.P. 120/1176",
            "25-21-00",
            1059,
            "1059",
            "maintenance_manual_ipl",
            "IPL",
            "mention_1.tif",
            "mention_1.txt",
            "m1",
            "000086",
            "additional page mentioning 120-37313-001",
            0,
        ),
        (
            "semantic_1",
            "m1",
            "T.P. 120/1176",
            "25-21-00",
            621,
            "621",
            "manual_page",
            "Repair",
            "semantic_1.tif",
            "semantic_1.txt",
            "m1",
            "000495",
            "semantic context about passenger seat equipment and magazine stowage",
            0,
        ),
    ]
    conn.executemany("INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.execute(
        """
        INSERT INTO part_catalog_clean VALUES (
            '12037313001', '120-37313-001', 'HOLDER, MAGAZINE', 3, 1,
            'pc1', 'cat_1', 1056, '1056', '25-21-00', 'cat_1.tif', 'cat_1.txt',
            '120-37313-001 HOLDER, MAGAZINE', 'high', '["HOLDER, MAGAZINE"]', CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO part_mentions VALUES ('pm1', '120-37313-001', '12037313001', 'm1', 'mention_1', 1059, '25-21-00', 'mention 120-37313-001', 'ocr')"
    )
    conn.execute(
        """
        INSERT INTO rag_chunks VALUES (
            'chunk_semantic', 'm1', 'semantic_1', 0,
            'This page discusses passenger seat equipment and related magazine stowage hardware.',
            'T.P. 120/1176', '25-21-00', 621, '621', 'manual_page', 'Repair',
            'semantic_1.tif', 'semantic_1.txt', 'm1', '000495'
        )
        """
    )
    conn.execute(
        "INSERT INTO rag_embeddings VALUES ('chunk_semantic', 'bge-m3:latest', 2, '[1.0, 0.0]')"
    )
    conn.commit()
    conn.close()


class FakeRetrieverOllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def embed(self, model: str, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeAnswerOllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def chat(self, model: str, messages, temperature: float = 0.0, num_ctx: int = 8192):
        return "Hybrid summary answer from local sources."


def test_nomenclature_summary_words_do_not_block_catalog_match() -> None:
    assert classify_query_intent("Summarize the sources related to magazine holder parts") == "nomenclature_summary"
    assert nomenclature_match_score(
        "Summarize the sources related to magazine holder parts",
        "HOLDER, MAGAZINE",
    ) > 0


def test_broad_nomenclature_summary_uses_catalog_mentions_and_vector(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "search.db"
    make_hybrid_db(db_path)
    monkeypatch.setattr("tiff.rag_retriever.OllamaClient", FakeRetrieverOllamaClient)

    retrieval = retrieve_rag_context(
        db_path,
        "Summarize the sources related to magazine holder parts",
        use_embeddings=True,
        top_k=4,
    )

    assert retrieval.query_intent == "nomenclature_summary"
    assert retrieval.used_embeddings
    assert any(s.source_type == "nomenclature_catalog_clean" for s in retrieval.sources)
    assert any(s.source_type == "part_mentions" for s in retrieval.sources)
    assert any(s.source_type == "vector" for s in retrieval.sources)


def test_broad_nomenclature_summary_uses_llm_instead_of_deterministic_lookup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "search.db"
    make_hybrid_db(db_path)
    monkeypatch.setattr("tiff.rag_retriever.OllamaClient", FakeRetrieverOllamaClient)
    monkeypatch.setattr("tiff.rag_answer.OllamaClient", FakeAnswerOllamaClient)

    answer = answer_question(
        db_path,
        "Summarize the sources related to magazine holder parts",
        use_embeddings=True,
        use_llm=True,
        top_k=4,
    )

    assert answer.used_llm
    assert answer.used_embeddings
    assert answer.answer == "Hybrid summary answer from local sources."
    assert any(s.source_type == "nomenclature_catalog_clean" for s in answer.sources)
    assert any(s.source_type == "vector" for s in answer.sources)
