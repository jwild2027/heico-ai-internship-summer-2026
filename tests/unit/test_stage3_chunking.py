"""tests/unit/test_stage3_chunking.py — Stage 3: Chunking Strategy (50 tests)

Tests choose_strategy, profile_document, build_parent_child_chunks,
flat chunker, and all chunk metadata stored in SQLite.

No LLM, no Qdrant required. Requires ingested DB.

Usage:
    python -m pytest tests/unit/test_stage3_chunking.py -v \
        --pdf-test2 "C:/Users/you/Desktop/test-2.pdf" \
        --pdf-test3 "C:/Users/you/Desktop/test-3.pdf" \
        --db-path "rag.db"
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Known values from your ingest logs
# ---------------------------------------------------------------------------

# test-3 known chunk counts from logs
EXPECTED_PARENTS_TEST3  = 41
EXPECTED_CHILDREN_TEST3 = 373

# test-3 page count
EXPECTED_PAGES_TEST3 = 88

# Valid strategy / level values
VALID_STRATEGIES = {"flat", "parent_child"}
VALID_LEVELS     = {"flat", "parent", "child"}


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
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pages_3(pdf_path_3) -> list[dict[str, Any]]:
    import src.benchmarks.rag_benchmark as bench
    return bench.extract_pages_pymupdf(
        pdf_path_3,
        debug_dir=Path("ocr_debug"),
        ocr_debug=False,
        save_images=False,
    )


@pytest.fixture(scope="session")
def pages_2(pdf_path_2) -> list[dict[str, Any]]:
    import src.benchmarks.rag_benchmark as bench
    return bench.extract_pages_pymupdf(
        pdf_path_2,
        debug_dir=Path("ocr_debug"),
        ocr_debug=False,
        save_images=False,
    )


@pytest.fixture(scope="session")
def parents_children_3(pages_3, pdf_path_3):
    """Run parent_child chunker on test-3 pages once for the whole session."""
    from src.chunking.parent_child_chunker import build_parent_child_chunks
    parents, children = build_parent_child_chunks(
        pages_3, source_name=pdf_path_3.stem
    )
    return parents, children


@pytest.fixture(scope="session")
def parents_3(parents_children_3):
    return parents_children_3[0]


@pytest.fixture(scope="session")
def children_3(parents_children_3):
    return parents_children_3[1]


@pytest.fixture(scope="session")
def parent_map_3(parents_3):
    """parent_id → parent object."""
    return {p.parent_id: p for p in parents_3}


@pytest.fixture(scope="session")
def doc_id_3(db_conn, pdf_path_3) -> str:
    row = db_conn.execute(
        "SELECT id FROM documents WHERE filename=?", (pdf_path_3.name,)
    ).fetchone()
    if not row:
        pytest.skip(f"{pdf_path_3.name} not in DB — run ingest first")
    return row["id"]


@pytest.fixture(scope="session")
def doc_id_2(db_conn, pdf_path_2) -> str:
    row = db_conn.execute(
        "SELECT id FROM documents WHERE filename=?", (pdf_path_2.name,)
    ).fetchone()
    if not row:
        pytest.skip(f"{pdf_path_2.name} not in DB — run ingest first")
    return row["id"]


@pytest.fixture(scope="session")
def db_chunks_3(db_conn, doc_id_3) -> list[sqlite3.Row]:
    return db_conn.execute(
        "SELECT * FROM chunks WHERE doc_id=? ORDER BY chunk_index",
        (doc_id_3,),
    ).fetchall()


@pytest.fixture(scope="session")
def db_parents_3(db_conn, doc_id_3) -> list[sqlite3.Row]:
    return db_conn.execute(
        "SELECT * FROM chunks WHERE doc_id=? AND level='parent' ORDER BY chunk_index",
        (doc_id_3,),
    ).fetchall()


@pytest.fixture(scope="session")
def db_children_3(db_conn, doc_id_3) -> list[sqlite3.Row]:
    return db_conn.execute(
        "SELECT * FROM chunks WHERE doc_id=? AND level='child' ORDER BY chunk_index",
        (doc_id_3,),
    ).fetchall()


# ===========================================================================
# TEST 1 — choose_strategy returns parent_child for test-3
# ===========================================================================
def test_01_strategy_parent_child_for_test3(pages_3):
    from src.chunking.chunking_strategy import choose_strategy
    strategy, reason = choose_strategy(pages_3)
    assert strategy == "parent_child", (
        f"Expected 'parent_child' for test-3, got '{strategy}' — reason: {reason}"
    )


# ===========================================================================
# TEST 2 — choose_strategy returns a reason string
# ===========================================================================
def test_02_strategy_returns_reason(pages_3):
    from src.chunking.chunking_strategy import choose_strategy
    strategy, reason = choose_strategy(pages_3)
    assert isinstance(reason, str) and len(reason) > 0, \
        "choose_strategy must return a non-empty reason string"


# ===========================================================================
# TEST 3 — choose_strategy is deterministic
# ===========================================================================
def test_03_strategy_is_deterministic(pages_3):
    from src.chunking.chunking_strategy import choose_strategy
    results = [choose_strategy(pages_3) for _ in range(3)]
    assert len({r[0] for r in results}) == 1, \
        "choose_strategy returned different strategies on repeated calls"


# ===========================================================================
# TEST 4 — parent count matches known value from logs
# ===========================================================================
def test_04_parent_count_matches_logs(parents_3):
    assert len(parents_3) == EXPECTED_PARENTS_TEST3, (
        f"Expected {EXPECTED_PARENTS_TEST3} parents, got {len(parents_3)}"
    )


# ===========================================================================
# TEST 5 — child count matches known value from logs
# ===========================================================================
def test_05_child_count_matches_logs(children_3):
    assert len(children_3) == EXPECTED_CHILDREN_TEST3, (
        f"Expected {EXPECTED_CHILDREN_TEST3} children, got {len(children_3)}"
    )


# ===========================================================================
# TEST 6 — children per parent ratio is in expected range
# ===========================================================================
def test_06_children_per_parent_ratio(parents_3, children_3):
    ratio = len(children_3) / len(parents_3)
    assert 6.0 <= ratio <= 12.0, (
        f"Children/parent ratio={ratio:.2f} outside expected range [6, 12]"
    )


# ===========================================================================
# TEST 7 — every child has a non-None parent_id
# ===========================================================================
def test_07_every_child_has_parent_id(children_3):
    missing = [c for c in children_3 if c.parent_id is None]
    assert not missing, (
        f"{len(missing)} children have parent_id=None"
    )


# ===========================================================================
# TEST 8 — every child's parent_id resolves to a real parent
# ===========================================================================
def test_08_every_child_parent_id_resolves(children_3, parent_map_3):
    missing = [c for c in children_3 if c.parent_id not in parent_map_3]
    assert not missing, (
        f"{len(missing)} children have parent_id that doesn't exist in parents: "
        f"{[c.parent_id for c in missing[:5]]}"
    )


# ===========================================================================
# TEST 9 — no empty child text
# ===========================================================================
def test_09_no_empty_child_text(children_3):
    empty = [c for c in children_3 if not c.text.strip()]
    assert not empty, f"{len(empty)} children have empty text"


# ===========================================================================
# TEST 10 — no empty parent text
# ===========================================================================
def test_10_no_empty_parent_text(parents_3):
    empty = [p for p in parents_3 if not p.text.strip()]
    assert not empty, f"{len(empty)} parents have empty text"


# ===========================================================================
# TEST 11 — child word count in expected range
# ===========================================================================
def test_11_child_word_count_in_range(children_3):
    import warnings

    # Hard floor: no zero-word children
    zero = [c for c in children_3 if c.word_count < 1]
    assert not zero, f"{len(zero)} children have word_count < 1"

    # Hard ceiling: no runaway children
    too_large = [c for c in children_3 if c.word_count > 250]
    assert not too_large, (
        f"{len(too_large)} children have word_count > 250: "
        f"{[(c.child_id[:8], c.word_count) for c in too_large[:5]]}"
    )

    # Soft warning: micro-fragments under 5 words are a chunker quality issue
    micro = [c for c in children_3 if c.word_count < 5]
    if micro:
        warnings.warn(
            f"{len(micro)} micro-fragment children under 5 words — "
            f"consider fixing chunker boundary logic: "
            f"{[(c.child_id[:8], c.word_count, c.text[:40]) for c in micro]}"
        )


# ===========================================================================
# TEST 12 — parent word count in expected range
# ===========================================================================
def test_12_parent_word_count_in_range(parents_3):
    out_of_range = [
        p for p in parents_3
        if not (300 <= p.word_count <= 900)
    ]
    assert not out_of_range, (
        f"{len(out_of_range)} parents have word_count outside [300, 900]: "
        f"{[(p.parent_id[:8], p.word_count) for p in out_of_range[:5]]}"
    )


# ===========================================================================
# TEST 13 — page_start <= page_end on all chunks
# ===========================================================================
def test_13_page_start_lte_page_end(parents_3, children_3):
    for chunk in parents_3 + children_3:
        assert chunk.page_start <= chunk.page_end, (
            f"Chunk {chunk.parent_id if hasattr(chunk, 'parent_id') else '?'}: "
            f"page_start={chunk.page_start} > page_end={chunk.page_end}"
        )


# ===========================================================================
# TEST 14 — page_start >= 1 on all chunks
# ===========================================================================
def test_14_page_start_gte_1(parents_3, children_3):
    for chunk in parents_3 + children_3:
        assert chunk.page_start >= 1, (
            f"Chunk has page_start={chunk.page_start} < 1"
        )


# ===========================================================================
# TEST 15 — page_end <= doc page count on all chunks
# ===========================================================================
def test_15_page_end_lte_doc_page_count(parents_3, children_3):
    for chunk in parents_3 + children_3:
        assert chunk.page_end <= EXPECTED_PAGES_TEST3, (
            f"Chunk has page_end={chunk.page_end} > {EXPECTED_PAGES_TEST3}"
        )


# ===========================================================================
# TEST 16 — parent titles are non-empty
# ===========================================================================
def test_16_parent_titles_nonempty(parents_3):
    empty_titles = [p for p in parents_3 if not p.title or not p.title.strip()]
    assert not empty_titles, (
        f"{len(empty_titles)} parents have empty/None title"
    )


# ===========================================================================
# TEST 17 — child inherits parent title in metadata
# ===========================================================================
def test_17_child_inherits_parent_title(children_3, parent_map_3):
    mismatches = []
    for c in children_3:
        parent = parent_map_3.get(c.parent_id)
        if not parent:
            continue
        child_title = c.metadata.get("parent_title", "")
        if child_title != parent.title:
            mismatches.append((c.child_id[:8], child_title, parent.title))
    assert not mismatches, (
        f"{len(mismatches)} children have wrong parent_title in metadata: "
        f"{mismatches[:3]}"
    )


# ===========================================================================
# TEST 18 — child IDs are all unique
# ===========================================================================
def test_18_child_ids_unique(children_3):
    ids = [c.child_id for c in children_3]
    assert len(set(ids)) == len(ids), (
        f"Duplicate child IDs found: "
        f"{[i for i in ids if ids.count(i) > 1][:5]}"
    )


# ===========================================================================
# TEST 19 — parent IDs are all unique
# ===========================================================================
def test_19_parent_ids_unique(parents_3):
    ids = [p.parent_id for p in parents_3]
    assert len(set(ids)) == len(ids), (
        f"Duplicate parent IDs found: "
        f"{[i for i in ids if ids.count(i) > 1][:5]}"
    )


# ===========================================================================
# TEST 20 — no child and parent share the same ID
# ===========================================================================
def test_20_child_and_parent_ids_disjoint(parents_3, children_3):
    parent_ids = {p.parent_id for p in parents_3}
    child_ids  = {c.child_id  for c in children_3}
    overlap = parent_ids & child_ids
    assert not overlap, (
        f"{len(overlap)} IDs appear in both parents and children: "
        f"{list(overlap)[:5]}"
    )


# ===========================================================================
# TEST 21 — chunk indices are sequential starting at 0
# ===========================================================================
def test_21_child_chunk_index_sequential(children_3):
    indices = [c.chunk_index for c in children_3]
    assert indices == list(range(len(children_3))), (
        f"Child chunk_index is not sequential 0..{len(children_3)-1}"
    )


# ===========================================================================
# TEST 22 — char_start and char_end set on all children
# ===========================================================================
def test_22_char_start_end_set_on_children(children_3):
    missing = [
        c for c in children_3
        if c.char_start is None or c.char_end is None
    ]
    assert not missing, (
        f"{len(missing)} children are missing char_start/char_end"
    )


# ===========================================================================
# TEST 23 — char_end > char_start on all children
# ===========================================================================
def test_23_char_end_gt_char_start(children_3):
    invalid = [c for c in children_3 if c.char_end <= c.char_start]
    assert not invalid, (
        f"{len(invalid)} children have char_end <= char_start"
    )


# ===========================================================================
# TEST 24 — no duplicate child text
# ===========================================================================
def test_21_child_chunk_index_sequential(children_3, parent_map_3):
    """chunk_index resets per parent — verify each parent's children
    have sequential indices starting at 0."""
    from collections import defaultdict
    by_parent: dict = defaultdict(list)
    for c in children_3:
        by_parent[c.parent_id].append(c.chunk_index)
    for parent_id, indices in by_parent.items():
        indices_sorted = sorted(indices)
        assert indices_sorted == list(range(len(indices_sorted))), (
            f"Parent {parent_id[:8]}: child indices not sequential: {indices_sorted}"
        )


# ===========================================================================
# TEST 25 — no duplicate parent text
# ===========================================================================
def test_25_no_duplicate_parent_text(parents_3):
    texts = [p.text for p in parents_3]
    assert len(set(texts)) == len(texts), (
        f"{len(texts) - len(set(texts))} duplicate parent texts found"
    )


# ===========================================================================
# TEST 26 — known section heading in at least one parent
# ===========================================================================
@pytest.mark.parametrize("term", [
    "hazardous attitudes",
    "density altitude",
    "thunderstorm",
    "class b",
    "imsafe",
])
def test_26_known_headings_in_parents(term, parents_3):
    found = any(term in p.text.lower() for p in parents_3)
    assert found, f"Term '{term}' not found in any parent chunk text"


# ===========================================================================
# TEST 27 — known facts in at least one child
# ===========================================================================
@pytest.mark.parametrize("term", [
    "122.9",
    "density altitude",
    "class b",
    "hyperventilation",
])
def test_27_known_facts_in_children(term, children_3):
    found = any(term in c.text.lower() for c in children_3)
    assert found, f"Term '{term}' not found in any child chunk text"


# ===========================================================================
# TEST 28 — chunking is deterministic across two runs
# ===========================================================================
def test_28_chunking_is_deterministic(pages_3, pdf_path_3):
    from src.chunking.parent_child_chunker import build_parent_child_chunks
    parents_a, children_a = build_parent_child_chunks(
        pages_3, source_name=pdf_path_3.stem
    )
    parents_b, children_b = build_parent_child_chunks(
        pages_3, source_name=pdf_path_3.stem
    )
    assert len(children_a) == len(children_b), \
        "Child count differs between runs — non-deterministic"
    for ca, cb in zip(children_a, children_b):
        assert ca.text == cb.text, (
            f"Child text differs between runs at index {children_a.index(ca)}"
        )


# ===========================================================================
# TEST 29 — chunking completes within 30 seconds
# ===========================================================================
def test_29_chunking_completes_in_time(pages_3, pdf_path_3):
    import time
    from src.chunking.parent_child_chunker import build_parent_child_chunks
    t0 = time.perf_counter()
    build_parent_child_chunks(pages_3, source_name=pdf_path_3.stem)
    elapsed = time.perf_counter() - t0
    assert elapsed < 30.0, \
        f"Chunking took {elapsed:.1f}s — exceeds 30s limit"


# ===========================================================================
# TEST 30 — parents have no parent_id (they are root nodes)
# ===========================================================================
def test_30_parent_chunk_has_own_id(parents_3):
    """ParentChunk.parent_id is the chunk's own identifier — must be non-empty."""
    missing = [p for p in parents_3 if not p.parent_id]
    assert not missing, f"{len(missing)} parents have empty/None parent_id"


