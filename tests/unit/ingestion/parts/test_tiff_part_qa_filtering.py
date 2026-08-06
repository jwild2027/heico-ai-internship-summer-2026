import sqlite3

from tiff.part_qa import (
    report_nomenclature_groups,
    report_part_nomenclature_conflicts,
    report_parts_missing_nomenclature,
)


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE pages (page_id TEXT PRIMARY KEY, page_label TEXT, page_sequence INTEGER, ata_code TEXT);
        CREATE TABLE part_mentions (
            mention_id TEXT PRIMARY KEY,
            part_number_display TEXT,
            part_number_normalized TEXT,
            page_id TEXT,
            page_sequence INTEGER,
            ata_code TEXT
        );
        CREATE TABLE part_catalog_mentions_clean (
            catalog_id TEXT PRIMARY KEY,
            part_number_display TEXT,
            part_number_normalized TEXT,
            clean_nomenclature TEXT
        );
        CREATE TABLE part_catalog_clean (
            part_number_normalized TEXT PRIMARY KEY,
            part_number_display TEXT,
            canonical_nomenclature TEXT,
            best_ata_code TEXT
        );
        """
    )
    conn.execute("INSERT INTO pages VALUES ('p1','1056',1,'25-21-00')")
    conn.execute("INSERT INTO part_mentions VALUES ('m1','25-21-00-46','25210046','p1',1,'25-21-00')")
    conn.execute("INSERT INTO part_mentions VALUES ('m2','120-37313-001','12037313001','p1',1,'25-21-00')")
    conn.execute("INSERT INTO part_mentions VALUES ('m3','999-00000-001','99900000001','p1',1,'25-21-00')")
    conn.execute("INSERT INTO part_catalog_clean VALUES ('12037313001','120-37313-001','HOLDER, MAGAZINE','25-21-00')")
    conn.execute("INSERT INTO part_catalog_mentions_clean VALUES ('c1','120-37313-001','12037313001','HOLDER, MAGAZINE')")
    conn.execute("INSERT INTO part_catalog_mentions_clean VALUES ('c2','120-37313-001','12037313001','HOLDER, MAGAZINE VS4956')")
    conn.execute("INSERT INTO part_catalog_mentions_clean VALUES ('c3','120-48023-001','12048023001','PIN, ATTACH')")
    conn.execute("INSERT INTO part_catalog_mentions_clean VALUES ('c4','120-48023-001','12048023001','BRACKET')")
    conn.commit()
    return conn


def test_missing_nomenclature_filters_ata_references():
    rows = report_parts_missing_nomenclature(make_conn())
    parts = {r.part_number for r in rows}
    assert "25-21-00-46" not in parts
    assert "999-00000-001" in parts


def test_conflicts_ignore_ocr_tail_variants_but_keep_real_conflicts():
    rows = report_part_nomenclature_conflicts(make_conn())
    keys = {r.key for r in rows}
    assert "12037313001" not in keys
    assert "12048023001" in keys


def test_nomenclature_groups_filter_bad_names():
    rows = report_nomenclature_groups(make_conn())
    names = {r.nomenclature for r in rows}
    assert "HOLDER, MAGAZINE" in names
    assert "T.P" not in names
