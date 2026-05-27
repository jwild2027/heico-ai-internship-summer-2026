"""Incremental changed-page backend update helpers.

This module is the bridge between the file-level incremental TIFF detector and
backend tables used for search/RAG.  It updates only pages that correspond to
changed TIFFs, then lets the existing embedding builder reuse unchanged chunk
embeddings.

The implementation is deliberately conservative:
- It matches changed TIFFs to ResCarta staging pages by path/stem/digit token.
- It updates page-scoped search rows for only those pages.
- It updates clean OCR, part catalog rows, canonical part rows, and RAG chunks
  for only the affected pages/parts.
- It does not mutate unrelated pages.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


TIFF_EXTENSIONS = {".tif", ".tiff"}


@dataclass(frozen=True)
class ChangedPageMatch:
    changed_tiff: str
    page_id: str
    manual_id: str
    page_sequence: int | None
    page_label: str | None
    ata_code: str | None
    tiff_path: str | None
    ocr_text_path: str | None


@dataclass
class ChangedBackendSummary:
    db_path: Path
    changed_list_path: Path
    export_root: Path | None = None
    changed_files: int = 0
    affected_pages: int = 0
    search_pages_updated: int = 0
    part_mentions_updated: int = 0
    clean_pages_updated: int = 0
    part_catalog_rows_updated: int = 0
    canonical_parts_updated: int = 0
    rag_chunks_updated: int = 0
    stale_embeddings_deleted: int = 0
    unmatched_changed_files: list[str] = field(default_factory=list)
    affected_page_ids: list[str] = field(default_factory=list)
    affected_part_numbers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PageScopedDeleteCounts:
    page_fts: int = 0
    part_mentions: int = 0
    pages: int = 0
    part_catalog: int = 0
    ocr_clean_pages: int = 0
    part_catalog_mentions_clean: int = 0
    rag_chunks: int = 0
    rag_embeddings: int = 0


def read_changed_tiffs(path: str | Path) -> tuple[str, ...]:
    p = Path(path)
    if not p.exists():
        return ()
    lines = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        text = raw.strip().strip('"').strip("'")
        if text and not text.startswith("#"):
            lines.append(text)
    return tuple(lines)


def _norm_path(value: str | Path | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\\", "/").lower().strip()


def _stem(value: str | Path | None) -> str:
    if value is None:
        return ""
    return Path(str(value).replace("\\", "/")).stem.lower()


def _digit_tokens(value: str | Path | None) -> set[str]:
    stem = _stem(value)
    tokens = set(re.findall(r"\d{3,}", stem))
    # Include normalized integer forms so 000083 can match 83/00000083 cases.
    expanded: set[str] = set(tokens)
    for token in tokens:
        try:
            expanded.add(str(int(token)))
        except ValueError:
            pass
    return expanded


def tiff_paths_match(changed_tiff: str, candidate_tiff: str | None, candidate_ocr: str | None = None) -> bool:
    """Return True when a changed source TIFF likely maps to a staging page."""

    if not candidate_tiff and not candidate_ocr:
        return False
    changed_norm = _norm_path(changed_tiff)
    changed_name = Path(changed_norm).name
    changed_stem = _stem(changed_tiff)
    changed_digits = _digit_tokens(changed_tiff)

    for candidate in (candidate_tiff, candidate_ocr):
        if not candidate:
            continue
        cand_norm = _norm_path(candidate)
        cand_name = Path(cand_norm).name
        cand_stem = _stem(candidate)
        if changed_norm == cand_norm:
            return True
        if changed_name and changed_name == cand_name:
            return True
        if changed_stem and (changed_stem == cand_stem or changed_stem in cand_stem or cand_stem in changed_stem):
            return True
        cand_digits = _digit_tokens(candidate)
        if changed_digits and cand_digits and changed_digits.intersection(cand_digits):
            return True
    return False


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ? LIMIT 1",
            (name,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _placeholders(values: Sequence[object]) -> str:
    return ",".join("?" for _ in values)


def _delete_by_page_ids(conn: sqlite3.Connection, table: str, page_ids: Sequence[str]) -> int:
    if not page_ids or not _table_exists(conn, table):
        return 0
    cols = _columns(conn, table)
    if "page_id" not in cols:
        return 0
    before = conn.total_changes
    conn.execute(f"DELETE FROM {table} WHERE page_id IN ({_placeholders(page_ids)})", tuple(page_ids))
    return conn.total_changes - before


def _delete_fts_by_page_ids(conn: sqlite3.Connection, table: str, page_ids: Sequence[str]) -> int:
    # FTS5 tables do not appear in PRAGMA table_info exactly like ordinary
    # tables across versions, but DELETE by page_id works for our virtual tables.
    if not page_ids or not _table_exists(conn, table):
        return 0
    try:
        before = conn.total_changes
        conn.execute(f"DELETE FROM {table} WHERE page_id IN ({_placeholders(page_ids)})", tuple(page_ids))
        return conn.total_changes - before
    except sqlite3.OperationalError:
        return 0


def _chunk_ids_for_pages(conn: sqlite3.Connection, page_ids: Sequence[str]) -> list[str]:
    if not page_ids or not _table_exists(conn, "rag_chunks"):
        return []
    cols = _columns(conn, "rag_chunks")
    if "page_id" not in cols or "chunk_id" not in cols:
        return []
    rows = conn.execute(
        f"SELECT chunk_id FROM rag_chunks WHERE page_id IN ({_placeholders(page_ids)})",
        tuple(page_ids),
    ).fetchall()
    return [str(row[0]) for row in rows]


def delete_page_scoped_backend_rows(conn: sqlite3.Connection, page_ids: Sequence[str]) -> PageScopedDeleteCounts:
    """Delete derived rows that can be rebuilt for affected pages."""

    page_ids = tuple(dict.fromkeys(str(p) for p in page_ids if p))
    if not page_ids:
        return PageScopedDeleteCounts()

    chunk_ids = _chunk_ids_for_pages(conn, page_ids)
    rag_embeddings_deleted = 0
    if chunk_ids and _table_exists(conn, "rag_embeddings") and "chunk_id" in _columns(conn, "rag_embeddings"):
        before = conn.total_changes
        conn.execute(
            f"DELETE FROM rag_embeddings WHERE chunk_id IN ({_placeholders(chunk_ids)})",
            tuple(chunk_ids),
        )
        rag_embeddings_deleted = conn.total_changes - before

    return PageScopedDeleteCounts(
        page_fts=_delete_fts_by_page_ids(conn, "page_fts", page_ids),
        part_mentions=_delete_by_page_ids(conn, "part_mentions", page_ids),
        pages=_delete_by_page_ids(conn, "pages", page_ids),
        part_catalog=_delete_by_page_ids(conn, "part_catalog", page_ids),
        ocr_clean_pages=_delete_by_page_ids(conn, "ocr_clean_pages", page_ids),
        part_catalog_mentions_clean=_delete_by_page_ids(conn, "part_catalog_mentions_clean", page_ids),
        rag_chunks=_delete_by_page_ids(conn, "rag_chunks", page_ids) + _delete_fts_by_page_ids(conn, "rag_chunk_fts", page_ids),
        rag_embeddings=rag_embeddings_deleted,
    )


def _build_page_records_for_changed_export_pages(export_root: Path, changed_tiffs: Sequence[str]):
    """Yield (changed_tiff, manual, page_record) for matching staging pages."""

    from tiff.search_index import build_manual_record, build_page_record, iter_manual_dirs

    changed = tuple(changed_tiffs)
    for manual_dir in iter_manual_dirs(Path(export_root)):
        ocr_dir = Path(manual_dir) / "ocr"
        ocr_files = sorted(p for p in ocr_dir.glob("*.txt") if p.is_file()) if ocr_dir.exists() else []
        if not ocr_files:
            continue
        manual = build_manual_record(Path(manual_dir), page_count=len(ocr_files))
        for index, ocr_file in enumerate(ocr_files, start=1):
            page = build_page_record(manual, Path(manual_dir), ocr_file, sequence_fallback=index)
            for changed_tiff in changed:
                if tiff_paths_match(changed_tiff, page.tiff_path, page.ocr_text_path):
                    yield changed_tiff, manual, page
                    break


def update_search_index_for_changed_pages(
    *,
    export_root: str | Path,
    db_path: str | Path,
    changed_list_path: str | Path,
) -> ChangedBackendSummary:
    """Update pages/page_fts/part_mentions for only changed staging pages."""

    from tiff.search_index import create_schema, insert_manual, insert_page, insert_part_mentions

    export_root = Path(export_root)
    db_path = Path(db_path)
    changed_list_path = Path(changed_list_path)
    changed_tiffs = read_changed_tiffs(changed_list_path)
    summary = ChangedBackendSummary(db_path=db_path, export_root=export_root, changed_list_path=changed_list_path, changed_files=len(changed_tiffs))

    if not changed_tiffs:
        return summary

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        create_schema(conn, reset=not _table_exists(conn, "pages"))
        matched_changed: set[str] = set()
        seen_pages: set[str] = set()
        for changed_tiff, manual, page in _build_page_records_for_changed_export_pages(export_root, changed_tiffs):
            matched_changed.add(changed_tiff)
            if page.page_id in seen_pages:
                continue
            seen_pages.add(page.page_id)
            # Clear only this page's search/index rows before re-inserting.
            delete_page_scoped_backend_rows(conn, [page.page_id])
            insert_manual(conn, manual)
            insert_page(conn, page)
            summary.part_mentions_updated += insert_part_mentions(conn, page)
            summary.search_pages_updated += 1
            summary.affected_page_ids.append(page.page_id)
            summary.affected_pages += 1
        for changed_tiff in changed_tiffs:
            if changed_tiff not in matched_changed:
                summary.unmatched_changed_files.append(changed_tiff)
        conn.commit()
    finally:
        conn.close()
    return summary


def _fetch_affected_part_numbers(conn: sqlite3.Connection, page_ids: Sequence[str]) -> set[str]:
    part_norms: set[str] = set()
    if page_ids and _table_exists(conn, "part_mentions"):
        cols = _columns(conn, "part_mentions")
        if {"page_id", "part_number_normalized"}.issubset(cols):
            rows = conn.execute(
                f"SELECT DISTINCT part_number_normalized FROM part_mentions WHERE page_id IN ({_placeholders(page_ids)})",
                tuple(page_ids),
            ).fetchall()
            part_norms.update(str(row[0]) for row in rows if row[0])
    if page_ids and _table_exists(conn, "part_catalog"):
        cols = _columns(conn, "part_catalog")
        if {"page_id", "part_number_normalized"}.issubset(cols):
            rows = conn.execute(
                f"SELECT DISTINCT part_number_normalized FROM part_catalog WHERE page_id IN ({_placeholders(page_ids)})",
                tuple(page_ids),
            ).fetchall()
            part_norms.update(str(row[0]) for row in rows if row[0])
    return part_norms


def _insert_clean_catalog_mentions_for_pages(conn: sqlite3.Connection, page_ids: Sequence[str]) -> tuple[int, set[str]]:
    from tiff.ocr_cleanup import clean_part_nomenclature, nomenclature_quality_score

    if not page_ids or not _table_exists(conn, "part_catalog"):
        return 0, set()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""
        SELECT *
        FROM part_catalog
        WHERE page_id IN ({_placeholders(page_ids)})
        ORDER BY part_number_normalized, page_sequence, catalog_id
        """,
        tuple(page_ids),
    ).fetchall()
    count = 0
    affected_parts: set[str] = set()
    for row in rows:
        clean_name = clean_part_nomenclature(row["nomenclature"])
        quality = nomenclature_quality_score(clean_name, row["confidence"])
        affected_parts.add(row["part_number_normalized"])
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
                row["nomenclature"],
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
        count += 1
    return count, affected_parts


