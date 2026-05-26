"""tests/unit/test_stage4_sqlite.py — Stage 4: SQLite Persistence (50 tests)

Tests the full DB layer: documents, pages, page_texts, images, chunks,
ingestion_runs, and all foreign key relationships.

No LLM, no Qdrant, no PDF extraction required for most tests.
Requires an ingested DB with both test-2 and test-3.

Usage:
    python -m pytest tests/unit/test_stage4_sqlite.py -v \
        --pdf-test2 "C:/Users/you/Desktop/test-2.pdf" \
        --pdf-test3 "C:/Users/you/Desktop/test-3.pdf" \
        --db-path "rag.db"
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Known values from ingest logs
# ---------------------------------------------------------------------------

EXPECTED_PAGES_TEST3    = 88
EXPECTED_PAGES_TEST2    = 12   # update if your test-2 has a different count
EXPECTED_PARENTS_TEST3  = 41
EXPECTED_CHILDREN_TEST3 = 373
EXPECTED_TOTAL_DOCS     = 2

VALID_DOC_STATUSES      = {"pending", "ingesting", "done", "error"}
VALID_RUN_STATUSES      = {"running", "done", "error"}
VALID_STRATEGIES        = {"native", "tesseract", "merged"}
VALID_CHUNK_STRATEGIES  = {"flat", "parent_child"}
VALID_CHUNK_LEVELS      = {"flat", "parent", "child"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pdf_path_2(request) -> Path:
    p = Path(request.config.getoption("--pdf-test2")).resolve()
    if not p.exists():
        pytest.skip(f"test-2 PDF not found at {p}")
    return p


@pytest.fixture(scope="session")
def pdf_path_3(request) -> Path:
    p = Path(request.config.getoption("--pdf-test3")).resolve()
    if not p.exists():
        pytest.skip(f"test-3 PDF not found at {p}")
    return p


@pytest.fixture(scope="session")
def db_path(request) -> Path:
    p = Path(request.config.getoption("--db-path")).resolve()
    if not p.exists():
        pytest.skip(f"DB not found at {p} — run ingest first")
    return p


@pytest.fixture(scope="session")
def db_conn(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def db(db_path):
    from src.db.storage import RAGDatabase
    d = RAGDatabase(db_path)
    yield d
    d.close()


@pytest.fixture(scope="session")
def doc_id_2(db_conn, pdf_path_2) -> str:
    row = db_conn.execute(
        "SELECT id FROM documents WHERE filename=?", (pdf_path_2.name,)
    ).fetchone()
    if not row:
        pytest.skip(f"{pdf_path_2.name} not in DB")
    return row["id"]


@pytest.fixture(scope="session")
def doc_id_3(db_conn, pdf_path_3) -> str:
    row = db_conn.execute(
        "SELECT id FROM documents WHERE filename=?", (pdf_path_3.name,)
    ).fetchone()
    if not row:
        pytest.skip(f"{pdf_path_3.name} not in DB")
    return row["id"]


@pytest.fixture(scope="session")
def doc_row_2(db_conn, doc_id_2) -> sqlite3.Row:
    return db_conn.execute(
        "SELECT * FROM documents WHERE id=?", (doc_id_2,)
    ).fetchone()


@pytest.fixture(scope="session")
def doc_row_3(db_conn, doc_id_3) -> sqlite3.Row:
    return db_conn.execute(
        "SELECT * FROM documents WHERE id=?", (doc_id_3,)
    ).fetchone()


# ===========================================================================
# DOCUMENTS TABLE
# ===========================================================================

def test_01_two_documents_in_db(db_conn):
    """Exactly 2 documents must exist after ingesting test-2 and test-3."""
    count = db_conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()["cnt"]
    assert count == EXPECTED_TOTAL_DOCS, (
        f"Expected {EXPECTED_TOTAL_DOCS} documents, got {count}"
    )


def test_02_document_ids_are_valid_uuids(db_conn):
    """Every document id must be a valid UUID4 string."""
    rows = db_conn.execute("SELECT id FROM documents").fetchall()
    for row in rows:
        try:
            uuid.UUID(row["id"])
        except ValueError:
            pytest.fail(f"Document id '{row['id']}' is not a valid UUID")


def test_03_document_filenames_correct(db_conn, pdf_path_2, pdf_path_3):
    """Stored filenames must match the actual PDF filenames."""
    filenames = {r["filename"] for r in db_conn.execute(
        "SELECT filename FROM documents"
    ).fetchall()}
    assert pdf_path_2.name in filenames, \
        f"{pdf_path_2.name} not found in documents table"
    assert pdf_path_3.name in filenames, \
        f"{pdf_path_3.name} not found in documents table"


def test_04_document_filepath_is_absolute(db_conn):
    """Stored filepath must be an absolute path."""
    rows = db_conn.execute("SELECT filepath, filename FROM documents").fetchall()
    for row in rows:
        p = Path(row["filepath"])
        assert p.is_absolute(), (
            f"{row['filename']}: filepath '{row['filepath']}' is not absolute"
        )


def test_05_document_checksum_is_sha256(db_conn):
    """pdf_checksum must be a 64-character hex string (SHA-256)."""
    rows = db_conn.execute("SELECT pdf_checksum, filename FROM documents").fetchall()
    for row in rows:
        cs = row["pdf_checksum"]
        assert len(cs) == 64, \
            f"{row['filename']}: checksum length {len(cs)} != 64"
        assert all(c in "0123456789abcdef" for c in cs), \
            f"{row['filename']}: checksum '{cs}' contains non-hex chars"


def test_06_document_checksums_unique(db_conn):
    """No two documents should have the same pdf_checksum."""
    rows = db_conn.execute("SELECT pdf_checksum FROM documents").fetchall()
    checksums = [r["pdf_checksum"] for r in rows]
    assert len(set(checksums)) == len(checksums), \
        "Duplicate pdf_checksum found — same PDF ingested twice as different doc"


def test_07_document_status_done(db_conn):
    """Both documents must have status='done' after successful ingest."""
    rows = db_conn.execute("SELECT filename, status FROM documents").fetchall()
    for row in rows:
        assert row["status"] == "done", (
            f"{row['filename']}: status='{row['status']}' — expected 'done'"
        )


def test_08_document_status_valid_values(db_conn):
    """All document status values must be in the known set."""
    rows = db_conn.execute("SELECT DISTINCT status FROM documents").fetchall()
    found = {r["status"] for r in rows}
    unexpected = found - VALID_DOC_STATUSES
    assert not unexpected, f"Unexpected document status values: {unexpected}"


def test_09_document_page_count_correct_test3(doc_row_3):
    """test-3 must have page_count=88."""
    assert doc_row_3["page_count"] == EXPECTED_PAGES_TEST3, (
        f"test-3 page_count={doc_row_3['page_count']}, expected {EXPECTED_PAGES_TEST3}"
    )


def test_10_document_page_count_correct_test2(doc_row_2):
    """test-2 must have a positive page_count."""
    assert doc_row_2["page_count"] is not None, "test-2 page_count is NULL"
    assert doc_row_2["page_count"] > 0, \
        f"test-2 page_count={doc_row_2['page_count']} — must be > 0"


def test_11_document_created_at_valid(db_conn):
    """created_at must be a non-empty ISO timestamp string."""
    rows = db_conn.execute("SELECT created_at, filename FROM documents").fetchall()
    for row in rows:
        assert row["created_at"] and len(row["created_at"]) >= 10, (
            f"{row['filename']}: created_at='{row['created_at']}' invalid"
        )


def test_12_upsert_document_no_duplicate_on_reingest(db, pdf_path_3):
    """Calling upsert_document twice on the same PDF must not create a new row."""
    count_before = db._conn.execute(
        "SELECT COUNT(*) as cnt FROM documents"
    ).fetchone()["cnt"]
    doc_id, is_new = db.upsert_document(pdf_path_3)
    count_after = db._conn.execute(
        "SELECT COUNT(*) as cnt FROM documents"
    ).fetchone()["cnt"]
    assert not is_new, "upsert_document returned is_new=True for existing PDF"
    assert count_after == count_before, (
        f"Document count changed from {count_before} to {count_after} on re-upsert"
    )


def test_13_upsert_document_returns_same_id(db, pdf_path_3, doc_id_3):
    """upsert_document must return the same doc_id on repeated calls."""
    returned_id, _ = db.upsert_document(pdf_path_3)
    assert returned_id == doc_id_3, (
        f"upsert_document returned '{returned_id}', expected '{doc_id_3}'"
    )


# ===========================================================================
# PAGES TABLE
# ===========================================================================

def test_14_page_count_matches_document_test3(db_conn, doc_id_3):
    """Rows in pages table must equal documents.page_count for test-3."""
    page_rows = db_conn.execute(
        "SELECT COUNT(*) as cnt FROM pages WHERE doc_id=?", (doc_id_3,)
    ).fetchone()["cnt"]
    assert page_rows == EXPECTED_PAGES_TEST3, (
        f"pages table has {page_rows} rows for test-3, expected {EXPECTED_PAGES_TEST3}"
    )


def test_15_page_numbers_sequential_test3(db_conn, doc_id_3):
    """page_number values must be 1..88 with no gaps or duplicates."""
    rows = db_conn.execute(
        "SELECT page_number FROM pages WHERE doc_id=? ORDER BY page_number",
        (doc_id_3,),
    ).fetchall()
    nums = [r["page_number"] for r in rows]
    assert nums == list(range(1, EXPECTED_PAGES_TEST3 + 1)), (
        f"Page numbers not sequential 1..{EXPECTED_PAGES_TEST3}: {nums[:10]}..."
    )


def test_16_page_doc_id_fk_valid(db_conn):
    """Every pages.doc_id must reference a valid documents.id."""
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM pages p
           LEFT JOIN documents d ON d.id = p.doc_id
           WHERE d.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} pages have invalid doc_id (FK violation)"


def test_17_page_run_id_fk_valid(db_conn):
    """Every non-NULL pages.run_id must reference a valid ingestion_runs.id."""
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM pages p
           LEFT JOIN ingestion_runs r ON r.id = p.run_id
           WHERE p.run_id IS NOT NULL AND r.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} pages have invalid run_id (FK violation)"


def test_18_pages_one_run_id_per_doc(db_conn, doc_id_3):
    """All pages for test-3 must reference the same run_id (no stale pages)."""
    rows = db_conn.execute(
        "SELECT DISTINCT run_id FROM pages WHERE doc_id=?", (doc_id_3,)
    ).fetchall()
    run_ids = [r["run_id"] for r in rows if r["run_id"]]
    assert len(run_ids) == 1, (
        f"test-3 pages reference {len(run_ids)} run_ids — stale pages present: {run_ids}"
    )


def test_19_page_ids_are_valid_uuids(db_conn, doc_id_3):
    """All page ids must be valid UUIDs."""
    rows = db_conn.execute(
        "SELECT id FROM pages WHERE doc_id=?", (doc_id_3,)
    ).fetchall()
    for row in rows:
        try:
            uuid.UUID(row["id"])
        except ValueError:
            pytest.fail(f"page id '{row['id']}' is not a valid UUID")


def test_20_two_docs_have_separate_page_sets(db_conn, doc_id_2, doc_id_3):
    """Page IDs for test-2 and test-3 must be completely disjoint."""
    ids_2 = {r["id"] for r in db_conn.execute(
        "SELECT id FROM pages WHERE doc_id=?", (doc_id_2,)
    ).fetchall()}
    ids_3 = {r["id"] for r in db_conn.execute(
        "SELECT id FROM pages WHERE doc_id=?", (doc_id_3,)
    ).fetchall()}
    overlap = ids_2 & ids_3
    assert not overlap, \
        f"{len(overlap)} page IDs appear in both test-2 and test-3"


# ===========================================================================
# PAGE_TEXTS TABLE
# ===========================================================================

def test_21_selected_row_count_equals_page_count(db_conn, doc_id_3):
    """Number of is_selected=1 rows must equal page count for test-3."""
    selected = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM page_texts pt
           JOIN pages p ON p.id = pt.page_id
           WHERE p.doc_id=? AND pt.is_selected=1""",
        (doc_id_3,),
    ).fetchone()["cnt"]
    assert selected == EXPECTED_PAGES_TEST3, (
        f"selected page_texts={selected}, expected {EXPECTED_PAGES_TEST3}"
    )


