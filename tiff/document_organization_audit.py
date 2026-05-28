"""Read-only logical organization audit for the TIFF backend.

The backend should not depend on messy raw folder structure being clean. This
module builds a lightweight logical tree from the SQLite/source-link data so we
can inspect how pages group by manual, ATA, and part number before scaling to a
larger document batch.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_DB_PATH = "local_data/db/tiff_search.db"


@dataclass(frozen=True)
class AtaTreeRow:
    manual_id: str
    publication_number: str
    ata_code: str
    page_count: int
    part_mention_count: int
    source_link_count: int
    empty_ocr_pages: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PartTreeRow:
    part_number: str
    nomenclature: str
    page_count: int
    mention_count: int
    ata_codes: tuple[str, ...] = field(default_factory=tuple)
    manuals: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DocumentOrganizationAuditSummary:
    db_path: str
    source_table: str = ""
    source_table_exists: bool = False
    pages_total: int = 0
    source_links_total: int = 0
    manuals_total: int = 0
    ata_groups_total: int = 0
    pages_with_ata: int = 0
    pages_without_ata: int = 0
    pages_with_source_links: int = 0
    part_mentions_total: int = 0
    distinct_parts_total: int = 0
    pages_with_parts: int = 0
    empty_ocr_pages: int = 0
    part_tree_source: str = ""
    raw_part_mentions_total: int = 0
    raw_distinct_parts_total: int = 0
    raw_mentions_excluded_from_part_tree: int = 0
    compound_part_references_suppressed: int = 0
    top_ata_groups: tuple[AtaTreeRow, ...] = field(default_factory=tuple)
    top_parts: tuple[PartTreeRow, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def logical_tree_ready(self) -> bool:
        return self.source_table_exists and self.pages_total > 0 and self.manuals_total > 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["logical_tree_ready"] = self.logical_tree_ready
        data["top_ata_groups"] = [row.to_dict() for row in self.top_ata_groups]
        data["top_parts"] = [row.to_dict() for row in self.top_parts]
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


def _ocr_path(row: Mapping[str, Any]) -> str:
    return _clean(_row_get(row, "ocr_text_path", "ocr_path", "text_path", default=""))


def _part_number(row: Mapping[str, Any]) -> str:
    """Return the human/display part number from any known part table schema.

    The main search-index schema stores mentions as ``part_number_display`` and
    ``part_number_normalized``. Earlier/local test tables used simpler names
    such as ``part_number``. Prefer display values so the logical tree is human
    readable, then fall back to normalized keys when needed.
    """
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
    """Return all usable display/normalized keys for joining part tables."""
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


def _is_empty_file(path_text: str) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    try:
        return path.exists() and path.is_file() and path.stat().st_size == 0
    except OSError:
        return False


def _is_compound_part_reference(part: str) -> bool:
    """Return True for slash-separated part groups/ranges.

    The logical organization tree should show canonical single-part entries.
    Raw OCR/catalog data can contain grouped references such as
    ``120-41824-007/507`` or ``120272/120273``. Those are useful as raw
    evidence, but they should not become top-level canonical part nodes.
    """
    return "/" in _clean(part)


def _load_canonical_part_lookup(conn: sqlite3.Connection) -> tuple[dict[str, tuple[str, str]], bool]:
    """Load canonical/clean part keys.

    Returns a lookup mapping every known display/normalized key to
    ``(display_part_number, nomenclature)`` plus a boolean indicating whether a
    clean canonical catalog was available. The audit uses this as an allow-list
    when possible so the logical part tree is not dominated by raw OCR noise.
    """
    lookup: dict[str, tuple[str, str]] = {}
    clean_available = False
    for table_name in ("part_catalog_clean", "part_catalog_mentions_clean"):
        if not _table_exists(conn, table_name):
            continue
        rows = _select_all(conn, table_name)
        if rows:
            clean_available = True
        for row in rows:
            display = _part_number(row)
            if not display:
                continue
            if _is_compound_part_reference(display):
                continue
            name = _part_nomenclature(row)
            keys = _part_number_keys(row) or (display,)
            for part_key in keys:
                if not part_key or _is_compound_part_reference(part_key):
                    continue
                lookup.setdefault(part_key, (display, name))
    return lookup, clean_available


def _load_part_names(conn: sqlite3.Connection) -> dict[str, str]:
    """Load fallback nomenclature keyed by both display and normalized values."""
    names: dict[str, str] = {}
    for table_name in ("part_catalog_clean", "part_catalog_mentions_clean", "part_catalog"):
        if not _table_exists(conn, table_name):
            continue
        rows = _select_all(conn, table_name)
        for row in rows:
            name = _part_nomenclature(row)
            if not name:
                continue
            for part_key in _part_number_keys(row):
                names.setdefault(part_key, name)
    return names


def _load_part_mentions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "part_mentions"):
        return []
    return _select_all(conn, "part_mentions", order_cols=("part_number", "part_number_display", "page_id"))


def _canonical_part_from_mention(
    row: Mapping[str, Any],
    canonical_lookup: Mapping[str, tuple[str, str]],
    fallback_names: Mapping[str, str],
    *,
    use_canonical_allowlist: bool,
) -> tuple[str, str, str] | None:
    """Return ``(display_part, nomenclature, reason)`` for a raw mention.

    ``reason`` is ``ok``, ``compound``, or ``not_in_clean_catalog``. Returning
    ``None`` means there was no usable part value at all.
    """
    display = _part_number(row)
    keys = _part_number_keys(row) or ((display,) if display else ())
    if not display and not keys:
        return None
    if display and _is_compound_part_reference(display):
        return (display, "", "compound")
    for key in keys:
        if _is_compound_part_reference(key):
            return (key, "", "compound")
    if use_canonical_allowlist:
        for key in keys:
            hit = canonical_lookup.get(key)
            if hit:
                return (hit[0], hit[1], "ok")
        return (display or next(iter(keys), ""), "", "not_in_clean_catalog")
    name = fallback_names.get(display, "")
    for key in keys:
        if not name:
            name = fallback_names.get(key, "")
    return (display or next(iter(keys), ""), name, "ok")


def audit_document_organization(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    top_ata_limit: int = 20,
    top_part_limit: int = 20,
) -> DocumentOrganizationAuditSummary:
    """Build a read-only logical manual/ATA/part organization summary."""

    db_path = Path(db_path)
    warnings: list[str] = []
    top_ata_limit = max(1, int(top_ata_limit))
    top_part_limit = max(1, int(top_part_limit))

    if not db_path.exists():
        return DocumentOrganizationAuditSummary(
            db_path=str(db_path),
            warnings=(f"database does not exist: {db_path}",),
        )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        page_table = _best_page_table(conn)
        if page_table is None:
            return DocumentOrganizationAuditSummary(
                db_path=str(db_path),
                warnings=("no source_links/pages rows found; run the backend pipeline first",),
            )

        page_rows = _select_all(conn, page_table, order_cols=("manual_id", "page_sequence", "page_label", "page_id"))
        source_links_total = _count(conn, "SELECT COUNT(*) FROM source_links") if _table_exists(conn, "source_links") else 0
        pages_table_total = _count(conn, "SELECT COUNT(*) FROM pages") if _table_exists(conn, "pages") else len(page_rows)
        mention_rows = _load_part_mentions(conn)
        canonical_lookup, clean_catalog_available = _load_canonical_part_lookup(conn)
        part_names = _load_part_names(conn)

    page_by_id: dict[str, dict[str, Any]] = {}
    manual_ids: set[str] = set()
    ata_pages: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    source_link_pages: set[str] = set()
    empty_ocr_page_ids: set[str] = set()

    for index, row in enumerate(page_rows):
        pid = _page_id(row) or f"row_{index}"
        page_by_id[pid] = row
        manual = _manual_id(row)
        manual_ids.add(manual)
        publication = _publication(row)
        ata = _ata(row)
        if ata:
            ata_pages[(manual, publication, ata)].add(pid)
        if page_table == "source_links":
            source_link_pages.add(pid)
        if _is_empty_file(_ocr_path(row)):
            empty_ocr_page_ids.add(pid)

    pages_total = len(page_rows)
    pages_with_ata = len({pid for pids in ata_pages.values() for pid in pids})
    pages_without_ata = max(0, pages_total - pages_with_ata)

    page_parts: dict[str, set[str]] = defaultdict(set)
    part_pages: dict[str, set[str]] = defaultdict(set)
    part_mentions: Counter[str] = Counter()
    part_display_names: dict[str, str] = {}
    raw_part_mentions: Counter[str] = Counter()
    raw_mentions_excluded = 0
    compound_references_suppressed = 0
    use_canonical_allowlist = clean_catalog_available and bool(canonical_lookup)

    for row in mention_rows:
        raw_part = _part_number(row)
        if raw_part:
            raw_part_mentions[raw_part] += 1
        canonical = _canonical_part_from_mention(
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
        if pid:
            page_parts[pid].add(part)
            part_pages[part].add(pid)

    ata_part_counts: Counter[tuple[str, str, str]] = Counter()
    for (manual, publication, ata), pids in ata_pages.items():
        for pid in pids:
            ata_part_counts[(manual, publication, ata)] += len(page_parts.get(pid, set()))

    ata_rows: list[AtaTreeRow] = []
    for (manual, publication, ata), pids in ata_pages.items():
        ata_rows.append(
            AtaTreeRow(
                manual_id=manual,
                publication_number=publication,
                ata_code=ata,
                page_count=len(pids),
                part_mention_count=int(ata_part_counts[(manual, publication, ata)]),
                source_link_count=len(pids & source_link_pages) if source_link_pages else 0,
                empty_ocr_pages=len(pids & empty_ocr_page_ids),
            )
        )
    ata_rows.sort(key=lambda item: (-item.page_count, item.manual_id, item.ata_code))

    part_rows: list[PartTreeRow] = []
    for part, pids in part_pages.items():
        atas: set[str] = set()
        manuals: set[str] = set()
        for pid in pids:
            page = page_by_id.get(pid, {})
            ata = _ata(page)
            manual = _manual_id(page)
            if ata:
                atas.add(ata)
            if manual:
                manuals.add(manual)
        part_rows.append(
            PartTreeRow(
                part_number=part,
                nomenclature=part_display_names.get(part) or part_names.get(part, ""),
                page_count=len(pids),
                mention_count=int(part_mentions[part]),
                ata_codes=tuple(sorted(atas)),
                manuals=tuple(sorted(manuals)),
            )
        )
    part_rows.sort(key=lambda item: (-item.page_count, -item.mention_count, item.part_number))

    if pages_without_ata:
        warnings.append(f"{pages_without_ata} pages do not have an ATA code in the logical organization layer.")
    if not ata_rows:
        warnings.append("no ATA groups were inferred; check OCR/header extraction before scaling.")
    if empty_ocr_page_ids:
        warnings.append(f"{len(empty_ocr_page_ids)} pages have empty OCR text and may need blank-page review or OCR regeneration.")
    if raw_mentions_excluded:
        warnings.append(
            f"{raw_mentions_excluded} raw part mentions were excluded from the logical part tree because they are compound references or not in the clean catalog."
        )
    if pages_total and not part_rows:
        warnings.append("no canonical part mentions were available for the logical part tree.")

    return DocumentOrganizationAuditSummary(
        db_path=str(db_path),
        source_table=page_table,
        source_table_exists=True,
        pages_total=pages_total,
        source_links_total=source_links_total,
        manuals_total=len(manual_ids),
        ata_groups_total=len(ata_rows),
        pages_with_ata=pages_with_ata,
        pages_without_ata=pages_without_ata,
        pages_with_source_links=len(source_link_pages) if source_link_pages else source_links_total,
        part_mentions_total=sum(part_mentions.values()),
        distinct_parts_total=len(part_pages),
        pages_with_parts=len(page_parts),
        empty_ocr_pages=len(empty_ocr_page_ids),
        part_tree_source="clean_catalog_allowlist" if use_canonical_allowlist else "raw_part_mentions",
        raw_part_mentions_total=sum(raw_part_mentions.values()),
        raw_distinct_parts_total=len(raw_part_mentions),
        raw_mentions_excluded_from_part_tree=raw_mentions_excluded,
        compound_part_references_suppressed=compound_references_suppressed,
        top_ata_groups=tuple(ata_rows[:top_ata_limit]),
        top_parts=tuple(part_rows[:top_part_limit]),
        warnings=tuple(warnings),
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_document_organization_audit(
    summary: DocumentOrganizationAuditSummary,
    *,
    top_ata_limit: int = 20,
    top_part_limit: int = 20,
) -> str:
    lines: list[str] = []
    lines.append("Document organization audit")
    lines.append(f"  Status: {'OK' if summary.logical_tree_ready else 'NEEDS ATTENTION'}")
    lines.append(f"  DB: {summary.db_path}")
    lines.append(f"  Source table: {summary.source_table or '-'}")
    lines.append(f"  Logical tree ready: {_yes_no(summary.logical_tree_ready)}")
    lines.append("")
    lines.append("Logical organization counts:")
    lines.append(f"  Manuals: {summary.manuals_total}")
    lines.append(f"  Pages: {summary.pages_total}")
    lines.append(f"  Source links: {summary.source_links_total}")
    lines.append(f"  Pages with source links: {summary.pages_with_source_links}")
    lines.append(f"  ATA groups: {summary.ata_groups_total}")
    lines.append(f"  Pages with ATA: {summary.pages_with_ata}")
    lines.append(f"  Pages without ATA: {summary.pages_without_ata}")
    lines.append(f"  Part tree source: {summary.part_tree_source or '-'}")
    lines.append(f"  Logical/canonical distinct parts: {summary.distinct_parts_total}")
    lines.append(f"  Logical/canonical part mentions: {summary.part_mentions_total}")
    lines.append(f"  Pages with logical parts: {summary.pages_with_parts}")
    lines.append(f"  Raw distinct parts seen: {summary.raw_distinct_parts_total}")
    lines.append(f"  Raw part mentions seen: {summary.raw_part_mentions_total}")
    lines.append(f"  Raw mentions excluded from logical part tree: {summary.raw_mentions_excluded_from_part_tree}")
    lines.append(f"  Compound part references suppressed: {summary.compound_part_references_suppressed}")
    lines.append(f"  Empty OCR pages: {summary.empty_ocr_pages}")

    if summary.top_ata_groups:
        lines.append("")
        lines.append("Top manual/ATA groups:")
        for idx, row in enumerate(summary.top_ata_groups[: max(0, top_ata_limit)], start=1):
            label = row.publication_number or row.manual_id
            lines.append(
                f"  {idx}. {label} | ATA {row.ata_code} | pages={row.page_count} "
                f"parts={row.part_mention_count} source_links={row.source_link_count} empty_ocr={row.empty_ocr_pages}"
            )

    if summary.top_parts:
        lines.append("")
        lines.append("Top part tree entries:")
        for idx, row in enumerate(summary.top_parts[: max(0, top_part_limit)], start=1):
            name = f" | {row.nomenclature}" if row.nomenclature else ""
            atas = ", ".join(row.ata_codes[:3]) if row.ata_codes else "-"
            if len(row.ata_codes) > 3:
                atas += f", +{len(row.ata_codes) - 3} more"
            lines.append(
                f"  {idx}. {row.part_number}{name} | pages={row.page_count} mentions={row.mention_count} ATA={atas}"
            )

    if summary.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in summary.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


def write_document_organization_json(summary: DocumentOrganizationAuditSummary, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
