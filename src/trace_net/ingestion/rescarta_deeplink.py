"""Helpers for building configurable ResCarta deep links.

The local MVP uses placeholder URLs like:
    http://localhost:8080/rescarta/{object_id}/{page_id}

Production ResCarta-Web deployments often use site-specific JSP routes and query
parameters, so this module intentionally does not hard-code one final URL shape.
Instead, it builds URLs from a template and a source_links row.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any, Dict, Iterable, Mapping, Sequence
from urllib.parse import quote, urlparse
import json
import re
import sqlite3


DEFAULT_DB_PATH = Path("local_data/db/tiff_search.db")
DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_TEMPLATE = "{base_url}/jsp/RcWebImageViewer.jsp?doc_id={object_id}/{page_id}"
PLACEHOLDER_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org"}


class ResCartaTemplateError(ValueError):
    """Raised when a URL template cannot be rendered safely."""


@dataclass(frozen=True)
class SourceLinkRow:
    """Normalized source-link row used by the deep-link builder."""

    page_id: str
    manual_id: str = ""
    manual_title: str = ""
    ata_code: str = ""
    page_label: str = ""
    tiff_path: str = ""
    ocr_path: str = ""
    current_rescarta_url: str = ""
    source_url: str = ""

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "SourceLinkRow":
        def pick(*names: str) -> str:
            for name in names:
                value = row.get(name)
                if value is not None and str(value) != "":
                    return str(value)
            return ""

        return cls(
            page_id=pick("page_id", "id"),
            manual_id=pick("manual_id", "object_id", "manual", "document_id"),
            manual_title=pick("manual_title", "title", "publication_title", "publication_number"),
            ata_code=pick("ata_code", "ata"),
            page_label=pick("page_label", "label", "page_number"),
            tiff_path=pick("tiff_path", "tiff_file", "image_path"),
            ocr_path=pick("ocr_path", "ocr_file", "text_path"),
            current_rescarta_url=pick("rescarta_url", "current_rescarta_url"),
            source_url=pick("source_url"),
        )


def normalize_base_url(base_url: str) -> str:
    """Return a clean base URL with no trailing slash."""
    base_url = (base_url or "").strip()
    if not base_url:
        raise ResCartaTemplateError("base_url is required")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ResCartaTemplateError("base_url must start with http:// or https://")
    return base_url.rstrip("/")


def is_placeholder_url(url: str) -> bool:
    """Return True if a URL looks like a local/test placeholder."""
    if not url:
        return True
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in PLACEHOLDER_HOSTS


def _last_url_parts(url: str) -> tuple[str, str]:
    """Extract object/page-ish segments from the current placeholder URL."""
    if not url:
        return "", ""
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    # Placeholder shape is usually /rescarta/{object_id}/{page_id}
    if len(path_parts) >= 2:
        return path_parts[-2], path_parts[-1]
    return "", ""


def _path_stem(path_text: str) -> str:
    if not path_text:
        return ""
    return Path(path_text.replace("\\", "/")).stem


def _first_page_number_from_stem(stem: str) -> str:
    if not stem:
        return ""
    first = stem.split("_", 1)[0]
    return first if first else stem


def _second_page_number_from_stem(stem: str) -> str:
    if not stem:
        return ""
    parts = stem.split("_", 1)
    return parts[1] if len(parts) > 1 else stem


def _safe_slug(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def build_tokens(row: SourceLinkRow | Mapping[str, Any], base_url: str = "") -> Dict[str, str]:
    """Build template tokens from one source_links row.

    Supported tokens intentionally include several aliases because different
    ResCarta installations use different URL parameter names.
    """
    if not isinstance(row, SourceLinkRow):
        row = SourceLinkRow.from_mapping(row)

    placeholder_object, placeholder_page = _last_url_parts(row.current_rescarta_url or row.source_url)
    tiff_stem = _path_stem(row.tiff_path)
    ocr_stem = _path_stem(row.ocr_path)
    page_seq = placeholder_page or _first_page_number_from_stem(tiff_stem) or row.page_id
    page_name = _second_page_number_from_stem(tiff_stem) or page_seq
    object_id = row.manual_id or placeholder_object

    return {
        "base_url": base_url.rstrip("/"),
        "object_id": object_id,
        "manual_id": row.manual_id or object_id,
        "manual_title": row.manual_title,
        "manual_slug": _safe_slug(row.manual_title) or _safe_slug(row.manual_id),
        "page_id": page_seq,
        "page_id_raw": row.page_id,
        "page_name": page_name,
        "page_label": row.page_label,
        "ata_code": row.ata_code,
        "tiff_path": row.tiff_path,
        "ocr_path": row.ocr_path,
        "tiff_stem": tiff_stem,
        "ocr_stem": ocr_stem,
        "current_rescarta_url": row.current_rescarta_url,
        "source_url": row.source_url,
    }


def template_fields(template: str) -> set[str]:
    """Return named fields used by a Python format template."""
    fields: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            # Strip format suffix/indexing if a user accidentally uses it.
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return fields


def validate_template(template: str, available_tokens: Iterable[str] | None = None) -> None:
    """Validate that a template can produce useful page-specific URLs."""
    if not template or "{" not in template:
        raise ResCartaTemplateError("url template must contain placeholders")
    fields = template_fields(template)
    allowed = set(available_tokens or build_tokens(SourceLinkRow(page_id="p1"), "https://example.org").keys())
    unknown = fields - allowed
    if unknown:
        raise ResCartaTemplateError(f"unknown template placeholder(s): {', '.join(sorted(unknown))}")
    if "base_url" not in fields:
        raise ResCartaTemplateError("url template should include {base_url}")
    if not ({"page_id", "page_name", "page_id_raw", "tiff_stem", "ocr_stem"} & fields):
        raise ResCartaTemplateError("url template should include a page token such as {page_id} or {page_name}")


def render_url(template: str, row: SourceLinkRow | Mapping[str, Any], base_url: str, quote_values: bool = True) -> str:
    """Render a ResCarta URL from a template and a source-link row."""
    normalized = normalize_base_url(base_url)
    tokens = build_tokens(row, normalized)
    validate_template(template, tokens.keys())
    values = dict(tokens)
    if quote_values:
        values = {key: quote(str(value), safe="/:@._-~") for key, value in values.items()}
        values["base_url"] = normalized
    return template.format(**values)


def connect_db(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def source_link_columns(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("PRAGMA table_info(source_links)").fetchall()
    return [str(row[1]) for row in rows]


def fetch_source_rows(conn: sqlite3.Connection, limit: int = 10, where: str = "") -> list[dict[str, Any]]:
    cols = source_link_columns(conn)
    if not cols:
        raise RuntimeError("source_links table not found or has no columns")
    order_col = "page_id" if "page_id" in cols else cols[0]
    query = "SELECT * FROM source_links"
    if where:
        query += f" WHERE {where}"
    query += f" ORDER BY {order_col} LIMIT ?"
    return [dict(row) for row in conn.execute(query, (limit,)).fetchall()]


def preview_links(rows: Sequence[Mapping[str, Any]], template: str, base_url: str) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for row in rows:
        normalized = SourceLinkRow.from_mapping(row)
        tokens = build_tokens(normalized, normalize_base_url(base_url))
        previews.append(
            {
                "page_id": normalized.page_id,
                "manual_id": normalized.manual_id or tokens.get("object_id", ""),
                "ata_code": normalized.ata_code,
                "page_label": normalized.page_label,
                "current_rescarta_url": normalized.current_rescarta_url,
                "proposed_rescarta_url": render_url(template, normalized, base_url),
                "tokens": tokens,
            }
        )
    return previews


def update_source_link_urls(
    conn: sqlite3.Connection,
    template: str,
    base_url: str,
    *,
    update_source_url: bool = True,
    limit: int | None = None,
) -> int:
    """Update source_links URLs in-place and return row count.

    Requires a source_links.page_id column so updates are deterministic.
    """
    cols = source_link_columns(conn)
    if "page_id" not in cols:
        raise RuntimeError("source_links.page_id is required for URL updates")
    if "rescarta_url" not in cols:
        raise RuntimeError("source_links.rescarta_url is required for URL updates")

    select = "SELECT * FROM source_links ORDER BY page_id"
    params: tuple[Any, ...] = ()
    if limit is not None:
        select += " LIMIT ?"
        params = (limit,)
    rows = [dict(row) for row in conn.execute(select, params).fetchall()]
    count = 0
    for row in rows:
        url = render_url(template, row, base_url)
        if update_source_url and "source_url" in cols:
            conn.execute(
                "UPDATE source_links SET rescarta_url = ?, source_url = ? WHERE page_id = ?",
                (url, url, row["page_id"]),
            )
        else:
            conn.execute(
                "UPDATE source_links SET rescarta_url = ? WHERE page_id = ?",
                (url, row["page_id"]),
            )
        count += 1
    return count


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