def test_22_no_page_with_zero_page_texts(db_conn, doc_id_3):
    """Every page must have at least one page_text row."""
    rows = db_conn.execute(
        """SELECT p.page_number, COUNT(pt.id) as cnt
           FROM pages p
           LEFT JOIN page_texts pt ON pt.page_id = p.id
           WHERE p.doc_id=?
           GROUP BY p.id
           HAVING cnt = 0""",
        (doc_id_3,),
    ).fetchall()
    assert not rows, (
        f"{len(rows)} pages have zero page_text rows: "
        f"{[r['page_number'] for r in rows]}"
    )


def test_23_page_texts_strategy_valid_values(db_conn, doc_id_3):
    """All strategy values must be in known set."""
    rows = db_conn.execute(
        """SELECT DISTINCT pt.strategy FROM page_texts pt
           JOIN pages p ON p.id = pt.page_id
           WHERE p.doc_id=?""",
        (doc_id_3,),
    ).fetchall()
    found = {r["strategy"] for r in rows}
    unexpected = found - VALID_STRATEGIES
    assert not unexpected, f"Unexpected page_text strategy values: {unexpected}"


def test_24_page_texts_no_orphans(db_conn):
    """No page_texts row should reference a non-existent page_id."""
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM page_texts pt
           LEFT JOIN pages p ON p.id = pt.page_id
           WHERE p.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} orphaned page_texts rows (invalid page_id)"


