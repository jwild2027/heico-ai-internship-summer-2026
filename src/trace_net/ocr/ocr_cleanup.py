"""OCR cleanup and canonical part nomenclature helpers.

This module keeps raw OCR intact and creates cleaned derivative tables inside
``tiff_search.db``. Downstream search/RAG code can use the cleaned tables when
present, while the original OCR text remains available for audit.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from tiff.part_filters import canonicalize_nomenclature_for_comparison, is_bad_nomenclature, is_probable_real_part_number


OCR_CLEANUP_SCHEMA_VERSION = 1
WHITESPACE_RE = re.compile(r"\s+")
REGION_LABEL_RE = re.compile(r"\[[^\]\n]{1,80}\]")
NOISE_ONLY_RE = re.compile(r"^[\s|+_.,:;=\-~`'\"/\\()\[\]{}<>*]+$")
DOT_LEADER_RE = re.compile(r"(?:\.{2,}|[.·]{2,}|(?:\s[.·]){2,})")
REPEATED_PUNCT_RE = re.compile(r"([:;,.|_=+\-])(?:\s*\1){1,}")
HEADER_LABEL_RE = re.compile(
    r"\b(?:ITEM|PART\s*NO\.?|P\s*/\s*N|PN|NOMENCLATURE|DESCRIPTION|DESC|QTY|QUANTITY|EFFECTIVITY|EFF)\b\s*[:#\-]*",
    re.I,
)
TRAILING_QTY_RE = re.compile(r"(?:\s+|\b)(?:QTY\.?\s*)?(?:[0-9]{1,4}|AR|REF|NHA|N/R|NP|OPT)\s*$", re.I)
TRAILING_EFFECTIVITY_RE = re.compile(r"\s+(?:[A-Z]{0,4}\d{3,6}|[A-Z]{1,5}\d{2,6}[A-Z]?)\s*$", re.I)
BAD_NOMENCLATURE_WORDS = {
    "BOTTOM",
    "RIGHT",
    "TITLE",
    "BLOCK",
    "STRIP",
    "TOP",
    "EFFECTIVITY",
    "MANUAL",
    "ILLUSTRATED",
    "PARTS",
    "LIST",
    "PAGE",
}
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ocr_clean_pages (
    page_id TEXT PRIMARY KEY,
    raw_sha256 TEXT NOT NULL,
    raw_char_count INTEGER NOT NULL,
    clean_char_count INTEGER NOT NULL,
    clean_line_count INTEGER NOT NULL,
    removed_line_count INTEGER NOT NULL,
    clean_ocr_text TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS part_catalog_mentions_clean (
    catalog_id TEXT PRIMARY KEY,
    part_number_display TEXT NOT NULL,
    part_number_normalized TEXT NOT NULL,
    raw_nomenclature TEXT,
    clean_nomenclature TEXT,
    item_number TEXT,
    quantity TEXT,
    figure_number TEXT,
    manual_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    page_sequence INTEGER,
    page_label TEXT,
    ata_code TEXT,
    source_tiff_path TEXT,
    source_ocr_path TEXT,
    evidence_text TEXT,
    confidence TEXT,
    quality_score REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS part_catalog_clean (
    part_number_normalized TEXT PRIMARY KEY,
    part_number_display TEXT NOT NULL,
    canonical_nomenclature TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    variant_count INTEGER NOT NULL,
    best_catalog_id TEXT,
    best_page_id TEXT,
    best_page_sequence INTEGER,
    best_page_label TEXT,
    best_ata_code TEXT,
    source_tiff_path TEXT,
    source_ocr_path TEXT,
    evidence_text TEXT,
    confidence TEXT,
    variants_json TEXT DEFAULT '[]',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ocr_clean_pages_page ON ocr_clean_pages(page_id);
CREATE INDEX IF NOT EXISTS idx_pcmc_norm ON part_catalog_mentions_clean(part_number_normalized);
CREATE INDEX IF NOT EXISTS idx_pcmc_page ON part_catalog_mentions_clean(page_id);
CREATE INDEX IF NOT EXISTS idx_pcmc_name ON part_catalog_mentions_clean(clean_nomenclature);
CREATE INDEX IF NOT EXISTS idx_pcc_norm ON part_catalog_clean(part_number_normalized);
CREATE INDEX IF NOT EXISTS idx_pcc_name ON part_catalog_clean(canonical_nomenclature);
"""


