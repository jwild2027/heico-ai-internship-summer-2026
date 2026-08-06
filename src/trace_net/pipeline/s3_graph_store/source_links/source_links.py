"""Source-link and ResCarta mapping helpers for local TIFF/RAG results.

The current TIFF/RAG backend stores accurate TIFF and OCR file paths. This
module adds a small mapping table that gives each page a stable source-link
record. The mapping works before native ResCarta import is finished: it stores
ResCarta object/page identifiers when available, optional ResCarta URL templates,
and file URI fallbacks for local TIFF/OCR review.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import csv
import html
import json
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_OUTPUT_DIR = "local_data/source_links"
DEFAULT_REPORT_BASENAME = "rescarta_mapping_report"


@dataclass(frozen=True)
class SourceLinkBuildSummary:
    db_path: Path
    pages_seen: int = 0
    links_written: int = 0
    missing_tiff_path: int = 0
    missing_ocr_path: int = 0
    rescarta_urls_written: int = 0
    source_urls_written: int = 0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceLinkReportSummary:
    db_path: Path
    total_links: int = 0
    missing_tiff_path: int = 0
    missing_ocr_path: int = 0
    missing_rescarta_url: int = 0
    distinct_manuals: int = 0
    output_csv: Path | None = None
    output_json: Path | None = None
    output_html: Path | None = None


class SafeFormatDict(dict):
    """Format-map helper that leaves unknown placeholders blank."""

    def __missing__(self, key: str) -> str:
        return ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _maybe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _path_to_file_uri(value: str | None) -> str:
    if not value:
        return ""
    try:
        return Path(value).resolve().as_uri()
    except Exception:
        return ""


def _page_fallback_id(row: Mapping[str, Any]) -> str:
    manual_id = _clean_text(row.get("manual_id")) or "manual"
    seq = _maybe_int(row.get("page_sequence"))
    if seq is not None:
        return f"{manual_id}_p{seq:06d}"
    label = _clean_text(row.get("page_label")) or _clean_text(row.get("tiff_path")) or "page"
    safe = "".join(ch if ch.isalnum() else "_" for ch in label).strip("_") or "page"
    return f"{manual_id}_{safe}"


def _rescarta_page_fallback(row: Mapping[str, Any]) -> str:
    existing = _clean_text(row.get("rescarta_page_id"))
    if existing:
        return existing
    seq = _maybe_int(row.get("page_sequence"))
    if seq is not None:
        return f"{seq:06d}"
    label = _clean_text(row.get("page_label"))
    return label


def _build_url_from_template(url_template: str | None, row: Mapping[str, Any]) -> str:
    template = _clean_text(url_template)
    if not template:
        return ""
    values = SafeFormatDict({k: "" if v is None else str(v) for k, v in row.items()})
    # User-friendly aliases.
    values.setdefault("object_id", values.get("rescarta_object_id", ""))
    values.setdefault("page_id", values.get("rescarta_page_id", ""))
    values.setdefault("manual", values.get("manual_id", ""))
    values.setdefault("page", values.get("page_sequence", ""))
    values.setdefault("label", values.get("page_label", ""))
    try:
        return template.format_map(values)
    except Exception:
        return ""


def create_source_link_schema(conn: sqlite3.Connection, *, reset: bool = False) -> None:
    if reset:
        conn.execute("DROP TABLE IF EXISTS source_links")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_links (
            source_link_id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL,
            manual_id TEXT NOT NULL,
            publication_number TEXT,
            ata_code TEXT,
            page_sequence INTEGER,
            page_label TEXT,
            page_type TEXT,
            title TEXT,
            tiff_path TEXT,
            ocr_text_path TEXT,
            thumbnail_path TEXT,
            tiff_uri TEXT,
            ocr_uri TEXT,
            rescarta_object_id TEXT,
            rescarta_page_id TEXT,
            rescarta_url TEXT,
            source_url TEXT,
            source_kind TEXT DEFAULT 'rescarta_staging',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_source_links_page_id ON source_links(page_id);
        CREATE INDEX IF NOT EXISTS idx_source_links_manual_id ON source_links(manual_id);
        CREATE INDEX IF NOT EXISTS idx_source_links_rescarta ON source_links(rescarta_object_id, rescarta_page_id);
        CREATE INDEX IF NOT EXISTS idx_source_links_part_lookup ON source_links(manual_id, page_label);
        """
    )
    conn.commit()