def test_25_word_count_consistent_with_text(db_conn, doc_id_3):
    """word_count must equal len(text.split()) for a sample of selected rows."""
    rows = db_conn.execute(
        """SELECT pt.text, pt.word_count, p.page_number
           FROM page_texts pt
           JOIN pages p ON p.id = pt.page_id
           WHERE p.doc_id=? AND pt.is_selected=1
           LIMIT 30""",
        (doc_id_3,),
    ).fetchall()
    for row in rows:
        expected = len(row["text"].split())
        assert row["word_count"] == expected, (
            f"Page {row['page_number']}: word_count={row['word_count']} "
            f"but actual={expected}"
        )


def test_26_char_count_consistent_with_text(db_conn, doc_id_3):
    """char_count must equal len(text) for a sample of selected rows."""
    rows = db_conn.execute(
        """SELECT pt.text, pt.char_count, p.page_number
           FROM page_texts pt
           JOIN pages p ON p.id = pt.page_id
           WHERE p.doc_id=? AND pt.is_selected=1
           LIMIT 30""",
        (doc_id_3,),
    ).fetchall()
    for row in rows:
        expected = len(row["text"])
        assert row["char_count"] == expected, (
            f"Page {row['page_number']}: char_count={row['char_count']} "
            f"but actual={expected}"
        )


