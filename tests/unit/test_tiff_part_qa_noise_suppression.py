import sqlite3

from tiff.part_qa import report_nomenclature_groups, report_parts_missing_nomenclature


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_missing_nomenclature_suppresses_ata_references_but_keeps_real_parts():
    conn = make_conn()
    conn.executescript(
        """
        CREATE TABLE part_mentions (
            part_number_display TEXT,
            part_number_normalized TEXT,
            page_id TEXT
        );
        CREATE TABLE pages (
            page_id TEXT,
            page_label TEXT,
            page_sequence INTEGER
        );
        CREATE TABLE part_catalog_clean (
            part_number_display TEXT,
            part_number_normalized TEXT,
            canonical_nomenclature TEXT
        );
        INSERT INTO pages VALUES ('p1', '1012', 1);
        INSERT INTO part_mentions VALUES ('25-21-00-46', '25210046', 'p1');
        INSERT INTO part_mentions VALUES ('25-IPL', '25IPL', 'p1');
        INSERT INTO part_mentions VALUES ('120TP250008.MCE', '120TP250008MCE', 'p1');
        INSERT INTO part_mentions VALUES ('AM03078-22', 'AM0307822', 'p1');
        """
    )
    records = report_parts_missing_nomenclature(conn, limit=20)
    assert [r.part_number for r in records] == ["AM03078-22"]


def test_nomenclature_groups_suppress_header_noise():
    conn = make_conn()
    conn.executescript(
        """
        CREATE TABLE part_catalog_clean (
            part_number_display TEXT,
            part_number_normalized TEXT,
            canonical_nomenclature TEXT
        );
        INSERT INTO part_catalog_clean VALUES ('120-37313-001', '12037313001', 'HOLDER, MAGAZINE');
        INSERT INTO part_catalog_clean VALUES ('120-36843-001', '12036843001', 'HOLDER, MAGAZINE');
        INSERT INTO part_catalog_clean VALUES ('25-IPL', '25IPL', 'T.P');
        INSERT INTO part_catalog_clean VALUES ('120TP250008.MCE', '120TP250008MCE', 'IGURE');
        INSERT INTO part_catalog_clean VALUES ('25-21-00-46', '25210046', 'SHEET');
        """
    )
    records = report_nomenclature_groups(conn, limit=20)
    assert len(records) == 1
    assert records[0].nomenclature == "HOLDER, MAGAZINE"
    assert records[0].count == 2
