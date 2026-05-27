"""Changed-page backend update helpers for the local TIFF search/RAG stack.

This module is the first page-scoped backend update layer.  It keeps the
existing full backend rebuild as the safe default, but provides a smaller path
for runs where the incremental scanner already knows which TIFF files changed.

The update is intentionally source-backed: it rebuilds affected page records
from the ResCarta staging export, then refreshes derived page-scoped rows:

* pages and page_fts
* part_mentions
* ocr_clean_pages
* part_catalog rows for affected pages
* part_catalog_mentions_clean rows for affected pages
* canonical part_catalog_clean rows for affected part numbers
* rag_chunks for affected pages

Embeddings are not created here; ``scripts/build_rag_embeddings.py`` should run
afterward.  Because embeddings are keyed by chunk_hash, unchanged chunks are
reused and stale embeddings are pruned there.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from tiff.ocr_cleanup import (
    choose_canonical_part,
    clean_ocr_text,
    clean_part_nomenclature,
    create_ocr_cleanup_schema,
    json_dumps as cleanup_json_dumps,
    nomenclature_quality_score,
    sha256_text,
)
from tiff.part_catalog import (
    create_part_catalog_schema,
    extract_catalog_entry_from_page,
    insert_catalog_entry,
)
from tiff.rag_chunks import (
    RagChunk,
    _fetch_page_parts,
    _insert_chunk,
    chunk_text_by_lines,
    create_rag_schema,
    json_dumps,
    sha256_text as chunk_sha256_text,
    table_exists,
)
from tiff.search_index import (
    build_manual_record,
    build_page_record,
    create_schema,
    insert_manual,
    insert_page,
    insert_part_mentions,
    iter_manual_dirs,
)


@dataclass(frozen=True)
class AffectedPage:
    page_id: str
    changed_path: str
    match_reason: str


@dataclass
class ChangedPageUpdateSummary:
    db_path: Path
    export_root: Path
    changed_list_path: Path | None = None
    changed_paths: int = 0
    matched_pages: int = 0
    unmatched_paths: int = 0
    pages_updated: int = 0
    part_mentions_updated: int = 0
    clean_pages_updated: int = 0
    catalog_rows_updated: int = 0
    canonical_parts_updated: int = 0
    rag_chunks_updated: int = 0
    stale_embeddings_deleted: int = 0
    qa_ran: bool = False
    eval_ran: bool = False
    affected_page_ids: list[str] = field(default_factory=list)
    affected_part_numbers: list[str] = field(default_factory=list)
    unmatched_changed_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def read_changed_paths(path: str | Path) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _norm_path(value: str | Path | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\\", "/").lower().strip()


def _stem_tokens(path: str | Path | None) -> set[str]:
    text = _norm_path(path)
    if not text:
        return set()
    p = Path(text)
    stem = p.stem.lower()
    name = p.name.lower()
    tokens = {stem, name}
    for part in re.split(r"[^a-z0-9]+", stem):
        if part:
            tokens.add(part)
    # ResCarta staging names often look like 000083_00000083.tif while the
    # source TIFF may be 00000083.tif.  Keep numeric components and normalized
    # zero-stripped versions so these match safely.
    for match in re.finditer(r"\d{3,}", stem):
        raw = match.group(0)
        tokens.add(raw)
        stripped = raw.lstrip("0") or "0"
        tokens.add(stripped)
    return tokens


def _path_keys(path: str | Path | None) -> set[str]:
    text = _norm_path(path)
    if not text:
        return set()
    keys = {text, Path(text).name.lower(), Path(text).stem.lower()}
    keys.update(_stem_tokens(path))
    return {k for k in keys if k}


def paths_might_refer_to_same_page(changed_path: str | Path, candidate_path: str | Path | None) -> bool:
    changed_keys = _path_keys(changed_path)
    candidate_keys = _path_keys(candidate_path)
    if not changed_keys or not candidate_keys:
        return False
    if changed_keys & candidate_keys:
        return True
    # Conservative containment check for staged TIFF names that embed the raw
    # TIFF stem, e.g. changed 00000083.tif vs staged 000083_00000083.tif.
    changed_stems = {k for k in changed_keys if len(k) >= 4}
    candidate_stems = {k for k in candidate_keys if len(k) >= 4}
    return any(c in d or d in c for c in changed_stems for d in candidate_stems)


def resolve_affected_pages(db_path: str | Path, changed_paths: Sequence[str | Path]) -> tuple[list[AffectedPage], list[str]]:
    """Resolve changed TIFF paths to current page_ids in an existing DB."""

    db_path = Path(db_path)
    if not db_path.exists() or not changed_paths:
        return [], [str(p) for p in changed_paths]
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "pages"):
            return [], [str(p) for p in changed_paths]
        rows = conn.execute(
            """
            SELECT page_id, tiff_path, ocr_text_path, page_sequence, rescarta_page_id
            FROM pages
            ORDER BY manual_id, page_sequence
            """
        ).fetchall()
        matched: list[AffectedPage] = []
        matched_paths: set[str] = set()
        seen_pages: set[str] = set()
        for changed in changed_paths:
            changed_text = str(changed)
            for row in rows:
                reason = None
                if paths_might_refer_to_same_page(changed_text, row["tiff_path"]):
                    reason = "tiff_path"
                elif paths_might_refer_to_same_page(changed_text, row["ocr_text_path"]):
                    reason = "ocr_text_path"
                else:
                    changed_tokens = _stem_tokens(changed_text)
                    sequence = str(row["page_sequence"] or "")
                    page_id = str(row["page_id"] or "").lower()
                    rescarta_page_id = str(row["rescarta_page_id"] or "").lower()
                    if sequence and sequence in changed_tokens:
                        reason = "page_sequence"
                    elif rescarta_page_id and rescarta_page_id in changed_tokens:
                        reason = "rescarta_page_id"
                    elif page_id and page_id in _path_keys(changed_text):
                        reason = "page_id"
                if reason:
                    matched_paths.add(changed_text)
                    if row["page_id"] not in seen_pages:
                        matched.append(AffectedPage(row["page_id"], changed_text, reason))
                        seen_pages.add(row["page_id"])
        unmatched = [str(p) for p in changed_paths if str(p) not in matched_paths]
        return matched, unmatched
    finally:
        conn.close()


def _iter_rescarta_page_records(export_root: Path):
    for manual_dir in iter_manual_dirs(export_root):
        ocr_dir = manual_dir / "ocr"
        ocr_files = sorted(p for p in ocr_dir.glob("*.txt") if p.is_file()) if ocr_dir.exists() else []
        if not ocr_files:
            continue
        manual = build_manual_record(manual_dir, page_count=len(ocr_files))
        for i, ocr_file in enumerate(ocr_files, start=1):
            page = build_page_record(manual, manual_dir, ocr_file, sequence_fallback=i)
            yield manual, page


def _record_matches_changed(page, changed_paths: Sequence[str | Path]) -> bool:
    for changed in changed_paths:
        if paths_might_refer_to_same_page(changed, page.tiff_path):
            return True
        if paths_might_refer_to_same_page(changed, page.ocr_text_path):
            return True
    return False


def _delete_page_search_rows(conn: sqlite3.Connection, page_ids: Sequence[str]) -> None:
    for page_id in page_ids:
        conn.execute("DELETE FROM page_fts WHERE page_id = ?", (page_id,))
        conn.execute("DELETE FROM part_mentions WHERE page_id = ?", (page_id,))


def update_search_index_pages(db_path: str | Path, export_root: str | Path, changed_paths: Sequence[str | Path]) -> tuple[list[str], int]:
    """Refresh pages + part_mentions for changed paths from ResCarta staging."""

    db_path = Path(db_path)
    export_root = Path(export_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    updated_page_ids: list[str] = []
    mention_count = 0
    try:
        create_schema(conn, reset=False)
        for manual, page in _iter_rescarta_page_records(export_root):
            if not _record_matches_changed(page, changed_paths):
                continue
            insert_manual(conn, manual)
            _delete_page_search_rows(conn, [page.page_id])
            insert_page(conn, page)
            mention_count += insert_part_mentions(conn, page)
            updated_page_ids.append(page.page_id)
        conn.commit()
        return updated_page_ids, mention_count
    finally:
        conn.close()


def _clean_one_page(conn: sqlite3.Connection, page_id: str) -> bool:
    row = conn.execute("SELECT page_id, ocr_text FROM pages WHERE page_id = ?", (page_id,)).fetchone()
    if row is None:
        return False
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
        (page_id, sha256_text(raw), raw_chars, clean_chars, line_count, removed, clean),
    )
    return True


def _page_part_rows(conn: sqlite3.Connection, page_ids: Sequence[str]) -> list[sqlite3.Row]:
    if not page_ids:
        return []
    placeholders = ",".join("?" for _ in page_ids)
    conn.row_factory = sqlite3.Row
    return conn.execute(
        f"""
        SELECT
            p.page_id, p.manual_id, p.page_sequence, p.page_label, p.ata_code,
            p.tiff_path, p.ocr_text_path,
            COALESCE(oc.clean_ocr_text, p.ocr_text) AS ocr_text,
            pm.part_number_display, pm.part_number_normalized
        FROM part_mentions pm
        JOIN pages p ON p.page_id = pm.page_id
        LEFT JOIN ocr_clean_pages oc ON oc.page_id = p.page_id
        WHERE p.page_id IN ({placeholders})
        ORDER BY p.manual_id, p.page_sequence, pm.part_number_normalized
        """,
        tuple(page_ids),
    ).fetchall()


def _next_catalog_sequence(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "part_catalog"):
        return 0
    rows = conn.execute("SELECT catalog_id FROM part_catalog").fetchall()
    max_num = 0
    for row in rows:
        match = re.search(r"(\d+)$", str(row[0] or ""))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num


def _insert_clean_catalog_row(conn: sqlite3.Connection, row: sqlite3.Row) -> str | None:
    raw_name = row["nomenclature"]
    clean_name = clean_part_nomenclature(raw_name)
    quality = nomenclature_quality_score(clean_name, row["confidence"])
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
    return row["part_number_normalized"] if clean_name else None


def _upsert_canonical_part(conn: sqlite3.Connection, part_norm: str) -> bool:
    canonical = choose_canonical_part(conn, part_norm, [])
    if canonical is None:
        conn.execute("DELETE FROM part_catalog_clean WHERE part_number_normalized = ?", (part_norm,))
        return False
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
            cleanup_json_dumps(list(canonical.variants)),
        ),
    )
    return True


def update_clean_catalog_for_pages(db_path: str | Path, page_ids: Sequence[str]) -> tuple[int, set[str], int]:
    """Refresh clean OCR, page catalog rows, and affected canonical parts."""

    if not page_ids:
        return 0, set(), 0
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    clean_pages = 0
    catalog_rows = 0
    affected_parts: set[str] = set()
    try:
        create_ocr_cleanup_schema(conn, reset=False)
        create_part_catalog_schema(conn, reset=False)
        for page_id in page_ids:
            if _clean_one_page(conn, page_id):
                clean_pages += 1
        placeholders = ",".join("?" for _ in page_ids)
        old_parts = {
            row[0]
            for row in conn.execute(
                f"SELECT DISTINCT part_number_normalized FROM part_catalog WHERE page_id IN ({placeholders})",
                tuple(page_ids),
            ).fetchall()
            if row[0]
        }
        affected_parts.update(old_parts)
        conn.execute(f"DELETE FROM part_catalog WHERE page_id IN ({placeholders})", tuple(page_ids))
        conn.execute(f"DELETE FROM part_catalog_mentions_clean WHERE page_id IN ({placeholders})", tuple(page_ids))
        sequence = _next_catalog_sequence(conn)
        seen: set[tuple[str, str, str]] = set()
        for row in _page_part_rows(conn, page_ids):
            key = (row["page_id"], row["part_number_normalized"], row["part_number_display"])
            if key in seen:
                continue
            seen.add(key)
            entry = extract_catalog_entry_from_page(row, row["part_number_display"], row["part_number_normalized"])
            if entry is None:
                continue
            sequence += 1
            insert_catalog_entry(conn, entry, sequence)
            catalog_rows += 1
        new_rows = conn.execute(
            f"""
            SELECT * FROM part_catalog
            WHERE page_id IN ({placeholders})
            ORDER BY part_number_normalized, page_sequence, catalog_id
            """,
            tuple(page_ids),
        ).fetchall()
        for row in new_rows:
            part_norm = _insert_clean_catalog_row(conn, row)
            if part_norm:
                affected_parts.add(part_norm)
        canonical_count = 0
        for part_norm in sorted(affected_parts):
            if _upsert_canonical_part(conn, part_norm):
                canonical_count += 1
        conn.commit()
        return catalog_rows, affected_parts, canonical_count
    finally:
        conn.close()


def update_rag_chunks_for_pages(
    db_path: str | Path,
    page_ids: Sequence[str],
    *,
    max_chars: int = 1400,
    overlap_chars: int = 180,
) -> int:
    """Refresh RAG chunks for changed pages only."""

    if not page_ids:
        return 0
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        create_rag_schema(conn, reset=False)
        placeholders = ",".join("?" for _ in page_ids)
        conn.execute(f"DELETE FROM rag_chunk_fts WHERE page_id IN ({placeholders})", tuple(page_ids))
        conn.execute(f"DELETE FROM rag_chunks WHERE page_id IN ({placeholders})", tuple(page_ids))
        rows = conn.execute(
            f"""
            SELECT
                p.page_id, p.manual_id, p.publication_number, p.ata_code, p.page_sequence,
                p.page_label, p.page_type, p.title, p.tiff_path, p.ocr_text_path,
                p.rescarta_object_id, p.rescarta_page_id,
                COALESCE(oc.clean_ocr_text, p.ocr_text) AS ocr_text,
                p.is_blank
            FROM pages p
            LEFT JOIN ocr_clean_pages oc ON oc.page_id = p.page_id
            WHERE p.page_id IN ({placeholders})
              AND COALESCE(p.is_blank, 0) = 0
              AND COALESCE(oc.clean_ocr_text, p.ocr_text) IS NOT NULL
              AND TRIM(COALESCE(oc.clean_ocr_text, p.ocr_text)) <> ''
            ORDER BY p.manual_id, p.page_sequence
            """,
            tuple(page_ids),
        ).fetchall()
        chunks_created = 0
        for page in rows:
            part_numbers, nomenclatures = _fetch_page_parts(conn, page["page_id"])
            chunks = chunk_text_by_lines(page["ocr_text"] or "", max_chars=max_chars, overlap_chars=overlap_chars)
            for idx, text in enumerate(chunks, start=1):
                chunk = RagChunk(
                    chunk_id=f"{page['page_id']}_c{idx:04d}",
                    page_id=page["page_id"],
                    manual_id=page["manual_id"],
                    chunk_index=idx,
                    chunk_text=text,
                    chunk_hash=chunk_sha256_text(text),
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
                chunks_created += 1
        conn.commit()
        return chunks_created
    finally:
        conn.close()


def delete_stale_embeddings_for_pages(db_path: str | Path, page_ids: Sequence[str]) -> int:
    """Delete embeddings for chunks that no longer match current rag_chunks."""

    if not page_ids:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        if not table_exists(conn, "rag_embeddings") or not table_exists(conn, "rag_chunks"):
            return 0
        placeholders = ",".join("?" for _ in page_ids)
        before = conn.execute("SELECT COUNT(*) FROM rag_embeddings").fetchone()[0]
        conn.execute(
            f"""
            DELETE FROM rag_embeddings
            WHERE chunk_id IN (
                SELECT e.chunk_id
                FROM rag_embeddings e
                LEFT JOIN rag_chunks c ON c.chunk_id = e.chunk_id
                WHERE c.chunk_id IS NULL
                   OR COALESCE(e.chunk_hash, '') <> COALESCE(c.chunk_hash, '')
                   OR c.page_id IN ({placeholders})
            )
            """,
            tuple(page_ids),
        )
        after = conn.execute("SELECT COUNT(*) FROM rag_embeddings").fetchone()[0]
        conn.commit()
        return int(before - after)
    finally:
        conn.close()


def run_changed_page_backend_update(
    *,
    db_path: str | Path,
    export_root: str | Path,
    changed_paths: Sequence[str | Path] | None = None,
    changed_list_path: str | Path | None = None,
    max_chars: int = 1400,
    overlap_chars: int = 180,
) -> ChangedPageUpdateSummary:
    """Run the changed-page backend update through RAG chunk refresh.

    This does not call Ollama.  Run ``scripts/build_rag_embeddings.py`` after
    this function to write embeddings only for chunks that are new or changed.
    """

    if changed_paths is None:
        if changed_list_path is None:
            changed_paths = []
        else:
            changed_paths = read_changed_paths(changed_list_path)
    changed_paths = list(changed_paths)
    summary = ChangedPageUpdateSummary(
        db_path=Path(db_path),
        export_root=Path(export_root),
        changed_list_path=Path(changed_list_path) if changed_list_path else None,
        changed_paths=len(changed_paths),
    )
    if not changed_paths:
        summary.warnings.append("No changed paths were provided.")
        return summary

    matched_before, unmatched_before = resolve_affected_pages(db_path, changed_paths)
    updated_page_ids, mentions = update_search_index_pages(db_path, export_root, changed_paths)
    if not updated_page_ids:
        # If the DB had matches but the staging export did not, keep the matched
        # page ids as affected so derived rows can be invalidated/rebuilt later.
        updated_page_ids = [m.page_id for m in matched_before]
    summary.affected_page_ids = sorted(set(updated_page_ids))
    summary.matched_pages = len(summary.affected_page_ids)
    summary.unmatched_changed_paths = sorted(set(unmatched_before))
    summary.unmatched_paths = len(summary.unmatched_changed_paths)
    summary.pages_updated = len(updated_page_ids)
    summary.part_mentions_updated = mentions
    if not summary.affected_page_ids:
        summary.warnings.append("No changed paths matched pages in the search DB or ResCarta staging export.")
        return summary

    catalog_rows, affected_parts, canonical_count = update_clean_catalog_for_pages(db_path, summary.affected_page_ids)
    summary.clean_pages_updated = len(summary.affected_page_ids)
    summary.catalog_rows_updated = catalog_rows
    summary.affected_part_numbers = sorted(affected_parts)
    summary.canonical_parts_updated = canonical_count
    summary.rag_chunks_updated = update_rag_chunks_for_pages(
        db_path,
        summary.affected_page_ids,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )
    summary.stale_embeddings_deleted = delete_stale_embeddings_for_pages(db_path, summary.affected_page_ids)
    return summary
