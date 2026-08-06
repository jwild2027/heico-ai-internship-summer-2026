from pathlib import Path
import json

from tiff.trace_net_postgres_loader import (
    PostgresLoaderPaths,
    collect_ocr_records,
    collect_payloads,
    schema_sql,
)


def test_schema_contains_core_tables():
    sql = schema_sql()
    assert "create table if not exists pages" in sql
    assert "create table if not exists ocr_records" in sql
    assert "create table if not exists rag_candidate_chunks" in sql
    assert "create table if not exists source_citations" in sql
    assert "create table if not exists feedback_events" in sql


def test_collect_ocr_records_from_page_index(tmp_path: Path):
    ocr_dir = tmp_path / "ocr_export"
    (ocr_dir / "ocr").mkdir(parents=True)
    txt = ocr_dir / "ocr" / "page1.txt"
    txt.write_text("hello 120-50645-009 world\nsecond line\n", encoding="utf-8")
    (ocr_dir / "page_index.json").write_text(json.dumps({
        "pages": [{
            "page_id": "p1",
            "page_label": "1",
            "document_id": "doc",
            "source_image_path": "page1.tif",
            "ocr_text_path": str(txt),
            "ocr_pilot_status": "ocr_succeeded",
            "ocr_depth_classification": "likely_full_page",
        }]
    }), encoding="utf-8")
    pages, ocr_records = collect_ocr_records(PostgresLoaderPaths(ocr_export_dir=ocr_dir, organization_dir=tmp_path / "org", trace_net_dir=tmp_path / "trace"))
    assert len(pages) == 1
    assert len(ocr_records) == 1
    assert ocr_records[0]["page_id"] == "p1"
    assert ocr_records[0]["chars"] > 0
    assert "120-50645-009" in ocr_records[0]["text"]


def test_collect_payloads_handles_missing_trace_artifacts(tmp_path: Path):
    ocr_dir = tmp_path / "ocr_export"
    ocr_dir.mkdir(parents=True)
    (ocr_dir / "page_index.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
    payloads = collect_payloads(PostgresLoaderPaths(ocr_export_dir=ocr_dir, organization_dir=tmp_path / "org", trace_net_dir=tmp_path / "trace"))
    assert payloads["pages"] == []
    assert payloads["rag_candidate_chunks"] == []
    assert payloads["graph_nodes"] == []
