"""db/schema.py — SQLite schema for the RAG pipeline.

Tables:
    documents       — one row per PDF file
    ingestion_runs  — one row per ingest attempt, with config snapshot
    pages           — one row per page in a document
    page_texts      — one or more extraction attempts per page (native, tesseract, …)
    images          — page renders and variants (render, thumbnail, figure, table)
    chunks          — text chunks derived from a selected page_text
    retrieval_logs  — every query + what was returned, for offline eval

Chroma stores:
    chunk_id → embedding vector
    metadata: doc_id, page_id, page_number, strategy, chunker_version
    (Chroma is an index into this DB, not the source of truth)
"""
from __future__ import annotations

CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,          -- uuid
    filename        TEXT NOT NULL,
    filepath        TEXT NOT NULL,
    pdf_checksum    TEXT NOT NULL,             -- sha256 of the PDF bytes
    page_count      INTEGER,
    status          TEXT NOT NULL DEFAULT 'pending',
                                               -- pending | ingesting | done | error
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_INGESTION_RUNS = """
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id              TEXT PRIMARY KEY,          -- uuid
    doc_id          TEXT NOT NULL REFERENCES documents(id),
    status          TEXT NOT NULL DEFAULT 'running',
                                               -- running | done | error
    config_json     TEXT,                      -- JSON snapshot of all ingest params
    error           TEXT,
    started_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at     TEXT
);
"""

CREATE_PAGES = """
CREATE TABLE IF NOT EXISTS pages (
    id              TEXT PRIMARY KEY,          -- uuid
    doc_id          TEXT NOT NULL REFERENCES documents(id),
    run_id          TEXT REFERENCES ingestion_runs(id),
    page_number     INTEGER NOT NULL,
    width_pt        REAL,                      -- page dimensions in PDF points
    height_pt       REAL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_PAGE_TEXTS = """
CREATE TABLE IF NOT EXISTS page_texts (
    id              TEXT PRIMARY KEY,          -- uuid
    page_id         TEXT NOT NULL REFERENCES pages(id),
    strategy        TEXT NOT NULL,             -- native | tesseract | paddleocr | azure | merged
    text            TEXT NOT NULL DEFAULT '',
    quality_score   REAL,                      -- 0.0–1.0 heuristic quality
    confidence      REAL,                      -- 0.0–100.0 OCR engine confidence (null for native)
    char_count      INTEGER,
    word_count      INTEGER,
    is_selected     INTEGER NOT NULL DEFAULT 0, -- 1 = this is the text used for chunking
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_IMAGES = """
CREATE TABLE IF NOT EXISTS images (
    id              TEXT PRIMARY KEY,          -- uuid
    page_id         TEXT NOT NULL REFERENCES pages(id),
    image_type      TEXT NOT NULL,             -- render | thumbnail | crop | figure | table
    path            TEXT NOT NULL,             -- filepath on disk
    width_px        INTEGER,
    height_px       INTEGER,
    dpi             INTEGER,
    checksum        TEXT,                      -- sha256 for dedup
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY ON CONFLICT REPLACE,  -- deterministic hash, upsert-safe
    doc_id          TEXT NOT NULL REFERENCES documents(id),
    page_id         TEXT NOT NULL REFERENCES pages(id),
    page_text_id    TEXT NOT NULL REFERENCES page_texts(id),
    run_id          TEXT REFERENCES ingestion_runs(id),
    chunk_index     INTEGER NOT NULL,          -- 0-based order within the document
    text            TEXT NOT NULL,
    title           TEXT,                      -- section heading extracted by chunker
    char_start      INTEGER,                   -- char offset into page_text.text
    char_end        INTEGER,
    word_count      INTEGER,
    token_count     INTEGER,
    page_start      INTEGER,                   -- first page number spanned
    page_end        INTEGER,                   -- last page number spanned
    chunker_version TEXT,                      -- e.g. "semantic_v1"
    strategy        TEXT NOT NULL DEFAULT 'flat',  -- "flat" | "parent_child"
    level           TEXT NOT NULL DEFAULT 'flat',  -- "flat" | "parent" | "child"
    parent_id       TEXT,                      -- FK to parent chunk if level=child; NULL otherwise
    config_json     TEXT,                      -- JSON of chunker params (target_words, overlap, …)
    embedded        INTEGER NOT NULL DEFAULT 0, -- 1 = vector is in Chroma
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_RETRIEVAL_LOGS = """
CREATE TABLE IF NOT EXISTS retrieval_logs (
    id                    TEXT PRIMARY KEY,    -- uuid
    query_text            TEXT NOT NULL,
    query_embedding_model TEXT,
    top_k                 INTEGER,
    fetch_k               INTEGER,
    rerank_method         TEXT,                -- lexical | cross_encoder | none
    chunk_ids_returned    TEXT,               -- JSON array of chunk_ids
    distances             TEXT,               -- JSON array of distances
    latency_ms            REAL,
    llm_model             TEXT,
    llm_response          TEXT,
    grounded              INTEGER,             -- 1 | 0 | null if no LLM call
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

# Indexes for the most common lookup patterns
# The UNIQUE index on documents.pdf_checksum enforces the "one row per PDF
# content hash" invariant that upsert_document() relies on. Without it a
# duplicate insert (or a stale/corrupted upsert path) could silently produce
# two rows for the same PDF — or, worse, mask a wipe-and-reinsert as success.
CREATE_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_checksum_unique ON documents(pdf_checksum);
CREATE INDEX IF NOT EXISTS idx_pages_doc_id         ON pages(doc_id);
CREATE INDEX IF NOT EXISTS idx_page_texts_page_id   ON page_texts(page_id);
CREATE INDEX IF NOT EXISTS idx_page_texts_selected  ON page_texts(page_id, is_selected);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id        ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page_id       ON chunks(page_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedded      ON chunks(embedded);
CREATE INDEX IF NOT EXISTS idx_chunks_parent_id     ON chunks(parent_id);
CREATE INDEX IF NOT EXISTS idx_chunks_level         ON chunks(level);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_doc   ON ingestion_runs(doc_id);
CREATE INDEX IF NOT EXISTS idx_images_page_id       ON images(page_id);
"""

ALL_TABLES = [
    CREATE_DOCUMENTS,
    CREATE_INGESTION_RUNS,
    CREATE_PAGES,
    CREATE_PAGE_TEXTS,
    CREATE_IMAGES,
    CREATE_CHUNKS,
    CREATE_RETRIEVAL_LOGS,
]