# ===========================================================================
# CHUNKS TABLE
# ===========================================================================

def test_27_chunk_count_test3(db_conn, doc_id_3):
    """Total chunks for test-3 must equal parents + children."""
    count = db_conn.execute(
        "SELECT COUNT(*) as cnt FROM chunks WHERE doc_id=?", (doc_id_3,)
    ).fetchone()["cnt"]
    expected = EXPECTED_PARENTS_TEST3 + EXPECTED_CHILDREN_TEST3
    assert count == expected, (
        f"test-3 chunk count={count}, expected {expected}"
    )


def test_28_all_children_embedded(db_conn, doc_id_3):
    """All child chunks must have embedded=1."""
    not_emb = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM chunks
           WHERE doc_id=? AND level='child' AND embedded=0""",
        (doc_id_3,),
    ).fetchone()["cnt"]
    assert not_emb == 0, \
        f"{not_emb} child chunks have embedded=0 for test-3"


def test_29_chunk_doc_id_fk_valid(db_conn):
    """Every chunks.doc_id must reference a valid documents.id."""
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM chunks c
           LEFT JOIN documents d ON d.id = c.doc_id
           WHERE d.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} chunks have invalid doc_id"


def test_30_chunk_page_id_fk_valid(db_conn):
    """Every chunks.page_id must reference a valid pages.id."""
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM chunks c
           LEFT JOIN pages p ON p.id = c.page_id
           WHERE p.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} chunks have invalid page_id"


def test_31_chunk_page_text_id_fk_valid(db_conn):
    """Every chunks.page_text_id must reference a valid page_texts.id."""
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM chunks c
           LEFT JOIN page_texts pt ON pt.id = c.page_text_id
           WHERE pt.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} chunks have invalid page_text_id"


def test_32_chunk_run_id_fk_valid(db_conn):
    """Every non-NULL chunks.run_id must reference a valid ingestion_runs.id."""
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM chunks c
           LEFT JOIN ingestion_runs r ON r.id = c.run_id
           WHERE c.run_id IS NOT NULL AND r.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} chunks have invalid run_id"


def test_33_chunk_strategy_valid_values(db_conn):
    """All chunk strategy values must be in known set."""
    rows = db_conn.execute("SELECT DISTINCT strategy FROM chunks").fetchall()
    found = {r["strategy"] for r in rows}
    unexpected = found - VALID_CHUNK_STRATEGIES
    assert not unexpected, f"Unexpected chunk strategy values: {unexpected}"


def test_34_chunk_level_valid_values(db_conn):
    """All chunk level values must be in known set."""
    rows = db_conn.execute("SELECT DISTINCT level FROM chunks").fetchall()
    found = {r["level"] for r in rows}
    unexpected = found - VALID_CHUNK_LEVELS
    assert not unexpected, f"Unexpected chunk level values: {unexpected}"


def test_35_child_parent_id_fk_valid(db_conn, doc_id_3):
    """Every child chunk's parent_id must reference a parent chunk in DB."""
    parent_ids = {r["id"] for r in db_conn.execute(
        "SELECT id FROM chunks WHERE doc_id=? AND level='parent'", (doc_id_3,)
    ).fetchall()}
    children = db_conn.execute(
        "SELECT id, parent_id FROM chunks WHERE doc_id=? AND level='child'",
        (doc_id_3,),
    ).fetchall()
    missing = [r["id"] for r in children if r["parent_id"] not in parent_ids]
    assert not missing, (
        f"{len(missing)} child chunks have parent_id not in parent chunks"
    )


