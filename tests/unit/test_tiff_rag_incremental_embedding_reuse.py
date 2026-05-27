from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_chunks import build_rag_chunks
from tiff.rag_retriever import build_rag_embeddings


class FakeOllamaClient:
    calls = 0

    def __init__(self, base_url: str):
        self.base_url = base_url

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        FakeOllamaClient.calls += len(texts)
        return [[float(len(text)), 1.0, 0.5] for text in texts]


def _make_db(path: Path, ocr_text: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE pages (
            page_id TEXT PRIMARY KEY,
            manual_id TEXT NOT NULL,
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
        """
    )
    conn.execute(
        """
        INSERT INTO pages (
            page_id, manual_id, publication_number, ata_code, page_sequence,
            page_label, page_type, title, tiff_path, ocr_text_path,
            rescarta_object_id, rescarta_page_id, ocr_text, is_blank
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            "manual_p0001",
            "manual",
            "T.P. 120/1176",
            "25-21-00",
            1,
            "1",
            "manual_page",
            "PAGE",
            "page.tif",
            "page.txt",
            "manual",
            "000001",
            ocr_text,
        ),
    )
    conn.commit()
    conn.close()


def _update_ocr(path: Path, ocr_text: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("UPDATE pages SET ocr_text = ? WHERE page_id = ?", (ocr_text, "manual_p0001"))
    conn.commit()
    conn.close()


def test_rag_embeddings_are_reused_when_chunks_do_not_change(tmp_path: Path, monkeypatch):
    db = tmp_path / "search.db"
    _make_db(db, "120-37313-001 HOLDER, MAGAZINE")
    monkeypatch.setattr("tiff.rag_retriever.OllamaClient", FakeOllamaClient)
    FakeOllamaClient.calls = 0

    build_rag_chunks(db)
    first = build_rag_embeddings(db, model="fake-embed")
    assert first.embeddings_written == 1
    assert first.skipped_existing == 0
    assert FakeOllamaClient.calls == 1

    build_rag_chunks(db)
    second = build_rag_embeddings(db, model="fake-embed")
    assert second.embeddings_written == 0
    assert second.skipped_existing == 1
    assert second.stale_deleted == 0
    assert FakeOllamaClient.calls == 1


def test_rag_embeddings_are_rebuilt_when_chunk_text_changes(tmp_path: Path, monkeypatch):
    db = tmp_path / "search.db"
    _make_db(db, "120-37313-001 HOLDER, MAGAZINE")
    monkeypatch.setattr("tiff.rag_retriever.OllamaClient", FakeOllamaClient)
    FakeOllamaClient.calls = 0

    build_rag_chunks(db)
    first = build_rag_embeddings(db, model="fake-embed")
    assert first.embeddings_written == 1

    _update_ocr(db, "120-37313-001 HOLDER, MAGAZINE changed evidence")
    build_rag_chunks(db)
    second = build_rag_embeddings(db, model="fake-embed")
    assert second.stale_deleted == 1
    assert second.embeddings_written == 1
    assert second.skipped_existing == 0