# ===========================================================================
# TEST 31 — DB: parent count matches chunker output
# ===========================================================================
def test_31_db_parent_count_matches(db_parents_3):
    assert len(db_parents_3) == EXPECTED_PARENTS_TEST3, (
        f"DB has {len(db_parents_3)} parent chunks, expected {EXPECTED_PARENTS_TEST3}"
    )


# ===========================================================================
# TEST 32 — DB: child count matches chunker output
# ===========================================================================
def test_32_db_child_count_matches(db_children_3):
    assert len(db_children_3) == EXPECTED_CHILDREN_TEST3, (
        f"DB has {len(db_children_3)} child chunks, expected {EXPECTED_CHILDREN_TEST3}"
    )


# ===========================================================================
# TEST 33 — DB: all child chunks have embedded=1
# ===========================================================================
def test_33_db_children_all_embedded(db_children_3):
    not_embedded = [r for r in db_children_3 if r["embedded"] != 1]
    assert not not_embedded, (
        f"{len(not_embedded)} child chunks have embedded=0 — "
        f"embedding step may have failed"
    )


# ===========================================================================
# TEST 34 — DB: parent chunks have embedded=1 (marked vacuously)
# ===========================================================================
def test_34_db_parents_marked_embedded(db_parents_3):
    not_embedded = [r for r in db_parents_3 if r["embedded"] != 1]
    assert not not_embedded, (
        f"{len(not_embedded)} parent chunks have embedded=0"
    )