def test_36_no_chunk_text_empty(db_conn):
    """No chunk should have empty or whitespace-only text."""
    count = db_conn.execute(
        "SELECT COUNT(*) as cnt FROM chunks WHERE trim(text) = ''"
    ).fetchone()["cnt"]
    assert count == 0, f"{count} chunks have empty text"


def test_37_chunk_word_count_positive(db_conn):
    """All chunks must have word_count >= 1."""
    count = db_conn.execute(
        "SELECT COUNT(*) as cnt FROM chunks WHERE word_count < 1"
    ).fetchone()["cnt"]
    assert count == 0, f"{count} chunks have word_count < 1"


def test_38_chunk_isolation_between_docs(db_conn, doc_id_2, doc_id_3):
    """Chunk IDs for test-2 and test-3 must be completely disjoint."""
    ids_2 = {r["id"] for r in db_conn.execute(
        "SELECT id FROM chunks WHERE doc_id=?", (doc_id_2,)
    ).fetchall()}
    ids_3 = {r["id"] for r in db_conn.execute(
        "SELECT id FROM chunks WHERE doc_id=?", (doc_id_3,)
    ).fetchall()}
    overlap = ids_2 & ids_3
    assert not overlap, \
        f"{len(overlap)} chunk IDs appear in both test-2 and test-3"


