from __future__ import annotations

from pathlib import Path
import sqlite3

from tiff.ocr_coverage_audit import audit_ocr_coverage, format_ocr_coverage_audit, write_ocr_coverage_json


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE pages (page_id TEXT PRIMARY KEY)")
        conn.execute(
            """
            CREATE TABLE source_links (
                page_id TEXT,
                manual_id TEXT,
                publication_number TEXT,
                ata_code TEXT,
                page_label TEXT,
                page_sequence INTEGER,
                ocr_text_path TEXT,
                tiff_path TEXT,
                rescarta_url TEXT
            )
            """
        )


def _insert_source(conn: sqlite3.Connection, *, page_id: str, ocr_path: str, tiff_path: str = "page.tif") -> None:
    conn.execute("INSERT INTO pages(page_id) VALUES (?)", (page_id,))
    conn.execute(
        """
        INSERT INTO source_links(
            page_id, manual_id, publication_number, ata_code, page_label,
            page_sequence, ocr_text_path, tiff_path, rescarta_url
        ) VALUES (?, 'manual_a', 'Manual A', '25-21-00', ?, 1, ?, ?, 'http://localhost/page')
        """,
        (page_id, page_id, ocr_path, tiff_path),
    )


def test_audit_counts_empty_and_nonempty_ocr(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _make_db(db)
    ocr1 = tmp_path / "page1.txt"
    ocr2 = tmp_path / "page2.txt"
    ocr1.write_text("This page has useful OCR text.", encoding="utf-8")
    ocr2.write_text("", encoding="utf-8")
    with sqlite3.connect(db) as conn:
        _insert_source(conn, page_id="p1", ocr_path=str(ocr1))
        _insert_source(conn, page_id="p2", ocr_path=str(ocr2))

    summary = audit_ocr_coverage(db, min_chars=10)

    assert summary.local_ocr_paths_ready is True
    assert summary.total_source_links == 2
    assert summary.nonempty_ocr_files == 1
    assert summary.empty_ocr_files == 1
    assert summary.has_empty_or_short_ocr is True
    assert any(row.reason == "empty_ocr_file" for row in summary.sample_rows)


def test_audit_flags_missing_ocr_file_as_not_ready(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _make_db(db)
    with sqlite3.connect(db) as conn:
        _insert_source(conn, page_id="p1", ocr_path=str(tmp_path / "missing.txt"))

    summary = audit_ocr_coverage(db)

    assert summary.local_ocr_paths_ready is False
    assert summary.missing_ocr_files == 1
    assert any(row.reason == "missing_ocr_file" for row in summary.sample_rows)


def test_audit_flags_missing_ocr_path_as_not_ready(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _make_db(db)
    with sqlite3.connect(db) as conn:
        _insert_source(conn, page_id="p1", ocr_path="")

    summary = audit_ocr_coverage(db)

    assert summary.local_ocr_paths_ready is False
    assert summary.missing_ocr_paths == 1
    assert any(row.reason == "missing_ocr_path" for row in summary.sample_rows)


def test_audit_detects_short_nonempty_ocr(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _make_db(db)
    ocr = tmp_path / "short.txt"
    ocr.write_text("abc", encoding="utf-8")
    with sqlite3.connect(db) as conn:
        _insert_source(conn, page_id="p1", ocr_path=str(ocr))

    summary = audit_ocr_coverage(db, min_chars=10)

    assert summary.local_ocr_paths_ready is True
    assert summary.empty_ocr_files == 0
    assert summary.short_ocr_files == 1
    assert summary.has_empty_or_short_ocr is True


def test_format_and_json_are_cli_friendly(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _make_db(db)
    ocr = tmp_path / "page.txt"
    ocr.write_text("Useful OCR text for this test.", encoding="utf-8")
    with sqlite3.connect(db) as conn:
        _insert_source(conn, page_id="p1", ocr_path=str(ocr))

    summary = audit_ocr_coverage(db)
    text = format_ocr_coverage_audit(summary)
    out = write_ocr_coverage_json(summary, tmp_path / "out" / "ocr.json")

    assert "OCR coverage audit" in text
    assert "Local OCR paths ready: yes" in text
    assert out.exists()
    assert "nonempty_ocr_files" in out.read_text(encoding="utf-8")