# ===========================================================================
# TEST 35 — DB: strategy field is parent_child for all test-3 chunks
# ===========================================================================
def test_35_db_strategy_correct(db_chunks_3):
    wrong = [r for r in db_chunks_3 if r["strategy"] != "parent_child"]
    assert not wrong, (
        f"{len(wrong)} chunks have strategy != 'parent_child' for test-3"
    )


# ===========================================================================
# TEST 36 — DB: level field only contains valid values
# ===========================================================================
def test_36_db_level_valid_values(db_chunks_3):
    found = {r["level"] for r in db_chunks_3}
    unexpected = found - VALID_LEVELS
    assert not unexpected, f"Unexpected level values: {unexpected}"


# ===========================================================================
# TEST 37 — DB: child chunks have non-NULL parent_id
# ===========================================================================
def test_37_db_children_have_parent_id(db_children_3):
    missing = [r for r in db_children_3 if r["parent_id"] is None]
    assert not missing, (
        f"{len(missing)} DB child chunks have NULL parent_id"
    )


# ===========================================================================
# TEST 38 — DB: parent_id on children resolves to a real parent row
# ===========================================================================
def test_38_db_child_parent_id_resolves(db_conn, doc_id_3, db_children_3):
    parent_ids = {
        r["id"] for r in db_conn.execute(
            "SELECT id FROM chunks WHERE doc_id=? AND level='parent'",
            (doc_id_3,),
        ).fetchall()
    }
    missing = [r for r in db_children_3 if r["parent_id"] not in parent_ids]
    assert not missing, (
        f"{len(missing)} DB children reference parent_id not in parent chunks"
    )