@dataclass(frozen=True)
class CleanedLine:
    raw: str
    clean: str
    removed: bool = False


@dataclass(frozen=True)
class CanonicalPart:
    part_number_display: str
    part_number_normalized: str
    canonical_nomenclature: str
    source_count: int
    variant_count: int
    best_catalog_id: str | None
    best_page_id: str | None
    best_page_sequence: int | None
    best_page_label: str | None
    best_ata_code: str | None
    source_tiff_path: str | None
    source_ocr_path: str | None
    evidence_text: str | None
    confidence: str | None
    variants: tuple[str, ...]


@dataclass
class OcrCleanupSummary:
    db_path: Path
    pages_seen: int = 0
    pages_cleaned: int = 0
    raw_chars: int = 0
    clean_chars: int = 0
    removed_lines: int = 0
    catalog_rows_seen: int = 0
    catalog_rows_cleaned: int = 0
    canonical_parts: int = 0
    warnings: list[str] = field(default_factory=list)


def collapse_ws(value: str | None) -> str:
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", str(value)).strip()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1",
        (name,),
    ).fetchone() is not None


def sha256_text(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="replace")).hexdigest()


def normalize_ocr_artifacts(text: str | None) -> str:
    """Normalize common OCR punctuation without removing meaningful content."""

    if not text:
        return ""
    out = str(text)
    out = out.replace("\u00a0", " ")
    out = out.replace("\u2010", "-").replace("\u2011", "-").replace("\u2012", "-").replace("\u2013", "-").replace("\u2014", "-")
    out = out.replace("\u2212", "-").replace("\u00b7", ".")
    out = out.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    # OCR often sees T.P. 120/1176 as [T].[P]. [120]/[1176]. Keep the meaning.
    out = re.sub(r"\[([A-Za-z0-9])\]", r"\1", out)
    out = re.sub(r"\[([0-9]{1,6})\]", r"\1", out)
    return out


def clean_ocr_line(line: str | None, *, keep_region_labels: bool = False) -> CleanedLine:
    raw = collapse_ws(normalize_ocr_artifacts(line))
    if not raw:
        return CleanedLine(raw="", clean="", removed=True)
    clean = raw if keep_region_labels else REGION_LABEL_RE.sub(" ", raw)
    clean = DOT_LEADER_RE.sub(" ... ", clean)
    clean = REPEATED_PUNCT_RE.sub(r"\1", clean)
    clean = collapse_ws(clean)
    clean = clean.strip(" |+_=;:,")
    if not clean or NOISE_ONLY_RE.fullmatch(clean):
        return CleanedLine(raw=raw, clean="", removed=True)
    return CleanedLine(raw=raw, clean=clean, removed=False)


def clean_ocr_text(text: str | None, *, keep_region_labels: bool = False) -> tuple[str, int]:
    """Return cleaned OCR text and number of discarded decoration/noise lines."""

    if not text:
        return "", 0
    raw = normalize_ocr_artifacts(text).replace("\r\n", "\n").replace("\r", "\n")
    out_lines: list[str] = []
    removed = 0
    for line in raw.split("\n"):
        cleaned = clean_ocr_line(line, keep_region_labels=keep_region_labels)
        if cleaned.removed:
            if cleaned.raw:
                removed += 1
            continue
        out_lines.append(cleaned.clean)
    return "\n".join(out_lines).strip(), removed


def _strip_nomenclature_tail(text: str) -> str:
    # Dot leaders in IPL rows usually separate nomenclature from effectivity/model codes.
    text = DOT_LEADER_RE.split(text, maxsplit=1)[0]
    # If the general OCR cleaner already compressed leaders, they can look like
    # " . 0 . 0 :EEEE ...". Treat that as the same kind of tail noise.
    text = re.sub(r"\s+\.\s*0(?:\s*\.\s*0)*\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s+(?:0+C0|C0+|E{3,}|=+)\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s+[=:]+\s*[A-Z0-9-]+\s*$", "", text, flags=re.I)
    # Remove trailing effectivity-looking codes only when there is already a word-like name.
    for _ in range(2):
        candidate = TRAILING_EFFECTIVITY_RE.sub("", text).strip()
        if candidate != text and any(ch.isalpha() for ch in candidate) and len(candidate) >= 3:
            text = candidate
        else:
            break
    text = TRAILING_QTY_RE.sub("", text).strip()
    return text


