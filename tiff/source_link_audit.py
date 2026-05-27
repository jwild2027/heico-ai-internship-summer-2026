"""Command-line source-link audit helpers for the local TIFF/RAG backend.

The source_links table is the bridge between search/RAG answers and the
underlying TIFF/OCR/ResCarta source page. This module verifies that bridge
without generating HTML reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

DEFAULT_DB_PATH = "local_data/db/tiff_search.db"
DEFAULT_PLACEHOLDER_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "example.com")
DEFAULT_SAMPLE_PARTS = ("120-37313-001", "AM03078-22")


@dataclass(frozen=True)
class SourceLinkSampleRow:
    """A small source-link row shown in the CLI audit output."""

    query: str
    manual_id: str = ""
    publication_number: str = ""
    ata_code: str = ""
    page_label: str = ""
    page_sequence: int | None = None
    rescarta_object_id: str = ""
    rescarta_page_id: str = ""
    rescarta_url: str = ""
    source_url: str = ""
    tiff_path: str = ""
    ocr_text_path: str = ""


@dataclass(frozen=True)
class SourceLinkAuditSummary:
    """Summary of source-link health for a search/RAG database."""

    db_path: str
    source_links_table_exists: bool = False
    total_links: int = 0
    distinct_manuals: int = 0
    pages_total: int = 0
    pages_without_source_links: int = 0
    missing_tiff_path: int = 0
    missing_ocr_path: int = 0
    missing_rescarta_url: int = 0
    missing_source_url: int = 0
    local_or_placeholder_rescarta_urls: int = 0
    rescarta_urls_with_template_braces: int = 0
    source_url_file_fallbacks: int = 0
    missing_tiff_files: int = 0
    missing_ocr_files: int = 0
    sample_queries_checked: int = 0
    sample_queries_without_results: int = 0
    sample_rows: tuple[SourceLinkSampleRow, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ready_for_local_source_review(self) -> bool:
        """True when every indexed page has a source row and local paths exist."""
        return (
            self.source_links_table_exists
            and self.total_links > 0
            and self.pages_without_source_links == 0
            and self.missing_tiff_path == 0
            and self.missing_ocr_path == 0
            and self.missing_source_url == 0
            and self.missing_tiff_files == 0
            and self.missing_ocr_files == 0
        )

    @property
    def ready_for_real_rescarta_deeplinks(self) -> bool:
        """True when ResCarta URLs look non-local and complete."""
        return (
            self.ready_for_local_source_review
            and self.missing_rescarta_url == 0
            and self.local_or_placeholder_rescarta_urls == 0
            and self.rescarta_urls_with_template_braces == 0
        )


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _norm_part(value: str) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> int:
    return int(conn.execute(sql, tuple(params)).fetchone()[0])


def _looks_local_or_placeholder_url(url: str, placeholder_hosts: Iterable[str]) -> bool:
    text = _clean(url)
    if not text:
        return False
    if "{" in text or "}" in text:
        return True
    try:
        host = (urlparse(text).hostname or "").lower()
    except Exception:
        return False
    placeholders = {str(hostname).lower() for hostname in placeholder_hosts}
    return host in placeholders


def _path_missing(path_text: str) -> bool:
    text = _clean(path_text)
    if not text:
        return False
    try:
        return not Path(text).exists()
    except OSError:
        return True


def _sample_rows_for_query(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int,
) -> list[SourceLinkSampleRow]:
    q = _clean(query)
    qnorm = _norm_part(q)
    if not q:
        return []

    conn.row_factory = sqlite3.Row
    rows: list[sqlite3.Row] = []

    # Direct page/source lookup first.
    rows.extend(
        conn.execute(
            """
            SELECT sl.*
            FROM source_links sl
            WHERE sl.page_id=? OR sl.page_label=? OR sl.rescarta_page_id=?
            ORDER BY sl.manual_id, sl.page_sequence, sl.page_label
            LIMIT ?
            """,
            (q, q, q, limit),
        ).fetchall()
    )

    if not rows and qnorm and _table_exists(conn, "part_mentions"):
        rows.extend(
            conn.execute(
                """
                SELECT DISTINCT sl.*
                FROM source_links sl
                JOIN part_mentions pm ON pm.page_id = sl.page_id
                WHERE pm.part_number_normalized=? OR UPPER(pm.part_number_display)=UPPER(?)
                ORDER BY sl.manual_id, sl.page_sequence, sl.page_label
                LIMIT ?
                """,
                (qnorm, q, limit),
            ).fetchall()
        )

    if not rows and qnorm and _table_exists(conn, "part_catalog_clean"):
        rows.extend(
            conn.execute(
                """
                SELECT DISTINCT sl.*
                FROM source_links sl
                JOIN part_catalog_clean pc ON pc.page_id = sl.page_id
                WHERE pc.part_number_normalized=? OR UPPER(pc.part_number_display)=UPPER(?)
                ORDER BY sl.manual_id, sl.page_sequence, sl.page_label
                LIMIT ?
                """,
                (qnorm, q, limit),
            ).fetchall()
        )

    sample_rows: list[SourceLinkSampleRow] = []
    for row in rows[:limit]:
        sample_rows.append(
            SourceLinkSampleRow(
                query=q,
                manual_id=_clean(row["manual_id"]),
                publication_number=_clean(row["publication_number"]),
                ata_code=_clean(row["ata_code"]),
                page_label=_clean(row["page_label"]),
                page_sequence=row["page_sequence"] if row["page_sequence"] is not None else None,
                rescarta_object_id=_clean(row["rescarta_object_id"]),
                rescarta_page_id=_clean(row["rescarta_page_id"]),
                rescarta_url=_clean(row["rescarta_url"]),
                source_url=_clean(row["source_url"]),
                tiff_path=_clean(row["tiff_path"]),
                ocr_text_path=_clean(row["ocr_text_path"]),
            )
        )
    return sample_rows


def audit_source_links(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    sample_queries: Sequence[str] = DEFAULT_SAMPLE_PARTS,
    sample_limit: int = 5,
    check_files: bool = True,
    placeholder_hosts: Sequence[str] = DEFAULT_PLACEHOLDER_HOSTS,
) -> SourceLinkAuditSummary:
    """Audit source-link coverage and sample source resolution."""
    path = Path(db_path)
    warnings: list[str] = []
    if not path.exists():
        return SourceLinkAuditSummary(
            db_path=str(path),
            warnings=(f"database does not exist: {path}",),
        )

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "source_links"):
            return SourceLinkAuditSummary(
                db_path=str(path),
                warnings=("source_links table does not exist; run scripts/build_rescarta_mapping.py first",),
            )

        total_links = _count(conn, "SELECT COUNT(*) FROM source_links")
        distinct_manuals = _count(conn, "SELECT COUNT(DISTINCT manual_id) FROM source_links")
        pages_total = _count(conn, "SELECT COUNT(*) FROM pages") if _table_exists(conn, "pages") else 0
        pages_without_source_links = 0
        if _table_exists(conn, "pages"):
            pages_without_source_links = _count(
                conn,
                """
                SELECT COUNT(*)
                FROM pages p
                LEFT JOIN source_links sl ON sl.page_id = p.page_id
                WHERE sl.page_id IS NULL
                """,
            )

        missing_tiff_path = _count(conn, "SELECT COUNT(*) FROM source_links WHERE COALESCE(tiff_path, '') = ''")
        missing_ocr_path = _count(conn, "SELECT COUNT(*) FROM source_links WHERE COALESCE(ocr_text_path, '') = ''")
        missing_rescarta_url = _count(conn, "SELECT COUNT(*) FROM source_links WHERE COALESCE(rescarta_url, '') = ''")
        missing_source_url = _count(conn, "SELECT COUNT(*) FROM source_links WHERE COALESCE(source_url, '') = ''")
        source_url_file_fallbacks = _count(conn, "SELECT COUNT(*) FROM source_links WHERE source_url LIKE 'file:%'")
        urls_with_braces = _count(
            conn,
            "SELECT COUNT(*) FROM source_links WHERE rescarta_url LIKE '%{%' OR rescarta_url LIKE '%}%'",
        )

        local_urls = 0
        missing_tiff_files = 0
        missing_ocr_files = 0
        rows = conn.execute("SELECT rescarta_url, tiff_path, ocr_text_path FROM source_links").fetchall()
        for row in rows:
            if _looks_local_or_placeholder_url(_clean(row["rescarta_url"]), placeholder_hosts):
                local_urls += 1
            if check_files:
                if _path_missing(_clean(row["tiff_path"])):
                    missing_tiff_files += 1
                if _path_missing(_clean(row["ocr_text_path"])):
                    missing_ocr_files += 1

        samples: list[SourceLinkSampleRow] = []
        sample_queries_without_results = 0
        checked_queries = [_clean(query) for query in sample_queries if _clean(query)]
        for query in checked_queries:
            query_rows = _sample_rows_for_query(conn, query, limit=max(1, sample_limit))
            if not query_rows:
                sample_queries_without_results += 1
            samples.extend(query_rows)

    if local_urls:
        warnings.append(
            "ResCarta URLs use local/placeholder hosts; replace the URL template once the real ResCarta deep-link format is known."
        )
    if source_url_file_fallbacks:
        warnings.append("Some source_url values fall back to file:// links instead of ResCarta URLs.")

    return SourceLinkAuditSummary(
        db_path=str(path),
        source_links_table_exists=True,
        total_links=total_links,
        distinct_manuals=distinct_manuals,
        pages_total=pages_total,
        pages_without_source_links=pages_without_source_links,
        missing_tiff_path=missing_tiff_path,
        missing_ocr_path=missing_ocr_path,
        missing_rescarta_url=missing_rescarta_url,
        missing_source_url=missing_source_url,
        local_or_placeholder_rescarta_urls=local_urls,
        rescarta_urls_with_template_braces=urls_with_braces,
        source_url_file_fallbacks=source_url_file_fallbacks,
        missing_tiff_files=missing_tiff_files,
        missing_ocr_files=missing_ocr_files,
        sample_queries_checked=len(checked_queries),
        sample_queries_without_results=sample_queries_without_results,
        sample_rows=tuple(samples),
        warnings=tuple(warnings),
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_source_link_audit(summary: SourceLinkAuditSummary, *, sample_limit: int = 10) -> str:
    """Format an audit summary for terminal output."""
    lines = [
        "Source-link audit",
        f"  DB: {summary.db_path}",
        f"  source_links table exists: {_yes_no(summary.source_links_table_exists)}",
        f"  Total links: {summary.total_links}",
        f"  Distinct manuals: {summary.distinct_manuals}",
        f"  Indexed pages: {summary.pages_total}",
        f"  Pages without source links: {summary.pages_without_source_links}",
        "",
        "Path/link coverage:",
        f"  Missing TIFF paths: {summary.missing_tiff_path}",
        f"  Missing OCR paths: {summary.missing_ocr_path}",
        f"  Missing source URLs: {summary.missing_source_url}",
        f"  Missing ResCarta URLs: {summary.missing_rescarta_url}",
        f"  Local/placeholder ResCarta URLs: {summary.local_or_placeholder_rescarta_urls}",
        f"  ResCarta URLs with template braces: {summary.rescarta_urls_with_template_braces}",
        f"  source_url file:// fallbacks: {summary.source_url_file_fallbacks}",
        "",
        "File existence:",
        f"  Missing TIFF files on disk: {summary.missing_tiff_files}",
        f"  Missing OCR files on disk: {summary.missing_ocr_files}",
        "",
        "Readiness:",
        f"  Local source review ready: {_yes_no(summary.ready_for_local_source_review)}",
        f"  Real ResCarta deep-link ready: {_yes_no(summary.ready_for_real_rescarta_deeplinks)}",
    ]

    if summary.sample_queries_checked:
        lines.extend(
            [
                "",
                "Sample source resolution:",
                f"  Queries checked: {summary.sample_queries_checked}",
                f"  Queries without results: {summary.sample_queries_without_results}",
            ]
        )
        shown = 0
        for row in summary.sample_rows[: max(0, sample_limit)]:
            shown += 1
            label = row.publication_number or row.manual_id or "unknown manual"
            page = row.page_label or row.rescarta_page_id or "unknown page"
            details = [label]
            if row.ata_code:
                details.append(f"ATA {row.ata_code}")
            details.append(f"Page {page}")
            lines.append(f"  {shown}. query={row.query} | " + " - ".join(details))
            if row.rescarta_url:
                lines.append(f"     ResCarta: {row.rescarta_url}")
            if row.source_url and row.source_url != row.rescarta_url:
                lines.append(f"     Source URL: {row.source_url}")
            if row.tiff_path:
                lines.append(f"     TIFF: {row.tiff_path}")
            if row.ocr_text_path:
                lines.append(f"     OCR: {row.ocr_text_path}")
        if len(summary.sample_rows) > shown:
            lines.append(f"  ... {len(summary.sample_rows) - shown} more sample rows not shown")

    if summary.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in summary.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


def source_link_audit_to_dict(summary: SourceLinkAuditSummary) -> dict[str, Any]:
    payload = asdict(summary)
    payload["ready_for_local_source_review"] = summary.ready_for_local_source_review
    payload["ready_for_real_rescarta_deeplinks"] = summary.ready_for_real_rescarta_deeplinks
    return payload


def write_source_link_audit_json(summary: SourceLinkAuditSummary, path: str | Path) -> Path:
    """Write the audit summary to JSON. No HTML report is produced."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(source_link_audit_to_dict(summary), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out
