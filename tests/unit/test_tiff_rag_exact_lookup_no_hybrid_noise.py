from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_retriever import retrieve_rag_context


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
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
                ocr_text TEXT
            );
            CREATE TABLE part_catalog_clean (
                part_number_display TEXT,
                part_number_normalized TEXT,
                canonical_nomenclature TEXT,
                evidence_text TEXT,
                source_count INTEGER,
                variant_count INTEGER,
                variants_json TEXT,
                best_page_id TEXT,
                best_page_label TEXT,
                best_page_sequence INTEGER,
                source_tiff_path TEXT,
                source_ocr_path TEXT
            );
            CREATE TABLE part_mentions (
                part_number_display TEXT,
                part_number_normalized TEXT,
                page_id TEXT,
                context TEXT
            );
            CREATE TABLE source_links (
                page_id TEXT PRIMARY KEY,
                tiff_path TEXT,
                ocr_text_path TEXT,
                tiff_uri TEXT,
                ocr_uri TEXT,
                rescarta_object_id TEXT,
                rescarta_page_id TEXT,
                rescarta_url TEXT,
                source_url TEXT
            );
            """
        )
        pages = [
            ("p1", "m1", "T.P. 120/1176", "25-21-00", 83, "1056", "maintenance_manual_ipl", "", "p1.tif", "p1.txt", "m1", "000083", "120-37313-001 HOLDER, MAGAZINE"),
            ("p2", "m1", "T.P. 120/1176", "25-21-00", 86, "1059", "maintenance_manual_ipl", "", "p2.tif", "p2.txt", "m1", "000086", "120-37313-001"),
        ]
        conn.executemany("INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", pages)
        conn.execute(
            "INSERT INTO part_catalog_clean VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "120-37313-001",
                "12037313001",
                "HOLDER, MAGAZINE",
                "120-37313-001 HOLDER, MAGAZINE",
                1,
                1,
                "[]",
                "p1",
                "1056",
                83,
                "p1.tif",
                "p1.txt",
            ),
        )
        conn.executemany(
            "INSERT INTO part_mentions VALUES (?,?,?,?)",
            [
                ("120-37313-001", "12037313001", "p1", "catalog row"),
                ("120-37313-001", "12037313001", "p2", "additional row"),
            ],
        )
        conn.executemany(
            "INSERT INTO source_links VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("p1", "p1.tif", "p1.txt", "file:///p1.tif", "file:///p1.txt", "m1", "000083", "http://rescarta/m1/000083", "http://rescarta/m1/000083"),
                ("p2", "p2.tif", "p2.txt", "file:///p2.tif", "file:///p2.txt", "m1", "000086", "http://rescarta/m1/000086", "http://rescarta/m1/000086"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_exact_part_lookup_ignores_global_hybrid_retrieval(tmp_path: Path):
    db = tmp_path / "search.db"
    _make_db(db)

    result = retrieve_rag_context(
        db,
        "What is part number 120-37313-001?",
        answer_mode="auto",
        retrieval_mode="hybrid",
        use_embeddings=True,
        top_k=8,
    )

    assert result.answer_mode == "part_lookup"
    assert result.retrieval_mode == "structured"
    assert result.used_embeddings is False
    assert [s.source_type for s in result.sources] == ["part_catalog_clean", "part_mentions"]
    assert result.sources[0].rescarta_url == "http://rescarta/m1/000083"


def test_force_embeddings_can_still_override_exact_lookup(monkeypatch, tmp_path: Path):
    db = tmp_path / "search.db"
    _make_db(db)

    def fake_embedding_sources(*args, **kwargs):
        return [], True, []

    monkeypatch.setattr("tiff.rag_retriever.retrieve_embedding_sources", fake_embedding_sources)
    result = retrieve_rag_context(
        db,
        "What is part number 120-37313-001?",
        answer_mode="auto",
        retrieval_mode="hybrid",
        use_embeddings=True,
        force_embeddings=True,
        top_k=8,
    )

    assert result.used_embeddings is True