def clean_part_nomenclature(value: str | None) -> str | None:
    """Aggressively clean a part nomenclature fragment.

    Examples:
        HOLDER, MAGAZINE... VWS4956 -> HOLDER, MAGAZINE
        HOLDER, MAGAZINE........0..0..:EEEE WS4956 -> HOLDER, MAGAZINE
    """

    if not value:
        return None
    text = normalize_ocr_artifacts(value)
    text = REGION_LABEL_RE.sub(" ", text)
    text = HEADER_LABEL_RE.sub(" ", text)
    text = re.sub(r"^[\s|:;,._/\\+\-=]+", "", text)
    text = collapse_ws(text)
    text = _strip_nomenclature_tail(text)
    text = REPEATED_PUNCT_RE.sub(r"\1", text)
    text = re.sub(r"\s*[,;:]\s*", lambda m: m.group(0).strip() + " ", text)
    text = collapse_ws(text.strip(" |:;,.=_+-"))
    if not text:
        return None
    text = text.upper()
    text = re.sub(r"\s*,\s*", ", ", text)
    text = collapse_ws(text)
    if not looks_like_clean_nomenclature(text) or is_bad_nomenclature(text):
        return None
    return text


def looks_like_clean_nomenclature(value: str | None) -> bool:
    if not value:
        return False
    text = collapse_ws(value).upper().strip(" |:;,.()")
    if len(text) < 3 or len(text) > 80:
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    if is_bad_nomenclature(text):
        return False
    tokens = re.findall(r"[A-Z0-9/.-]+", text)
    if not tokens:
        return False
    if any(token in BAD_NOMENCLATURE_WORDS for token in tokens[:3]):
        return False
    alpha_tokens = [t for t in tokens if any(ch.isalpha() for ch in t)]
    if not alpha_tokens:
        return False
    # Reject mostly-code strings such as VWS4956 WS4956.
    code_like = sum(1 for t in tokens if re.fullmatch(r"[A-Z]{0,4}\d{2,6}[A-Z]?", t))
    if code_like >= max(1, len(tokens) - 1):
        return False
    return True


def nomenclature_quality_score(value: str | None, confidence: str | None = None) -> float:
    if not value:
        return 0.0
    text = collapse_ws(value).upper()
    score = 50.0
    if confidence == "high":
        score += 20.0
    elif confidence == "medium":
        score += 10.0
    score += min(20.0, len(re.findall(r"[A-Z]+", text)) * 4.0)
    score -= min(25.0, len(re.findall(r"[0-9]", text)) * 2.5)
    score -= min(20.0, len(re.findall(r"[|_=+:;]", text)) * 3.0)
    if "," in text:
        score += 5.0
    if 4 <= len(text) <= 36:
        score += 10.0
    elif len(text) > 60:
        score -= 10.0
    return max(0.0, score)


def create_ocr_cleanup_schema(conn: sqlite3.Connection, reset: bool = False) -> None:
    if reset:
        conn.executescript(
            """
            DROP TABLE IF EXISTS ocr_clean_pages;
            DROP TABLE IF EXISTS part_catalog_mentions_clean;
            DROP TABLE IF EXISTS part_catalog_clean;
            """
        )
    conn.executescript(SCHEMA_SQL)
    if table_exists(conn, "schema_info"):
        conn.execute(
            "INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)",
            ("ocr_cleanup_schema_version", str(OCR_CLEANUP_SCHEMA_VERSION)),
        )
    conn.commit()


