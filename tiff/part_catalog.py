"""Part catalog and nomenclature extraction for the local TIFF search DB.

This module adds a lightweight, source-backed parts catalog on top of the
existing OCR search database. It does not guess part names. It extracts a
nomenclature only when nearby OCR text provides evidence, usually from an IPL
row such as:

    ITEM  PART NUMBER      NOMENCLATURE       QTY
    12    120-37313-001    MAGAZINE HOLDER    1

The extraction intentionally starts simple. It uses existing OCR text and page
metadata, then stores the evidence text so questionable rows can be reviewed.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tiff.search_index import collapse_ws, normalize_part_number


CATALOG_SCHEMA_VERSION = 1

REGION_LABEL_RE = re.compile(r"\[[^\]\n]{1,80}\]")
PART_LIKE_RE = re.compile(r"(?<![A-Z0-9])(?:[A-Z0-9]{2,12}(?:[-/.][A-Z0-9]{1,12}){1,6})(?![A-Z0-9])", re.I)
FIGURE_RE = re.compile(r"\b(?:FIG(?:URE)?\.?|FIG)\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{0,12})\b", re.I)
QTY_RE = re.compile(r"(?:\s+|\b)(?:QTY\.?\s*)?([0-9]{1,4}|AR|REF|NHA|N/R|NP|OPT)\s*$", re.I)
ITEM_RE = re.compile(r"(?:^|\s)([A-Z]?\d{1,4}[A-Z]?|\d{1,3}[A-Z]?[-.]\d{1,3})\s*$", re.I)

HEADER_WORDS = {
    "ITEM",
    "PART",
    "PARTS",
    "NUMBER",
    "NO",
    "NOMENCLATURE",
    "DESCRIPTION",
    "DESC",
    "QTY",
    "QUANTITY",
    "EFF",
    "EFFECTIVITY",
    "PAGE",
    "FIG",
    "FIGURE",
    "MANUAL",
    "CONTENTS",
    "LIST",
    "ILLUSTRATED",
}

BAD_NAME_PHRASES = [
    "EFFECTIVITY ALL",
    "T P 120",
    "T.P. 120",
    "PAGE ",
    "JAN ",
    "SEP ",
    "MAINTENANCE MANUAL",
    "ILLUSTRATED PARTS LIST",
    "BOTTOM RIGHT TITLE BLOCK",
    "BOTTOM STRIP",
    "TOP STRIP",
]


@dataclass
class PartCatalogEntry:
    part_number_display: str
    part_number_normalized: str
    nomenclature: str | None
    manual_id: str
    page_id: str
    page_sequence: int | None
    page_label: str | None
    ata_code: str | None
    item_number: str | None = None
    quantity: str | None = None
    figure_number: str | None = None
    source_tiff_path: str | None = None
    source_ocr_path: str | None = None
    evidence_text: str | None = None
    confidence: str = "low"
    extraction_method: str = "ocr-nearby-line"


@dataclass
class PartCatalogSummary:
    db_path: Path
    catalog_entries: int = 0
    high_confidence: int = 0
    medium_confidence: int = 0
    low_confidence: int = 0
    skipped_mentions: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class PartCatalogRow:
    part_number_display: str
    part_number_normalized: str
    nomenclature: str | None
    item_number: str | None
    quantity: str | None
    figure_number: str | None
    manual_id: str
    page_id: str
    page_sequence: int | None
    page_label: str | None
    ata_code: str | None
    source_tiff_path: str | None
    source_ocr_path: str | None
    evidence_text: str | None
    confidence: str | None


def create_part_catalog_schema(conn: sqlite3.Connection, reset: bool = False) -> None:
    """Create the part_catalog table in an existing TIFF search DB."""

    if reset:
        conn.executescript(
            """
            DROP TABLE IF EXISTS part_catalog;
            DROP TABLE IF EXISTS part_catalog_warnings;
            """
        )

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS part_catalog (
            catalog_id TEXT PRIMARY KEY,
            part_number_display TEXT NOT NULL,
            part_number_normalized TEXT NOT NULL,
            nomenclature TEXT,
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
            confidence TEXT DEFAULT 'low',
            extraction_method TEXT DEFAULT 'ocr-nearby-line',
            reviewed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES pages(page_id),
            FOREIGN KEY (manual_id) REFERENCES manuals(manual_id)
        );

        CREATE TABLE IF NOT EXISTS part_catalog_warnings (
            warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_part_catalog_norm ON part_catalog(part_number_normalized);
        CREATE INDEX IF NOT EXISTS idx_part_catalog_page ON part_catalog(page_id);
        CREATE INDEX IF NOT EXISTS idx_part_catalog_manual ON part_catalog(manual_id);
        CREATE INDEX IF NOT EXISTS idx_part_catalog_name ON part_catalog(nomenclature);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)",
        ("part_catalog_schema_version", str(CATALOG_SCHEMA_VERSION)),
    )
    conn.commit()


def is_ata_reference_number(value: str | None) -> bool:
    """Return True for ATA/figure reference values that should not be catalog parts."""

    if not value:
        return False
    display = collapse_ws(value).upper()
    if re.fullmatch(r"\d{2}[-\s]\d{2}[-\s]\d{2}[-\s][A-Z0-9]{1,4}", display):
        return True
    if re.fullmatch(r"\d{2}[-\s]\d{2}[-\s]\d{2}", display):
        return True
    return False


def is_probable_catalog_part(value: str | None) -> bool:
    """Filter obvious non-part references before catalog extraction."""

    if not value:
        return False
    display = collapse_ws(value).upper()
    norm = normalize_part_number(display)
    if not norm:
        return False
    if is_ata_reference_number(display):
        return False
    if len(norm) < 5:
        return False
    if any(ch.isalpha() for ch in norm):
        return True
    return len(norm) >= 8 and bool(re.search(r"[-/.\s]", display))


def split_ocr_lines(text: str | None) -> list[str]:
    """Split OCR text into useful lines while preserving table context."""

    if not text:
        return []
    raw_lines: list[str] = []
    for line in str(text).replace("\r", "\n").split("\n"):
        line = collapse_ws(line)
        if not line:
            continue
        parts = re.split(r"(?=\[[A-Za-z0-9_ \-]{2,80}\])", line)
        for part in parts:
            part = collapse_ws(part)
            if part:
                raw_lines.append(part)
    return raw_lines


def remove_region_labels(text: str | None) -> str:
    return collapse_ws(REGION_LABEL_RE.sub(" ", text or ""))


def norm_span_in_text(text: str, normalized: str) -> tuple[int, int] | None:
    """Find the original character span matching a normalized part number."""

    if not text or not normalized:
        return None
    positions: list[int] = []
    chars: list[str] = []
    for idx, ch in enumerate(text):
        if ch.isalnum():
            positions.append(idx)
            chars.append(ch.upper())
    joined = "".join(chars)
    pos = joined.find(normalized.upper())
    if pos < 0:
        return None
    start = positions[pos]
    end = positions[pos + len(normalized) - 1] + 1
    return start, end


def strip_after_next_part(text: str) -> str:
    match = PART_LIKE_RE.search(text)
    if match and match.start() > 0:
        return text[: match.start()]
    return text


def extract_trailing_quantity(text: str) -> tuple[str, str | None]:
    cleaned = collapse_ws(text)
    match = QTY_RE.search(cleaned)
    if not match:
        return cleaned, None
    qty = match.group(1).upper()
    before = collapse_ws(cleaned[: match.start(1)])
    if len(before) >= 3:
        return before, qty
    return cleaned, None


def clean_nomenclature(candidate: str | None) -> tuple[str | None, str | None]:
    """Clean a raw nearby OCR fragment into a possible nomenclature and quantity."""

    if not candidate:
        return None, None
    text = remove_region_labels(candidate)
    text = strip_after_next_part(text)
    text = re.sub(r"^[\s|:;,.\-_/]+", "", text)
    text = re.sub(r"\b(?:ITEM|PART\s*NO\.?|P\s*/\s*N|PN|NOMENCLATURE|DESCRIPTION|QTY)\b\s*[:#-]*", " ", text, flags=re.I)
    text = collapse_ws(text)
    text, qty = extract_trailing_quantity(text)
    text = re.sub(r"[|]{2,}", " ", text)
    text = collapse_ws(text.strip(" |:;,.")).upper()
    if not looks_like_nomenclature(text):
        return None, qty
    return text, qty


def looks_like_nomenclature(value: str | None) -> bool:
    if not value:
        return False
    text = collapse_ws(value).strip(" |:;,.()").upper()
    if len(text) < 3 or len(text) > 96:
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    for phrase in BAD_NAME_PHRASES:
        if phrase in text:
            return False
    tokens = re.findall(r"[A-Z0-9/.-]+", text)
    if not tokens:
        return False
    if all(token in HEADER_WORDS for token in tokens):
        return False
    if tokens[0] in {"PAGE", "FIG", "FIGURE", "EFFECTIVITY", "ALL"}:
        return False
    alpha_tokens = [t for t in tokens if any(ch.isalpha() for ch in t)]
    if not alpha_tokens:
        return False
    code_like = sum(1 for t in tokens if re.fullmatch(r"[A-Z]?\d+[A-Z0-9.-]*", t))
    if code_like >= max(2, len(tokens) - 1):
        return False
    return True


def extract_item_number(before_part: str | None) -> str | None:
    before = remove_region_labels(before_part)
    before = re.sub(r"\b(?:ITEM|FIG|FIGURE|PART|NO|NOMENCLATURE)\b", " ", before, flags=re.I)
    before = collapse_ws(before.strip(" |:;,.")).upper()
    if not before:
        return None
    match = ITEM_RE.search(before)
    if not match:
        return None
    item = match.group(1).upper()
    if len(item) > 6:
        return None
    return item


def extract_figure_number(evidence: str | None) -> str | None:
    if not evidence:
        return None
    match = FIGURE_RE.search(evidence)
    return match.group(1).upper() if match else None


def confidence_for(method: str, nomenclature: str | None) -> str:
    if not nomenclature:
        return "low"
    if method == "same-line":
        return "high"
    if method.startswith("adjacent"):
        return "medium"
    return "low"


def best_nomenclature_from_lines(lines: list[str], normalized: str) -> tuple[str | None, str | None, str | None, str | None, str, str | None]:
    """Return nomenclature, item, qty, figure, confidence, evidence for a part."""

    best: tuple[str | None, str | None, str | None, str | None, str, str | None] = (None, None, None, None, "low", None)
    confidence_rank = {"high": 3, "medium": 2, "low": 1}

    for idx, line in enumerate(lines):
        span = norm_span_in_text(line, normalized)
        if not span:
            continue
        start, end = span
        before = line[:start]
        after = line[end:]
        evidence_parts = [line]
        if idx + 1 < len(lines):
            evidence_parts.append(lines[idx + 1])
        if idx + 2 < len(lines):
            evidence_parts.append(lines[idx + 2])
        evidence = collapse_ws(" ".join(evidence_parts))
        item_number = extract_item_number(before)
        figure_number = extract_figure_number(evidence)

        candidates: list[tuple[str, str]] = [("same-line", after)]
        if idx + 1 < len(lines):
            candidates.append(("adjacent-next-line", lines[idx + 1]))
        if idx + 2 < len(lines):
            candidates.append(("adjacent-second-line", lines[idx + 2]))
        if idx > 0:
            candidates.append(("adjacent-previous-line", lines[idx - 1]))

        for method, raw_candidate in candidates:
            nomenclature, qty = clean_nomenclature(raw_candidate)
            conf = confidence_for(method, nomenclature)
            if nomenclature and confidence_rank[conf] > confidence_rank[best[4]]:
                best = (nomenclature, item_number, qty, figure_number, conf, evidence)
                if conf == "high":
                    return best

        if best[5] is None:
            best = (None, item_number, None, figure_number, "low", evidence)

    return best


def extract_catalog_entry_from_page(page: sqlite3.Row, part_display: str, part_norm: str) -> PartCatalogEntry | None:
    if not is_probable_catalog_part(part_display):
        return None
    lines = split_ocr_lines(page["ocr_text"] or "")
    if not lines:
        return None
    nomenclature, item_number, qty, figure_number, confidence, evidence = best_nomenclature_from_lines(lines, part_norm)
    if not nomenclature:
        return None
    return PartCatalogEntry(
        part_number_display=part_display,
        part_number_normalized=part_norm,
        nomenclature=nomenclature,
        item_number=item_number,
        quantity=qty,
        figure_number=figure_number,
        manual_id=page["manual_id"],
        page_id=page["page_id"],
        page_sequence=page["page_sequence"],
        page_label=page["page_label"],
        ata_code=page["ata_code"],
        source_tiff_path=page["tiff_path"],
        source_ocr_path=page["ocr_text_path"],
        evidence_text=evidence,
        confidence=confidence,
    )


def insert_catalog_entry(conn: sqlite3.Connection, entry: PartCatalogEntry, sequence: int) -> None:
    catalog_id = f"{entry.page_id}_{entry.part_number_normalized}_{sequence:04d}"
    conn.execute(
        """
        INSERT OR REPLACE INTO part_catalog (
            catalog_id, part_number_display, part_number_normalized, nomenclature,
            item_number, quantity, figure_number, manual_id, page_id, page_sequence,
            page_label, ata_code, source_tiff_path, source_ocr_path, evidence_text,
            confidence, extraction_method
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            catalog_id,
            entry.part_number_display,
            entry.part_number_normalized,
            entry.nomenclature,
            entry.item_number,
            entry.quantity,
            entry.figure_number,
            entry.manual_id,
            entry.page_id,
            entry.page_sequence,
            entry.page_label,
            entry.ata_code,
            entry.source_tiff_path,
            entry.source_ocr_path,
            entry.evidence_text,
            entry.confidence,
            entry.extraction_method,
        ),
    )


