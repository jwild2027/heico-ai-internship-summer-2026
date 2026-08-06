from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from tiff.source_link_audit import (
    audit_source_links,
    format_source_link_audit,
    write_source_link_audit_json,
)


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    tiff_path = tmp_path / "page1.tif"
    ocr_path = tmp_path / "page1.txt"
    tiff_path.write_text("fake tiff", encoding="utf-8")
    ocr_path.write_text("ocr", encoding="utf-8")

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE pages (
                page_id TEXT PRIMARY KEY,
                manual_id TEXT,
                page_sequence INTEGER,
                page_label TEXT
            );
            CREATE TABLE source_links (
                source_link_id TEXT PRIMARY KEY,
                page_id TEXT,
                manual_id TEXT,
                publication_number TEXT,
                ata_code TEXT,
                page_sequence INTEGER,
                page_label TEXT,
                page_type TEXT,
                title TEXT,
                tiff_path TEXT,
                ocr_text_path TEXT,
                thumbnail_path TEXT,
                tiff_uri TEXT,
                ocr_uri TEXT,
                rescarta_object_id TEXT,
                rescarta_page_id TEXT,
                rescarta_url TEXT,
                source_url TEXT,
                source_kind TEXT,
                created_at TEXT
            );
            CREATE TABLE part_mentions (
                page_id TEXT,
                part_number_normalized TEXT,
                part_number_display TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO pages (page_id, manual_id, page_sequence, page_label) VALUES (?, ?, ?, ?)",
            [
                ("p1", "m1", 1, "000001"),
                ("p2", "m1", 2, "000002"),
                ("p3", "m1", 3, "000003"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO source_links (
                source_link_id, page_id, manual_id, publication_number, ata_code,
                page_sequence, page_label, tiff_path, ocr_text_path,
                rescarta_object_id, rescarta_page_id, rescarta_url, source_url, source_kind, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "m1:p1",
                    "p1",
                    "m1",
                    "T.P. TEST",
                    "25-21-00",
                    1,
                    "000001",
                    str(tiff_path),
                    str(ocr_path),
                    "m1",
                    "000001",
                    "http://localhost:8080/rescarta/m1/000001",
                    "http://localhost:8080/rescarta/m1/000001",
                    "rescarta_staging",
                    "now",
                ),
                (
                    "m1:p2",
                    "p2",
                    "m1",
                    "T.P. TEST",
                    "25-21-00",
                    2,
                    "000002",
                    str(tmp_path / "missing.tif"),
                    "",
                    "m1",
                    "000002",
                    "",
                    "file:///tmp/missing.tif",
                    "rescarta_staging",
                    "now",
                ),
            ],
        )
        conn.execute(
            "INSERT INTO part_mentions (page_id, part_number_normalized, part_number_display) VALUES (?, ?, ?)",
            ("p1", "12037313001", "120-37313-001"),
        )
        conn.commit()
    return db_path


def test_audit_source_links_counts_coverage_and_file_problems(tmp_path: Path):
    db_path = _make_db(tmp_path)

    summary = audit_source_links(db_path, sample_queries=("120-37313-001", "NO-SUCH-PART"))

    assert summary.source_links_table_exists is True
    assert summary.total_links == 2
    assert summary.distinct_manuals == 1
    assert summary.pages_total == 3
    assert summary.pages_without_source_links == 1
    assert summary.missing_tiff_path == 0
    assert summary.missing_ocr_path == 1
    assert summary.missing_rescarta_url == 1
    assert summary.missing_source_url == 0
    assert summary.local_or_placeholder_rescarta_urls == 1
    assert summary.source_url_file_fallbacks == 1
    assert summary.missing_tiff_files == 1
    assert summary.missing_ocr_files == 0
    assert summary.sample_queries_checked == 2
    assert summary.sample_queries_without_results == 1
    assert summary.sample_rows[0].query == "120-37313-001"
    assert summary.ready_for_local_source_review is False
    assert summary.ready_for_real_rescarta_deeplinks is False


def test_format_source_link_audit_is_command_line_friendly(tmp_path: Path):
    summary = audit_source_links(_make_db(tmp_path), sample_queries=("120-37313-001",), sample_limit=2)

    text = format_source_link_audit(summary, sample_limit=1)

    assert "Source-link audit" in text
    assert "Path/link coverage:" in text
    assert "File existence:" in text
    assert "Sample source resolution:" in text
    assert "Local/placeholder ResCarta URLs: 1" in text
    assert "<html" not in text.lower()


def test_write_source_link_audit_json(tmp_path: Path):
    summary = audit_source_links(_make_db(tmp_path), sample_queries=("120-37313-001",))
    out = write_source_link_audit_json(summary, tmp_path / "audit.json")

    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["total_links"] == 2
    assert payload["ready_for_local_source_review"] is False
    assert payload["ready_for_real_rescarta_deeplinks"] is False
    assert payload["sample_rows"][0]["query"] == "120-37313-001"


def test_missing_database_returns_warning(tmp_path: Path):
    summary = audit_source_links(tmp_path / "missing.db")

    assert summary.source_links_table_exists is False
    assert summary.total_links == 0
    assert summary.warnings


def test_missing_source_links_table_returns_warning(tmp_path: Path):
    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE pages (page_id TEXT)")
        conn.commit()

    summary = audit_source_links(db_path)

    assert summary.source_links_table_exists is False
    assert "source_links table does not exist" in summary.warnings[0]