def _page_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not table_exists(conn, "pages"):
        return []
    cols = table_columns(conn, "pages")
    wanted = [
        "page_id",
        "manual_id",
        "publication_number",
        "ata_code",
        "page_sequence",
        "page_label",
        "page_type",
        "title",
        "tiff_path",
        "ocr_text_path",
        "thumbnail_path",
        "rescarta_object_id",
        "rescarta_page_id",
    ]
    select_parts = [col if col in cols else f"NULL AS {col}" for col in wanted]
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT " + ", ".join(select_parts) + " FROM pages ORDER BY manual_id, page_sequence, page_label, page_id"
    ).fetchall()
    return [dict(row) for row in rows]


def build_source_links(
    db_path: str | Path,
    *,
    rescarta_url_template: str | None = None,
    reset: bool = True,
    source_kind: str = "rescarta_staging",
) -> SourceLinkBuildSummary:
    """Build or rebuild the source_links table from the existing pages table."""

    path = Path(db_path)
    warnings: list[str] = []
    if not path.exists():
        raise FileNotFoundError(f"Search database does not exist: {path}")

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        if not table_exists(conn, "pages"):
            raise RuntimeError("The database does not contain a pages table. Build the search index first.")
        create_source_link_schema(conn, reset=reset)
        rows = _page_rows(conn)
        written = 0
        missing_tiff = 0
        missing_ocr = 0
        rescarta_urls = 0
        source_urls = 0
        now = utc_now()
        for raw in rows:
            row = dict(raw)
            page_id = _clean_text(row.get("page_id")) or _page_fallback_id(row)
            manual_id = _clean_text(row.get("manual_id")) or "unknown_manual"
            row["page_id"] = page_id
            row["manual_id"] = manual_id
            row["rescarta_object_id"] = _clean_text(row.get("rescarta_object_id")) or manual_id
            row["rescarta_page_id"] = _rescarta_page_fallback(row)
            row["object_id"] = row["rescarta_object_id"]
            row["page_id_for_url"] = row["rescarta_page_id"]
            row["page"] = row.get("page_sequence") or ""
            row["label"] = row.get("page_label") or ""

            tiff_path = _clean_text(row.get("tiff_path"))
            ocr_path = _clean_text(row.get("ocr_text_path"))
            tiff_uri = _path_to_file_uri(tiff_path)
            ocr_uri = _path_to_file_uri(ocr_path)
            if not tiff_path:
                missing_tiff += 1
            if not ocr_path:
                missing_ocr += 1

            url_values = dict(row)
            url_values["page_id"] = row["rescarta_page_id"]
            url_values["page_record_id"] = page_id
            rescarta_url = _build_url_from_template(rescarta_url_template, url_values)
            source_url = rescarta_url or tiff_uri or tiff_path
            if rescarta_url:
                rescarta_urls += 1
            if source_url:
                source_urls += 1

            source_link_id = f"{manual_id}:{page_id}"
            conn.execute(
                """
                INSERT OR REPLACE INTO source_links (
                    source_link_id, page_id, manual_id, publication_number, ata_code,
                    page_sequence, page_label, page_type, title, tiff_path,
                    ocr_text_path, thumbnail_path, tiff_uri, ocr_uri,
                    rescarta_object_id, rescarta_page_id, rescarta_url, source_url,
                    source_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_link_id,
                    page_id,
                    manual_id,
                    _clean_text(row.get("publication_number")),
                    _clean_text(row.get("ata_code")),
                    _maybe_int(row.get("page_sequence")),
                    _clean_text(row.get("page_label")),
                    _clean_text(row.get("page_type")),
                    _clean_text(row.get("title")),
                    tiff_path,
                    ocr_path,
                    _clean_text(row.get("thumbnail_path")),
                    tiff_uri,
                    ocr_uri,
                    _clean_text(row.get("rescarta_object_id")),
                    _clean_text(row.get("rescarta_page_id")),
                    rescarta_url,
                    source_url,
                    source_kind,
                    now,
                ),
            )
            written += 1
        conn.commit()

    return SourceLinkBuildSummary(
        db_path=path,
        pages_seen=len(rows),
        links_written=written,
        missing_tiff_path=missing_tiff,
        missing_ocr_path=missing_ocr,
        rescarta_urls_written=rescarta_urls,
        source_urls_written=source_urls,
        warnings=tuple(warnings),
    )


def source_link_for_page(conn: sqlite3.Connection, page_id: str) -> dict[str, Any] | None:
    if not table_exists(conn, "source_links"):
        return None
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM source_links WHERE page_id=?", (page_id,)).fetchone()
    return dict(row) if row else None


def enrich_sources_with_source_links(db_path: str | Path, sources: Sequence[Any]) -> tuple[Any, ...]:
    """Attach source-link metadata to RagSource-like dataclass objects.

    This function is deliberately duck-typed so source_links.py does not depend
    on rag_retriever.py. If the source_links table does not exist, the input is
    returned unchanged.
    """

    if not sources:
        return tuple(sources)
    path = Path(db_path)
    if not path.exists():
        return tuple(sources)
    try:
        with sqlite3.connect(path) as conn:
            if not table_exists(conn, "source_links"):
                return tuple(sources)
            conn.row_factory = sqlite3.Row
            page_ids = sorted({str(getattr(src, "page_id", "") or "") for src in sources if getattr(src, "page_id", None)})
            if not page_ids:
                return tuple(sources)
            placeholders = ",".join("?" for _ in page_ids)
            rows = conn.execute(f"SELECT * FROM source_links WHERE page_id IN ({placeholders})", page_ids).fetchall()
            by_page = {row["page_id"]: dict(row) for row in rows}
    except Exception:
        return tuple(sources)

    enriched: list[Any] = []
    for src in sources:
        page_id = str(getattr(src, "page_id", "") or "")
        link = by_page.get(page_id)
        if not link:
            enriched.append(src)
            continue
        extra = dict(getattr(src, "extra", {}) or {})
        for key in (
            "source_link_id",
            "source_url",
            "rescarta_url",
            "tiff_uri",
            "ocr_uri",
            "source_kind",
        ):
            if link.get(key):
                extra.setdefault(key, link.get(key))
        updates: dict[str, Any] = {"extra": extra}
        if getattr(src, "rescarta_object_id", None) in (None, "") and link.get("rescarta_object_id"):
            updates["rescarta_object_id"] = link.get("rescarta_object_id")
        if getattr(src, "rescarta_page_id", None) in (None, "") and link.get("rescarta_page_id"):
            updates["rescarta_page_id"] = link.get("rescarta_page_id")
        try:
            enriched.append(replace(src, **updates))
        except Exception:
            enriched.append(src)
    return tuple(enriched)


def _report_rows(conn: sqlite3.Connection, limit: int | None = None) -> list[dict[str, Any]]:
    if not table_exists(conn, "source_links"):
        return []
    sql = "SELECT * FROM source_links ORDER BY manual_id, page_sequence, page_label, page_id"
    params: tuple[Any, ...] = ()
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params = (int(limit),)
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def summarize_source_links(db_path: str | Path) -> SourceLinkReportSummary:
    path = Path(db_path)
    if not path.exists():
        return SourceLinkReportSummary(db_path=path)
    with sqlite3.connect(path) as conn:
        if not table_exists(conn, "source_links"):
            return SourceLinkReportSummary(db_path=path)
        total = conn.execute("SELECT COUNT(*) FROM source_links").fetchone()[0]
        missing_tiff = conn.execute("SELECT COUNT(*) FROM source_links WHERE COALESCE(tiff_path, '') = ''").fetchone()[0]
        missing_ocr = conn.execute("SELECT COUNT(*) FROM source_links WHERE COALESCE(ocr_text_path, '') = ''").fetchone()[0]
        missing_rescarta = conn.execute("SELECT COUNT(*) FROM source_links WHERE COALESCE(rescarta_url, '') = ''").fetchone()[0]
        manuals = conn.execute("SELECT COUNT(DISTINCT manual_id) FROM source_links").fetchone()[0]
    return SourceLinkReportSummary(
        db_path=path,
        total_links=int(total),
        missing_tiff_path=int(missing_tiff),
        missing_ocr_path=int(missing_ocr),
        missing_rescarta_url=int(missing_rescarta),
        distinct_manuals=int(manuals),
    )


def write_source_link_report(
    db_path: str | Path,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    basename: str = DEFAULT_REPORT_BASENAME,
    limit: int | None = None,
) -> SourceLinkReportSummary:
    """Write CSV/JSON/HTML source-link mapping reports."""

    path = Path(db_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{basename}.csv"
    json_path = out_dir / f"{basename}.json"
    html_path = out_dir / f"{basename}.html"

    with sqlite3.connect(path) as conn:
        rows = _report_rows(conn, limit=limit)

    fields = [
        "source_link_id",
        "manual_id",
        "publication_number",
        "ata_code",
        "page_sequence",
        "page_label",
        "page_type",
        "title",
        "rescarta_object_id",
        "rescarta_page_id",
        "rescarta_url",
        "source_url",
        "tiff_path",
        "ocr_text_path",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    payload = {
        "summary": summarize_source_links(path).__dict__ | {"db_path": str(path)},
        "rows": rows,
    }
    # Convert Path objects if any.
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    html_rows = []
    for row in rows:
        html_rows.append(
            "<tr>"
            + "".join(f"<td>{html.escape(str(row.get(field, '') or ''))}</td>" for field in fields)
            + "</tr>"
        )
    html_text = """<!doctype html>
<html><head><meta charset=\"utf-8\"><title>ResCarta / Source Link Mapping</title>
<style>body{font-family:Arial,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px;vertical-align:top}th{background:#f5f5f5}code{white-space:pre-wrap}</style>
</head><body>
<h1>ResCarta / Source Link Mapping</h1>
<table><thead><tr>__HEADERS__</tr></thead><tbody>__ROWS__</tbody></table>
</body></html>
""".replace("__HEADERS__", "".join(f"<th>{html.escape(field)}</th>" for field in fields)).replace("__ROWS__", "\n".join(html_rows))
    html_path.write_text(html_text, encoding="utf-8")

    summary = summarize_source_links(path)
    return SourceLinkReportSummary(
        db_path=summary.db_path,
        total_links=summary.total_links,
        missing_tiff_path=summary.missing_tiff_path,
        missing_ocr_path=summary.missing_ocr_path,
        missing_rescarta_url=summary.missing_rescarta_url,
        distinct_manuals=summary.distinct_manuals,
        output_csv=csv_path,
        output_json=json_path,
        output_html=html_path,
    )


def format_build_summary(summary: SourceLinkBuildSummary) -> str:
    lines = [
        "ResCarta/source-link mapping build complete",
        f"  DB: {summary.db_path}",
        f"  Pages seen: {summary.pages_seen}",
        f"  Source links written: {summary.links_written}",
        f"  Missing TIFF paths: {summary.missing_tiff_path}",
        f"  Missing OCR paths: {summary.missing_ocr_path}",
        f"  ResCarta URLs written: {summary.rescarta_urls_written}",
        f"  Source URLs written: {summary.source_urls_written}",
    ]
    for warning in summary.warnings:
        lines.append(f"  Warning: {warning}")
    return "\n".join(lines)


def format_report_summary(summary: SourceLinkReportSummary) -> str:
    lines = [
        "ResCarta/source-link mapping report",
        f"  DB: {summary.db_path}",
        f"  Total links: {summary.total_links}",
        f"  Distinct manuals: {summary.distinct_manuals}",
        f"  Missing TIFF paths: {summary.missing_tiff_path}",
        f"  Missing OCR paths: {summary.missing_ocr_path}",
        f"  Missing ResCarta URLs: {summary.missing_rescarta_url}",
    ]
    if summary.output_csv:
        lines.append(f"  CSV: {summary.output_csv}")
    if summary.output_json:
        lines.append(f"  JSON: {summary.output_json}")
    if summary.output_html:
        lines.append(f"  HTML: {summary.output_html}")
    return "\n".join(lines)
