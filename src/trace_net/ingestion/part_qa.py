"""QA reports for the extracted TIFF part catalog.

The QA layer is intentionally conservative: it should highlight rows that need
review, but it should not flood reports with obvious non-part references such as
ATA figure numbers (for example 25-21-00-46) or OCR fragments such as T.P,
IGURE, and SHEET. Those values remain searchable in OCR, but they are not useful
as part-catalog QA defects.
"""

from __future__ import annotations

import csv
import html
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tiff.part_filters import (
    canonicalize_nomenclature_for_comparison,
    is_bad_nomenclature,
    is_catalog_part_candidate,
    is_good_qa_nomenclature,
    is_obvious_reference_number,
    is_reference_like_part_number,
)


@dataclass(frozen=True)
class QARecord:
    report: str
    key: str
    count: int = 0
    details: str = ""
    severity: str = "review"
    part_number: str = ""
    nomenclature: str = ""
    ata_code: str = ""
    page_label: str = ""
    tiff_path: str = ""
    ocr_text_path: str = ""


CSV_FIELDS = [
    "report",
    "severity",
    "key",
    "count",
    "part_number",
    "nomenclature",
    "ata_code",
    "page_label",
    "details",
    "tiff_path",
    "ocr_text_path",
]


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _display_part(row: sqlite3.Row) -> str:
    return str(row["part_number_display"] or row["part_number_normalized"] or "").strip()


def _norm_part(row: sqlite3.Row) -> str:
    return str(row["part_number_normalized"] or row["part_number_display"] or "").strip()


def _good_part(display: str | None, norm: str | None = None) -> bool:
    value = display or norm or ""
    if not value:
        return False
    if is_reference_like_part_number(value) or is_obvious_reference_number(value):
        return False
    return is_catalog_part_candidate(value)


def _good_name(name: str | None) -> bool:
    return is_good_qa_nomenclature(name)


def _join_unique(values: Iterable[Any], limit: int = 20, sep: str = ",") -> str:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return sep.join(out)


def _fetch_catalog_name_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if table_exists(conn, "part_catalog_mentions_clean"):
        return conn.execute(
            """
            SELECT
                part_number_display,
                part_number_normalized,
                clean_nomenclature AS nomenclature,
                COUNT(*) AS row_count
            FROM part_catalog_mentions_clean
            WHERE clean_nomenclature IS NOT NULL AND TRIM(clean_nomenclature) <> ''
            GROUP BY part_number_normalized, UPPER(TRIM(clean_nomenclature))
            ORDER BY part_number_normalized, row_count DESC
            """
        ).fetchall()
    if table_exists(conn, "part_catalog"):
        return conn.execute(
            """
            SELECT
                part_number_display,
                part_number_normalized,
                nomenclature,
                COUNT(*) AS row_count
            FROM part_catalog
            WHERE nomenclature IS NOT NULL AND TRIM(nomenclature) <> ''
            GROUP BY part_number_normalized, UPPER(TRIM(nomenclature))
            ORDER BY part_number_normalized, row_count DESC
            """
        ).fetchall()
    return []


def report_part_nomenclature_conflicts(conn: sqlite3.Connection, *, limit: int = 100) -> list[QARecord]:
    """Find likely real part numbers with genuinely different clean names."""

    rows = _fetch_catalog_name_rows(conn)
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        display = _display_part(row)
        norm = _norm_part(row)
        if not _good_part(display, norm):
            continue
        raw_name = row["nomenclature"] or ""
        if not _good_name(raw_name):
            continue
        name = canonicalize_nomenclature_for_comparison(raw_name)
        if not _good_name(name):
            continue
        bucket = grouped.setdefault(norm, {"display": display, "variants": {}, "rows": 0})
        bucket["variants"][name] = bucket["variants"].get(name, 0) + int(row["row_count"] or 0)
        bucket["rows"] += int(row["row_count"] or 0)

    records: list[QARecord] = []
    for norm, data in grouped.items():
        variants = sorted(data["variants"], key=lambda v: (-data["variants"][v], v))
        if len(variants) <= 1:
            continue
        base = variants[0]
        # Same name with OCR tails is low severity and suppressed from the main review list.
        if all(v == base or v.startswith(base) or base.startswith(v) for v in variants):
            continue
        records.append(
            QARecord(
                report="part_nomenclature_conflicts",
                key=norm,
                count=len(variants),
                part_number=data["display"],
                details=", ".join(variants),
                severity="review",
            )
        )
    records.sort(key=lambda r: (-r.count, r.key))
    return records[: int(limit)]


