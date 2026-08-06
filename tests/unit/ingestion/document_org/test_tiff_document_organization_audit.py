from __future__ import annotations

import sqlite3
from pathlib import Path

from tiff.document_organization_audit import (
    audit_document_organization,
    format_document_organization_audit,
    write_document_organization_json,
)


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    ocr1 = tmp_path / "p1.txt"
    ocr2 = tmp_path / "p2.txt"
    ocr1.write_text("part text", encoding="utf-8")
    ocr2.write_text("", encoding="utf-8")
    with sqlite3.connect(db) as conn:
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
        conn.executemany(
            "INSERT INTO source_links VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("p1", "m1", "Manual One", "25-21-00", "1", 1, str(ocr1), "p1.tif", "url1"),
                ("p2", "m1", "Manual One", "25-21-00", "2", 2, str(ocr2), "p2.tif", "url2"),
                ("p3", "m1", "Manual One", "", "3", 3, "", "p3.tif", "url3"),
            ],
        )
        conn.execute("CREATE TABLE pages (page_id TEXT)")
        conn.executemany("INSERT INTO pages VALUES (?)", [("p1",), ("p2",), ("p3",)])
        # Use the real search-index schema names here: part_number_display and
        # part_number_normalized, not only the simplified part_number name.
        conn.execute(
            """
            CREATE TABLE part_mentions (
                page_id TEXT,
                part_number_display TEXT,
                part_number_normalized TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO part_mentions VALUES (?, ?, ?)",
            [
                ("p1", "120-AAA", "120AAA"),
                ("p2", "120-AAA", "120AAA"),
                ("p2", "120-BBB", "120BBB"),
                ("p2", "RAW-NOISE", "RAWNOISE"),
                ("p2", "120-AAA/BBB", "120AAABBB"),
            ],
        )
        conn.execute(
            """
            CREATE TABLE part_catalog_clean (
                part_number_display TEXT,
                part_number_normalized TEXT,
                canonical_nomenclature TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO part_catalog_clean VALUES (?, ?, ?)",
            [
                ("120-AAA", "120AAA", "BRACKET"),
                ("120-BBB", "120BBB", "CLIP"),
                ("120-AAA/BBB", "120AAABBB", "SHOULD NOT BE TOP LEVEL"),
            ],
        )
    return db


def test_audit_builds_manual_ata_and_part_tree_with_real_part_schema(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    summary = audit_document_organization(db, top_ata_limit=5, top_part_limit=5)
    assert summary.logical_tree_ready is True
    assert summary.pages_total == 3
    assert summary.manuals_total == 1
    assert summary.ata_groups_total == 1
    assert summary.pages_with_ata == 2
    assert summary.pages_without_ata == 1
    assert summary.empty_ocr_pages == 1
    assert summary.part_tree_source == "clean_catalog_allowlist"
    assert summary.raw_part_mentions_total == 5
    assert summary.raw_distinct_parts_total == 4
    assert summary.part_mentions_total == 3
    assert summary.distinct_parts_total == 2
    assert summary.pages_with_parts == 2
    assert summary.raw_mentions_excluded_from_part_tree == 2
    assert summary.compound_part_references_suppressed == 1
    assert summary.top_ata_groups[0].ata_code == "25-21-00"
    assert summary.top_ata_groups[0].page_count == 2
    assert summary.top_ata_groups[0].part_mention_count == 3
    assert summary.top_parts[0].part_number == "120-AAA"
    assert summary.top_parts[0].nomenclature == "BRACKET"
    assert summary.top_parts[0].page_count == 2
    assert summary.top_parts[0].mention_count == 2
    assert all("/" not in row.part_number for row in summary.top_parts)


def test_audit_falls_back_to_simplified_part_schema(tmp_path: Path) -> None:
    db = tmp_path / "simple.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE source_links (page_id TEXT, manual_id TEXT, publication_number TEXT, ata_code TEXT)")
        conn.execute("INSERT INTO source_links VALUES ('p1', 'm1', 'Manual One', '25-21-00')")
        conn.execute("CREATE TABLE part_mentions (page_id TEXT, part_number TEXT)")
        conn.execute("INSERT INTO part_mentions VALUES ('p1', '120-CCC')")
        conn.execute("CREATE TABLE part_catalog_clean (part_number TEXT, nomenclature TEXT)")
        conn.execute("INSERT INTO part_catalog_clean VALUES ('120-CCC', 'HINGE')")
    summary = audit_document_organization(db, top_ata_limit=5, top_part_limit=5)
    assert summary.part_tree_source == "clean_catalog_allowlist"
    assert summary.distinct_parts_total == 1
    assert summary.top_parts[0].part_number == "120-CCC"
    assert summary.top_parts[0].nomenclature == "HINGE"


def test_format_includes_expected_sections(tmp_path: Path) -> None:
    summary = audit_document_organization(_make_db(tmp_path), top_ata_limit=5, top_part_limit=5)
    text = format_document_organization_audit(summary)
    assert "Document organization audit" in text
    assert "Top manual/ATA groups" in text
    assert "Top part tree entries" in text
    assert "Pages without ATA: 1" in text
    assert "Part tree source: clean_catalog_allowlist" in text
    assert "Raw mentions excluded from logical part tree: 2" in text
    assert "120-AAA" in text


def test_json_writer_outputs_logical_tree_ready(tmp_path: Path) -> None:
    summary = audit_document_organization(_make_db(tmp_path), top_ata_limit=5, top_part_limit=5)
    out = write_document_organization_json(summary, tmp_path / "org.json")
    text = out.read_text(encoding="utf-8")
    assert '"logical_tree_ready": true' in text
    assert '"top_ata_groups"' in text
    assert '"top_parts"' in text


def test_missing_db_is_not_ready(tmp_path: Path) -> None:
    summary = audit_document_organization(tmp_path / "missing.db")
    assert summary.logical_tree_ready is False
    assert summary.pages_total == 0
    assert summary.warnings