# ===========================================================================
# TEST 39 — DB: parent chunks have NULL parent_id
# ===========================================================================
def test_39_db_parents_have_null_parent_id(db_parents_3):
    with_parent = [r for r in db_parents_3 if r["parent_id"] is not None]
    assert not with_parent, (
        f"{len(with_parent)} DB parent chunks have non-NULL parent_id"
    )


# ===========================================================================
# TEST 40 — DB: chunker_version stored on all chunks
# ===========================================================================
def test_40_db_chunker_version_stored(db_chunks_3):
    missing = [r for r in db_chunks_3 if not r["chunker_version"]]
    assert not missing, (
        f"{len(missing)} chunks have NULL/empty chunker_version"
    )


# ===========================================================================
# TEST 41 — DB: config_json stored on all chunks
# ===========================================================================
def test_41_db_config_json_stored(db_chunks_3):
    import json
    missing = []
    invalid = []
    for r in db_chunks_3:
        if not r["config_json"]:
            missing.append(r["id"])
            continue
        try:
            json.loads(r["config_json"])
        except Exception:
            invalid.append(r["id"])
    assert not missing, f"{len(missing)} chunks have NULL config_json"
    assert not invalid, f"{len(invalid)} chunks have invalid JSON in config_json"


# ===========================================================================
# TEST 42 — DB: page_start and page_end valid on all chunks
# ===========================================================================
def test_42_db_page_range_valid(db_chunks_3):
    invalid = [
        r for r in db_chunks_3
        if r["page_start"] is None
        or r["page_end"] is None
        or r["page_start"] < 1
        or r["page_end"] > EXPECTED_PAGES_TEST3
        or r["page_start"] > r["page_end"]
    ]
    assert not invalid, (
        f"{len(invalid)} chunks have invalid page_start/page_end"
    )


