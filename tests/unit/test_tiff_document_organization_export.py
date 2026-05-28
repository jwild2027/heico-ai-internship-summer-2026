from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tiff.document_organization_export import (
    build_document_organization_export,
    format_document_organization_export,
    write_document_organization_export,
)


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    ocr1 = tmp_path / "p1.txt"
    ocr2 = tmp_path / "p2.txt"
    ocr1.write_text("Part 120-1 text", encoding="utf-8")
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
                source_url TEXT,
                rescarta_url TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO source_links VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("p1", "m1", "Manual One", "25-21-00", "1", 1, str(ocr1), "p1.tif", "source1", "res1"),
                ("p2", "m1", "Manual One", "25-21-00", "2", 2, str(ocr2), "p2.tif", "source2", "res2"),
                ("p3", "m1", "Manual One", "11-00-66", "3", 3, "", "p3.tif", "source3", "res3"),
            ],
        )
        conn.execute("CREATE TABLE pages (page_id TEXT)")
        conn.executemany("INSERT INTO pages VALUES (?)", [("p1",), ("p2",), ("p3",)])
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
                ("p1", "120-1", "1201"),
                ("p1", "120-2", "1202"),
                ("p2", "120-1", "1201"),
                ("p1", "120-1/2", "12012"),
                ("p3", "RAW-NOT-CLEAN", "rawnotclean"),
            ],
        )
        conn.execute(
            """
            CREATE TABLE part_catalog_clean (
                part_number_display TEXT,
                part_number_normalized TEXT,
                nomenclature TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO part_catalog_clean VALUES (?, ?, ?)",
            [
                ("120-1", "1201", "TEST PART ONE"),
                ("120-2", "1202", "TEST PART TWO"),
            ],
        )
    return db


def test_build_export_counts_and_trees(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    export = build_document_organization_export(db, output_dir=tmp_path / "out")

    assert export.summary.ready is True
    assert export.summary.page_count == 3
    assert export.summary.manual_count == 1
    assert export.summary.ata_group_count == 2
    assert export.summary.part_count == 2
    assert export.summary.part_mention_count == 3
    assert export.summary.part_tree_source == "clean_catalog_allowlist"
    assert export.summary.raw_part_count == 4
    assert export.summary.raw_part_mention_count == 5
    assert export.summary.raw_mentions_excluded_from_part_tree == 2
    assert export.summary.compound_part_references_suppressed == 1
    assert export.summary.empty_ocr_page_count == 1

    manual = export.manual_tree["manuals"][0]
    assert manual["manual_id"] == "m1"
    assert manual["manual"] == "Manual One"
    assert manual["title"] == "Manual One"
    assert manual["page_count"] == 3
    assert len(manual["ata_groups"]) == 2

    ata_groups = {(row["manual_id"], row["ata_code"]): row for row in export.ata_tree["ata_groups"]}
    assert ata_groups[("m1", "25-21-00")]["manual"] == "Manual One"
    assert ata_groups[("m1", "25-21-00")]["ata"] == "25-21-00"

    page_index = {row["page_id"]: row for row in export.page_index["pages"]}
    assert page_index["p1"]["manual"] == "Manual One"
    assert page_index["p1"]["ata"] == "25-21-00"

    parts = {row["part_number"]: row for row in export.part_tree["parts"]}
    assert set(parts) == {"120-1", "120-2"}
    assert parts["120-1"]["nomenclature"] == "TEST PART ONE"
    assert parts["120-1"]["page_count"] == 2
    assert "25-21-00" in parts["120-1"]["ata_codes"]
    assert page_index["p1"]["part_numbers"] == ["120-1", "120-2"]


def test_write_export_files(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    export = build_document_organization_export(db, output_dir=tmp_path / "out")
    summary = write_document_organization_export(export, tmp_path / "out")

    expected = {
        "manual_ata_tree.json",
        "ata_tree.json",
        "part_tree.json",
        "page_index.json",
        "organization_summary.json",
    }
    assert {Path(path).name for path in summary.files_written} == expected
    summary_json = json.loads((tmp_path / "out" / "organization_summary.json").read_text(encoding="utf-8"))
    assert {Path(path).name for path in summary_json["files_written"]} == expected
    assert len(summary_json["files_written"]) == 5
    part_tree = json.loads((tmp_path / "out" / "part_tree.json").read_text(encoding="utf-8"))
    exported_parts = {row["part_number"] for row in part_tree["parts"]}
    assert exported_parts == {"120-1", "120-2"}
    assert "120-1/2" not in exported_parts
    assert "RAW-NOT-CLEAN" not in exported_parts
    assert summary_json["part_tree_source"] == "clean_catalog_allowlist"
    assert summary_json["raw_mentions_excluded_from_part_tree"] == 2


def test_format_export_summary(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    export = build_document_organization_export(db, output_dir=tmp_path / "out")
    summary = write_document_organization_export(export, tmp_path / "out")
    text = format_document_organization_export(summary)

    assert "Document organization export" in text
    assert "Status: OK" in text
    assert "Distinct parts: 2" in text
    assert "Raw part mentions seen: 5" in text
    assert "Raw mentions excluded from part tree: 2" in text
    assert "manual_ata_tree.json" in text


def test_missing_db_is_not_ready(tmp_path: Path) -> None:
    export = build_document_organization_export(tmp_path / "missing.db", output_dir=tmp_path / "out")

    assert export.summary.ready is False
    assert export.summary.page_count == 0
    assert export.summary.warnings
