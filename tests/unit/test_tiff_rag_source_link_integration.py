from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.rag_retriever import RagSource, enrich_sources_with_source_links, source_to_dict
from tiff.rag_answer import make_context_block
from tiff.pipeline_manifest import collect_sqlite_counts
from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest


def test_retrieved_sources_are_enriched_from_source_links(tmp_path: Path):
    db = tmp_path / "search.db"
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE source_links ("
            "page_id TEXT PRIMARY KEY, tiff_path TEXT, ocr_text_path TEXT, "
            "tiff_uri TEXT, ocr_uri TEXT, rescarta_object_id TEXT, rescarta_page_id TEXT, "
            "rescarta_url TEXT, source_url TEXT)"
        )
        conn.execute(
            "INSERT INTO source_links VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "p1",
                "pages/000001.tif",
                "ocr/000001.txt",
                "file:///pages/000001.tif",
                "file:///ocr/000001.txt",
                "manual1",
                "000001",
                "http://rescarta/manual1/000001",
                "file:///pages/000001.tif",
            ),
        )
        src = RagSource(
            source_id="s1",
            source_type="part_mentions",
            page_id="p1",
            manual_id="manual1",
            chunk_text="part evidence",
        )
        enriched = enrich_sources_with_source_links(conn, [src])[0]

    assert enriched.tiff_path == "pages/000001.tif"
    assert enriched.ocr_text_path == "ocr/000001.txt"
    assert enriched.rescarta_url == "http://rescarta/manual1/000001"
    assert enriched.source_url == "file:///pages/000001.tif"
    assert source_to_dict(enriched)["rescarta_url"] == "http://rescarta/manual1/000001"


def test_answer_context_displays_rescarta_and_source_urls():
    src = RagSource(
        source_id="s1",
        source_type="part_catalog_clean",
        page_id="p1",
        manual_id="manual1",
        chunk_text="120-37313-001 HOLDER, MAGAZINE",
        publication_number="T.P. 120/1176",
        page_label="1056",
        rescarta_url="http://rescarta/manual1/000001",
        source_url="file:///pages/000001.tif",
        tiff_path="pages/000001.tif",
        ocr_text_path="ocr/000001.txt",
    )
    block = make_context_block([src])
    assert "ResCarta URL: http://rescarta/manual1/000001" in block
    assert "Source URL: file:///pages/000001.tif" in block


def test_manifest_and_quality_gate_include_source_links(tmp_path: Path):
    db = tmp_path / "search.db"
    with sqlite3.connect(db) as conn:
        for table in ["manuals", "pages", "part_mentions", "part_catalog_clean", "rag_chunks", "rag_embeddings", "source_links"]:
            conn.execute(f"CREATE TABLE {table} (id TEXT)")
            conn.execute(f"INSERT INTO {table} VALUES ('x')")
    counts = collect_sqlite_counts(db)
    assert counts["source_links"] == 1

    manifest = {
        "status": "ok",
        "steps": [{"name": "x", "returncode": 0}],
        "sqlite_counts": counts,
        "eval_summary": {"status_counts": {"pass": 1}},
        "qa_summary": {"by_severity": {"review": 0}, "by_report": {"suspicious_part_ata": 0}},
    }
    result = check_pipeline_manifest(manifest, thresholds=QualityGateThresholds(max_manual_review=0, max_qa_review=0, max_suspicious_part_ata=0))
    assert result.ok
    assert any(check["name"] == "table_count_source_links" for check in result.checks)