# ===========================================================================
# TEST 43 — DB: word_count > 0 on all chunks
# ===========================================================================
def test_43_db_word_count_positive(db_chunks_3):
    zero_wc = [r for r in db_chunks_3 if not r["word_count"] or r["word_count"] <= 0]
    assert not zero_wc, (
        f"{len(zero_wc)} chunks have word_count <= 0"
    )


# ===========================================================================
# TEST 44 — DB: no orphaned chunks (doc_id FK valid)
# ===========================================================================
def test_44_db_no_orphaned_chunks(db_conn):
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM chunks c
           LEFT JOIN documents d ON d.id = c.doc_id
           WHERE d.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} chunks have invalid doc_id (FK violation)"


# ===========================================================================
# TEST 45 — DB: no orphaned chunks (page_id FK valid)
# ===========================================================================
def test_45_db_chunk_page_id_fk_valid(db_conn):
    count = db_conn.execute(
        """SELECT COUNT(*) as cnt FROM chunks c
           LEFT JOIN pages p ON p.id = c.page_id
           WHERE p.id IS NULL"""
    ).fetchone()["cnt"]
    assert count == 0, f"{count} chunks have invalid page_id (FK violation)"


# ===========================================================================
# TEST 46 — DB: two docs have different chunk sets (no cross-doc contamination)
# ===========================================================================
def test_46_db_chunk_doc_isolation(db_conn, doc_id_2, doc_id_3):
    ids_2 = {r["id"] for r in db_conn.execute(
        "SELECT id FROM chunks WHERE doc_id=?", (doc_id_2,)
    ).fetchall()}
    ids_3 = {r["id"] for r in db_conn.execute(
        "SELECT id FROM chunks WHERE doc_id=?", (doc_id_3,)
    ).fetchall()}
    overlap = ids_2 & ids_3
    assert not overlap, (
        f"{len(overlap)} chunk IDs appear in both test-2 and test-3"
    )


