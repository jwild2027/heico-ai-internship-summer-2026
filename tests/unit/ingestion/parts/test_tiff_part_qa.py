import sqlite3

from tiff.part_qa import (
    report_nomenclature_groups,
    report_part_nomenclature_conflicts,
    report_parts_missing_nomenclature,
    report_suspicious_part_ata,
)


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE pages (
            page_id TEXT PRIMARY KEY,
            manual_id TEXT,
            page_sequence INTEGER,
            page_label TEXT,
            ata_code TEXT,
            tiff_path TEXT,
            ocr_text_path TEXT
        );
        CREATE TABLE part_mentions (
            mention_id TEXT PRIMARY KEY,
            part_number_display TEXT,
            part_number_normalized TEXT,
            manual_id TEXT,
            page_id TEXT,
            page_sequence INTEGER,
            ata_code TEXT,
            context TEXT
        );
        CREATE TABLE part_catalog (
            catalog_id TEXT PRIMARY KEY,
            part_number_display TEXT,
            part_number_normalized TEXT,
            nomenclature TEXT,
            page_id TEXT,
            manual_id TEXT
        );
        CREATE TABLE part_catalog_clean (
            part_number_normalized TEXT PRIMARY KEY,
            part_number_display TEXT,
            canonical_nomenclature TEXT,
            best_ata_code TEXT
        );
        """
    )
    conn.execute("INSERT INTO pages VALUES ('p1','m1',1,'1056','25-21-00','a.tif','a.txt')")
    conn.execute("INSERT INTO pages VALUES ('p2','m1',2,'1021','11-00-66','b.tif','b.txt')")
    conn.execute("INSERT INTO part_mentions VALUES ('m1','120-37313-001','12037313001','m1','p1',1,'25-21-00','ctx')")
    conn.execute("INSERT INTO part_mentions VALUES ('m2','120-37313-001','12037313001','m1','p2',2,'11-00-66','ctx')")
    conn.execute("INSERT INTO part_mentions VALUES ('m3','999-00000-001','99900000001','m1','p2',2,'11-00-66','ctx')")
    conn.execute("INSERT INTO part_catalog VALUES ('c1','120-37313-001','12037313001','HOLDER, MAGAZINE','p1','m1')")
    conn.execute("INSERT INTO part_catalog VALUES ('c2','120-37313-001','12037313001','HOLDER MAGAZINE','p2','m1')")
    conn.execute("INSERT INTO part_catalog_clean VALUES ('12037313001','120-37313-001','HOLDER, MAGAZINE','25-21-00')")
    conn.commit()
    return conn


def test_report_part_nomenclature_conflicts():
    conn = make_conn()
    rows = report_part_nomenclature_conflicts(conn)
    assert rows
    assert rows[0].part_number == "120-37313-001"


def test_report_nomenclature_groups():
    conn = make_conn()
    rows = report_nomenclature_groups(conn)
    assert rows[0].nomenclature == "HOLDER, MAGAZINE"
    assert "120-37313-001" in rows[0].details


def test_report_parts_missing_nomenclature():
    conn = make_conn()
    rows = report_parts_missing_nomenclature(conn)
    assert any(r.part_number == "999-00000-001" for r in rows)


def test_report_suspicious_part_ata():
    conn = make_conn()
    rows = report_suspicious_part_ata(conn)
    assert rows
    assert rows[0].part_number == "120-37313-001"
    assert "Catalog ATA: 25-21-00" in rows[0].details