def _recompute_canonical_parts(conn: sqlite3.Connection, part_norms: Iterable[str]) -> int:
    from tiff.ocr_cleanup import choose_canonical_part, json_dumps

    count = 0
    for part_norm in sorted(set(p for p in part_norms if p)):
        if not _table_exists(conn, "part_catalog_clean"):
            continue
        conn.execute("DELETE FROM part_catalog_clean WHERE part_number_normalized = ?", (part_norm,))
        canonical = choose_canonical_part(conn, part_norm, [])
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
        count += 1
    return count


def update_part_catalog_for_pages(db_path: str | Path, page_ids: Sequence[str]) -> ChangedBackendSummary:
    """Rebuild clean OCR/catalog/canonical rows for affected pages only."""

    from tiff.ocr_cleanup import clean_ocr_text, create_ocr_cleanup_schema, sha256_text
    from tiff.part_catalog import create_part_catalog_schema, extract_catalog_entry_from_page, insert_catalog_entry

    db_path = Path(db_path)
    summary = ChangedBackendSummary(db_path=db_path, changed_list_path=Path(""), affected_page_ids=list(page_ids))
    if not page_ids:
        return summary

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        create_ocr_cleanup_schema(conn, reset=False)
        create_part_catalog_schema(conn, reset=False)
        page_ids_tuple = tuple(dict.fromkeys(str(p) for p in page_ids if p))
        old_part_norms = _fetch_affected_part_numbers(conn, page_ids_tuple)

        # Update clean OCR rows for only affected pages.
        page_rows = conn.execute(
            f"SELECT page_id, ocr_text FROM pages WHERE page_id IN ({_placeholders(page_ids_tuple)})",
            page_ids_tuple,
        ).fetchall()
        for row in page_rows:
            raw = row["ocr_text"] or ""
            clean, removed = clean_ocr_text(raw)
            line_count = len([line for line in clean.split("\n") if line.strip()])
            conn.execute(
                """
                INSERT OR REPLACE INTO ocr_clean_pages (
                    page_id, raw_sha256, raw_char_count, clean_char_count,
                    clean_line_count, removed_line_count, clean_ocr_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (row["page_id"], sha256_text(raw), len(raw), len(clean), line_count, removed, clean),
            )
            summary.clean_pages_updated += 1

        # Remove old catalog rows for these pages, then re-extract from current
        # pages/part_mentions.
        _delete_by_page_ids(conn, "part_catalog", page_ids_tuple)
        _delete_by_page_ids(conn, "part_catalog_mentions_clean", page_ids_tuple)
        page_part_rows = conn.execute(
            f"""
            SELECT
                p.page_id, p.manual_id, p.page_sequence, p.page_label, p.ata_code,
                p.tiff_path, p.ocr_text_path,
                COALESCE(oc.clean_ocr_text, p.ocr_text) AS ocr_text,
                pm.part_number_display, pm.part_number_normalized
            FROM part_mentions pm
            JOIN pages p ON p.page_id = pm.page_id
            LEFT JOIN ocr_clean_pages oc ON oc.page_id = p.page_id
            WHERE p.page_id IN ({_placeholders(page_ids_tuple)})
            ORDER BY p.manual_id, p.page_sequence, pm.part_number_normalized
            """,
            page_ids_tuple,
        ).fetchall()
        sequence = 0
        seen_keys: set[tuple[str, str, str]] = set()
        for row in page_part_rows:
            key = (row["page_id"], row["part_number_normalized"], row["part_number_display"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entry = extract_catalog_entry_from_page(row, row["part_number_display"], row["part_number_normalized"])
            if entry is None:
                continue
            sequence += 1
            insert_catalog_entry(conn, entry, sequence)
            summary.part_catalog_rows_updated += 1

        clean_rows, new_part_norms = _insert_clean_catalog_mentions_for_pages(conn, page_ids_tuple)
        affected_parts = old_part_norms | new_part_norms | _fetch_affected_part_numbers(conn, page_ids_tuple)
        summary.canonical_parts_updated = _recompute_canonical_parts(conn, affected_parts)
        summary.affected_part_numbers = sorted(affected_parts)
        conn.commit()
    finally:
        conn.close()
    return summary


def update_rag_chunks_for_pages(
    db_path: str | Path,
    page_ids: Sequence[str],
    *,
    max_chars: int = 1400,
    overlap_chars: int = 180,
) -> ChangedBackendSummary:
    """Rebuild RAG chunks for affected pages only and delete stale embeddings."""

    from tiff.rag_chunks import (
        RagChunk,
        _fetch_page_parts,
        _insert_chunk,
        chunk_text_by_lines,
        create_rag_schema,
        json_dumps,
        sha256_text,
    )

    db_path = Path(db_path)
    summary = ChangedBackendSummary(db_path=db_path, changed_list_path=Path(""), affected_page_ids=list(page_ids))
    if not page_ids:
        return summary

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        create_rag_schema(conn, reset=False)
        page_ids_tuple = tuple(dict.fromkeys(str(p) for p in page_ids if p))
        chunk_ids = _chunk_ids_for_pages(conn, page_ids_tuple)
        if chunk_ids and _table_exists(conn, "rag_embeddings"):
            before = conn.total_changes
            conn.execute(
                f"DELETE FROM rag_embeddings WHERE chunk_id IN ({_placeholders(chunk_ids)})",
                tuple(chunk_ids),
            )
            summary.stale_embeddings_deleted += conn.total_changes - before
        _delete_by_page_ids(conn, "rag_chunks", page_ids_tuple)
        _delete_fts_by_page_ids(conn, "rag_chunk_fts", page_ids_tuple)

        page_rows = conn.execute(
            f"""
            SELECT
                p.page_id, p.manual_id, p.publication_number, p.ata_code, p.page_sequence,
                p.page_label, p.page_type, p.title, p.tiff_path, p.ocr_text_path,
                p.rescarta_object_id, p.rescarta_page_id,
                COALESCE(oc.clean_ocr_text, p.ocr_text) AS ocr_text,
                p.is_blank
            FROM pages p
            LEFT JOIN ocr_clean_pages oc ON oc.page_id = p.page_id
            WHERE p.page_id IN ({_placeholders(page_ids_tuple)})
              AND COALESCE(p.is_blank, 0) = 0
              AND COALESCE(oc.clean_ocr_text, p.ocr_text) IS NOT NULL
              AND TRIM(COALESCE(oc.clean_ocr_text, p.ocr_text)) <> ''
            ORDER BY p.manual_id, p.page_sequence
            """,
            page_ids_tuple,
        ).fetchall()
        for page in page_rows:
            part_numbers, nomenclatures = _fetch_page_parts(conn, page["page_id"])
            chunks = chunk_text_by_lines(page["ocr_text"] or "", max_chars=max_chars, overlap_chars=overlap_chars)
            for idx, text in enumerate(chunks, start=1):
                chunk = RagChunk(
                    chunk_id=f"{page['page_id']}_c{idx:04d}",
                    page_id=page["page_id"],
                    manual_id=page["manual_id"],
                    chunk_index=idx,
                    chunk_text=text,
                    chunk_hash=sha256_text(text),
                    publication_number=page["publication_number"],
                    ata_code=page["ata_code"],
                    page_sequence=page["page_sequence"],
                    page_label=page["page_label"],
                    page_type=page["page_type"],
                    title=page["title"],
                    tiff_path=page["tiff_path"],
                    ocr_text_path=page["ocr_text_path"],
                    rescarta_object_id=page["rescarta_object_id"],
                    rescarta_page_id=page["rescarta_page_id"],
                    part_numbers_json=json_dumps(part_numbers),
                    nomenclatures_json=json_dumps(nomenclatures),
                )
                _insert_chunk(conn, chunk)
                summary.rag_chunks_updated += 1
        conn.commit()
    finally:
        conn.close()
    return summary


def run_changed_page_backend_update(
    *,
    export_root: str | Path,
    db_path: str | Path,
    changed_list_path: str | Path,
    max_chars: int = 1400,
    overlap_chars: int = 180,
) -> ChangedBackendSummary:
    """Run page-scoped search/catalog/RAG chunk updates for changed TIFFs."""

    search = update_search_index_for_changed_pages(
        export_root=export_root,
        db_path=db_path,
        changed_list_path=changed_list_path,
    )
    page_ids = search.affected_page_ids
    catalog = update_part_catalog_for_pages(db_path, page_ids)
    rag = update_rag_chunks_for_pages(db_path, page_ids, max_chars=max_chars, overlap_chars=overlap_chars)

    merged = ChangedBackendSummary(
        db_path=Path(db_path),
        export_root=Path(export_root),
        changed_list_path=Path(changed_list_path),
        changed_files=search.changed_files,
        affected_pages=search.affected_pages,
        search_pages_updated=search.search_pages_updated,
        part_mentions_updated=search.part_mentions_updated,
        clean_pages_updated=catalog.clean_pages_updated,
        part_catalog_rows_updated=catalog.part_catalog_rows_updated,
        canonical_parts_updated=catalog.canonical_parts_updated,
        rag_chunks_updated=rag.rag_chunks_updated,
        stale_embeddings_deleted=rag.stale_embeddings_deleted,
        unmatched_changed_files=search.unmatched_changed_files,
        affected_page_ids=page_ids,
        affected_part_numbers=catalog.affected_part_numbers,
        warnings=[*search.warnings, *catalog.warnings, *rag.warnings],
    )
    return merged


def summary_to_dict(summary: ChangedBackendSummary) -> dict[str, object]:
    return {
        "db_path": str(summary.db_path),
        "export_root": str(summary.export_root) if summary.export_root else None,
        "changed_list_path": str(summary.changed_list_path),
        "changed_files": summary.changed_files,
        "affected_pages": summary.affected_pages,
        "search_pages_updated": summary.search_pages_updated,
        "part_mentions_updated": summary.part_mentions_updated,
        "clean_pages_updated": summary.clean_pages_updated,
        "part_catalog_rows_updated": summary.part_catalog_rows_updated,
        "canonical_parts_updated": summary.canonical_parts_updated,
        "rag_chunks_updated": summary.rag_chunks_updated,
        "stale_embeddings_deleted": summary.stale_embeddings_deleted,
        "unmatched_changed_files": list(summary.unmatched_changed_files),
        "affected_page_ids": list(summary.affected_page_ids),
        "affected_part_numbers": list(summary.affected_part_numbers),
        "warnings": list(summary.warnings),
    }


def write_summary_json(summary: ChangedBackendSummary, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")