def test_39_get_chunks_for_document_returns_correct_doc(db, doc_id_2, doc_id_3):
    """get_chunks_for_document must only return chunks for the requested doc."""
    chunks_2 = db.get_chunks_for_document(doc_id_2)
    chunks_3 = db.get_chunks_for_document(doc_id_3)
    assert all(c["doc_id"] == doc_id_2 for c in chunks_2), \
        "get_chunks_for_document(doc_2) returned chunks from another doc"
    assert all(c["doc_id"] == doc_id_3 for c in chunks_3), \
        "get_chunks_for_document(doc_3) returned chunks from another doc"


def test_40_get_chunks_by_ids_returns_correct_rows(db, doc_id_3, db_conn):
    """get_chunks_by_ids must return exactly the requested rows in order."""
    sample = db_conn.execute(
        "SELECT id FROM chunks WHERE doc_id=? AND level='child' LIMIT 5",
        (doc_id_3,),
    ).fetchall()
    ids = [r["id"] for r in sample]
    returned = db.get_chunks_by_ids(ids)
    assert len(returned) == len(ids), \
        f"Requested {len(ids)} chunks, got {len(returned)}"
    assert [c["id"] for c in returned] == ids, \
        "get_chunks_by_ids returned rows in wrong order"


def test_41_get_parent_chunk_returns_correct_parent(db, db_conn, doc_id_3):
    """get_parent_chunk(child_id) must return the correct parent row."""
    child = db_conn.execute(
        """SELECT id, parent_id FROM chunks
           WHERE doc_id=? AND level='child' AND parent_id IS NOT NULL
           LIMIT 1""",
        (doc_id_3,),
    ).fetchone()
    assert child, "No child chunk found for test-3"
    parent = db.get_parent_chunk(child["id"])
    assert parent is not None, \
        f"get_parent_chunk returned None for child {child['id'][:8]}"
    assert parent["id"] == child["parent_id"], (
        f"get_parent_chunk returned wrong parent: "
        f"got {parent['id'][:8]}, expected {child['parent_id'][:8]}"
    )


def test_42_get_parents_by_ids_bulk(db, db_conn, doc_id_3):
    """get_parents_by_ids must return all requested parent rows."""
    sample = db_conn.execute(
        "SELECT id FROM chunks WHERE doc_id=? AND level='parent' LIMIT 5",
        (doc_id_3,),
    ).fetchall()
    ids = [r["id"] for r in sample]
    parents = db.get_parents_by_ids(ids)
    assert len(parents) == len(ids), (
        f"Requested {len(ids)} parents, got {len(parents)}"
    )
    returned_ids = {p["id"] for p in parents}
    assert returned_ids == set(ids), \
        f"get_parents_by_ids returned wrong IDs: {returned_ids} != {set(ids)}"


# ===========================================================================
# INGESTION_RUNS TABLE
# ===========================================================================

def test_43_ingestion_runs_exist_for_both_docs(db_conn, doc_id_2, doc_id_3):
    """At least one ingestion_run must exist for each document."""
    for doc_id, label in [(doc_id_2, "test-2"), (doc_id_3, "test-3")]:
        count = db_conn.execute(
            "SELECT COUNT(*) as cnt FROM ingestion_runs WHERE doc_id=?", (doc_id,)
        ).fetchone()["cnt"]
        assert count >= 1, f"{label}: no ingestion_runs found"


