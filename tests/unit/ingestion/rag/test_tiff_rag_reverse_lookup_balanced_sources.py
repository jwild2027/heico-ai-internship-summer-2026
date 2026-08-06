from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

from tiff.rag_answer import answer_question
from tiff.rag_retriever import retrieve_rag_context


def make_multi_part_reverse_lookup_db(path: Path) -> None:
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
        """
    )
    parts = [
        ("120-36843-001", "12036843001", 100),
        ("120-37313-001", "12037313001", 200),
        ("120-37313-535", "12037313535", 300),
    ]
    for part_display, part_norm, base_seq in parts:
        catalog_page = f"cat_{part_norm}"
        conn.execute(
            "INSERT INTO pages VALUES (?, 'm1', 'T.P. 120/1176', '25-21-00', ?, ?, 'maintenance_manual_ipl', 'IPL', ?, ?, 'm1', ?, ?, 0)",
            (
                catalog_page,
                base_seq,
                str(base_seq),
                f"{catalog_page}.tif",
                f"{catalog_page}.txt",
                f"{base_seq:06d}",
                f"{part_display} HOLDER, MAGAZINE",
            ),
        )
        conn.execute(
            "INSERT INTO part_catalog_clean VALUES (?, ?, 'HOLDER, MAGAZINE', 3, 1, ?, ?, ?, ?, '25-21-00', ?, ?, ?, 'high', '[\"HOLDER, MAGAZINE\"]', CURRENT_TIMESTAMP)",
            (
                part_norm,
                part_display,
                f"pc_{part_norm}",
                catalog_page,
                base_seq,
                str(base_seq),
                f"{catalog_page}.tif",
                f"{catalog_page}.txt",
                f"{part_display} HOLDER, MAGAZINE",
            ),
        )
        # Include a same-page mention plus several additional mention pages.
        for offset in range(4):
            page_id = catalog_page if offset == 0 else f"mention_{part_norm}_{offset}"
            seq = base_seq + offset
            if offset:
                conn.execute(
                    "INSERT INTO pages VALUES (?, 'm1', 'T.P. 120/1176', '25-21-00', ?, ?, 'maintenance_manual_ipl', 'IPL', ?, ?, 'm1', ?, ?, 0)",
                    (
                        page_id,
                        seq,
                        str(seq),
                        f"{page_id}.tif",
                        f"{page_id}.txt",
                        f"{seq:06d}",
                        f"additional mention {part_display}",
                    ),
                )
            conn.execute(
                "INSERT INTO part_mentions VALUES (?, ?, ?, 'm1', ?, ?, '25-21-00', ?, 'ocr')",
                (
                    f"pm_{part_norm}_{offset}",
                    part_display,
                    part_norm,
                    page_id,
                    seq,
                    f"additional mention {part_display}",
                ),
            )
    conn.commit()
    conn.close()


def test_reverse_lookup_balances_mentions_for_each_matching_part(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_multi_part_reverse_lookup_db(db_path)

    retrieval = retrieve_rag_context(db_path, "Where is magazine holder shown?", use_embeddings=False, top_k=3)

    catalog_parts = [
        s.matched_part_number
        for s in retrieval.sources
        if s.source_type == "nomenclature_catalog_clean"
    ]
    assert catalog_parts == ["120-36843-001", "120-37313-001", "120-37313-535"]

    mention_counts = Counter(
        s.matched_part_number
        for s in retrieval.sources
        if s.source_type == "part_mentions"
    )
    assert mention_counts["120-36843-001"] == 3
    assert mention_counts["120-37313-001"] == 3
    assert mention_counts["120-37313-535"] == 3


def test_reverse_lookup_answer_lists_pages_under_each_part(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    make_multi_part_reverse_lookup_db(db_path)

    answer = answer_question(db_path, "magazine holder", use_llm=True, use_embeddings=False, top_k=3)

    assert not answer.used_llm
    assert "Match 1: 120-36843-001" in answer.answer
    assert "Additional pages where 120-36843-001 appears:" in answer.answer
    assert "Additional pages where 120-37313-001 appears:" in answer.answer
    assert "Additional pages where 120-37313-535 appears:" in answer.answer
