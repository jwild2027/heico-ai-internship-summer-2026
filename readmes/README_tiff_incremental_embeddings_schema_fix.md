# Incremental Embedding Schema Migration Fix

This patch fixes an upgrade issue when an existing `tiff_search.db` already has
`rag_chunks` or `rag_embeddings` tables from an older RAG build.

The previous incremental embedding patch added `chunk_hash`, but the schema setup
created indexes on `chunk_hash` before safely adding that column to older tables.
That could fail with:

```text
sqlite3.OperationalError: no such column: chunk_hash
```

This patch changes `create_rag_schema()` so it:

1. Creates the base RAG tables if missing.
2. Adds missing `chunk_hash` columns to old tables.
3. Creates indexes only after the columns exist.
4. Preserves existing embeddings so unchanged chunks can be skipped later.

After applying this patch, rerun the backend pipeline twice. The first run may
write embeddings once to populate hashes. The second run should skip unchanged
embeddings.
