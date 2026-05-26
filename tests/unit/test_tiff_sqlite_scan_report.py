from __future__ import annotations

import json

from tiff.sqlite_store import connect, get_scan_report, list_tiff_files, upsert_scan_report


def sample_report() -> dict:
    return {
        "schema_version": "tiff_scan_report.v3",
        "generated_at_utc": "2026-05-26T15:33:03Z",
        "scan_status": "ok",
        "source": {
            "type": "single_tiff_upload_or_file",
            "path": "C:/tmp/00000018.tif",
            "relative_path": "00000018.tif",
        },
        "file": {
            "file_name": "00000018.tif",
            "extension": ".tif",
            "file_size_bytes": 38656,
            "modified_time_utc": "2026-05-26T15:33:01Z",
            "sha256": "aeb66b86579e3652c6080682649121b8a07f30c5ce40fbe",
        },
        "tiff": {
            "page_count": 1,
            "width_px": 3562,
            "height_px": 4608,
            "dpi_x": 419.0,
            "dpi_y": 419.0,
            "color_mode": "1",
            "compression": "group4",
            "read_error": None,
        },
        "document_classification": {
            "detected_type": "maintenance_manual_ipl",
            "confidence": 1.0,
            "signals": ["manual_title", "figure_number", "ata_code"],
        },
        "drawing_metadata": {
            "drawing_number": None,
            "document_number": None,
            "part_number": None,
            "revision": None,
            "sheet_number": None,
            "sheet_count": None,
            "title": None,
            "classification": None,
            "metadata_confidence": 0.05,
        },
        "manual_metadata": {
            "document_type": "maintenance_manual_ipl",
            "manufacturer": "EMBRAER",
            "manual_title": "MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST",
            "document_code": "120TP250002.MCE",
            "figure_title": "Double Passenger Seat",
            "figure_number": "2",
            "effectivity": "ALL",
            "ata_code": "25-21-00",
            "page_number": 4,
            "revision_date": "Sep 30/98",
            "callouts": ["ASHTRAY"],
            "metadata_confidence": 1.0,
        },
        "ocr": {
            "enabled": True,
            "status": "ok",
            "engine": "tesseract",
            "page_index": 0,
            "combined_text": "120TP250002.MCE\nDouble Passenger Seat\nFigure 2",
            "regions": [
                {
                    "region_name": "bottom_strip",
                    "page_index": 0,
                    "bbox": [0, 3225, 3562, 4608],
                    "status": "ok",
                    "text": "120TP250002.MCE\nDouble Passenger Seat\nFigure 2",
                    "char_count": 44,
                    "error": None,
                }
            ],
        },
    }


def test_upsert_scan_report_saves_manual_metadata_and_ocr(tmp_path):
    db_path = tmp_path / "tiff_scans.db"
    with connect(db_path) as conn:
        file_id = upsert_scan_report(conn, sample_report())

        assert file_id == "aeb66b86579e3652c6080682649121b8"

        manual = conn.execute("SELECT * FROM tiff_manual_metadata WHERE file_id = ?", (file_id,)).fetchone()
        assert manual["manufacturer"] == "EMBRAER"
        assert manual["document_code"] == "120TP250002.MCE"
        assert manual["figure_title"] == "Double Passenger Seat"
        assert json.loads(manual["callouts_json"]) == ["ASHTRAY"]

        doc_type = conn.execute("SELECT * FROM tiff_document_classification WHERE file_id = ?", (file_id,)).fetchone()
        assert doc_type["detected_type"] == "maintenance_manual_ipl"
        assert json.loads(doc_type["signals_json"]) == ["manual_title", "figure_number", "ata_code"]

        ocr_rows = conn.execute("SELECT region_type, text FROM tiff_ocr_texts WHERE file_id = ? ORDER BY region_type", (file_id,)).fetchall()
        assert [row["region_type"] for row in ocr_rows] == ["bottom_strip", "combined"]

        saved_report = get_scan_report(conn, file_id)
        assert saved_report["manual_metadata"]["ata_code"] == "25-21-00"

        rows = list_tiff_files(conn, limit=5)
        assert rows[0]["file_name"] == "00000018.tif"
        assert rows[0]["detected_type"] == "maintenance_manual_ipl"
        assert rows[0]["document_code"] == "120TP250002.MCE"


def test_upsert_scan_report_replaces_ocr_rows_for_same_file(tmp_path):
    report = sample_report()
    with connect(tmp_path / "tiff_scans.db") as conn:
        file_id = upsert_scan_report(conn, report)
        report["ocr"]["combined_text"] = "EMBRAER"
        report["ocr"]["regions"] = [
            {
                "region_name": "top_strip",
                "page_index": 0,
                "bbox": [0, 0, 3562, 829],
                "status": "ok",
                "text": "EMBRAER",
            }
        ]
        upsert_scan_report(conn, report)
        rows = conn.execute("SELECT region_type, text FROM tiff_ocr_texts WHERE file_id = ? ORDER BY region_type", (file_id,)).fetchall()
        assert [row["region_type"] for row in rows] == ["combined", "top_strip"]
        assert rows[0]["text"] == "EMBRAER"