def test_44_latest_run_status_done(db_conn, doc_id_2, doc_id_3):
    """The most recent ingestion_run for each doc must have status='done'."""
    for doc_id, label in [(doc_id_2, "test-2"), (doc_id_3, "test-3")]:
        row = db_conn.execute(
            """SELECT status FROM ingestion_runs
               WHERE doc_id=? ORDER BY started_at DESC LIMIT 1""",
            (doc_id,),
        ).fetchone()
        assert row["status"] == "done", (
            f"{label}: latest run status='{row['status']}', expected 'done'"
        )


def test_45_run_status_valid_values(db_conn):
    """All ingestion_run status values must be in known set."""
    rows = db_conn.execute("SELECT DISTINCT status FROM ingestion_runs").fetchall()
    found = {r["status"] for r in rows}
    unexpected = found - VALID_RUN_STATUSES
    assert not unexpected, f"Unexpected ingestion_run status values: {unexpected}"


def test_46_run_config_json_valid(db_conn, doc_id_3):
    """config_json on ingestion_runs must be valid JSON containing known keys."""
    row = db_conn.execute(
        """SELECT config_json FROM ingestion_runs
           WHERE doc_id=? ORDER BY started_at DESC LIMIT 1""",
        (doc_id_3,),
    ).fetchone()
    assert row["config_json"], "config_json is NULL on latest run"
    try:
        config = json.loads(row["config_json"])
    except json.JSONDecodeError as e:
        pytest.fail(f"config_json is not valid JSON: {e}")
    assert "model" in config, "config_json missing 'model' key"
    assert "chunk_words" in config, "config_json missing 'chunk_words' key"


def test_47_run_finished_at_set_on_done_runs(db_conn):
    """All ingestion_runs with status='done' must have finished_at set."""
    rows = db_conn.execute(
        "SELECT id, finished_at FROM ingestion_runs WHERE status='done'"
    ).fetchall()
    missing = [r["id"] for r in rows if not r["finished_at"]]
    assert not missing, (
        f"{len(missing)} 'done' runs have NULL finished_at"
    )


def test_48_run_doc_id_fk_valid(db_conn):
    """Every ingestion_runs.doc_id must reference a valid documents.id."""
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM ingestion_runs r
           LEFT JOIN documents d ON d.id = r.doc_id
           WHERE d.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} ingestion_runs have invalid doc_id"


# ===========================================================================
# CLEAR AND STATUS METHODS
# ===========================================================================

def test_49_status_method_returns_correct_counts(db):
    """db.status() must return counts consistent with direct SQL queries."""
    status = db.status()
    assert status["documents"] == EXPECTED_TOTAL_DOCS, (
        f"status documents={status['documents']}, expected {EXPECTED_TOTAL_DOCS}"
    )
    assert status["chunks"] > 0, "status chunks=0 — no chunks in DB"
    assert status["embedded_chunks"] > 0, "status embedded_chunks=0"
    assert status["pages"] > 0, "status pages=0"
    assert isinstance(status["document_list"], list), \
        "status document_list is not a list"
    assert len(status["document_list"]) == EXPECTED_TOTAL_DOCS, \
        f"document_list has {len(status['document_list'])} entries"


def test_50_list_documents_returns_both_docs(db, pdf_path_2, pdf_path_3):
    """db.list_documents() must return entries for both test-2 and test-3."""
    docs = db.list_documents()
    filenames = {d["filename"] for d in docs}
    assert pdf_path_2.name in filenames, \
        f"{pdf_path_2.name} not in list_documents() result"
    assert pdf_path_3.name in filenames, \
        f"{pdf_path_3.name} not in list_documents() result"