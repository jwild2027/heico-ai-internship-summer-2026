"""Export logical organization artifacts for the TIFF backend.

This module turns the SQLite/search backend into UI/API-friendly logical
organization JSON files. It does not move, rename, OCR, or mutate source files.
The raw ResCarta/TIFF file layout can stay messy; these artifacts provide clean
views over the indexed metadata.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

from tiff.document_organization_audit import (
    _canonical_part_from_mention as _audit_canonical_part_from_mention,
    _load_canonical_part_lookup as _audit_load_canonical_part_lookup,
    _load_part_names as _audit_load_part_names,
)

DEFAULT_DB_PATH = "local_data/db/tiff_search.db"
DEFAULT_OUTPUT_DIR = "local_data/organization/export"


@dataclass(frozen=True)
class OrganizationExportSummary:
    db_path: str
    output_dir: str
    source_table: str = ""
    source_table_exists: bool = False
    page_count: int = 0
    manual_count: int = 0
    ata_group_count: int = 0
    pages_with_ata: int = 0
    pages_without_ata: int = 0
    source_link_count: int = 0
    pages_with_source_links: int = 0
    part_count: int = 0
    part_mention_count: int = 0
    pages_with_parts: int = 0
    part_tree_source: str = ""
    raw_part_count: int = 0
    raw_part_mention_count: int = 0
    raw_mentions_excluded_from_part_tree: int = 0
    compound_part_references_suppressed: int = 0
    empty_ocr_page_count: int = 0
    files_written: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        return self.source_table_exists and self.page_count > 0 and self.manual_count > 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ready"] = self.ready
        return data


@dataclass(frozen=True)
class OrganizationExport:
    summary: OrganizationExportSummary
    manual_tree: dict[str, Any]
    ata_tree: dict[str, Any]
    part_tree: dict[str, Any]
    page_index: dict[str, Any]


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


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}


def _count(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> int:
    row = conn.execute(sql, tuple(params)).fetchone()
    return int(row[0] if row else 0)


def _row_get(row: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return default


def _select_all(conn: sqlite3.Connection, table_name: str, *, order_cols: Iterable[str] = ()) -> list[dict[str, Any]]:
    cols = _columns(conn, table_name)
    order = [col for col in order_cols if col in cols]
    sql = f"SELECT * FROM {table_name}"
    if order:
        sql += " ORDER BY " + ", ".join(order)
    rows = conn.execute(sql).fetchall()
    return [dict(row) for row in rows]


def _best_page_table(conn: sqlite3.Connection) -> str | None:
    if _table_exists(conn, "source_links") and _count(conn, "SELECT COUNT(*) FROM source_links") > 0:
        return "source_links"
    if _table_exists(conn, "pages") and _count(conn, "SELECT COUNT(*) FROM pages") > 0:
        return "pages"
    return None


def _page_id(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "page_id", "id", "source_page_id"))


def _manual_id(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "manual_id", "document_id", "object_id", "manual", default="unknown_manual")) or "unknown_manual"


def _publication(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "publication_number", "manual_title", "title", "document_title", default=""))


def _ata(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "ata_code", "ata", "section", default=""))


def _page_label(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "page_label", "page_number", "page", default=""))


def _page_sequence(row: Mapping[str, Any]) -> int:
    value = _row_get(row, "page_sequence", "sequence", "sort_order", default=0)
    try:
        return int(value)
    except Exception:
        return 0


def _tiff_path(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "tiff_path", "image_path", "source_image_path", default=""))


def _ocr_path(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "ocr_text_path", "ocr_path", "text_path", default=""))


def _source_url(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "source_url", "rescarta_url", "url", default=""))


def _rescarta_url(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "rescarta_url", "source_url", "url", default=""))


def _is_empty_file(path_text: str) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    try:
        return path.exists() and path.is_file() and path.stat().st_size == 0
    except OSError:
        return False


def _part_number(row: Mapping[str, Any]) -> str:
    return _clean(
        _row_get(
            row,
            "part_number_display",
            "part_number",
            "canonical_part_number",
            "part",
            "candidate",
            "matched_part_number",
            "part_number_normalized",
            "normalized_part_number",
            default="",
        )
    )


def _part_number_keys(row: Mapping[str, Any]) -> tuple[str, ...]:
    keys: list[str] = []
    for key in (
        "part_number_display",
        "part_number",
        "canonical_part_number",
        "matched_part_number",
        "part",
        "candidate",
        "part_number_normalized",
        "normalized_part_number",
    ):
        value = _clean(row.get(key) if key in row else "")
        if value and value not in keys:
            keys.append(value)
    return tuple(keys)


def _part_nomenclature(row: Mapping[str, Any]) -> str:
    return _clean(
        _row_get(
            row,
            "nomenclature",
            "canonical_nomenclature",
            "clean_nomenclature",
            "part_nomenclature",
            "part_name",
            "description",
            default="",
        )
    )


def _load_part_names(conn: sqlite3.Connection) -> dict[str, str]:
    names: dict[str, str] = {}
    for table_name in ("part_catalog_clean", "part_catalog_mentions_clean", "part_catalog"):
        if not _table_exists(conn, table_name):
            continue
        for row in _select_all(conn, table_name):
            name = _part_nomenclature(row)
            if not name:
                continue
            for part_key in _part_number_keys(row):
                names.setdefault(part_key, name)
    return names


def _load_part_mentions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "part_mentions"):
        return []
    return _select_all(conn, "part_mentions", order_cols=("page_id", "part_number", "part_number_display"))


def _page_record(row: Mapping[str, Any], page_parts: Mapping[str, set[str]]) -> dict[str, Any]:
    pid = _page_id(row)
    manual_id = _manual_id(row)
    publication_number = _publication(row)
    ata_code = _ata(row)
    # UI/API-friendly aliases are intentionally duplicated beside the canonical
    # field names.  The canonical names keep backend compatibility; the short
    # aliases make exported JSON easier for a future frontend to consume.
    manual_label = publication_number or manual_id
    return {
        "page_id": pid,
        "manual_id": manual_id,
        "manual": manual_label,
        "publication_number": publication_number,
        "ata_code": ata_code,
        "ata": ata_code,
        "page_label": _page_label(row),
        "page_sequence": _page_sequence(row),
        "part_numbers": sorted(page_parts.get(pid, set())),
        "tiff_path": _tiff_path(row),
        "ocr_text_path": _ocr_path(row),
        "source_url": _source_url(row),
        "rescarta_url": _rescarta_url(row),
        "empty_ocr": _is_empty_file(_ocr_path(row)),
    }


def build_document_organization_export(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> OrganizationExport:
    """Build logical organization trees from the current backend database.

    The returned data is read-only. Use ``write_document_organization_export`` to
    write JSON files for UI/API prototyping.
    """

    db_path = Path(db_path)
    output_dir = Path(output_dir)
    warnings: list[str] = []

    if not db_path.exists():
        summary = OrganizationExportSummary(
            db_path=str(db_path),
            output_dir=str(output_dir),
            warnings=(f"database does not exist: {db_path}",),
        )
        empty = {"manuals": [], "ata_groups": [], "parts": [], "pages": []}
        return OrganizationExport(summary, {"manuals": []}, {"ata_groups": []}, {"parts": []}, {"pages": []})

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        page_table = _best_page_table(conn)
        if page_table is None:
            summary = OrganizationExportSummary(
                db_path=str(db_path),
                output_dir=str(output_dir),
                warnings=("no source_links/pages rows found; run the backend pipeline first",),
            )
            return OrganizationExport(summary, {"manuals": []}, {"ata_groups": []}, {"parts": []}, {"pages": []})

        page_rows = _select_all(conn, page_table, order_cols=("manual_id", "ata_code", "page_sequence", "page_label", "page_id"))
        source_link_count = _count(conn, "SELECT COUNT(*) FROM source_links") if _table_exists(conn, "source_links") else 0
        mention_rows = _load_part_mentions(conn)
        canonical_lookup, clean_catalog_available = _audit_load_canonical_part_lookup(conn)
        part_names = _audit_load_part_names(conn) or _load_part_names(conn)

    use_canonical_allowlist = clean_catalog_available and bool(canonical_lookup)

    page_by_id: dict[str, dict[str, Any]] = {}
    page_parts: dict[str, set[str]] = defaultdict(set)
    part_pages: dict[str, set[str]] = defaultdict(set)
    part_mentions: Counter[str] = Counter()
    part_display_names: dict[str, str] = {}
    raw_part_mentions: Counter[str] = Counter()
    raw_mentions_excluded = 0
    compound_references_suppressed = 0

    for index, row in enumerate(page_rows):
        pid = _page_id(row) or f"row_{index}"
        normalized_row = dict(row)
        if not _page_id(normalized_row):
            normalized_row["page_id"] = pid
        page_by_id[pid] = normalized_row

    for row in mention_rows:
        raw_part = _part_number(row)
        if raw_part:
            raw_part_mentions[raw_part] += 1

        canonical = _audit_canonical_part_from_mention(
            row,
            canonical_lookup,
            part_names,
            use_canonical_allowlist=use_canonical_allowlist,
        )
        if canonical is None:
            continue

        part, name, reason = canonical
        if reason == "compound":
            compound_references_suppressed += 1
            raw_mentions_excluded += 1
            continue
        if reason == "not_in_clean_catalog":
            raw_mentions_excluded += 1
            continue

        pid = _clean(_row_get(row, "page_id", "source_page_id", default=""))
        if not part:
            continue
        part_mentions[part] += 1
        if name:
            part_display_names.setdefault(part, name)
        if pid and pid in page_by_id:
            page_parts[pid].add(part)
            part_pages[part].add(pid)

    page_records = [_page_record(row, page_parts) for row in page_by_id.values()]
    page_records.sort(key=lambda p: (p["manual_id"], p["ata_code"], p["page_sequence"], p["page_label"], p["page_id"]))

    manuals: dict[str, dict[str, Any]] = {}
    ata_groups: dict[tuple[str, str], dict[str, Any]] = {}
    for page in page_records:
        manual_id = page["manual_id"] or "unknown_manual"
        ata_code = page["ata_code"] or "unknown_ata"
        manual = manuals.setdefault(
            manual_id,
            {
                "manual_id": manual_id,
                "manual": page.get("manual") or page["publication_number"] or manual_id,
                "publication_number": page["publication_number"],
                "title": page.get("manual") or page["publication_number"] or manual_id,
                "page_count": 0,
                "part_mention_count": 0,
                "empty_ocr_page_count": 0,
                "ata_groups": [],
            },
        )
        manual["page_count"] += 1
        manual["part_mention_count"] += len(page["part_numbers"])
        if page["empty_ocr"]:
            manual["empty_ocr_page_count"] += 1

        key = (manual_id, ata_code)
        ata = ata_groups.setdefault(
            key,
            {
                "manual_id": manual_id,
                "manual": page.get("manual") or page["publication_number"] or manual_id,
                "publication_number": page["publication_number"],
                "ata_code": ata_code,
                "ata": ata_code,
                "page_count": 0,
                "part_mention_count": 0,
                "distinct_part_count": 0,
                "empty_ocr_page_count": 0,
                "page_ids": [],
                "pages": [],
            },
        )
        ata["page_count"] += 1
        ata["part_mention_count"] += len(page["part_numbers"])
        if page["empty_ocr"]:
            ata["empty_ocr_page_count"] += 1
        ata["page_ids"].append(page["page_id"])
        ata["pages"].append(page)

    for ata in ata_groups.values():
        distinct_parts: set[str] = set()
        for page in ata["pages"]:
            distinct_parts.update(page["part_numbers"])
        ata["distinct_part_count"] = len(distinct_parts)

    for manual in manuals.values():
        manual_ata = [group for group in ata_groups.values() if group["manual_id"] == manual["manual_id"]]
        manual_ata.sort(key=lambda group: (group["ata_code"], group["page_count"]))
        manual["ata_groups"] = manual_ata

    manual_list = sorted(manuals.values(), key=lambda item: (item["publication_number"] or item["manual_id"]))
    ata_list = sorted(ata_groups.values(), key=lambda item: (item["manual_id"], item["ata_code"]))

    part_list: list[dict[str, Any]] = []
    for part, pids in part_pages.items():
        part_page_records = [page for page in page_records if page["page_id"] in pids]
        ata_codes = sorted({page["ata_code"] for page in part_page_records if page["ata_code"]})
        manual_ids = sorted({page["manual_id"] for page in part_page_records if page["manual_id"]})
        part_list.append(
            {
                "part_number": part,
                "nomenclature": part_display_names.get(part) or part_names.get(part, ""),
                "mention_count": int(part_mentions[part]),
                "page_count": len(pids),
                "ata_codes": ata_codes,
                "manual_ids": manual_ids,
                "pages": part_page_records,
            }
        )
    part_list.sort(key=lambda item: (-int(item["page_count"]), -int(item["mention_count"]), str(item["part_number"])))

    pages_with_ata = len([p for p in page_records if p["ata_code"]])
    pages_with_source_links = len([p for p in page_records if p["source_url"] or p["rescarta_url"] or p["tiff_path"] or p["ocr_text_path"]])
    empty_ocr_count = len([p for p in page_records if p["empty_ocr"]])
    pages_with_parts = len([p for p in page_records if p["part_numbers"]])

    if not page_records:
        warnings.append("no pages were available for organization export")
    if page_records and not part_list:
        warnings.append("no part tree entries were exported; check the part_mentions table")
    if empty_ocr_count:
        warnings.append(f"{empty_ocr_count} pages have empty OCR text and remain visible in the organization export")
    if raw_mentions_excluded:
        warnings.append(
            f"{raw_mentions_excluded} raw part mentions were excluded from the exported logical part tree because they are compound references or not in the clean catalog"
        )
    if len(part_list) != len(part_pages):
        warnings.append("part tree count did not match part-page mapping count")

    summary = OrganizationExportSummary(
        db_path=str(db_path),
        output_dir=str(output_dir),
        source_table=page_table,
        source_table_exists=True,
        page_count=len(page_records),
        manual_count=len(manual_list),
        ata_group_count=len(ata_list),
        pages_with_ata=pages_with_ata,
        pages_without_ata=max(0, len(page_records) - pages_with_ata),
        source_link_count=source_link_count,
        pages_with_source_links=pages_with_source_links,
        part_count=len(part_list),
        part_mention_count=sum(part_mentions.values()),
        pages_with_parts=pages_with_parts,
        part_tree_source="clean_catalog_allowlist" if use_canonical_allowlist else "raw_part_mentions",
        raw_part_count=len(raw_part_mentions),
        raw_part_mention_count=sum(raw_part_mentions.values()),
        raw_mentions_excluded_from_part_tree=raw_mentions_excluded,
        compound_part_references_suppressed=compound_references_suppressed,
        empty_ocr_page_count=empty_ocr_count,
        warnings=tuple(warnings),
    )

    return OrganizationExport(
        summary=summary,
        manual_tree={"manuals": manual_list},
        ata_tree={"ata_groups": ata_list},
        part_tree={"parts": part_list},
        page_index={"pages": page_records},
    )


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_document_organization_export(export: OrganizationExport, output_dir: str | Path | None = None) -> OrganizationExportSummary:
    output = Path(output_dir or export.summary.output_dir)
    tree_files = [
        _write_json(output / "manual_ata_tree.json", export.manual_tree),
        _write_json(output / "ata_tree.json", export.ata_tree),
        _write_json(output / "part_tree.json", export.part_tree),
        _write_json(output / "page_index.json", export.page_index),
    ]
    summary_file = output / "organization_summary.json"
    files = [*tree_files, summary_file]

    # Keep the on-disk summary consistent with the returned summary and with the
    # pipeline manifest. The previous implementation wrote organization_summary
    # before adding organization_summary.json to files_written, so the command
    # printed five files while the quality gate saw only four from the JSON file.
    summary_data = export.summary.to_dict()
    summary_data["files_written"] = [str(path) for path in files]
    _write_json(summary_file, summary_data)

    data = asdict(export.summary)
    data["files_written"] = tuple(str(path) for path in files)
    return OrganizationExportSummary(**data)


def format_document_organization_export(summary: OrganizationExportSummary) -> str:
    lines: list[str] = []
    lines.append("Document organization export")
    lines.append(f"  Status: {'OK' if summary.ready else 'NEEDS ATTENTION'}")
    lines.append(f"  DB: {summary.db_path}")
    lines.append(f"  Output dir: {summary.output_dir}")
    lines.append(f"  Source table: {summary.source_table or '-'}")
    lines.append("")
    lines.append("Logical organization counts:")
    lines.append(f"  Manuals: {summary.manual_count}")
    lines.append(f"  Pages: {summary.page_count}")
    lines.append(f"  Source links: {summary.source_link_count}")
    lines.append(f"  Pages with source links: {summary.pages_with_source_links}")
    lines.append(f"  ATA groups: {summary.ata_group_count}")
    lines.append(f"  Pages with ATA: {summary.pages_with_ata}")
    lines.append(f"  Pages without ATA: {summary.pages_without_ata}")
    lines.append(f"  Distinct parts: {summary.part_count}")
    lines.append(f"  Part mentions: {summary.part_mention_count}")
    lines.append(f"  Pages with parts: {summary.pages_with_parts}")
    lines.append(f"  Part tree source: {summary.part_tree_source or '-'}")
    if summary.raw_part_mention_count:
        lines.append(f"  Raw distinct parts seen: {summary.raw_part_count}")
        lines.append(f"  Raw part mentions seen: {summary.raw_part_mention_count}")
        lines.append(f"  Raw mentions excluded from part tree: {summary.raw_mentions_excluded_from_part_tree}")
        lines.append(f"  Compound part references suppressed: {summary.compound_part_references_suppressed}")
    lines.append(f"  Empty OCR pages: {summary.empty_ocr_page_count}")
    if summary.files_written:
        lines.append("")
        lines.append("Files written:")
        for path in summary.files_written:
            lines.append(f"  {path}")
    if summary.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in summary.warnings:
            lines.append(f"  - {warning}")
    return "\n".join(lines)
