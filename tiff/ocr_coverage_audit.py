"""OCR coverage audit helpers for TIFF/ResCarta source links.

This module is intentionally read-only. It checks whether source-linked pages
have OCR text paths, whether those files exist, and whether any OCR files are
empty or suspiciously short. Empty OCR files are not automatically treated as a
fatal error because some scanned pages are blank separators/covers, but they
should be visible before scaling to larger batches.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import sqlite3
from typing import Any, Sequence

DEFAULT_DB_PATH = "local_data/db/tiff_search.db"
DEFAULT_MIN_CHARS = 20


@dataclass(frozen=True)
class OcrCoverageSampleRow:
    page_id: str = ""
    manual_id: str = ""
    publication_number: str = ""
    ata_code: str = ""
    page_label: str = ""
    page_sequence: int | None = None
    ocr_text_path: str = ""
    tiff_path: str = ""
    rescarta_url: str = ""
    size_bytes: int | None = None
    char_count: int | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OcrCoverageAuditSummary:
    db_path: str
    source_links_table_exists: bool = False
    total_source_links: int = 0
    distinct_manuals: int = 0
    pages_total: int = 0
    missing_ocr_paths: int = 0
    missing_ocr_files: int = 0
    empty_ocr_files: int = 0
    short_ocr_files: int = 0
    nonempty_ocr_files: int = 0
    readable_ocr_files: int = 0
    unreadable_ocr_files: int = 0
    total_ocr_chars: int = 0
    min_chars: int = DEFAULT_MIN_CHARS
    sample_rows: tuple[OcrCoverageSampleRow, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def local_ocr_paths_ready(self) -> bool:
        return (
            self.source_links_table_exists
            and self.total_source_links > 0
            and self.missing_ocr_paths == 0
            and self.missing_ocr_files == 0
            and self.unreadable_ocr_files == 0
        )

    @property
    def has_empty_or_short_ocr(self) -> bool:
        return self.empty_ocr_files > 0 or self.short_ocr_files > 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["local_ocr_paths_ready"] = self.local_ocr_paths_ready
        data["has_empty_or_short_ocr"] = self.has_empty_or_short_ocr
        data["sample_rows"] = [row.to_dict() for row in self.sample_rows]
        return data


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> int:
    return int(conn.execute(sql, tuple(params)).fetchone()[0])


def _row_value(row: sqlite3.Row, key: str, default: Any = "") -> Any:
    try:
        return row[key]
    except Exception:
        return default


def _read_text_count(path: Path) -> tuple[int | None, str | None]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, str(exc)
    return len(text.strip()), None


def _sample_from_row(row: sqlite3.Row, *, reason: str, size_bytes: int | None = None, char_count: int | None = None) -> OcrCoverageSampleRow:
    return OcrCoverageSampleRow(
        page_id=_clean(_row_value(row, "page_id")),
        manual_id=_clean(_row_value(row, "manual_id")),
        publication_number=_clean(_row_value(row, "publication_number")),
        ata_code=_clean(_row_value(row, "ata_code")),
        page_label=_clean(_row_value(row, "page_label")),
        page_sequence=_row_value(row, "page_sequence", None),
        ocr_text_path=_clean(_row_value(row, "ocr_text_path")),
        tiff_path=_clean(_row_value(row, "tiff_path")),
        rescarta_url=_clean(_row_value(row, "rescarta_url")),
        size_bytes=size_bytes,
        char_count=char_count,
        reason=reason,
    )


def audit_ocr_coverage(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    min_chars: int = DEFAULT_MIN_CHARS,
    sample_limit: int = 20,
) -> OcrCoverageAuditSummary:
    """Audit OCR path/file coverage for rows in source_links."""

    path = Path(db_path)
    warnings: list[str] = []
    samples: list[OcrCoverageSampleRow] = []
    min_chars = max(1, int(min_chars))

    if not path.exists():
        return OcrCoverageAuditSummary(
            db_path=str(path),
            min_chars=min_chars,
            warnings=(f"database does not exist: {path}",),
        )

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "source_links"):
            return OcrCoverageAuditSummary(
                db_path=str(path),
                min_chars=min_chars,
                warnings=("source_links table does not exist; run the backend pipeline/source-link build first",),
            )

        total_links = _count(conn, "SELECT COUNT(*) FROM source_links")
        distinct_manuals = _count(conn, "SELECT COUNT(DISTINCT manual_id) FROM source_links")
        pages_total = _count(conn, "SELECT COUNT(*) FROM pages") if _table_exists(conn, "pages") else 0
        rows = conn.execute(
            """
            SELECT *
            FROM source_links
            ORDER BY manual_id, page_sequence, page_label, page_id
            """
        ).fetchall()

    missing_paths = 0
    missing_files = 0
    empty_files = 0
    short_files = 0
    nonempty_files = 0
    readable_files = 0
    unreadable_files = 0
    total_chars = 0

    for row in rows:
        ocr_path_text = _clean(_row_value(row, "ocr_text_path"))
        if not ocr_path_text:
            missing_paths += 1
            if len(samples) < sample_limit:
                samples.append(_sample_from_row(row, reason="missing_ocr_path"))
            continue

        ocr_path = Path(ocr_path_text)
        try:
            exists = ocr_path.exists()
        except OSError:
            exists = False
        if not exists:
            missing_files += 1
            if len(samples) < sample_limit:
                samples.append(_sample_from_row(row, reason="missing_ocr_file"))
            continue

        try:
            size_bytes = int(ocr_path.stat().st_size)
        except OSError:
            size_bytes = None

        char_count, read_error = _read_text_count(ocr_path)
        if read_error is not None or char_count is None:
            unreadable_files += 1
            if len(samples) < sample_limit:
                samples.append(_sample_from_row(row, reason="unreadable_ocr_file", size_bytes=size_bytes))
            continue

        readable_files += 1
        total_chars += char_count
        if char_count == 0:
            empty_files += 1
            if len(samples) < sample_limit:
                samples.append(_sample_from_row(row, reason="empty_ocr_file", size_bytes=size_bytes, char_count=char_count))
        else:
            nonempty_files += 1
            if char_count < min_chars:
                short_files += 1
                if len(samples) < sample_limit:
                    samples.append(_sample_from_row(row, reason="short_ocr_file", size_bytes=size_bytes, char_count=char_count))

    if empty_files:
        warnings.append(
            "Some OCR text files are empty. They may be blank/separator pages, but inspect samples before scaling or relying on OCR coverage."
        )
    if short_files:
        warnings.append(f"Some non-empty OCR text files have fewer than {min_chars} visible characters.")
    if missing_paths or missing_files:
        warnings.append("Some source-linked pages are missing OCR paths or OCR files.")
    if unreadable_files:
        warnings.append("Some OCR text files could not be read from disk.")

    return OcrCoverageAuditSummary(
        db_path=str(path),
        source_links_table_exists=True,
        total_source_links=total_links,
        distinct_manuals=distinct_manuals,
        pages_total=pages_total,
        missing_ocr_paths=missing_paths,
        missing_ocr_files=missing_files,
        empty_ocr_files=empty_files,
        short_ocr_files=short_files,
        nonempty_ocr_files=nonempty_files,
        readable_ocr_files=readable_files,
        unreadable_ocr_files=unreadable_files,
        total_ocr_chars=total_chars,
        min_chars=min_chars,
        sample_rows=tuple(samples),
        warnings=tuple(warnings),
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_ocr_coverage_audit(summary: OcrCoverageAuditSummary, *, sample_limit: int = 20) -> str:
    lines: list[str] = []
    status_ok = summary.local_ocr_paths_ready
    lines.append("OCR coverage audit")
    lines.append(f"  Status: {'OK' if status_ok else 'NEEDS ATTENTION'}")
    lines.append(f"  DB: {summary.db_path}")
    lines.append(f"  source_links table exists: {_yes_no(summary.source_links_table_exists)}")
    lines.append(f"  Total source-linked pages: {summary.total_source_links}")
    lines.append(f"  Distinct manuals: {summary.distinct_manuals}")
    lines.append(f"  Indexed pages: {summary.pages_total}")
    lines.append("")
    lines.append("OCR path/file coverage:")
    lines.append(f"  Missing OCR paths: {summary.missing_ocr_paths}")
    lines.append(f"  Missing OCR files: {summary.missing_ocr_files}")
    lines.append(f"  Unreadable OCR files: {summary.unreadable_ocr_files}")
    lines.append(f"  Readable OCR files: {summary.readable_ocr_files}")
    lines.append(f"  Non-empty OCR files: {summary.nonempty_ocr_files}")
    lines.append(f"  Empty OCR files: {summary.empty_ocr_files}")
    lines.append(f"  Short OCR files (<{summary.min_chars} chars, non-empty): {summary.short_ocr_files}")
    lines.append(f"  Total visible OCR chars: {summary.total_ocr_chars}")
    lines.append("")
    lines.append("Readiness:")
    lines.append(f"  Local OCR paths ready: {_yes_no(summary.local_ocr_paths_ready)}")
    lines.append(f"  Empty/short OCR review needed: {_yes_no(summary.has_empty_or_short_ocr)}")

    if summary.sample_rows:
        lines.append("")
        lines.append("Sample OCR coverage rows:")
        for idx, row in enumerate(summary.sample_rows[: max(0, sample_limit)], start=1):
            label = row.publication_number or row.manual_id or "unknown manual"
            page = row.page_label or row.page_id or "unknown page"
            parts = [label]
            if row.ata_code:
                parts.append(f"ATA {row.ata_code}")
            parts.append(f"Page {page}")
            size = "" if row.size_bytes is None else f" size={row.size_bytes}"
            chars = "" if row.char_count is None else f" chars={row.char_count}"
            lines.append(f"  {idx}. {row.reason} | " + " - ".join(parts) + size + chars)
            if row.ocr_text_path:
                lines.append(f"     OCR: {row.ocr_text_path}")
            if row.tiff_path:
                lines.append(f"     TIFF: {row.tiff_path}")
            if row.rescarta_url:
                lines.append(f"     ResCarta: {row.rescarta_url}")
        if len(summary.sample_rows) > sample_limit:
            lines.append(f"  ... {len(summary.sample_rows) - sample_limit} more sample rows not shown")

    if summary.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in summary.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


def write_ocr_coverage_json(summary: OcrCoverageAuditSummary, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