def build_clean_ocr_pages(conn: sqlite3.Connection, summary: OcrCleanupSummary) -> None:
    if not table_exists(conn, "pages"):
        raise RuntimeError("Database is missing pages. Build tiff_search.db first.")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT page_id, ocr_text FROM pages ORDER BY manual_id, page_sequence").fetchall()
    for row in rows:
        raw = row["ocr_text"] or ""
        clean, removed = clean_ocr_text(raw)
        raw_chars = len(raw)
        clean_chars = len(clean)
        line_count = len([line for line in clean.split("\n") if line.strip()])
        conn.execute(
            """
            INSERT OR REPLACE INTO ocr_clean_pages (
                page_id, raw_sha256, raw_char_count, clean_char_count,
                clean_line_count, removed_line_count, clean_ocr_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (row["page_id"], sha256_text(raw), raw_chars, clean_chars, line_count, removed, clean),
        )
        summary.pages_seen += 1
        summary.pages_cleaned += 1
        summary.raw_chars += raw_chars
        summary.clean_chars += clean_chars
        summary.removed_lines += removed


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except Exception:
        return default


def _catalog_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if not table_exists(conn, "part_catalog"):
        return []
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT
            catalog_id, part_number_display, part_number_normalized, nomenclature,
            item_number, quantity, figure_number, manual_id, page_id, page_sequence,
            page_label, ata_code, source_tiff_path, source_ocr_path, evidence_text,
            confidence
        FROM part_catalog
        ORDER BY part_number_normalized, page_sequence, catalog_id
        """
    ).fetchall()