def report_nomenclature_groups(conn: sqlite3.Connection, *, limit: int = 100) -> list[QARecord]:
    """Find useful clean nomenclatures that map to one or more real part numbers."""

    if table_exists(conn, "part_catalog_clean"):
        rows = conn.execute(
            """
            SELECT
                canonical_nomenclature AS nomenclature,
                part_number_display,
                part_number_normalized
            FROM part_catalog_clean
            WHERE canonical_nomenclature IS NOT NULL AND TRIM(canonical_nomenclature) <> ''
            ORDER BY canonical_nomenclature, part_number_display
            """
        ).fetchall()
    elif table_exists(conn, "part_catalog"):
        rows = conn.execute(
            """
            SELECT nomenclature, part_number_display, part_number_normalized
            FROM part_catalog
            WHERE nomenclature IS NOT NULL AND TRIM(nomenclature) <> ''
            ORDER BY nomenclature, part_number_display
            """
        ).fetchall()
    else:
        return []

    grouped: dict[str, set[str]] = {}
    display_name: dict[str, str] = {}
    for row in rows:
        part = _display_part(row)
        norm = _norm_part(row)
        if not _good_part(part, norm):
            continue
        name = canonicalize_nomenclature_for_comparison(row["nomenclature"] or "")
        if not _good_name(name):
            continue
        key = name.upper()
        display_name.setdefault(key, name)
        grouped.setdefault(key, set()).add(part)

    records: list[QARecord] = []
    for key, parts in grouped.items():
        name = display_name[key]
        count = len(parts)
        records.append(
            QARecord(
                report="nomenclature_groups",
                key=name,
                count=count,
                nomenclature=name,
                details=",".join(sorted(parts)),
                severity="info" if count > 1 else "ok",
            )
        )
    records.sort(key=lambda r: (-r.count, r.nomenclature))
    return records[: int(limit)]


def _missing_nomenclature_rows(conn: sqlite3.Connection, *, limit: int) -> list[sqlite3.Row]:
    if table_exists(conn, "part_catalog_clean"):
        return conn.execute(
            """
            SELECT
                pm.part_number_display,
                pm.part_number_normalized,
                COUNT(*) AS mention_count,
                GROUP_CONCAT(DISTINCT COALESCE(p.page_label, p.page_sequence)) AS pages
            FROM part_mentions pm
            LEFT JOIN part_catalog_clean pcc ON pcc.part_number_normalized = pm.part_number_normalized
            LEFT JOIN pages p ON p.page_id = pm.page_id
            WHERE pcc.part_number_normalized IS NULL
            GROUP BY pm.part_number_normalized
            ORDER BY mention_count DESC, pm.part_number_normalized
            LIMIT ?
            """,
            (int(limit) * 20,),
        ).fetchall()
    if table_exists(conn, "part_catalog"):
        return conn.execute(
            """
            SELECT
                pm.part_number_display,
                pm.part_number_normalized,
                COUNT(*) AS mention_count,
                GROUP_CONCAT(DISTINCT COALESCE(p.page_label, p.page_sequence)) AS pages
            FROM part_mentions pm
            LEFT JOIN part_catalog pc
              ON pc.part_number_normalized = pm.part_number_normalized
             AND pc.nomenclature IS NOT NULL
             AND TRIM(pc.nomenclature) <> ''
            LEFT JOIN pages p ON p.page_id = pm.page_id
            WHERE pc.part_number_normalized IS NULL
            GROUP BY pm.part_number_normalized
            ORDER BY mention_count DESC, pm.part_number_normalized
            LIMIT ?
            """,
            (int(limit) * 20,),
        ).fetchall()
    if table_exists(conn, "part_mentions"):
        return conn.execute(
            """
            SELECT part_number_display, part_number_normalized, COUNT(*) AS mention_count, '' AS pages
            FROM part_mentions
            GROUP BY part_number_normalized
            ORDER BY mention_count DESC, part_number_normalized
            LIMIT ?
            """,
            (int(limit) * 20,),
        ).fetchall()
    return []


def report_parts_missing_nomenclature(conn: sqlite3.Connection, *, limit: int = 100) -> list[QARecord]:
    """Find real-looking detected part numbers that do not have a clean catalog name."""

    if not table_exists(conn, "part_mentions"):
        return []
    records: list[QARecord] = []
    for row in _missing_nomenclature_rows(conn, limit=limit):
        display = _display_part(row)
        norm = _norm_part(row)
        if not _good_part(display, norm):
            continue
        records.append(
            QARecord(
                report="parts_missing_nomenclature",
                key=norm,
                count=int(row["mention_count"] or 0),
                part_number=display,
                details=f"Mention pages: {row['pages'] or '-'}",
                severity="review",
            )
        )
        if len(records) >= int(limit):
            break
    return records


