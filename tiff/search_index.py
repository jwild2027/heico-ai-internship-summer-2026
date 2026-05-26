"""Local TIFF search catalog helpers.

This module builds a small SQLite search database from the ResCarta staging
export that the TIFF OCR pipeline already creates.

It intentionally stores only searchable text, metadata, and source pointers.
It does not store TIFF image bytes in the search database.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


SQLITE_SCHEMA_VERSION = 1

PART_NUMBER_RE = re.compile(
    r"""
    (?<![A-Z0-9])
    (?:P\s*/?\s*N\s*[:#]?\s*)?
    (
        [A-Z0-9]{2,12}(?:[-/.][A-Z0-9]{1,12}){1,6}
        |
        \d{3,12}(?:\s+\d{2,12}){1,5}
    )
    (?![A-Z0-9])
    """,
    re.IGNORECASE | re.VERBOSE,
)

WHITESPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass
class BuildSummary:
    db_path: Path
    export_root: Path
    manuals: int = 0
    pages: int = 0
    part_mentions: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    page_id: str
    manual_id: str
    publication_number: str | None
    ata_code: str | None
    page_sequence: int | None
    page_label: str | None
    page_type: str | None
    title: str | None
    tiff_path: str | None
    ocr_text_path: str | None
    thumbnail_path: str | None
    rescarta_object_id: str | None
    rescarta_page_id: str | None
    matched_part_number: str | None = None
    matched_part_number_normalized: str | None = None
    part_nomenclature: str | None = None
    part_item_number: str | None = None
    part_quantity: str | None = None
    part_figure_number: str | None = None
    part_confidence: str | None = None
    part_evidence_text: str | None = None
    match_source: str = "keyword"
    snippet: str | None = None
    rank: float | None = None


@dataclass
class PageRecord:
    page_id: str
    manual_id: str
    page_sequence: int
    page_label: str | None
    page_type: str | None
    publication_number: str | None
    ata_code: str | None
    title: str | None
    tiff_path: str | None
    ocr_text_path: str | None
    thumbnail_path: str | None
    rescarta_object_id: str | None
    rescarta_page_id: str | None
    ocr_text: str
    is_blank: int
    metadata_json: str


@dataclass
class ManualRecord:
    manual_id: str
    title: str | None
    publication_number: str | None
    ata_code: str | None
    aircraft_model: str | None
    revision: str | None
    page_count: int
    source_dir: str
    metadata_json: str


def normalize_part_number(value: str | None) -> str:
    """Normalize a part number for exact search.

    Examples:
        120-50648-533 -> 12050648533
        120 50648 533 -> 12050648533
    """

    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def safe_slug(value: str | None, fallback: str = "unknown") -> str:
    if not value:
        return fallback
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or fallback


def collapse_ws(value: str | None) -> str:
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", value).strip()


def safe_load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except UnicodeDecodeError:
        with path.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def deep_get_first(value: Any, keys: Iterable[str]) -> Any:
    """Find the first matching key anywhere in a nested metadata structure."""

    wanted = {normalize_key(k) for k in keys}

    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if normalize_key(str(k)) in wanted and v not in (None, ""):
                    return v
            for v in obj.values():
                found = walk(v)
                if found not in (None, ""):
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = walk(item)
                if found not in (None, ""):
                    return found
        return None

    return walk(value)


def coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return "; ".join(parts) if parts else None
    text = str(value).strip()
    return text or None


def is_probable_ata_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{2}[-\s]\d{2}[-\s]\d{2}", value.strip()))


def is_probable_part_number(value: str) -> bool:
    """Heuristic for search routing and extraction.

    This is intentionally conservative to avoid turning ATA codes and manual
    publication numbers into too many false part-number hits. The raw OCR text
    remains keyword-searchable even when a candidate is not added to the parts
    table.
    """

    display = collapse_ws(value).upper()
    norm = normalize_part_number(display)
    if not norm:
        return False
    if is_probable_ata_code(display):
        return False
    has_digit = any(ch.isdigit() for ch in norm)
    has_alpha = any(ch.isalpha() for ch in norm)
    if not has_digit:
        return False
    if has_alpha and len(norm) >= 4:
        return True
    # Most aircraft part numbers we care about here are longer than ATA codes.
    return len(norm) >= 8


def extract_part_mentions(text: str, context_chars: int = 80) -> list[dict[str, str]]:
    """Extract part-like strings from OCR text.

    Returns display value, normalized value, and a short text context.
    """

    mentions: list[dict[str, str]] = []
    seen: set[tuple[str, int]] = set()
    for match in PART_NUMBER_RE.finditer(text or ""):
        display = collapse_ws(match.group(1))
        if not display or not is_probable_part_number(display):
            continue
        norm = normalize_part_number(display)
        if not norm:
            continue
        key = (norm, match.start(1))
        if key in seen:
            continue
        seen.add(key)
        start = max(0, match.start(1) - context_chars)
        end = min(len(text), match.end(1) + context_chars)
        context = collapse_ws(text[start:end])
        mentions.append(
            {
                "display": display,
                "normalized": norm,
                "context": context,
            }
        )
    return mentions


def create_schema(conn: sqlite3.Connection, reset: bool = True) -> None:
    if reset:
        conn.executescript(
            """
            DROP TABLE IF EXISTS schema_info;
            DROP TABLE IF EXISTS manuals;
            DROP TABLE IF EXISTS pages;
            DROP TABLE IF EXISTS part_mentions;
            DROP TABLE IF EXISTS build_warnings;
            DROP TABLE IF EXISTS page_fts;
            """
        )

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manuals (
            manual_id TEXT PRIMARY KEY,
            title TEXT,
            publication_number TEXT,
            ata_code TEXT,
            aircraft_model TEXT,
            revision TEXT,
            page_count INTEGER DEFAULT 0,
            source_dir TEXT NOT NULL,
            metadata_json TEXT
        );

        CREATE TABLE IF NOT EXISTS pages (
            page_id TEXT PRIMARY KEY,
            manual_id TEXT NOT NULL,
            page_sequence INTEGER,
            page_label TEXT,
            page_type TEXT,
            publication_number TEXT,
            ata_code TEXT,
            title TEXT,
            tiff_path TEXT,
            ocr_text_path TEXT,
            thumbnail_path TEXT,
            rescarta_object_id TEXT,
            rescarta_page_id TEXT,
            ocr_text TEXT,
            is_blank INTEGER DEFAULT 0,
            metadata_json TEXT,
            FOREIGN KEY (manual_id) REFERENCES manuals(manual_id)
        );

        CREATE TABLE IF NOT EXISTS part_mentions (
            mention_id TEXT PRIMARY KEY,
            part_number_display TEXT NOT NULL,
            part_number_normalized TEXT NOT NULL,
            manual_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            page_sequence INTEGER,
            ata_code TEXT,
            context TEXT,
            source TEXT DEFAULT 'ocr',
            FOREIGN KEY (page_id) REFERENCES pages(page_id),
            FOREIGN KEY (manual_id) REFERENCES manuals(manual_id)
        );

        CREATE TABLE IF NOT EXISTS build_warnings (
            warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(
            page_id UNINDEXED,
            manual_id UNINDEXED,
            page_sequence UNINDEXED,
            publication_number,
            ata_code,
            page_type,
            title,
            ocr_text
        );

        CREATE INDEX IF NOT EXISTS idx_pages_manual ON pages(manual_id);
        CREATE INDEX IF NOT EXISTS idx_pages_pub ON pages(publication_number);
        CREATE INDEX IF NOT EXISTS idx_pages_ata ON pages(ata_code);
        CREATE INDEX IF NOT EXISTS idx_pages_type ON pages(page_type);
        CREATE INDEX IF NOT EXISTS idx_parts_norm ON part_mentions(part_number_normalized);
        CREATE INDEX IF NOT EXISTS idx_parts_page ON part_mentions(page_id);
        CREATE INDEX IF NOT EXISTS idx_parts_manual ON part_mentions(manual_id);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)",
        ("schema_version", str(SQLITE_SCHEMA_VERSION)),
    )
    conn.commit()


def parse_page_sequence(stem: str, fallback: int) -> int:
    match = re.match(r"^(\d+)", stem)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return fallback


def find_tiff_for_stem(manual_dir: Path, stem: str) -> Path | None:
    pages_dir = manual_dir / "pages"
    for ext in (".tif", ".tiff", ".TIF", ".TIFF"):
        candidate = pages_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    # Fallback for exports that use the page file name in metadata but not OCR stem.
    if pages_dir.exists():
        matches = sorted(pages_dir.glob(f"{stem}.*"))
        for match in matches:
            if match.suffix.lower() in {".tif", ".tiff"}:
                return match
    return None


def iter_manual_dirs(export_root: Path) -> Iterable[Path]:
    export_root = Path(export_root)
    if not export_root.exists():
        return []
    manual_dirs: list[Path] = []
    for child in sorted(export_root.iterdir()):
        if child.is_dir() and ((child / "ocr").exists() or (child / "manifest.json").exists()):
            manual_dirs.append(child)
    return manual_dirs


def build_manual_record(manual_dir: Path, page_count: int) -> ManualRecord:
    metadata = safe_load_json(manual_dir / "metadata.json")
    manifest = safe_load_json(manual_dir / "manifest.json")
    combined = {"metadata": metadata, "manifest": manifest}

    manual_id = coerce_string(
        deep_get_first(combined, ["manual_id", "object_id", "id", "identifier"])
    ) or manual_dir.name
    title = coerce_string(
        deep_get_first(
            combined,
            [
                "title",
                "manual_title",
                "object_title",
                "publication_title",
                "document_title",
            ],
        )
    )
    publication_number = coerce_string(
        deep_get_first(
            combined,
            [
                "publication_number",
                "publication",
                "manual_code",
                "document_code",
                "pub_number",
            ],
        )
    )
    ata_code = coerce_string(
        deep_get_first(combined, ["ata_code", "ata", "ata_chapter", "chapter"])
    )
    aircraft_model = coerce_string(
        deep_get_first(combined, ["aircraft_model", "aircraft", "model"])
    )
    revision = coerce_string(
        deep_get_first(combined, ["revision", "rev", "revision_number"])
    )

    if not title and publication_number:
        title = publication_number

    return ManualRecord(
        manual_id=safe_slug(manual_id),
        title=title,
        publication_number=publication_number,
        ata_code=ata_code,
        aircraft_model=aircraft_model,
        revision=revision,
        page_count=page_count,
        source_dir=str(manual_dir),
        metadata_json=json_dumps(combined),
    )


def build_page_record(
    manual: ManualRecord,
    manual_dir: Path,
    ocr_file: Path,
    sequence_fallback: int,
) -> PageRecord:
    stem = ocr_file.stem
    page_sequence = parse_page_sequence(stem, sequence_fallback)
    page_id = f"{manual.manual_id}_p{page_sequence:06d}"
    page_metadata_path = ocr_file.with_suffix(".metadata.json")
    page_metadata = safe_load_json(page_metadata_path)

    try:
        ocr_text = ocr_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        ocr_text = ocr_file.read_text(encoding="utf-8-sig")
    except Exception:
        ocr_text = ""

    tiff_path = find_tiff_for_stem(manual_dir, stem)
    title = coerce_string(
        deep_get_first(page_metadata, ["title", "page_title", "component_title", "section_title"])
    )
    page_type = coerce_string(
        deep_get_first(page_metadata, ["page_type", "document_type", "classification", "type"])
    )
    page_label = coerce_string(
        deep_get_first(page_metadata, ["page_label", "printed_page", "page", "page_number"])
    )
    publication_number = coerce_string(
        deep_get_first(page_metadata, ["publication_number", "publication", "manual_code"])
    ) or manual.publication_number
    ata_code = coerce_string(deep_get_first(page_metadata, ["ata_code", "ata", "ata_chapter"])) or manual.ata_code
    thumbnail_path = coerce_string(deep_get_first(page_metadata, ["thumbnail_path", "thumbnail"]))
    rescarta_object_id = coerce_string(
        deep_get_first(page_metadata, ["rescarta_object_id", "object_id"])
    ) or manual.manual_id
    rescarta_page_id = coerce_string(deep_get_first(page_metadata, ["rescarta_page_id", "page_id"]))

    if not page_label:
        page_label = str(page_sequence)
    if not rescarta_page_id:
        rescarta_page_id = f"{page_sequence:06d}"

    is_blank = 1 if (page_type == "blank_page" or not collapse_ws(ocr_text)) else 0

    return PageRecord(
        page_id=page_id,
        manual_id=manual.manual_id,
        page_sequence=page_sequence,
        page_label=page_label,
        page_type=page_type,
        publication_number=publication_number,
        ata_code=ata_code,
        title=title,
        tiff_path=str(tiff_path) if tiff_path else None,
        ocr_text_path=str(ocr_file),
        thumbnail_path=thumbnail_path,
        rescarta_object_id=rescarta_object_id,
        rescarta_page_id=rescarta_page_id,
        ocr_text=ocr_text,
        is_blank=is_blank,
        metadata_json=json_dumps(page_metadata),
    )


def insert_manual(conn: sqlite3.Connection, manual: ManualRecord) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO manuals (
            manual_id, title, publication_number, ata_code, aircraft_model,
            revision, page_count, source_dir, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            manual.manual_id,
            manual.title,
            manual.publication_number,
            manual.ata_code,
            manual.aircraft_model,
            manual.revision,
            manual.page_count,
            manual.source_dir,
            manual.metadata_json,
        ),
    )


def insert_page(conn: sqlite3.Connection, page: PageRecord) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO pages (
            page_id, manual_id, page_sequence, page_label, page_type,
            publication_number, ata_code, title, tiff_path, ocr_text_path,
            thumbnail_path, rescarta_object_id, rescarta_page_id, ocr_text,
            is_blank, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            page.page_id,
            page.manual_id,
            page.page_sequence,
            page.page_label,
            page.page_type,
            page.publication_number,
            page.ata_code,
            page.title,
            page.tiff_path,
            page.ocr_text_path,
            page.thumbnail_path,
            page.rescarta_object_id,
            page.rescarta_page_id,
            page.ocr_text,
            page.is_blank,
            page.metadata_json,
        ),
    )
    conn.execute(
        """
        INSERT INTO page_fts (
            page_id, manual_id, page_sequence, publication_number, ata_code,
            page_type, title, ocr_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            page.page_id,
            page.manual_id,
            str(page.page_sequence),
            page.publication_number or "",
            page.ata_code or "",
            page.page_type or "",
            page.title or "",
            page.ocr_text or "",
        ),
    )


def insert_part_mentions(conn: sqlite3.Connection, page: PageRecord) -> int:
    count = 0
    seen_for_page: set[str] = set()
    for idx, mention in enumerate(extract_part_mentions(page.ocr_text), start=1):
        norm = mention["normalized"]
        # Store each normalized part once per page. The page OCR remains available
        # for all repeated raw occurrences.
        if norm in seen_for_page:
            continue
        seen_for_page.add(norm)
        mention_id = f"{page.page_id}_part_{idx:04d}_{norm}"
        conn.execute(
            """
            INSERT OR REPLACE INTO part_mentions (
                mention_id, part_number_display, part_number_normalized,
                manual_id, page_id, page_sequence, ata_code, context, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mention_id,
                mention["display"],
                norm,
                page.manual_id,
                page.page_id,
                page.page_sequence,
                page.ata_code,
                mention["context"],
                "ocr",
            ),
        )
        count += 1
    return count


def build_search_index(export_root: Path, db_path: Path, reset: bool = True) -> BuildSummary:
    export_root = Path(export_root)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    summary = BuildSummary(db_path=db_path, export_root=export_root)
    conn = sqlite3.connect(str(db_path))
    try:
        create_schema(conn, reset=reset)
        manual_dirs = list(iter_manual_dirs(export_root))
        if not manual_dirs:
            summary.warnings.append(f"No manual export folders found under {export_root}")

        for manual_dir in manual_dirs:
            ocr_dir = manual_dir / "ocr"
            ocr_files = sorted(p for p in ocr_dir.glob("*.txt") if p.is_file()) if ocr_dir.exists() else []
            if not ocr_files:
                summary.warnings.append(f"No OCR text files found for {manual_dir}")
                continue

            manual = build_manual_record(manual_dir, page_count=len(ocr_files))
            insert_manual(conn, manual)
            summary.manuals += 1

            for i, ocr_file in enumerate(ocr_files, start=1):
                page = build_page_record(manual, manual_dir, ocr_file, sequence_fallback=i)
                insert_page(conn, page)
                summary.pages += 1
                summary.part_mentions += insert_part_mentions(conn, page)

        for warning in summary.warnings:
            conn.execute("INSERT INTO build_warnings(message) VALUES (?)", (warning,))
        conn.commit()
        conn.execute("INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)", ("manuals", str(summary.manuals)))
        conn.execute("INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)", ("pages", str(summary.pages)))
        conn.execute("INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)", ("part_mentions", str(summary.part_mentions)))
        conn.commit()
    finally:
        conn.close()
    return summary


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1",
        (name,),
    ).fetchone() is not None


def _row_to_result(row: sqlite3.Row, **extra: Any) -> SearchResult:
    return SearchResult(
        page_id=row["page_id"],
        manual_id=row["manual_id"],
        publication_number=row["publication_number"],
        ata_code=row["ata_code"],
        page_sequence=row["page_sequence"],
        page_label=row["page_label"],
        page_type=row["page_type"],
        title=row["title"],
        tiff_path=row["tiff_path"],
        ocr_text_path=row["ocr_text_path"],
        thumbnail_path=row["thumbnail_path"],
        rescarta_object_id=row["rescarta_object_id"],
        rescarta_page_id=row["rescarta_page_id"],
        matched_part_number=extra.get("matched_part_number"),
        matched_part_number_normalized=extra.get("matched_part_number_normalized"),
        part_nomenclature=extra.get("part_nomenclature", _row_get(row, "part_nomenclature")),
        part_item_number=extra.get("part_item_number", _row_get(row, "part_item_number")),
        part_quantity=extra.get("part_quantity", _row_get(row, "part_quantity")),
        part_figure_number=extra.get("part_figure_number", _row_get(row, "part_figure_number")),
        part_confidence=extra.get("part_confidence", _row_get(row, "part_confidence")),
        part_evidence_text=extra.get("part_evidence_text", _row_get(row, "part_evidence_text")),
        match_source=extra.get("match_source", "keyword"),
        snippet=extra.get("snippet"),
        rank=extra.get("rank"),
    )


def build_fts_query(query: str, joiner: str = "AND") -> str:
    tokens = TOKEN_RE.findall(query or "")
    tokens = [t for t in tokens if t]
    if not tokens:
        return ""
    safe_joiner = " OR " if joiner.upper() == "OR" else " AND "
    # Quoting each token keeps punctuation from becoming FTS syntax.
    return safe_joiner.join('"' + t.replace('"', '""') + '"' for t in tokens)


def search_db(db_path: Path, query: str, limit: int = 20, mode: str = "auto") -> list[SearchResult]:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Search database does not exist: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        results: list[SearchResult] = []
        seen_pages: set[str] = set()
        part_norm = normalize_part_number(query)
        query_is_part_like = is_probable_part_number(query)
        has_part_catalog = _table_exists(conn, "part_catalog")

        if mode in {"auto", "part"} and part_norm and (query_is_part_like or mode == "part"):
            if has_part_catalog:
                sql = """
                    SELECT
                        p.*,
                        pm.part_number_display AS matched_part_number,
                        pm.part_number_normalized AS matched_part_number_normalized,
                        pm.context AS context,
                        pc.nomenclature AS part_nomenclature,
                        pc.item_number AS part_item_number,
                        pc.quantity AS part_quantity,
                        pc.figure_number AS part_figure_number,
                        pc.confidence AS part_confidence,
                        pc.evidence_text AS part_evidence_text
                    FROM part_mentions pm
                    JOIN pages p ON p.page_id = pm.page_id
                    LEFT JOIN part_catalog pc
                      ON pc.page_id = pm.page_id
                     AND pc.part_number_normalized = pm.part_number_normalized
                    WHERE pm.part_number_normalized = ?
                    ORDER BY
                        CASE pc.confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END,
                        CASE WHEN pc.nomenclature IS NOT NULL AND pc.nomenclature <> '' THEN 0 ELSE 1 END,
                        p.manual_id,
                        p.page_sequence
                    LIMIT ?
                """
            else:
                sql = """
                    SELECT
                        p.*,
                        pm.part_number_display AS matched_part_number,
                        pm.part_number_normalized AS matched_part_number_normalized,
                        pm.context AS context,
                        NULL AS part_nomenclature,
                        NULL AS part_item_number,
                        NULL AS part_quantity,
                        NULL AS part_figure_number,
                        NULL AS part_confidence,
                        NULL AS part_evidence_text
                    FROM part_mentions pm
                    JOIN pages p ON p.page_id = pm.page_id
                    WHERE pm.part_number_normalized = ?
                    ORDER BY p.manual_id, p.page_sequence
                    LIMIT ?
                """
            part_rows = conn.execute(sql, (part_norm, limit)).fetchall()
            for row in part_rows:
                if row["page_id"] in seen_pages:
                    continue
                seen_pages.add(row["page_id"])
                results.append(
                    _row_to_result(
                        row,
                        matched_part_number=row["matched_part_number"],
                        matched_part_number_normalized=row["matched_part_number_normalized"],
                        part_nomenclature=row["part_nomenclature"],
                        part_item_number=row["part_item_number"],
                        part_quantity=row["part_quantity"],
                        part_figure_number=row["part_figure_number"],
                        part_confidence=row["part_confidence"],
                        part_evidence_text=row["part_evidence_text"],
                        match_source="part-number",
                        snippet=row["part_evidence_text"] or row["context"],
                        rank=0.0,
                    )
                )

        if mode in {"auto", "keyword"} and len(results) < limit:
            remaining = limit - len(results)
            for joiner in ("AND", "OR"):
                fts_query = build_fts_query(query, joiner=joiner)
                if not fts_query:
                    break
                try:
                    fts_rows = conn.execute(
                        """
                        SELECT
                            p.*,
                            snippet(page_fts, 7, '[', ']', '...', 24) AS snippet,
                            bm25(page_fts) AS rank
                        FROM page_fts
                        JOIN pages p ON p.page_id = page_fts.page_id
                        WHERE page_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (fts_query, remaining),
                    ).fetchall()
                except sqlite3.OperationalError:
                    fts_rows = []
                for row in fts_rows:
                    if row["page_id"] in seen_pages:
                        continue
                    seen_pages.add(row["page_id"])
                    results.append(
                        _row_to_result(
                            row,
                            match_source=f"keyword-{joiner.lower()}",
                            snippet=row["snippet"],
                            rank=float(row["rank"]) if row["rank"] is not None else None,
                        )
                    )
                    if len(results) >= limit:
                        break
                if results or joiner == "OR":
                    break

        if mode in {"auto", "keyword"} and len(results) < limit:
            # Last-resort LIKE search. This helps with punctuation-heavy values
            # that FTS tokenization may split differently.
            remaining = limit - len(results)
            like = f"%{query}%"
            like_rows = conn.execute(
                """
                SELECT *
                FROM pages
                WHERE ocr_text LIKE ?
                   OR publication_number LIKE ?
                   OR ata_code LIKE ?
                   OR title LIKE ?
                ORDER BY manual_id, page_sequence
                LIMIT ?
                """,
                (like, like, like, like, remaining),
            ).fetchall()
            for row in like_rows:
                if row["page_id"] in seen_pages:
                    continue
                seen_pages.add(row["page_id"])
                snippet = make_snippet(row["ocr_text"] or "", query)
                results.append(_row_to_result(row, match_source="keyword-like", snippet=snippet))

        return results[:limit]
    finally:
        conn.close()


def make_snippet(text: str, query: str, width: int = 120) -> str:
    if not text:
        return ""
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx < 0:
        token = next(iter(TOKEN_RE.findall(query)), "")
        idx = lower_text.find(token.lower()) if token else 0
        if idx < 0:
            idx = 0
    start = max(0, idx - width // 2)
    end = min(len(text), idx + width // 2)
    return collapse_ws(text[start:end])


def format_result(result: SearchResult, index: int) -> str:
    lines = [f"Result {index}"]
    lines.append(f"  Match type: {result.match_source}")
    if result.matched_part_number:
        lines.append(f"  Matched part: {result.matched_part_number}")
    if result.part_nomenclature:
        lines.append(f"  Nomenclature: {result.part_nomenclature}")
    if result.part_item_number:
        lines.append(f"  Item: {result.part_item_number}")
    if result.part_quantity:
        lines.append(f"  Quantity: {result.part_quantity}")
    if result.part_confidence:
        lines.append(f"  Nomenclature confidence: {result.part_confidence}")
    lines.append(f"  Manual ID: {result.manual_id}")
    if result.publication_number:
        lines.append(f"  Publication: {result.publication_number}")
    if result.ata_code:
        lines.append(f"  ATA: {result.ata_code}")
    if result.page_sequence is not None:
        lines.append(f"  Page sequence: {result.page_sequence}")
    if result.page_label:
        lines.append(f"  Page label: {result.page_label}")
    if result.page_type:
        lines.append(f"  Page type: {result.page_type}")
    if result.title:
        lines.append(f"  Title: {result.title}")
    if result.snippet:
        lines.append(f"  Snippet: {collapse_ws(result.snippet)}")
    if result.tiff_path:
        lines.append(f"  TIFF: {result.tiff_path}")
    if result.ocr_text_path:
        lines.append(f"  OCR: {result.ocr_text_path}")
    if result.rescarta_object_id:
        page = result.rescarta_page_id or ""
        lines.append(f"  ResCarta object/page: {result.rescarta_object_id} / {page}")
    return "\n".join(lines)


def result_to_dict(result: SearchResult) -> dict[str, Any]:
    return {
        "page_id": result.page_id,
        "manual_id": result.manual_id,
        "publication_number": result.publication_number,
        "ata_code": result.ata_code,
        "page_sequence": result.page_sequence,
        "page_label": result.page_label,
        "page_type": result.page_type,
        "title": result.title,
        "tiff_path": result.tiff_path,
        "ocr_text_path": result.ocr_text_path,
        "thumbnail_path": result.thumbnail_path,
        "rescarta_object_id": result.rescarta_object_id,
        "rescarta_page_id": result.rescarta_page_id,
        "matched_part_number": result.matched_part_number,
        "matched_part_number_normalized": result.matched_part_number_normalized,
        "part_nomenclature": result.part_nomenclature,
        "part_item_number": result.part_item_number,
        "part_quantity": result.part_quantity,
        "part_figure_number": result.part_figure_number,
        "part_confidence": result.part_confidence,
        "part_evidence_text": result.part_evidence_text,
        "match_source": result.match_source,
        "snippet": result.snippet,
        "rank": result.rank,
    }


def open_source_path(path: str | None) -> None:
    if not path:
        raise ValueError("No source path is available for this result")
    source = Path(path)
    system = platform.system().lower()
    if system == "windows":
        os.startfile(str(source))  # type: ignore[attr-defined]
    elif system == "darwin":
        subprocess.run(["open", str(source)], check=False)
    else:
        subprocess.run(["xdg-open", str(source)], check=False)
