from pathlib import Path
import json

from tiff.production_schema import (
    OPENSEARCH_INDICES,
    POSTGRES_TABLES,
    QDRANT_COLLECTIONS,
    opensearch_mappings,
    postgres_schema_sql,
    qdrant_collections,
    validate_schema_drafts,
    write_schema_drafts,
)


def test_postgres_schema_mentions_core_tables_and_traceability() -> None:
    sql = postgres_schema_sql()
    assert "CREATE SCHEMA IF NOT EXISTS tiff_lib" in sql
    for table in ["documents", "pages", "source_links", "parts", "page_contexts", "rag_chunks", "user_feedback"]:
        assert f"tiff_lib.{table}" in sql
    assert "qdrant_collection" in sql
    assert "qdrant_point_id" in sql
    assert "Raw TIFF bytes stay" in sql


def test_opensearch_mappings_include_expected_indices_and_fields() -> None:
    mappings = opensearch_mappings()
    for index in OPENSEARCH_INDICES:
        assert index in mappings
        assert "mappings" in mappings[index]
    page_props = mappings["tiff_pages_v1"]["mappings"]["properties"]
    assert "ocr_text" in page_props
    assert "page_id" in page_props
    assert "source_link_id" in page_props
    chunk_props = mappings["tiff_rag_chunks_v1"]["mappings"]["properties"]
    assert "chunk_id" in chunk_props
    assert "qdrant_point_id" in chunk_props


def test_qdrant_collections_include_graph_resolution_payloads() -> None:
    collections = qdrant_collections()
    for name in QDRANT_COLLECTIONS:
        assert name in collections
    chunk_payload = collections["tiff_rag_chunks_v1"]["payload_schema"]
    assert chunk_payload["chunk_id"] == "keyword"
    assert chunk_payload["page_id"] == "keyword"
    assert chunk_payload["source_link_id"] == "keyword"
    assert collections["tiff_rag_chunks_v1"]["vectors"]["size"] == 1024


def test_write_and_validate_schema_drafts(tmp_path: Path) -> None:
    summary = write_schema_drafts(tmp_path)
    assert summary.status == "OK"
    assert summary.artifacts_written == 5
    assert set(POSTGRES_TABLES).issubset(set(summary.postgres_tables))
    assert (tmp_path / "postgres_schema.sql").exists()
    assert (tmp_path / "opensearch_mappings.json").exists()
    assert (tmp_path / "qdrant_collections.json").exists()
    assert (tmp_path / "storage_migration_plan.md").exists()
    assert (tmp_path / "production_schema_summary.json").exists()
    assert validate_schema_drafts(tmp_path) == []
    payload = json.loads((tmp_path / "production_schema_summary.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == summary.schema_version
    assert payload["qdrant_collections"] == list(QDRANT_COLLECTIONS)
