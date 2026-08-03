"""SQLite storage for TIFF inventory, scan reports, and extracted metadata.

This module is separate from the existing PDF tables so the TIFF layer can be
added without risking the current PDF ingestion/RAG workflow.

The tables intentionally use a ``tiff_`` prefix. For the prototype, SQLite is
fine. For the 5 TB production server, the same logical model can move to
PostgreSQL later.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from tiff.inventory import TIFFInventoryRecord
from tiff.metadata_parser import ParsedDrawingMetadata

CREATE_TIFF_FILES = """
CREATE TABLE IF NOT EXISTS tiff_files (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    relative_path TEXT,
    file_name TEXT NOT NULL,
    extension TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    modified_time_utc TEXT NOT NULL,
    sha256 TEXT,
    inventory_status TEXT NOT NULL DEFAULT 'inventoried',
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_TIFF_TECHNICAL_METADATA = """
CREATE TABLE IF NOT EXISTS tiff_technical_metadata (
    file_id TEXT PRIMARY KEY REFERENCES tiff_files(id) ON DELETE CASCADE,
    page_count INTEGER,
    width_px INTEGER,
    height_px INTEGER,
    dpi_x REAL,
    dpi_y REAL,
    color_mode TEXT,
    compression TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_TIFF_DRAWING_METADATA = """
CREATE TABLE IF NOT EXISTS tiff_drawing_metadata (
    file_id TEXT PRIMARY KEY REFERENCES tiff_files(id) ON DELETE CASCADE,
    drawing_number TEXT,
    document_number TEXT,
    part_number TEXT,
    revision TEXT,
    sheet_number INTEGER,
    sheet_count INTEGER,
    title TEXT,
    classification TEXT,
    metadata_confidence REAL NOT NULL DEFAULT 0.0,
    source TEXT NOT NULL DEFAULT 'filename_or_header',
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_TIFF_MANUAL_METADATA = """
CREATE TABLE IF NOT EXISTS tiff_manual_metadata (
    file_id TEXT PRIMARY KEY REFERENCES tiff_files(id) ON DELETE CASCADE,
    document_type TEXT,
    manufacturer TEXT,
    manual_title TEXT,
    document_code TEXT,
    publication_number TEXT,
    component_title TEXT,
    section_title TEXT,
    figure_title TEXT,
    figure_number TEXT,
    effectivity TEXT,
    ata_code TEXT,
    page_number INTEGER,
    page_label TEXT,
    issue_date TEXT,
    revision_date TEXT,
    revision_label TEXT,
    part_numbers_json TEXT,
    callouts_json TEXT,
    metadata_confidence REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_TIFF_DOCUMENT_CLASSIFICATION = """
CREATE TABLE IF NOT EXISTS tiff_document_classification (
    file_id TEXT PRIMARY KEY REFERENCES tiff_files(id) ON DELETE CASCADE,
    detected_type TEXT NOT NULL DEFAULT 'unknown',
    confidence REAL NOT NULL DEFAULT 0.0,
    signals_json TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_TIFF_OCR_TEXTS = """
CREATE TABLE IF NOT EXISTS tiff_ocr_texts (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL REFERENCES tiff_files(id) ON DELETE CASCADE,
    page_number INTEGER,
    region_type TEXT NOT NULL,
    text TEXT NOT NULL,
    confidence REAL,
    engine TEXT,
    bbox_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_TIFF_SCAN_REPORTS = """
CREATE TABLE IF NOT EXISTS tiff_scan_reports (
    file_id TEXT PRIMARY KEY REFERENCES tiff_files(id) ON DELETE CASCADE,
    schema_version TEXT,
    generated_at_utc TEXT,
    scan_status TEXT,
    report_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

CREATE_TIFF_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tiff_files_sha256 ON tiff_files(sha256);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_files_name ON tiff_files(file_name);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_drawing_number ON tiff_drawing_metadata(drawing_number);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_part_number ON tiff_drawing_metadata(part_number);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_revision ON tiff_drawing_metadata(revision);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_classification ON tiff_drawing_metadata(classification);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_manual_document_code ON tiff_manual_metadata(document_code);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_manual_publication_number ON tiff_manual_metadata(publication_number);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_manual_section_title ON tiff_manual_metadata(section_title);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_manual_ata_code ON tiff_manual_metadata(ata_code);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_manual_figure_number ON tiff_manual_metadata(figure_number);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_document_type ON tiff_document_classification(detected_type);",
    "CREATE INDEX IF NOT EXISTS idx_tiff_ocr_file_region ON tiff_ocr_texts(file_id, region_type);",
]




def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_definition: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def _migrate_tiff_manual_metadata(conn: sqlite3.Connection) -> None:
    # Older prototype DBs only had the first manual/IPL fields. Add the newer
    # manual-page fields in-place so users do not need to delete local DBs.
    columns = {
        "publication_number": "TEXT",
        "component_title": "TEXT",
        "section_title": "TEXT",
        "page_label": "TEXT",
        "issue_date": "TEXT",
        "revision_label": "TEXT",
        "part_numbers_json": "TEXT",
    }
    for column_name, column_definition in columns.items():
        _ensure_column(conn, "tiff_manual_metadata", column_name, column_definition)

def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_tiff_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute(CREATE_TIFF_FILES)
        conn.execute(CREATE_TIFF_TECHNICAL_METADATA)
        conn.execute(CREATE_TIFF_DRAWING_METADATA)
        conn.execute(CREATE_TIFF_MANUAL_METADATA)
        conn.execute(CREATE_TIFF_DOCUMENT_CLASSIFICATION)
        conn.execute(CREATE_TIFF_OCR_TEXTS)
        conn.execute(CREATE_TIFF_SCAN_REPORTS)
        _migrate_tiff_manual_metadata(conn)
        for statement in CREATE_TIFF_INDEXES:
            conn.execute(statement)


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _file_id(record: TIFFInventoryRecord) -> str:
    if record.sha256:
        return record.sha256[:32]
    return _stable_id(record.source_path)


def _file_id_from_report(report: dict[str, Any]) -> str:
    file_info = report.get("file") or {}
    source_info = report.get("source") or {}
    sha256 = file_info.get("sha256")
    if sha256:
        return str(sha256)[:32]
    return _stable_id(str(source_info.get("path") or file_info.get("file_name") or "unknown_tiff"))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=False)


def upsert_tiff_inventory(conn: sqlite3.Connection, record: TIFFInventoryRecord) -> str:
    """Insert/update a TIFF inventory record and return file_id."""

    file_id = _file_id(record)
    with conn:
        conn.execute(
            """
            INSERT INTO tiff_files (
                id, source_path, relative_path, file_name, extension,
                file_size_bytes, modified_time_utc, sha256, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                relative_path=excluded.relative_path,
                file_name=excluded.file_name,
                extension=excluded.extension,
                file_size_bytes=excluded.file_size_bytes,
                modified_time_utc=excluded.modified_time_utc,
                sha256=excluded.sha256,
                error=excluded.error,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                record.source_path,
                record.relative_path,
                record.file_name,
                record.extension,
                record.file_size_bytes,
                record.modified_time_utc,
                record.sha256,
                record.error,
            ),
        )
        conn.execute(
            """
            INSERT INTO tiff_technical_metadata (
                file_id, page_count, width_px, height_px, dpi_x, dpi_y,
                color_mode, compression
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                page_count=excluded.page_count,
                width_px=excluded.width_px,
                height_px=excluded.height_px,
                dpi_x=excluded.dpi_x,
                dpi_y=excluded.dpi_y,
                color_mode=excluded.color_mode,
                compression=excluded.compression,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                record.page_count,
                record.width_px,
                record.height_px,
                record.dpi_x,
                record.dpi_y,
                record.color_mode,
                record.compression,
            ),
        )
    return file_id


def upsert_drawing_metadata(
    conn: sqlite3.Connection,
    file_id: str,
    metadata: ParsedDrawingMetadata,
    *,
    source: str = "filename_or_header",
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO tiff_drawing_metadata (
                file_id, drawing_number, document_number, part_number, revision,
                sheet_number, sheet_count, title, classification,
                metadata_confidence, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                drawing_number=excluded.drawing_number,
                document_number=excluded.document_number,
                part_number=excluded.part_number,
                revision=excluded.revision,
                sheet_number=excluded.sheet_number,
                sheet_count=excluded.sheet_count,
                title=excluded.title,
                classification=excluded.classification,
                metadata_confidence=excluded.metadata_confidence,
                source=excluded.source,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                metadata.drawing_number,
                metadata.document_number,
                metadata.part_number,
                metadata.revision,
                metadata.sheet_number,
                metadata.sheet_count,
                metadata.title,
                metadata.classification,
                metadata.metadata_confidence,
                source,
            ),
        )


def upsert_scan_report(conn: sqlite3.Connection, report: dict[str, Any]) -> str:
    """Persist one JSON scan report into normalized TIFF tables.

    This keeps the full JSON report for audit/debugging and also extracts the
    most useful searchable fields into normalized tables.
    """

    init_tiff_schema(conn)

    file_id = _file_id_from_report(report)
    source = report.get("source") or {}
    file_info = report.get("file") or {}
    tiff_info = report.get("tiff") or {}
    drawing = report.get("drawing_metadata") or {}
    manual = report.get("manual_metadata") or {}
    classification = report.get("document_classification") or {}
    ocr = report.get("ocr") or {}

    source_path = str(source.get("path") or file_info.get("file_name") or file_id)
    relative_path = source.get("relative_path")
    file_name = str(file_info.get("file_name") or Path(source_path).name or file_id)
    extension = str(file_info.get("extension") or Path(file_name).suffix or ".tif")
    file_size_bytes = int(file_info.get("file_size_bytes") or 0)
    modified_time_utc = str(file_info.get("modified_time_utc") or report.get("generated_at_utc") or "")
    sha256 = file_info.get("sha256")
    scan_status = str(report.get("scan_status") or "unknown")

    with conn:
        conn.execute(
            """
            INSERT INTO tiff_files (
                id, source_path, relative_path, file_name, extension,
                file_size_bytes, modified_time_utc, sha256, inventory_status, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                relative_path=excluded.relative_path,
                file_name=excluded.file_name,
                extension=excluded.extension,
                file_size_bytes=excluded.file_size_bytes,
                modified_time_utc=excluded.modified_time_utc,
                sha256=excluded.sha256,
                inventory_status=excluded.inventory_status,
                error=excluded.error,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                source_path,
                relative_path,
                file_name,
                extension,
                file_size_bytes,
                modified_time_utc,
                sha256,
                scan_status,
                tiff_info.get("read_error"),
            ),
        )

        conn.execute(
            """
            INSERT INTO tiff_technical_metadata (
                file_id, page_count, width_px, height_px, dpi_x, dpi_y,
                color_mode, compression
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                page_count=excluded.page_count,
                width_px=excluded.width_px,
                height_px=excluded.height_px,
                dpi_x=excluded.dpi_x,
                dpi_y=excluded.dpi_y,
                color_mode=excluded.color_mode,
                compression=excluded.compression,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                tiff_info.get("page_count"),
                tiff_info.get("width_px"),
                tiff_info.get("height_px"),
                tiff_info.get("dpi_x"),
                tiff_info.get("dpi_y"),
                tiff_info.get("color_mode"),
                tiff_info.get("compression"),
            ),
        )

        conn.execute(
            """
            INSERT INTO tiff_drawing_metadata (
                file_id, drawing_number, document_number, part_number, revision,
                sheet_number, sheet_count, title, classification,
                metadata_confidence, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                drawing_number=excluded.drawing_number,
                document_number=excluded.document_number,
                part_number=excluded.part_number,
                revision=excluded.revision,
                sheet_number=excluded.sheet_number,
                sheet_count=excluded.sheet_count,
                title=excluded.title,
                classification=excluded.classification,
                metadata_confidence=excluded.metadata_confidence,
                source=excluded.source,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                drawing.get("drawing_number"),
                drawing.get("document_number"),
                drawing.get("part_number"),
                drawing.get("revision"),
                drawing.get("sheet_number"),
                drawing.get("sheet_count"),
                drawing.get("title"),
                drawing.get("classification"),
                float(drawing.get("metadata_confidence") or 0.0),
                "json_report",
            ),
        )

        conn.execute(
            """
            INSERT INTO tiff_manual_metadata (
                file_id, document_type, manufacturer, manual_title, document_code,
                publication_number, component_title, section_title,
                figure_title, figure_number, effectivity, ata_code, page_number,
                page_label, issue_date, revision_date, revision_label,
                part_numbers_json, callouts_json, metadata_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                document_type=excluded.document_type,
                manufacturer=excluded.manufacturer,
                manual_title=excluded.manual_title,
                document_code=excluded.document_code,
                publication_number=excluded.publication_number,
                component_title=excluded.component_title,
                section_title=excluded.section_title,
                figure_title=excluded.figure_title,
                figure_number=excluded.figure_number,
                effectivity=excluded.effectivity,
                ata_code=excluded.ata_code,
                page_number=excluded.page_number,
                page_label=excluded.page_label,
                issue_date=excluded.issue_date,
                revision_date=excluded.revision_date,
                revision_label=excluded.revision_label,
                part_numbers_json=excluded.part_numbers_json,
                callouts_json=excluded.callouts_json,
                metadata_confidence=excluded.metadata_confidence,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                manual.get("document_type"),
                manual.get("manufacturer"),
                manual.get("manual_title"),
                manual.get("document_code"),
                manual.get("publication_number"),
                manual.get("component_title"),
                manual.get("section_title"),
                manual.get("figure_title"),
                manual.get("figure_number"),
                manual.get("effectivity"),
                manual.get("ata_code"),
                manual.get("page_number"),
                manual.get("page_label"),
                manual.get("issue_date"),
                manual.get("revision_date"),
                manual.get("revision_label"),
                _json_dumps(manual.get("part_numbers") or []),
                _json_dumps(manual.get("callouts") or []),
                float(manual.get("metadata_confidence") or 0.0),
            ),
        )

        conn.execute(
            """
            INSERT INTO tiff_document_classification (
                file_id, detected_type, confidence, signals_json
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                detected_type=excluded.detected_type,
                confidence=excluded.confidence,
                signals_json=excluded.signals_json,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                classification.get("detected_type") or "unknown",
                float(classification.get("confidence") or 0.0),
                _json_dumps(classification.get("signals") or []),
            ),
        )

        conn.execute(
            """
            INSERT INTO tiff_scan_reports (
                file_id, schema_version, generated_at_utc, scan_status, report_json
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                schema_version=excluded.schema_version,
                generated_at_utc=excluded.generated_at_utc,
                scan_status=excluded.scan_status,
                report_json=excluded.report_json,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                file_id,
                report.get("schema_version"),
                report.get("generated_at_utc"),
                scan_status,
                _json_dumps(report),
            ),
        )

        # Refresh OCR rows for this scan report. Keeping one set per latest scan
        # avoids duplicate region rows when a file is rescanned.
        conn.execute("DELETE FROM tiff_ocr_texts WHERE file_id = ?", (file_id,))

        combined_text = ocr.get("combined_text")
        if combined_text:
            row_id = _stable_id(f"{file_id}:combined")
            conn.execute(
                """
                INSERT INTO tiff_ocr_texts (
                    id, file_id, page_number, region_type, text, confidence, engine, bbox_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    file_id,
                    ocr.get("page_index"),
                    "combined",
                    combined_text,
                    None,
                    ocr.get("engine"),
                    None,
                ),
            )

        for index, region in enumerate(ocr.get("regions") or []):
            region_name = str(region.get("region_name") or f"region_{index}")
            text = region.get("text") or ""
            if not text:
                continue
            row_id = _stable_id(f"{file_id}:{region_name}:{index}")
            conn.execute(
                """
                INSERT INTO tiff_ocr_texts (
                    id, file_id, page_number, region_type, text, confidence, engine, bbox_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    file_id,
                    region.get("page_index", ocr.get("page_index")),
                    region_name,
                    text,
                    None,
                    ocr.get("engine"),
                    _json_dumps(region.get("bbox")) if region.get("bbox") is not None else None,
                ),
            )

    return file_id


def get_scan_report(conn: sqlite3.Connection, file_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT report_json FROM tiff_scan_reports WHERE file_id = ?",
        (file_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["report_json"])


def list_tiff_files(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            f.id,
            f.source_path,
            f.relative_path,
            f.file_name,
            f.extension,
            f.file_size_bytes,
            f.modified_time_utc,
            f.sha256,
            f.inventory_status,
            tm.page_count,
            tm.width_px,
            tm.height_px,
            dc.detected_type,
            dc.confidence AS document_type_confidence,
            dm.drawing_number,
            dm.part_number,
            dm.revision,
            dm.sheet_number,
            dm.sheet_count,
            dm.classification,
            dm.metadata_confidence AS drawing_metadata_confidence,
            mm.manufacturer,
            mm.manual_title,
            mm.document_code,
            mm.publication_number,
            mm.component_title,
            mm.section_title,
            mm.figure_title,
            mm.figure_number,
            mm.effectivity,
            mm.ata_code,
            mm.page_number,
            mm.page_label,
            mm.issue_date,
            mm.revision_date,
            mm.revision_label,
            mm.part_numbers_json,
            mm.metadata_confidence AS manual_metadata_confidence
        FROM tiff_files f
        LEFT JOIN tiff_technical_metadata tm ON tm.file_id = f.id
        LEFT JOIN tiff_document_classification dc ON dc.file_id = f.id
        LEFT JOIN tiff_drawing_metadata dm ON dm.file_id = f.id
        LEFT JOIN tiff_manual_metadata mm ON mm.file_id = f.id
        ORDER BY f.updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