def build_part_catalog(db_path: Path | str, reset: bool = True) -> PartCatalogSummary:
    """Build or rebuild part_catalog from pages + part_mentions in a search DB."""

    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Search database does not exist: {db_path}")

    summary = PartCatalogSummary(db_path=db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        create_part_catalog_schema(conn, reset=reset)
        page_rows = conn.execute(
            """
            SELECT
                p.page_id, p.manual_id, p.page_sequence, p.page_label, p.ata_code,
                p.tiff_path, p.ocr_text_path, p.ocr_text,
                pm.part_number_display, pm.part_number_normalized
            FROM part_mentions pm
            JOIN pages p ON p.page_id = pm.page_id
            ORDER BY p.manual_id, p.page_sequence, pm.part_number_normalized
            """
        ).fetchall()

        sequence = 0
        seen_keys: set[tuple[str, str, str]] = set()
        for row in page_rows:
            part_display = row["part_number_display"]
            part_norm = row["part_number_normalized"]
            key = (row["page_id"], part_norm, part_display)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entry = extract_catalog_entry_from_page(row, part_display, part_norm)
            if entry is None:
                summary.skipped_mentions += 1
                continue
            sequence += 1
            insert_catalog_entry(conn, entry, sequence)
            summary.catalog_entries += 1
            if entry.confidence == "high":
                summary.high_confidence += 1
            elif entry.confidence == "medium":
                summary.medium_confidence += 1
            else:
                summary.low_confidence += 1

        conn.execute(
            "INSERT OR REPLACE INTO schema_info(key, value) VALUES (?, ?)",
            ("part_catalog_entries", str(summary.catalog_entries)),
        )
        conn.commit()
    finally:
        conn.close()
    return summary


def query_part_catalog(db_path: Path | str, query: str | None = None, limit: int = 50) -> list[PartCatalogRow]:
    """Query catalog rows by part number or nomenclature."""

    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        norm = normalize_part_number(query or "")
        params: list[object] = []
        where = ""
        if query:
            if norm:
                where = "WHERE part_number_normalized = ? OR nomenclature LIKE ?"
                params.extend([norm, f"%{query}%"])
            else:
                where = "WHERE nomenclature LIKE ?"
                params.append(f"%{query}%")
        params.append(int(limit))
        rows = conn.execute(
            f"""
            SELECT *
            FROM part_catalog
            {where}
            ORDER BY
                CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                part_number_normalized,
                page_sequence
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            PartCatalogRow(
                part_number_display=row["part_number_display"],
                part_number_normalized=row["part_number_normalized"],
                nomenclature=row["nomenclature"],
                item_number=row["item_number"],
                quantity=row["quantity"],
                figure_number=row["figure_number"],
                manual_id=row["manual_id"],
                page_id=row["page_id"],
                page_sequence=row["page_sequence"],
                page_label=row["page_label"],
                ata_code=row["ata_code"],
                source_tiff_path=row["source_tiff_path"],
                source_ocr_path=row["source_ocr_path"],
                evidence_text=row["evidence_text"],
                confidence=row["confidence"],
            )
            for row in rows
        ]
    finally:
        conn.close()


def catalog_rows_to_csv(rows: Iterable[PartCatalogRow]) -> str:
    from io import StringIO

    output = StringIO()
    fieldnames = [
        "part_number_display",
        "part_number_normalized",
        "nomenclature",
        "item_number",
        "quantity",
        "figure_number",
        "manual_id",
        "page_id",
        "page_sequence",
        "page_label",
        "ata_code",
        "source_tiff_path",
        "source_ocr_path",
        "confidence",
        "evidence_text",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: getattr(row, name) or "" for name in fieldnames})
    return output.getvalue()


def format_catalog_row(row: PartCatalogRow, index: int) -> str:
    lines = [f"Part catalog row {index}"]
    lines.append(f"  Part number: {row.part_number_display}")
    if row.nomenclature:
        lines.append(f"  Nomenclature: {row.nomenclature}")
    if row.item_number:
        lines.append(f"  Item: {row.item_number}")
    if row.quantity:
        lines.append(f"  Qty: {row.quantity}")
    if row.figure_number:
        lines.append(f"  Figure: {row.figure_number}")
    lines.append(f"  Manual ID: {row.manual_id}")
    if row.ata_code:
        lines.append(f"  ATA: {row.ata_code}")
    if row.page_sequence is not None:
        lines.append(f"  Page sequence: {row.page_sequence}")
    if row.page_label:
        lines.append(f"  Page label: {row.page_label}")
    if row.confidence:
        lines.append(f"  Confidence: {row.confidence}")
    if row.evidence_text:
        lines.append(f"  Evidence: {collapse_ws(row.evidence_text)}")
    if row.source_tiff_path:
        lines.append(f"  TIFF: {row.source_tiff_path}")
    return "\n".join(lines)


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def part_catalog_summary_counts(db_path: Path | str) -> dict[str, int | str]:
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        out: dict[str, int | str] = {"db_path": str(db_path)}
        out["part_mentions"] = conn.execute("SELECT count(*) FROM part_mentions").fetchone()[0] if table_exists(conn, "part_mentions") else 0
        out["part_catalog"] = conn.execute("SELECT count(*) FROM part_catalog").fetchone()[0] if table_exists(conn, "part_catalog") else 0
        if table_exists(conn, "part_catalog"):
            out["high_confidence"] = conn.execute("SELECT count(*) FROM part_catalog WHERE confidence = 'high'").fetchone()[0]
            out["medium_confidence"] = conn.execute("SELECT count(*) FROM part_catalog WHERE confidence = 'medium'").fetchone()[0]
            out["low_confidence"] = conn.execute("SELECT count(*) FROM part_catalog WHERE confidence = 'low'").fetchone()[0]
        return out
    finally:
        conn.close()
