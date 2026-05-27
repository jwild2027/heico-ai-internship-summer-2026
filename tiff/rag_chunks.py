"""Build page-level and chunk-level RAG tables from the TIFF search database.

The search database already knows manuals, pages, OCR text, TIFF paths, and part
mentions. This module adds RAG-friendly chunk tables without changing the source
TIFF files.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


RAG_SCHEMA_VERSION = 1
WHITESPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-/]*")


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    page_id: str
    manual_id: str
    chunk_index: int
    chunk_text: str
    chunk_hash: str
    publication_number: str | None = None
    ata_code: str | None = None
    page_sequence: int | None = None
    page_label: str | None = None
    page_type: str | None = None
    title: str | None = None
    tiff_path: str | None = None
    ocr_text_path: str | None = None
    rescarta_object_id: str | None = None
    rescarta_page_id: str | None = None
    part_numbers_json: str = "[]"
    nomenclatures_json: str = "[]"


@dataclass(frozen=True)
class RagChunkBuildSummary:
    db_path: Path
    pages_seen: int = 0
    chunks_created: int = 0
    warnings: tuple[str, ...] = ()


def collapse_ws(value: str | None) -> str:
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", value).strip()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="replace")).hexdigest()


def build_fts_query(query: str, joiner: str = "AND") -> str:
    tokens = [t for t in TOKEN_RE.findall(query or "") if t]
    if not tokens:
        return ""
    sep = " OR " if joiner.upper() == "OR" else " AND "
    return sep.join('"' + t.replace('"', '""') + '"' for t in tokens)


def chunk_text_by_lines(text: str, max_chars: int = 1400, overlap_chars: int = 180) -> list[str]:
    """Split OCR text into stable chunks while preserving table-ish rows.

    The OCR export often has line/region markers. Keeping chunks line-oriented
    makes IPL table evidence easier to read than blind character splitting.
    """

    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [collapse_ws(line) for line in text.split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        clean = collapse_ws(text)
        return [clean] if clean else []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars:
            chunk = collapse_ws("\n".join(current))
            if chunk:
                chunks.append(chunk)
            if overlap_chars > 0:
                overlap: list[str] = []
                overlap_len = 0
                for old_line in reversed(current):
                    overlap_len += len(old_line) + 1
                    overlap.insert(0, old_line)
                    if overlap_len >= overlap_chars:
                        break
                current = overlap
                current_len = sum(len(x) + 1 for x in current)
            else:
                current = []
                current_len = 0
        current.append(line)
        current_len += line_len

    final = collapse_ws("\n".join(current))
    if final:
        chunks.append(final)

    # Deduplicate chunks that can happen on tiny pages with overlap.
    deduped: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk not in seen:
            deduped.append(chunk)
            seen.add(chunk)
    return deduped


def create_rag_schema(conn: sqlite3.Connection, reset: bool = False) -> None:
    if reset:
        # Reset chunk tables, but preserve rag_embeddings.  Embeddings are
        # keyed by (chunk_id, model, chunk_hash), so unchanged chunks can keep
        # their vectors across a backend rebuild.  Stale embeddings are pruned
        # by build_rag_embeddings after chunks are rebuilt.
        conn.executescript(
            """
            DROP TABLE IF EXISTS rag_chunks;
            DROP TABLE IF EXISTS rag_chunk_fts;
            """
        )

    # Create base tables first.  On an existing database, CREATE TABLE IF NOT
    # EXISTS does not add new columns, so migrations must run before indexes
    # reference those columns.  This specifically protects old rag_chunks and
    # rag_embeddings tables that were created before chunk_hash existed.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS rag_chunks (
            chunk_id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL,
            manual_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_hash TEXT NOT NULL,
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
            part_numbers_json TEXT DEFAULT '[]',
            nomenclatures_json TEXT DEFAULT '[]'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunk_fts USING fts5(
            chunk_id UNINDEXED,
            page_id UNINDEXED,
            manual_id UNINDEXED,
            publication_number,
            ata_code,
            page_type,
            title,
            part_numbers,
            nomenclatures,
            chunk_text
        );

        CREATE TABLE IF NOT EXISTS rag_embeddings (
            chunk_id TEXT NOT NULL,
            model TEXT NOT NULL,
            chunk_hash TEXT,
            dim INTEGER NOT NULL,
            embedding_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (chunk_id, model),
            FOREIGN KEY (chunk_id) REFERENCES rag_chunks(chunk_id)
        );
        """
    )

    # Migrate any older rag_chunks table in place.  Older prototypes had a
    # smaller rag_chunks schema, so every column referenced by inserts or
    # indexes must be present before index creation.
    _ensure_column(conn, "rag_chunks", "chunk_hash", "TEXT")
    _ensure_column(conn, "rag_chunks", "publication_number", "TEXT")
    _ensure_column(conn, "rag_chunks", "ata_code", "TEXT")
    _ensure_column(conn, "rag_chunks", "page_sequence", "INTEGER")
    _ensure_column(conn, "rag_chunks", "page_label", "TEXT")
    _ensure_column(conn, "rag_chunks", "page_type", "TEXT")
    _ensure_column(conn, "rag_chunks", "title", "TEXT")
    _ensure_column(conn, "rag_chunks", "tiff_path", "TEXT")
    _ensure_column(conn, "rag_chunks", "ocr_text_path", "TEXT")
    _ensure_column(conn, "rag_chunks", "rescarta_object_id", "TEXT")
    _ensure_column(conn, "rag_chunks", "rescarta_page_id", "TEXT")
    _ensure_column(conn, "rag_chunks", "part_numbers_json", "TEXT DEFAULT '[]'")
    _ensure_column(conn, "rag_chunks", "nomenclatures_json", "TEXT DEFAULT '[]'")
    _ensure_column(conn, "rag_embeddings", "chunk_hash", "TEXT")

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_page ON rag_chunks(page_id);
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_manual ON rag_chunks(manual_id);
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_ata ON rag_chunks(ata_code);
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_hash ON rag_chunks(chunk_hash);
        CREATE INDEX IF NOT EXISTS idx_rag_embeddings_model ON rag_embeddings(model);
        CREATE INDEX IF NOT EXISTS idx_rag_embeddings_hash ON rag_embeddings(model, chunk_hash);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)",
        ("rag_schema_version", str(RAG_SCHEMA_VERSION)),
    ) if table_exists(conn, "schema_info") else None
    conn.commit()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1",
            (name,),
        ).fetchone()
        is not None
    )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    if not table_exists(conn, table):
        return
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _fetch_page_parts(conn: sqlite3.Connection, page_id: str) -> tuple[list[str], list[str]]:
    part_numbers: list[str] = []
    nomenclatures: list[str] = []
    if table_exists(conn, "part_mentions"):
        rows = conn.execute(
            """
            SELECT DISTINCT part_number_display, part_number_normalized
            FROM part_mentions
            WHERE page_id = ?
            ORDER BY part_number_normalized
            """,
            (page_id,),
        ).fetchall()
        for row in rows:
            display = row[0] or row[1]
            if display and display not in part_numbers:
                part_numbers.append(display)
    if table_exists(conn, "part_catalog_mentions_clean"):
        rows = conn.execute(
            """
            SELECT DISTINCT clean_nomenclature
            FROM part_catalog_mentions_clean
            WHERE page_id = ? AND clean_nomenclature IS NOT NULL AND clean_nomenclature <> ''
            ORDER BY clean_nomenclature
            """,
            (page_id,),
        ).fetchall()
        for row in rows:
            name = row[0]
            if name and name not in nomenclatures:
                nomenclatures.append(name)
    elif table_exists(conn, "part_catalog"):
        rows = conn.execute(
            """
            SELECT DISTINCT nomenclature
            FROM part_catalog
            WHERE page_id = ? AND nomenclature IS NOT NULL AND nomenclature <> ''
            ORDER BY nomenclature
            """,
            (page_id,),
        ).fetchall()
        for row in rows:
            name = row[0]
            if name and name not in nomenclatures:
                nomenclatures.append(name)
    return part_numbers, nomenclatures