def build_clean_part_catalog(conn: sqlite3.Connection, summary: OcrCleanupSummary) -> None:
    rows = _catalog_rows(conn)
    if not rows:
        summary.warnings.append("No part_catalog rows found. Run scripts/build/ingestion/build_part_catalog.py first, then run OCR cleanup again.")
        return
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        summary.catalog_rows_seen += 1
        if not is_probable_real_part_number(_row_get(row, "part_number_display") or _row_get(row, "part_number_normalized")):
            continue
        raw_name = _row_get(row, "nomenclature")
        clean_name = clean_part_nomenclature(raw_name)
        quality = nomenclature_quality_score(clean_name, _row_get(row, "confidence"))
        if clean_name:
            summary.catalog_rows_cleaned += 1
        conn.execute(
            """
            INSERT OR REPLACE INTO part_catalog_mentions_clean (
                catalog_id, part_number_display, part_number_normalized, raw_nomenclature,
                clean_nomenclature, item_number, quantity, figure_number, manual_id, page_id,
                page_sequence, page_label, ata_code, source_tiff_path, source_ocr_path,
                evidence_text, confidence, quality_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["catalog_id"],
                row["part_number_display"],
                row["part_number_normalized"],
                raw_name,
                clean_name,
                row["item_number"],
                row["quantity"],
                row["figure_number"],
                row["manual_id"],
                row["page_id"],
                row["page_sequence"],
                row["page_label"],
                row["ata_code"],
                row["source_tiff_path"],
                row["source_ocr_path"],
                row["evidence_text"],
                row["confidence"],
                quality,
            ),
        )
        if clean_name:
            grouped[row["part_number_normalized"]].append(row)

    for part_norm, part_rows in grouped.items():
        canonical = choose_canonical_part(conn, part_norm, part_rows)
        if canonical is None:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO part_catalog_clean (
                part_number_normalized, part_number_display, canonical_nomenclature,
                source_count, variant_count, best_catalog_id, best_page_id,
                best_page_sequence, best_page_label, best_ata_code, source_tiff_path,
                source_ocr_path, evidence_text, confidence, variants_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical.part_number_normalized,
                canonical.part_number_display,
                canonical.canonical_nomenclature,
                canonical.source_count,
                canonical.variant_count,
                canonical.best_catalog_id,
                canonical.best_page_id,
                canonical.best_page_sequence,
                canonical.best_page_label,
                canonical.best_ata_code,
                canonical.source_tiff_path,
                canonical.source_ocr_path,
                canonical.evidence_text,
                canonical.confidence,
                json_dumps(list(canonical.variants)),
            ),
        )
        summary.canonical_parts += 1


def choose_canonical_part(conn: sqlite3.Connection, part_norm: str, raw_rows: Iterable[sqlite3.Row]) -> CanonicalPart | None:
    rows = conn.execute(
        """
        SELECT *
        FROM part_catalog_mentions_clean
        WHERE part_number_normalized = ?
          AND clean_nomenclature IS NOT NULL
          AND TRIM(clean_nomenclature) <> ''
        ORDER BY quality_score DESC, page_sequence
        """,
        (part_norm,),
    ).fetchall()
    if not rows:
        return None
    counts = Counter(row["clean_nomenclature"] for row in rows)
    best_row = None
    best_score = -1.0
    for row in rows:
        name = row["clean_nomenclature"]
        score = float(row["quality_score"] or 0.0) + counts[name] * 15.0
        if score > best_score:
            best_row = row
            best_score = score
    if best_row is None:
        return None
    variants = tuple(name for name, _ in counts.most_common())
    return CanonicalPart(
        part_number_display=best_row["part_number_display"],
        part_number_normalized=part_norm,
        canonical_nomenclature=best_row["clean_nomenclature"],
        source_count=len(rows),
        variant_count=len(counts),
        best_catalog_id=best_row["catalog_id"],
        best_page_id=best_row["page_id"],
        best_page_sequence=best_row["page_sequence"],
        best_page_label=best_row["page_label"],
        best_ata_code=best_row["ata_code"],
        source_tiff_path=best_row["source_tiff_path"],
        source_ocr_path=best_row["source_ocr_path"],
        evidence_text=best_row["evidence_text"],
        confidence=best_row["confidence"],
        variants=variants,
    )


def run_ocr_cleanup(db_path: Path | str, *, reset: bool = True, include_catalog: bool = True) -> OcrCleanupSummary:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Search database does not exist: {db_path}")
    summary = OcrCleanupSummary(db_path=db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        create_ocr_cleanup_schema(conn, reset=reset)
        build_clean_ocr_pages(conn, summary)
        if include_catalog:
            build_clean_part_catalog(conn, summary)
        if table_exists(conn, "schema_info"):
            conn.execute("INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)", ("ocr_clean_pages", str(summary.pages_cleaned)))
            conn.execute("INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)", ("part_catalog_clean_rows", str(summary.canonical_parts)))
        conn.commit()
    finally:
        conn.close()
    return summary


def rebuild_clean_part_catalog_pipeline(db_path: Path | str, *, reset: bool = True) -> OcrCleanupSummary:
    """Clean OCR pages, rebuild part_catalog from clean OCR, then canonicalize it."""

    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Search database does not exist: {db_path}")
    # First create only clean OCR pages.
    summary = run_ocr_cleanup(db_path, reset=reset, include_catalog=False)
    # Rebuild the part catalog. The patched part_catalog module uses ocr_clean_pages when present.
    from tiff.part_catalog import build_part_catalog

    part_summary = build_part_catalog(db_path, reset=True)
    # Then rebuild the cleanup tables while preserving clean pages and adding canonical catalog rows.
    second = run_ocr_cleanup(db_path, reset=False, include_catalog=True)
    summary.catalog_rows_seen = second.catalog_rows_seen
    summary.catalog_rows_cleaned = second.catalog_rows_cleaned
    summary.canonical_parts = second.canonical_parts
    summary.warnings.extend(second.warnings)
    # Keep the part extraction counts as informational warnings because the script output prints them too.
    summary.warnings.append(
        f"Part catalog rebuilt: {part_summary.catalog_entries} rows; high={part_summary.high_confidence}; medium={part_summary.medium_confidence}; low={part_summary.low_confidence}; skipped={part_summary.skipped_mentions}."
    )
    return summary


def cleanup_summary_counts(db_path: Path | str) -> dict[str, int | str]:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        out: dict[str, int | str] = {"db_path": str(db_path)}
        for table in ("ocr_clean_pages", "part_catalog_mentions_clean", "part_catalog_clean"):
            out[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] if table_exists(conn, table) else 0
        if table_exists(conn, "ocr_clean_pages"):
            out["removed_lines"] = conn.execute("SELECT COALESCE(sum(removed_line_count), 0) FROM ocr_clean_pages").fetchone()[0]
        return out
    finally:
        conn.close()
