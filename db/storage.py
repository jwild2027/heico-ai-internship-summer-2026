"""db/storage.py — SQLite connection and all storage operations.

Usage:
    from db.storage import RAGDatabase

    db = RAGDatabase("rag.db")          # creates file + tables on first run
    db = RAGDatabase()                  # defaults to rag.db in cwd

All write methods return the id of the inserted/updated row.
All read methods return dicts or lists of dicts (no ORM objects).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from db.schema import ALL_TABLES, CREATE_INDEXES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


# ---------------------------------------------------------------------------
# RAGDatabase
# ---------------------------------------------------------------------------

class RAGDatabase:
    """Thin wrapper around a SQLite connection for the RAG pipeline.

    Thread safety: create one instance per thread, or use check_same_thread=False
    carefully with external locking.
    """

    def __init__(self, db_path: str | Path = "rag.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            for ddl in ALL_TABLES:
                self._conn.execute(ddl)
            for stmt in CREATE_INDEXES.strip().splitlines():
                stmt = stmt.strip()
                if stmt:
                    self._conn.execute(stmt)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------

    def upsert_document(
        self,
        filepath: Path,
        *,
        doc_id: Optional[str] = None,
    ) -> tuple[str, bool]:
        """Insert or update a document record.

        Returns (doc_id, is_new).  If the PDF checksum already exists the
        existing record is returned unchanged (no duplicate ingestion).
        """
        filepath = Path(filepath).resolve()
        checksum = _sha256(filepath)

        existing = self._conn.execute(
            "SELECT id FROM documents WHERE pdf_checksum = ?", (checksum,)
        ).fetchone()
        if existing:
            return existing["id"], False

        doc_id = doc_id or _new_id()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO documents (id, filename, filepath, pdf_checksum, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (doc_id, filepath.name, str(filepath), checksum),
            )
        return doc_id, True

    def set_document_page_count(self, doc_id: str, page_count: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE documents SET page_count=?, updated_at=? WHERE id=?",
                (page_count, _now(), doc_id),
            )

    def set_document_status(self, doc_id: str, status: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE documents SET status=?, updated_at=? WHERE id=?",
                (status, _now(), doc_id),
            )

    def get_document(self, doc_id: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_documents(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM documents ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_document_content(self, doc_id: str) -> dict[str, int]:
        """Delete pages, page_texts, images, and chunks for a doc, keeping
        the document row + its ingestion_runs history.

        Use this at the start of a re-ingest so rows don't accumulate across
        runs. Returns a count of rows deleted per table so the caller can log
        what was cleared.
        """
        counts = {"chunks": 0, "page_texts": 0, "images": 0, "pages": 0}
        with self._conn:
            counts["chunks"] = self._conn.execute(
                "DELETE FROM chunks WHERE doc_id=?", (doc_id,)
            ).rowcount

            page_ids = [
                r["id"] for r in self._conn.execute(
                    "SELECT id FROM pages WHERE doc_id=?", (doc_id,)
                ).fetchall()
            ]
            if page_ids:
                placeholders = ",".join("?" * len(page_ids))
                counts["page_texts"] = self._conn.execute(
                    f"DELETE FROM page_texts WHERE page_id IN ({placeholders})",
                    page_ids,
                ).rowcount
                counts["images"] = self._conn.execute(
                    f"DELETE FROM images WHERE page_id IN ({placeholders})",
                    page_ids,
                ).rowcount
                counts["pages"] = self._conn.execute(
                    f"DELETE FROM pages WHERE id IN ({placeholders})", page_ids
                ).rowcount
        return counts

    def delete_document(self, doc_id: str) -> None:
        """Delete a document and all dependent rows (cascades via FK)."""
        with self._conn:
            # Delete in FK-safe order
            chunk_ids = [
                r["id"] for r in self._conn.execute(
                    "SELECT id FROM chunks WHERE doc_id=?", (doc_id,)
                ).fetchall()
            ]
            if chunk_ids:
                placeholders = ",".join("?" * len(chunk_ids))
                self._conn.execute(
                    f"DELETE FROM chunks WHERE id IN ({placeholders})", chunk_ids
                )

            page_ids = [
                r["id"] for r in self._conn.execute(
                    "SELECT id FROM pages WHERE doc_id=?", (doc_id,)
                ).fetchall()
            ]
            if page_ids:
                placeholders = ",".join("?" * len(page_ids))
                self._conn.execute(
                    f"DELETE FROM page_texts WHERE page_id IN ({placeholders})", page_ids
                )
                self._conn.execute(
                    f"DELETE FROM images WHERE page_id IN ({placeholders})", page_ids
                )
                self._conn.execute(
                    f"DELETE FROM pages WHERE id IN ({placeholders})", page_ids
                )

            self._conn.execute(
                "DELETE FROM ingestion_runs WHERE doc_id=?", (doc_id,)
            )
            self._conn.execute(
                "DELETE FROM documents WHERE id=?", (doc_id,)
            )

    # ------------------------------------------------------------------
    # ingestion_runs
    # ------------------------------------------------------------------

    def start_ingestion_run(self, doc_id: str, config: dict[str, Any]) -> str:
        run_id = _new_id()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO ingestion_runs (id, doc_id, status, config_json)
                VALUES (?, ?, 'running', ?)
                """,
                (run_id, doc_id, json.dumps(config)),
            )
        return run_id

    def finish_ingestion_run(self, run_id: str, *, error: Optional[str] = None) -> None:
        status = "error" if error else "done"
        with self._conn:
            self._conn.execute(
                """
                UPDATE ingestion_runs
                SET status=?, finished_at=?, error=?
                WHERE id=?
                """,
                (status, _now(), error, run_id),
            )

    # ------------------------------------------------------------------
    # pages
    # ------------------------------------------------------------------

    def insert_page(
        self,
        doc_id: str,
        run_id: str,
        page_number: int,
        *,
        width_pt: Optional[float] = None,
        height_pt: Optional[float] = None,
    ) -> str:
        page_id = _new_id()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO pages (id, doc_id, run_id, page_number, width_pt, height_pt)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (page_id, doc_id, run_id, page_number, width_pt, height_pt),
            )
        return page_id

    def get_page(self, page_id: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM pages WHERE id=?", (page_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_pages_for_document(self, doc_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM pages WHERE doc_id=? ORDER BY page_number", (doc_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # page_texts
    # ------------------------------------------------------------------

    def insert_page_text(
        self,
        page_id: str,
        strategy: str,
        text: str,
        *,
        quality_score: Optional[float] = None,
        confidence: Optional[float] = None,
        is_selected: bool = False,
    ) -> str:
        pt_id = _new_id()
        words = len(text.split()) if text else 0
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO page_texts
                    (id, page_id, strategy, text, quality_score, confidence,
                     char_count, word_count, is_selected)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pt_id, page_id, strategy, text,
                    quality_score, confidence,
                    len(text), words,
                    1 if is_selected else 0,
                ),
            )
        return pt_id

    def set_selected_page_text(self, page_id: str, page_text_id: str) -> None:
        """Mark one page_text row as selected, clearing any previous selection."""
        with self._conn:
            self._conn.execute(
                "UPDATE page_texts SET is_selected=0 WHERE page_id=?", (page_id,)
            )
            self._conn.execute(
                "UPDATE page_texts SET is_selected=1 WHERE id=?", (page_text_id,)
            )

    def get_selected_page_text(self, page_id: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM page_texts WHERE page_id=? AND is_selected=1",
            (page_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_all_page_texts(self, page_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM page_texts WHERE page_id=? ORDER BY created_at",
            (page_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # images
    # ------------------------------------------------------------------

    def insert_image(
        self,
        page_id: str,
        image_type: str,
        path: str | Path,
        *,
        width_px: Optional[int] = None,
        height_px: Optional[int] = None,
        dpi: Optional[int] = None,
    ) -> str:
        img_id = _new_id()
        path = Path(path)
        checksum = None
        if path.exists():
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            checksum = h.hexdigest()

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO images
                    (id, page_id, image_type, path, width_px, height_px, dpi, checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (img_id, page_id, image_type, str(path),
                 width_px, height_px, dpi, checksum),
            )
        return img_id

    # ------------------------------------------------------------------
    # chunks
    # ------------------------------------------------------------------

    def insert_chunk(
        self,
        doc_id: str,
        page_id: str,
        page_text_id: str,
        run_id: str,
        chunk_index: int,
        text: str,
        *,
        title: Optional[str] = None,
        char_start: Optional[int] = None,
        char_end: Optional[int] = None,
        word_count: Optional[int] = None,
        token_count: Optional[int] = None,
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
        chunker_version: str = "semantic_v1",
        config: Optional[dict[str, Any]] = None,
        strategy: str = "flat",
        level: str = "flat",
        parent_id: Optional[str] = None,
        explicit_id: Optional[str] = None,
    ) -> str:
        """Insert/upsert a chunk.

        - For flat chunks, leave strategy/level/parent_id at defaults.
        - For parent chunks, pass strategy="parent_child", level="parent".
        - For child chunks, pass strategy="parent_child", level="child", parent_id=<parent uuid>.
        - explicit_id overrides the deterministic hash (used when the chunker
          already generated a stable ID, e.g. parent_child chunker).
        """
        if explicit_id:
            chunk_id = explicit_id
        else:
            import hashlib as _hl
            chunk_id = _hl.sha256(
                f"{doc_id}::{level}::{chunk_index}::{chunker_version}".encode()
            ).hexdigest()[:32]
        wc = word_count if word_count is not None else len(text.split())
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO chunks
                    (id, doc_id, page_id, page_text_id, run_id, chunk_index,
                     text, title, char_start, char_end, word_count, token_count,
                     page_start, page_end, chunker_version, strategy, level,
                     parent_id, config_json, embedded)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET
                    text=excluded.text,
                    title=excluded.title,
                    word_count=excluded.word_count,
                    page_start=excluded.page_start,
                    page_end=excluded.page_end,
                    run_id=excluded.run_id,
                    strategy=excluded.strategy,
                    level=excluded.level,
                    parent_id=excluded.parent_id,
                    embedded=0
                """,
                (
                    chunk_id, doc_id, page_id, page_text_id, run_id, chunk_index,
                    text, title, char_start, char_end, wc, token_count,
                    page_start, page_end, chunker_version, strategy, level,
                    parent_id,
                    json.dumps(config) if config else None,
                ),
            )
        return chunk_id

    def get_parent_chunk(self, child_chunk_id: str) -> Optional[dict[str, Any]]:
        """Given a child chunk ID, fetch its parent chunk row (for LLM context)."""
        row = self._conn.execute(
            """
            SELECT p.* FROM chunks p
            JOIN chunks c ON c.parent_id = p.id
            WHERE c.id = ? AND p.level = 'parent'
            """,
            (child_chunk_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_parents_by_ids(self, parent_ids: list[str]) -> list[dict[str, Any]]:
        """Bulk-fetch parents by ID (used after child retrieval to assemble context)."""
        if not parent_ids:
            return []
        placeholders = ",".join("?" * len(parent_ids))
        rows = self._conn.execute(
            f"SELECT * FROM chunks WHERE id IN ({placeholders}) AND level='parent'",
            parent_ids,
        ).fetchall()
        row_map = {dict(r)["id"]: dict(r) for r in rows}
        return [row_map[pid] for pid in parent_ids if pid in row_map]

    def mark_chunk_embedded(self, chunk_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE chunks SET embedded=1 WHERE id=?", (chunk_id,)
            )

    def mark_chunks_embedded(self, chunk_ids: list[str]) -> None:
        with self._conn:
            placeholders = ",".join("?" * len(chunk_ids))
            self._conn.execute(
                f"UPDATE chunks SET embedded=1 WHERE id IN ({placeholders})",
                chunk_ids,
            )

    def get_unembedded_chunks(self, doc_id: Optional[str] = None) -> list[dict[str, Any]]:
        if doc_id:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE embedded=0 AND doc_id=? ORDER BY chunk_index",
                (doc_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE embedded=0 ORDER BY doc_id, chunk_index"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_chunks_for_document(self, doc_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM chunks WHERE doc_id=? ORDER BY chunk_index", (doc_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch full chunk rows for a list of IDs — used after Chroma retrieval."""
        if not chunk_ids:
            return []
        placeholders = ",".join("?" * len(chunk_ids))
        rows = self._conn.execute(
            f"SELECT * FROM chunks WHERE id IN ({placeholders})", chunk_ids
        ).fetchall()
        # Return in the same order as chunk_ids
        row_map = {dict(r)["id"]: dict(r) for r in rows}
        return [row_map[cid] for cid in chunk_ids if cid in row_map]

    # ------------------------------------------------------------------
    # retrieval_logs
    # ------------------------------------------------------------------

    def log_retrieval(
        self,
        query_text: str,
        chunk_ids: list[str],
        distances: list[float],
        *,
        query_embedding_model: Optional[str] = None,
        top_k: Optional[int] = None,
        fetch_k: Optional[int] = None,
        rerank_method: Optional[str] = None,
        latency_ms: Optional[float] = None,
        llm_model: Optional[str] = None,
        llm_response: Optional[str] = None,
        grounded: Optional[bool] = None,
    ) -> str:
        log_id = _new_id()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO retrieval_logs
                    (id, query_text, query_embedding_model, top_k, fetch_k,
                     rerank_method, chunk_ids_returned, distances,
                     latency_ms, llm_model, llm_response, grounded)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id, query_text, query_embedding_model, top_k, fetch_k,
                    rerank_method,
                    json.dumps(chunk_ids),
                    json.dumps(distances),
                    latency_ms, llm_model, llm_response,
                    (1 if grounded else 0) if grounded is not None else None,
                ),
            )
        return log_id

    # ------------------------------------------------------------------
    # status / inspection
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return a summary of what's in the DB — useful for a CLI status command."""
        doc_count = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        page_count = self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        chunk_count = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        embedded_count = self._conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedded=1"
        ).fetchone()[0]
        ocr_page_count = self._conn.execute(
            "SELECT COUNT(*) FROM page_texts WHERE strategy != 'native' AND is_selected=1"
        ).fetchone()[0]
        log_count = self._conn.execute("SELECT COUNT(*) FROM retrieval_logs").fetchone()[0]

        docs = self._conn.execute(
            """
            SELECT d.filename, d.status, d.page_count,
                   COUNT(c.id) AS chunks,
                   SUM(c.embedded) AS embedded
            FROM documents d
            LEFT JOIN chunks c ON c.doc_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC
            """
        ).fetchall()

        return {
            "db_path": str(self.db_path),
            "documents": doc_count,
            "pages": page_count,
            "chunks": chunk_count,
            "embedded_chunks": embedded_count,
            "ocr_selected_pages": ocr_page_count,
            "retrieval_logs": log_count,
            "document_list": [dict(r) for r in docs],
        }