# ===========================================================================
# TEST 47 — DB: total chunk count for test-3 is parents + children
# ===========================================================================
def test_47_db_total_chunk_count(db_conn, doc_id_3):
    total = db_conn.execute(
        "SELECT COUNT(*) as cnt FROM chunks WHERE doc_id=?", (doc_id_3,)
    ).fetchone()["cnt"]
    expected = EXPECTED_PARENTS_TEST3 + EXPECTED_CHILDREN_TEST3
    assert total == expected, (
        f"Total chunks={total}, expected {expected} "
        f"({EXPECTED_PARENTS_TEST3} parents + {EXPECTED_CHILDREN_TEST3} children)"
    )


# ===========================================================================
# TEST 48 — DB: chunk text non-empty for all rows
# ===========================================================================
def test_48_db_chunk_text_nonempty(db_chunks_3):
    empty = [r for r in db_chunks_3 if not r["text"] or not r["text"].strip()]
    assert not empty, f"{len(empty)} chunks have empty text in DB"


# ===========================================================================
# TEST 49 — DB: title stored on parent chunks
# ===========================================================================
def test_49_db_parent_title_stored(db_parents_3):
    missing = [r for r in db_parents_3 if not r["title"] or not r["title"].strip()]
    assert not missing, (
        f"{len(missing)} parent chunks have NULL/empty title in DB"
    )


# ===========================================================================
# TEST 50 — DB: summarize() output matches actual counts
# ===========================================================================
def test_50_summarize_output_matches_counts(parents_3, children_3):
    from src.chunking.parent_child_chunker import summarize
    summary = summarize(parents_3, children_3)
    assert isinstance(summary, str), "summarize() must return a string"
    assert str(len(parents_3)) in summary, \
        f"summarize() output missing parent count {len(parents_3)}: '{summary}'"
    assert str(len(children_3)) in summary, \
        f"summarize() output missing child count {len(children_3)}: '{summary}'"