def _iter_pages(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    if table_exists(conn, "ocr_clean_pages"):
        return conn.execute(
            """
            SELECT
                p.page_id, p.manual_id, p.publication_number, p.ata_code, p.page_sequence,
                p.page_label, p.page_type, p.title, p.tiff_path, p.ocr_text_path,
                p.rescarta_object_id, p.rescarta_page_id,
                COALESCE(oc.clean_ocr_text, p.ocr_text) AS ocr_text,
                p.is_blank
            FROM pages p
            LEFT JOIN ocr_clean_pages oc ON oc.page_id = p.page_id
            WHERE COALESCE(p.is_blank, 0) = 0
              AND COALESCE(oc.clean_ocr_text, p.ocr_text) IS NOT NULL
              AND TRIM(COALESCE(oc.clean_ocr_text, p.ocr_text)) <> ''
            ORDER BY p.manual_id, p.page_sequence
            """
        ).fetchall()
    return conn.execute(
        """
        SELECT
            page_id, manual_id, publication_number, ata_code, page_sequence,
            page_label, page_type, title, tiff_path, ocr_text_path,
            rescarta_object_id, rescarta_page_id, ocr_text, is_blank
        FROM pages
        WHERE COALESCE(is_blank, 0) = 0
          AND ocr_text IS NOT NULL
          AND TRIM(ocr_text) <> ''
        ORDER BY manual_id, page_sequence
        """
    ).fetchall()


def _insert_chunk(conn: sqlite3.Connection, chunk: RagChunk) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO rag_chunks (
            chunk_id, page_id, manual_id, chunk_index, chunk_text, chunk_hash,
            publication_number, ata_code, page_sequence, page_label, page_type,
            title, tiff_path, ocr_text_path, rescarta_object_id, rescarta_page_id,
            part_numbers_json, nomenclatures_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk.chunk_id,
            chunk.page_id,
            chunk.manual_id,
            chunk.chunk_index,
            chunk.chunk_text,
            chunk.chunk_hash,
            chunk.publication_number,
            chunk.ata_code,
            chunk.page_sequence,
            chunk.page_label,
            chunk.page_type,
            chunk.title,
            chunk.tiff_path,
            chunk.ocr_text_path,
            chunk.rescarta_object_id,
            chunk.rescarta_page_id,
            chunk.part_numbers_json,
            chunk.nomenclatures_json,
        ),
    )
    part_numbers = " ".join(json.loads(chunk.part_numbers_json or "[]"))
    nomenclatures = " ".join(json.loads(chunk.nomenclatures_json or "[]"))
    conn.execute(
        """
        INSERT INTO rag_chunk_fts (
            chunk_id, page_id, manual_id, publication_number, ata_code,
            page_type, title, part_numbers, nomenclatures, chunk_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk.chunk_id,
            chunk.page_id,
            chunk.manual_id,
            chunk.publication_number or "",
            chunk.ata_code or "",
            chunk.page_type or "",
            chunk.title or "",
            part_numbers,
            nomenclatures,
            chunk.chunk_text,
        ),
    )


def prune_stale_rag_embeddings(conn: sqlite3.Connection, model: str | None = None) -> int:
    """Delete embeddings whose chunk no longer exists or whose text hash changed."""

    if not table_exists(conn, "rag_embeddings") or not table_exists(conn, "rag_chunks"):
        return 0
    params: list[Any] = []
    model_filter = ""
    if model:
        model_filter = " AND e.model = ?"
        params.append(model)
    before = conn.execute("SELECT COUNT(*) FROM rag_embeddings e WHERE 1=1" + model_filter, params).fetchone()[0]
    conn.execute(
        """
        DELETE FROM rag_embeddings
        WHERE (? IS NULL OR model = ?)
          AND (
            chunk_id NOT IN (SELECT chunk_id FROM rag_chunks)
            OR COALESCE(chunk_hash, '') <> COALESCE((SELECT c.chunk_hash FROM rag_chunks c WHERE c.chunk_id = rag_embeddings.chunk_id), '')
          )
        """,
        (model, model),
    )
    after = conn.execute("SELECT COUNT(*) FROM rag_embeddings e WHERE 1=1" + model_filter, params).fetchone()[0]
    return int(before - after)


def build_rag_chunks(
    db_path: Path | str,
    *,
    reset: bool = True,
    max_chars: int = 1400,
    overlap_chars: int = 180,
) -> RagChunkBuildSummary:
    """Create rag_chunks and rag_chunk_fts from the existing pages table."""

    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Search database does not exist: {db_path}")

    warnings: list[str] = []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "pages"):
            raise RuntimeError("Database is missing the pages table. Build tiff_search.db first.")
        create_rag_schema(conn, reset=reset)
        pages = list(_iter_pages(conn))
        chunks_created = 0
        for page in pages:
            part_numbers, nomenclatures = _fetch_page_parts(conn, page["page_id"])
            chunks = chunk_text_by_lines(page["ocr_text"] or "", max_chars=max_chars, overlap_chars=overlap_chars)
            if not chunks:
                continue
            for idx, text in enumerate(chunks, start=1):
                chunk_id = f"{page['page_id']}_c{idx:04d}"
                chunk = RagChunk(
                    chunk_id=chunk_id,
                    page_id=page["page_id"],
                    manual_id=page["manual_id"],
                    chunk_index=idx,
                    chunk_text=text,
                    chunk_hash=sha256_text(text),
                    publication_number=page["publication_number"],
                    ata_code=page["ata_code"],
                    page_sequence=page["page_sequence"],
                    page_label=page["page_label"],
                    page_type=page["page_type"],
                    title=page["title"],
                    tiff_path=page["tiff_path"],
                    ocr_text_path=page["ocr_text_path"],
                    rescarta_object_id=page["rescarta_object_id"],
                    rescarta_page_id=page["rescarta_page_id"],
                    part_numbers_json=json_dumps(part_numbers),
                    nomenclatures_json=json_dumps(nomenclatures),
                )
                _insert_chunk(conn, chunk)
                chunks_created += 1
        conn.commit()
        return RagChunkBuildSummary(
            db_path=db_path,
            pages_seen=len(pages),
            chunks_created=chunks_created,
            warnings=tuple(warnings),
        )
    finally:
        conn.close()
