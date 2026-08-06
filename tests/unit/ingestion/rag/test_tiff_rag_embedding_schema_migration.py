from __future__ import annotations

import sqlite3

from tiff.rag_chunks import create_rag_schema, table_exists


def column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_create_rag_schema_migrates_old_tables_before_indexing(tmp_path):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE rag_chunks (
                chunk_id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                manual_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL
            );
            CREATE TABLE rag_embeddings (
                chunk_id TEXT NOT NULL,
                model TEXT NOT NULL,
                dim INTEGER NOT NULL,
                embedding_json TEXT NOT NULL,
                PRIMARY KEY (chunk_id, model)
            );
            INSERT INTO rag_chunks(chunk_id, page_id, manual_id, chunk_index, chunk_text)
            VALUES ('p1_c0001', 'p1', 'm1', 1, 'hello');
            INSERT INTO rag_embeddings(chunk_id, model, dim, embedding_json)
            VALUES ('p1_c0001', 'bge-m3:latest', 3, '[0.1, 0.2, 0.3]');
            """
        )
        conn.commit()

        create_rag_schema(conn, reset=False)

        assert table_exists(conn, "rag_chunks")
        assert table_exists(conn, "rag_embeddings")
        assert "chunk_hash" in column_names(conn, "rag_chunks")
        assert "chunk_hash" in column_names(conn, "rag_embeddings")
        assert conn.execute("SELECT COUNT(*) FROM rag_embeddings").fetchone()[0] == 1
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_rag_chunks_hash'").fetchone()
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_rag_embeddings_hash'").fetchone()
    finally:
        conn.close()