def report_reference_like_mentions(conn: sqlite3.Connection, *, limit: int = 100) -> list[QARecord]:
    """Info report for references suppressed from missing-nomenclature QA."""

    if not table_exists(conn, "part_mentions"):
        return []
    records: list[QARecord] = []
    for row in _missing_nomenclature_rows(conn, limit=limit):
        display = _display_part(row)
        norm = _norm_part(row)
        if _good_part(display, norm):
            continue
        records.append(
            QARecord(
                report="reference_like_mentions",
                key=norm,
                count=int(row["mention_count"] or 0),
                part_number=display,
                details=f"Suppressed from missing-nomenclature QA; mention pages: {row['pages'] or '-'}",
                severity="info",
            )
        )
        if len(records) >= int(limit):
            break
    return records


def report_suspicious_part_ata(conn: sqlite3.Connection, *, limit: int = 100) -> list[QARecord]:
    """Flag real part mentions whose ATA differs from the clean catalog source ATA."""

    if not (table_exists(conn, "part_mentions") and table_exists(conn, "part_catalog_clean")):
        return []
    rows = conn.execute(
        """
        SELECT
            pm.part_number_display,
            pm.part_number_normalized,
            pcc.canonical_nomenclature,
            pcc.best_ata_code AS catalog_ata,
            pm.ata_code AS mention_ata,
            COUNT(*) AS mention_count,
            GROUP_CONCAT(DISTINCT COALESCE(p.page_label, p.page_sequence)) AS pages
        FROM part_mentions pm
        JOIN part_catalog_clean pcc ON pcc.part_number_normalized = pm.part_number_normalized
        LEFT JOIN pages p ON p.page_id = pm.page_id
        WHERE COALESCE(pm.ata_code, '') <> ''
          AND COALESCE(pcc.best_ata_code, '') <> ''
          AND pm.ata_code <> pcc.best_ata_code
        GROUP BY pm.part_number_normalized, pm.ata_code, pcc.best_ata_code
        ORDER BY mention_count DESC, pm.part_number_normalized
        LIMIT ?
        """,
        (int(limit) * 3,),
    ).fetchall()
    records: list[QARecord] = []
    for row in rows:
        display = _display_part(row)
        norm = _norm_part(row)
        if not _good_part(display, norm):
            continue
        name = canonicalize_nomenclature_for_comparison(row["canonical_nomenclature"] or "")
        if not _good_name(name):
            continue
        records.append(
            QARecord(
                report="suspicious_part_ata",
                key=f"{norm}:{row['mention_ata']}",
                count=int(row["mention_count"] or 0),
                part_number=display,
                nomenclature=name,
                ata_code=row["mention_ata"] or "",
                details=f"Catalog ATA: {row['catalog_ata']}; mention pages: {row['pages'] or '-'}",
                severity="review",
            )
        )
        if len(records) >= int(limit):
            break
    return records


def run_all_part_qa_reports(
    conn: sqlite3.Connection,
    *,
    limit: int = 100,
    include_info_noise: bool = False,
) -> list[QARecord]:
    records: list[QARecord] = []
    records.extend(report_part_nomenclature_conflicts(conn, limit=limit))
    records.extend(report_nomenclature_groups(conn, limit=limit))
    records.extend(report_parts_missing_nomenclature(conn, limit=limit))
    records.extend(report_suspicious_part_ata(conn, limit=limit))
    if include_info_noise:
        records.extend(report_reference_like_mentions(conn, limit=limit))
    return records


def qa_record_to_dict(record: QARecord) -> dict[str, Any]:
    return {field: getattr(record, field) for field in CSV_FIELDS}


def write_qa_csv(records: Iterable[QARecord], path: str | Path) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(qa_record_to_dict(record))
    return out_path


def write_qa_json(records: Iterable[QARecord], path: str | Path) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([qa_record_to_dict(r) for r in records], indent=2), encoding="utf-8")
    return out_path


def write_qa_html(records: Iterable[QARecord], path: str | Path, *, title: str = "TIFF Part Catalog QA") -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        rows.append(
            f"<tr class='{html.escape(record.severity)}'>"
            f"<td>{html.escape(record.report)}</td>"
            f"<td>{html.escape(record.severity)}</td>"
            f"<td>{html.escape(record.key)}</td>"
            f"<td>{record.count}</td>"
            f"<td>{html.escape(record.part_number)}</td>"
            f"<td>{html.escape(record.nomenclature)}</td>"
            f"<td>{html.escape(record.ata_code)}</td>"
            f"<td>{html.escape(record.details)}</td>"
            "</tr>"
        )
    doc = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px; vertical-align: top; }}
th {{ background: #f3f3f3; }}
.review {{ background: #fff7e6; }}
.info {{ background: #f7fbff; }}
.ok {{ background: #f8fff8; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p>This filtered report suppresses obvious ATA/page/manual references and OCR-only nomenclature noise.</p>
<table>
<thead><tr><th>Report</th><th>Severity</th><th>Key</th><th>Count</th><th>Part</th><th>Nomenclature</th><th>ATA</th><th>Details</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</body></html>
"""
    out_path.write_text(doc, encoding="utf-8")
    return out_path
