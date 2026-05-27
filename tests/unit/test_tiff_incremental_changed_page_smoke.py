from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.incremental_changed_page_smoke import (
    ChangedPageSmokeReport,
    format_changed_page_smoke_report,
    select_smoke_source_page,
)


def _build_smoke_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE pages (
                page_id TEXT PRIMARY KEY,
                manual_id TEXT,
                page_label TEXT,
                ata_code TEXT,
                page_sequence INTEGER,
                tiff_path TEXT,
                ocr_text_path TEXT
            );
            CREATE TABLE source_links (
                page_id TEXT PRIMARY KEY,
                manual_id TEXT,
                page_label TEXT,
                ata_code TEXT,
                tiff_path TEXT,
                ocr_text_path TEXT,
                rescarta_url TEXT,
                source_url TEXT
            );
            CREATE TABLE part_mentions (
                mention_id TEXT PRIMARY KEY,
                part_number_normalized TEXT,
                page_id TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO pages VALUES (?,?,?,?,?,?,?)",
            ("p1", "m1", "101", "25-21-00", 1, "page1.tif", "page1.txt"),
        )
        conn.execute(
            "INSERT INTO source_links VALUES (?,?,?,?,?,?,?,?)",
            ("p1", "m1", "101", "25-21-00", "page1.tif", "page1.txt", "http://localhost/r/p1", "http://localhost/r/p1"),
        )
        conn.execute(
            "INSERT INTO part_mentions VALUES (?,?,?)",
            ("pm1", "12037313001", "p1"),
        )
        conn.commit()


def test_select_smoke_source_page_prefers_sample_part(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"
    _build_smoke_db(db_path)

    page = select_smoke_source_page(db_path, sample_part="120-37313-001")

    assert page.page_id == "p1"
    assert page.tiff_path == "page1.tif"
    assert page.rescarta_url.startswith("http://localhost")


def test_format_changed_page_smoke_report_is_command_line_first() -> None:
    report = ChangedPageSmokeReport(
        ok=True,
        config_path="local_config.yaml",
        db_path="local_data/db/tiff_search.db",
        work_dir="local_data/incremental_smoke",
        dry_run=False,
        source_page={"page_id": "p1", "manual_id": "m1", "ata_code": "25-21-00", "page_label": "101", "tiff_path": "source.tif"},
        temp_tiff_path="local_data/incremental_smoke/sample_tiffs/source.tif",
        changed_list="local_data/incremental_smoke/changed_tiffs.txt",
        changed_list_count=1,
        changed_list_rows=["local_data/incremental_smoke/sample_tiffs/source.tif"],
        new_files=0,
        changed_files=1,
        unchanged_files=0,
        state_committed=True,
        commit_message="Changed files were processed successfully.",
        backend_command_planned=True,
        changed_page_command_used=True,
        full_backend_command_used=False,
        ocr_command_skipped=True,
    )

    text = format_changed_page_smoke_report(report)

    assert "Status: OK" in text
    assert "Changed-page backend planned: True" in text
    assert "Used full backend rebuild: False" in text
