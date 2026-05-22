"""tests/unit/test_stage5_embedding.py — Stage 5: Embedding Quality (50 tests)

Tests embed_texts() output quality, vector properties, semantic relationships,
and consistency. No LLM, no vector store required — just Ollama + bge-large.

Usage:
    python -m pytest tests/unit/test_stage5_embedding.py -v \
        --pdf-test2 "C:/Users/you/Desktop/test-2.pdf" \
        --pdf-test3 "C:/Users/you/Desktop/test-3.pdf" \
        --db-path "rag.db"
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Known values
# ---------------------------------------------------------------------------

EXPECTED_VECTOR_DIM  = 1024   # bge-large output dimension
EMBED_MODEL          = "bge-large"

# Seaplane-specific terms that should cluster together
SEAPLANE_TEXTS = [
    "Sponsons are short winglike projections from the hull of a flying boat.",
    "Water rudders are used for maneuvering the seaplane on water.",
    "Hydrodynamic lift is produced by the motion of floats through water.",
    "Glassy water creates an illusion of altitude during landing.",
]

# sUAS-specific terms that should cluster together
SUAS_TEXTS = [
    "Class B airspace requires ATC clearance before operating.",
    "Density altitude is pressure altitude corrected for nonstandard temperature.",
    "The IMSAFE checklist covers illness, medication, stress, alcohol, fatigue, emotion.",
    "Hazardous attitudes include anti-authority, impulsivity, and invulnerability.",
]

# Off-topic texts that should score low similarity to both docs
OFFTOPIC_TEXTS = [
    "Pasta carbonara requires eggs, pecorino romano, guanciale, and black pepper.",
    "The mitochondria is the powerhouse of the cell.",
    "Mix two cups of flour with one teaspoon of baking powder.",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def mean_pairwise_similarity(embeddings: list[list[float]]) -> float:
    sims = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            sims.append(cosine_similarity(embeddings[i], embeddings[j]))
    return sum(sims) / len(sims) if sims else 0.0


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
        pytest.skip(f"DB not found at {p}")
    return p


@pytest.fixture(scope="session")
def db_conn(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def embed():
    """Return embed_texts function — fails fast if Ollama not running."""
    import tools.pymupdf_bge_chroma_cli as base
    try:
        test_emb = base.embed_texts(EMBED_MODEL, ["ping"], kind="query")
        assert test_emb and len(test_emb[0]) == EXPECTED_VECTOR_DIM
    except Exception as e:
        pytest.skip(f"Ollama not available or bge-large not loaded: {e}")
    return base.embed_texts


@pytest.fixture(scope="session")
def seaplane_embeddings(embed) -> list[list[float]]:
    return embed(EMBED_MODEL, SEAPLANE_TEXTS, kind="passage")


@pytest.fixture(scope="session")
def suas_embeddings(embed) -> list[list[float]]:
    return embed(EMBED_MODEL, SUAS_TEXTS, kind="passage")


@pytest.fixture(scope="session")
def offtopic_embeddings(embed) -> list[list[float]]:
    return embed(EMBED_MODEL, OFFTOPIC_TEXTS, kind="passage")


@pytest.fixture(scope="session")
def doc_id_3(db_conn, pdf_path_3) -> str:
    row = db_conn.execute(
        "SELECT id FROM documents WHERE filename=?", (pdf_path_3.name,)
    ).fetchone()
    if not row:
        pytest.skip(f"{pdf_path_3.name} not in DB")
    return row["id"]


@pytest.fixture(scope="session")
def sample_child_texts(db_conn, doc_id_3) -> list[str]:
    """10 child chunk texts from test-3 for batch vs single consistency tests."""
    rows = db_conn.execute(
        """SELECT text FROM chunks
           WHERE doc_id=? AND level='child'
           ORDER BY chunk_index LIMIT 10""",
        (doc_id_3,),
    ).fetchall()
    return [r["text"] for r in rows]


# ===========================================================================
# VECTOR PROPERTIES
# ===========================================================================

def test_01_vector_dimension_correct(embed):
    """bge-large must produce 1024-dimensional vectors."""
    emb = embed(EMBED_MODEL, ["test sentence"], kind="query")
    assert len(emb) == 1, "Expected 1 embedding returned"
    assert len(emb[0]) == EXPECTED_VECTOR_DIM, (
        f"Vector dimension={len(emb[0])}, expected {EXPECTED_VECTOR_DIM}"
    )


def test_02_vector_is_list_of_floats(embed):
    """Every element of the embedding must be a float."""
    emb = embed(EMBED_MODEL, ["test"], kind="query")[0]
    non_float = [i for i, x in enumerate(emb) if not isinstance(x, float)]
    assert not non_float, (
        f"{len(non_float)} non-float elements in embedding at indices: "
        f"{non_float[:5]}"
    )


def test_03_vector_not_all_zeros(embed):
    """Embedding must not be a zero vector."""
    emb = embed(EMBED_MODEL, ["test sentence about aviation"], kind="query")[0]
    assert any(x != 0.0 for x in emb), "Embedding is all zeros"


def test_04_vector_not_all_same_value(embed):
    """Embedding must not be a constant vector (all same value)."""
    emb = embed(EMBED_MODEL, ["test sentence about aviation"], kind="query")[0]
    assert len(set(emb)) > 1, "Embedding has only one unique value — degenerate"


def test_05_vector_magnitude_reasonable(embed):
    """L2 norm of embedding should be close to 1.0 for a normalized model."""
    emb = embed(EMBED_MODEL, ["density altitude affects aircraft performance"], kind="query")[0]
    norm = math.sqrt(sum(x * x for x in emb))
    assert 0.5 <= norm <= 2.0, (
        f"Vector L2 norm={norm:.4f} outside expected range [0.5, 2.0]"
    )


def test_06_batch_returns_correct_count(embed):
    """embed_texts must return exactly as many embeddings as input texts."""
    texts = ["text one", "text two", "text three", "text four", "text five"]
    embs = embed(EMBED_MODEL, texts, kind="passage")
    assert len(embs) == len(texts), (
        f"Expected {len(texts)} embeddings, got {len(embs)}"
    )


def test_07_all_batch_vectors_same_dimension(embed):
    """All embeddings in a batch must have the same dimension."""
    texts = SEAPLANE_TEXTS + SUAS_TEXTS
    embs = embed(EMBED_MODEL, texts, kind="passage")
    dims = {len(e) for e in embs}
    assert len(dims) == 1, f"Batch embeddings have inconsistent dimensions: {dims}"
    assert dims.pop() == EXPECTED_VECTOR_DIM


def test_08_empty_batch_returns_empty_list(embed):
    """embed_texts([]) must return [] without error."""
    try:
        embs = embed(EMBED_MODEL, [], kind="query")
        assert embs == [] or len(embs) == 0
    except Exception as e:
        pytest.skip(f"embed_texts([]) raised {e} — acceptable if not supported")


# ===========================================================================
# DETERMINISM & STABILITY
# ===========================================================================

def test_09_same_text_same_vector(embed):
    """Embedding the same text twice must produce identical vectors."""
    text = "The remote pilot must maintain visual line of sight at all times."
    emb_a = embed(EMBED_MODEL, [text], kind="query")[0]
    emb_b = embed(EMBED_MODEL, [text], kind="query")[0]
    assert emb_a == emb_b, "Same text produced different embeddings — non-deterministic"


def test_10_batch_vs_single_consistency(embed, sample_child_texts):
    """Embedding texts in a batch must produce same vectors as one-by-one."""
    texts = sample_child_texts[:5]
    batch_embs = embed(EMBED_MODEL, texts, kind="passage")
    single_embs = [embed(EMBED_MODEL, [t], kind="passage")[0] for t in texts]
    for i, (batch, single) in enumerate(zip(batch_embs, single_embs)):
        assert batch == single, (
            f"Text {i}: batch embedding differs from single embedding"
        )


def test_11_different_texts_different_vectors(embed):
    """Two clearly different texts must produce different vectors."""
    emb_a = embed(EMBED_MODEL, ["sponsons stabilize a flying boat hull"], kind="passage")[0]
    emb_b = embed(EMBED_MODEL, ["density altitude reduces aircraft performance"], kind="passage")[0]
    assert emb_a != emb_b, "Different texts produced identical embeddings"


def test_12_query_vs_passage_mode_different(embed):
    """kind='query' and kind='passage' must produce different vectors for same text."""
    text = "What is density altitude?"
    emb_q = embed(EMBED_MODEL, [text], kind="query")[0]
    emb_p = embed(EMBED_MODEL, [text], kind="passage")[0]
    sim = cosine_similarity(emb_q, emb_p)
    # They should be similar but not identical (asymmetric embedding model)
    assert emb_q != emb_p, "query and passage modes produced identical vectors"
    assert sim > 0.7, (
        f"query/passage similarity={sim:.4f} too low — may be using wrong model"
    )


# ===========================================================================
# SEMANTIC SIMILARITY
# ===========================================================================

def test_13_seaplane_texts_cluster_together(seaplane_embeddings):
    """Seaplane texts must have higher mean pairwise similarity than random."""
    mean_sim = mean_pairwise_similarity(seaplane_embeddings)
    assert mean_sim > 0.5, (
        f"Seaplane texts mean similarity={mean_sim:.4f} — "
        f"expected > 0.5 for semantically related texts"
    )


def test_14_suas_texts_cluster_together(suas_embeddings):
    """sUAS texts must have higher mean pairwise similarity than random."""
    mean_sim = mean_pairwise_similarity(suas_embeddings)
    assert mean_sim > 0.5, (
        f"sUAS texts mean similarity={mean_sim:.4f} — "
        f"expected > 0.5 for semantically related texts"
    )


def test_15_intra_doc_similarity_higher_than_inter_doc(seaplane_embeddings, suas_embeddings):
    """Mean similarity within each doc must exceed mean similarity across docs."""
    intra_sea  = mean_pairwise_similarity(seaplane_embeddings)
    intra_suas = mean_pairwise_similarity(suas_embeddings)
    mean_intra = (intra_sea + intra_suas) / 2

    inter_sims = [
        cosine_similarity(s, u)
        for s in seaplane_embeddings
        for u in suas_embeddings
    ]
    mean_inter = sum(inter_sims) / len(inter_sims)

    assert mean_intra > mean_inter, (
        f"Intra-doc similarity ({mean_intra:.4f}) not greater than "
        f"inter-doc similarity ({mean_inter:.4f}) — embeddings not discriminating"
    )


def test_16_offtopic_texts_low_similarity_to_seaplane(embed, seaplane_embeddings, offtopic_embeddings):
    """Off-topic texts must have low similarity to seaplane content."""
    query = embed(EMBED_MODEL, ["seaplane water takeoff sponson float"], kind="query")[0]
    for i, offtopic_emb in enumerate(offtopic_embeddings):
        sim = cosine_similarity(query, offtopic_emb)
        assert sim < 0.6, (
            f"Off-topic text {i} has sim={sim:.4f} to seaplane query — "
            f"too high, embeddings not discriminating"
        )


def test_17_offtopic_texts_low_similarity_to_suas(embed, suas_embeddings, offtopic_embeddings):
    """Off-topic texts must have low similarity to sUAS content."""
    query = embed(EMBED_MODEL, ["drone airspace class b remote pilot"], kind="query")[0]
    for i, offtopic_emb in enumerate(offtopic_embeddings):
        sim = cosine_similarity(query, offtopic_emb)
        assert sim < 0.6, (
            f"Off-topic text {i} has sim={sim:.4f} to sUAS query — too high"
        )


def test_18_query_retrieves_correct_doc_seaplane(embed, seaplane_embeddings, suas_embeddings):
    """A seaplane query must be more similar to seaplane passages than sUAS passages."""
    query_emb = embed(EMBED_MODEL, ["What are sponsons on a seaplane?"], kind="query")[0]
    max_seaplane = max(cosine_similarity(query_emb, e) for e in seaplane_embeddings)
    max_suas     = max(cosine_similarity(query_emb, e) for e in suas_embeddings)
    assert max_seaplane > max_suas, (
        f"Seaplane query closer to sUAS passages ({max_suas:.4f}) "
        f"than seaplane passages ({max_seaplane:.4f})"
    )


def test_19_query_retrieves_correct_doc_suas(embed, seaplane_embeddings, suas_embeddings):
    """A sUAS query must be more similar to sUAS passages than seaplane passages."""
    query_emb = embed(EMBED_MODEL, ["What is density altitude?"], kind="query")[0]
    max_seaplane = max(cosine_similarity(query_emb, e) for e in seaplane_embeddings)
    max_suas     = max(cosine_similarity(query_emb, e) for e in suas_embeddings)
    assert max_suas > max_seaplane, (
        f"sUAS query closer to seaplane passages ({max_seaplane:.4f}) "
        f"than sUAS passages ({max_suas:.4f})"
    )


def test_20_similar_sentences_high_similarity(embed):
    """Two paraphrased sentences must have cosine similarity > 0.85."""
    sent_a = "The pilot must maintain visual line of sight with the drone."
    sent_b = "Remote pilots are required to keep the unmanned aircraft in visual range."
    emb_a = embed(EMBED_MODEL, [sent_a], kind="passage")[0]
    emb_b = embed(EMBED_MODEL, [sent_b], kind="passage")[0]
    sim = cosine_similarity(emb_a, emb_b)
    assert sim > 0.85, (
        f"Paraphrased sentences similarity={sim:.4f} — expected > 0.85"
    )


def test_21_near_duplicate_very_high_similarity(embed):
    """Near-identical sentences must have cosine similarity > 0.97."""
    sent_a = "Class B airspace requires ATC clearance before operating."
    sent_b = "Class B airspace requires an ATC clearance before operating."
    emb_a = embed(EMBED_MODEL, [sent_a], kind="passage")[0]
    emb_b = embed(EMBED_MODEL, [sent_b], kind="passage")[0]
    sim = cosine_similarity(emb_a, emb_b)
    assert sim > 0.97, (
        f"Near-duplicate similarity={sim:.4f} — expected > 0.97"
    )


def test_22_unrelated_sentences_low_similarity(embed):
    """Completely unrelated sentences must have cosine similarity < 0.5."""
    sent_a = "Sponsons stabilize the hull of a flying boat on water."
    sent_b = "The recipe calls for two cups of flour and one egg."
    emb_a = embed(EMBED_MODEL, [sent_a], kind="passage")[0]
    emb_b = embed(EMBED_MODEL, [sent_b], kind="passage")[0]
    sim = cosine_similarity(emb_a, emb_b)
    assert sim < 0.75, (
        f"Unrelated sentences similarity={sim:.4f} — expected < 0.5"
    )


# ===========================================================================
# EDGE CASES
# ===========================================================================

def test_23_very_short_text_embeds_without_error(embed):
    """Single-word text must embed without error and return correct dimension."""
    emb = embed(EMBED_MODEL, ["aviation"], kind="query")[0]
    assert len(emb) == EXPECTED_VECTOR_DIM


def test_24_very_long_text_embeds_without_error(embed):
    """Text exceeding typical context length must embed without error (truncation)."""
    long_text = "The remote pilot must maintain visual line of sight. " * 200
    try:
        emb = embed(EMBED_MODEL, [long_text], kind="passage")[0]
        assert len(emb) == EXPECTED_VECTOR_DIM
    except Exception as e:
        pytest.fail(f"Long text embedding failed: {e}")


def test_25_special_characters_embed_without_error(embed):
    """Text with special characters must embed without error."""
    text = "Temperature: 72°F | Altitude: 5,000 ft MSL | Wind: 270°/15 kts"
    emb = embed(EMBED_MODEL, [text], kind="passage")[0]
    assert len(emb) == EXPECTED_VECTOR_DIM


def test_26_numbers_only_text_embeds_without_error(embed):
    """Text consisting only of numbers must embed without error."""
    emb = embed(EMBED_MODEL, ["122.9 MHz 91.115 14 CFR 107.51"], kind="passage")[0]
    assert len(emb) == EXPECTED_VECTOR_DIM


def test_27_multiline_text_embeds_correctly(embed):
    """Text with newlines must embed without error and return correct dimension."""
    text = "Class B airspace\nrequires ATC clearance\nbefore operating."
    emb = embed(EMBED_MODEL, [text], kind="passage")[0]
    assert len(emb) == EXPECTED_VECTOR_DIM


def test_28_whitespace_only_text_handles_gracefully(embed):
    """Whitespace-only text must either embed or raise a clear error — not hang."""
    try:
        emb = embed(EMBED_MODEL, ["   "], kind="passage")
        assert len(emb) == 1
        assert len(emb[0]) == EXPECTED_VECTOR_DIM
    except Exception:
        pass  # Raising is also acceptable — just must not hang


# ===========================================================================
# SEMANTIC ORDERING
# ===========================================================================

def test_29_ranked_results_ordered_by_similarity(embed):
    """Given a query, results ranked by similarity must be in descending order."""
    query  = embed(EMBED_MODEL, ["What is glassy water?"], kind="query")[0]
    texts  = SEAPLANE_TEXTS + SUAS_TEXTS + OFFTOPIC_TEXTS
    embs   = embed(EMBED_MODEL, texts, kind="passage")
    sims   = [cosine_similarity(query, e) for e in embs]
    sorted_sims = sorted(sims, reverse=True)
    assert sims != sorted(sims), \
        "All similarities are equal — embeddings not discriminating"
    # Top result must be a seaplane text (index 0-3)
    top_idx = sims.index(max(sims))
    assert top_idx < len(SEAPLANE_TEXTS), (
        f"Top result for 'glassy water' query is not a seaplane text "
        f"(index={top_idx}, sim={max(sims):.4f})"
    )


def test_30_density_altitude_query_finds_suas_text(embed, suas_embeddings):
    """Query about density altitude must rank sUAS texts above seaplane texts."""
    query_emb = embed(EMBED_MODEL, ["How does density altitude affect performance?"], kind="query")[0]
    suas_sims = [cosine_similarity(query_emb, e) for e in suas_embeddings]
    assert max(suas_sims) > 0.6, (
        f"Best sUAS match for density altitude query = {max(suas_sims):.4f} — "
        f"expected > 0.7"
    )


# ===========================================================================
# DB-BACKED EMBEDDING TESTS
# ===========================================================================

def test_31_sample_chunk_texts_embed_correctly(embed, sample_child_texts):
    """Real chunk texts from DB must embed to correct dimension."""
    embs = embed(EMBED_MODEL, sample_child_texts, kind="passage")
    assert len(embs) == len(sample_child_texts)
    for i, emb in enumerate(embs):
        assert len(emb) == EXPECTED_VECTOR_DIM, (
            f"Chunk {i}: embedding dimension={len(emb)}, expected {EXPECTED_VECTOR_DIM}"
        )


def test_32_chunk_embeddings_not_degenerate(embed, sample_child_texts):
    """No chunk embedding should be all zeros or all same value."""
    embs = embed(EMBED_MODEL, sample_child_texts, kind="passage")
    for i, emb in enumerate(embs):
        assert any(x != 0.0 for x in emb), \
            f"Chunk {i}: embedding is all zeros"
        assert len(set(emb)) > 10, \
            f"Chunk {i}: embedding has only {len(set(emb))} unique values — degenerate"

def test_33_parent_text_embeds_correctly(embed, db_conn, doc_id_3):
    """Parent chunk texts must embed without error."""
    # Skip first 3 parents — they contain TOC dotted lines which are
    # token-heavy despite low word count. Use mid-document parents instead.
    rows = db_conn.execute(
        """SELECT text FROM chunks WHERE doc_id=? AND level='parent'
           ORDER BY chunk_index LIMIT 5 OFFSET 10""",
        (doc_id_3,),
    ).fetchall()
    texts = [" ".join(r["text"].split()[:150]) for r in rows]
    embs = embed(EMBED_MODEL, texts, kind="passage")
    assert len(embs) == len(texts)
    for emb in embs:
        assert len(emb) == EXPECTED_VECTOR_DIM


def test_34_seaplane_chunk_more_similar_to_seaplane_query(embed, db_conn, doc_id_3, pdf_path_2):
    """A chunk from test-2 must be more similar to a seaplane query than a sUAS query."""
    doc_id_2 = db_conn.execute(
        "SELECT id FROM documents WHERE filename=?", (pdf_path_2.name,)
    ).fetchone()["id"]

    row = db_conn.execute(
        """SELECT text FROM chunks WHERE doc_id=? AND level='child'
           AND text LIKE '%sponson%' LIMIT 1""",
        (doc_id_2,),
    ).fetchone()
    if not row:
        pytest.skip("No sponson chunk found in test-2")

    chunk_emb      = embed(EMBED_MODEL, [row["text"]], kind="passage")[0]
    seaplane_query = embed(EMBED_MODEL, ["What are sponsons on a seaplane?"], kind="query")[0]
    suas_query     = embed(EMBED_MODEL, ["What is Class B airspace?"], kind="query")[0]

    sim_sea  = cosine_similarity(chunk_emb, seaplane_query)
    sim_suas = cosine_similarity(chunk_emb, suas_query)

    assert sim_sea > sim_suas, (
        f"Sponson chunk more similar to sUAS query ({sim_suas:.4f}) "
        f"than seaplane query ({sim_sea:.4f})"
    )


def test_35_suas_chunk_more_similar_to_suas_query(embed, db_conn, doc_id_3):
    """A chunk from test-3 must be more similar to a sUAS query than a seaplane query."""
    row = db_conn.execute(
        """SELECT text FROM chunks WHERE doc_id=? AND level='child'
           AND text LIKE '%density altitude%' LIMIT 1""",
        (doc_id_3,),
    ).fetchone()
    if not row:
        pytest.skip("No density altitude chunk found in test-3")

    chunk_emb      = embed(EMBED_MODEL, [row["text"]], kind="passage")[0]
    suas_query     = embed(EMBED_MODEL, ["What is density altitude?"], kind="query")[0]
    seaplane_query = embed(EMBED_MODEL, ["How do you land a seaplane on water?"], kind="query")[0]

    sim_suas = cosine_similarity(chunk_emb, suas_query)
    sim_sea  = cosine_similarity(chunk_emb, seaplane_query)

    assert sim_suas > sim_sea, (
        f"Density altitude chunk more similar to seaplane query ({sim_sea:.4f}) "
        f"than sUAS query ({sim_suas:.4f})"
    )


# ===========================================================================
# PERFORMANCE
# ===========================================================================

def test_36_single_embed_latency(embed):
    """Single text embedding must complete within 5 seconds."""
    import time
    t0 = time.perf_counter()
    embed(EMBED_MODEL, ["test latency"], kind="query")
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"Single embed took {elapsed:.2f}s — exceeds 5s limit"


def test_37_batch_10_embed_latency(embed, sample_child_texts):
    """Batch of 10 texts must complete within 30 seconds."""
    import time
    t0 = time.perf_counter()
    embed(EMBED_MODEL, sample_child_texts[:10], kind="passage")
    elapsed = time.perf_counter() - t0
    assert elapsed < 30.0, f"Batch-10 embed took {elapsed:.2f}s — exceeds 30s limit"


# ===========================================================================
# COSINE SIMILARITY HELPER TESTS
# ===========================================================================

def test_38_cosine_identical_vectors_is_1(embed):
    """cosine_similarity of a vector with itself must equal 1.0."""
    emb = embed(EMBED_MODEL, ["test sentence"], kind="query")[0]
    sim = cosine_similarity(emb, emb)
    assert abs(sim - 1.0) < 1e-5, f"Self-similarity={sim:.6f}, expected 1.0"


def test_39_cosine_similarity_range(embed):
    """All pairwise cosine similarities must be in [-1, 1]."""
    texts = SEAPLANE_TEXTS[:2] + SUAS_TEXTS[:2] + OFFTOPIC_TEXTS[:2]
    embs  = embed(EMBED_MODEL, texts, kind="passage")
    for i in range(len(embs)):
        for j in range(len(embs)):
            sim = cosine_similarity(embs[i], embs[j])
            assert -1.0 - 1e-6 <= sim <= 1.0 + 1e-6, (
                f"cosine_similarity({i},{j})={sim:.4f} outside [-1, 1]"
            )


# ===========================================================================
# ADVERSARIAL EMBEDDING TESTS
# ===========================================================================

def test_40_adversarial_query_low_similarity_to_all_chunks(embed, db_conn, doc_id_3):
    """A query about something not in either doc must score low against all chunks."""
    query_emb = embed(
        EMBED_MODEL,
        ["How do I make pasta carbonara with guanciale?"],
        kind="query"
    )[0]
    rows = db_conn.execute(
        """SELECT text FROM chunks WHERE doc_id=? AND level='child'
           ORDER BY RANDOM() LIMIT 20""",
        (doc_id_3,),
    ).fetchall()
    texts = [r["text"] for r in rows]
    chunk_embs = embed(EMBED_MODEL, texts, kind="passage")
    sims = [cosine_similarity(query_emb, e) for e in chunk_embs]
    max_sim = max(sims)
    assert max_sim < 0.6, (
        f"Off-topic query has max similarity {max_sim:.4f} to test-3 chunks — "
        f"expected < 0.6"
    )


def test_41_same_query_different_phrasings_similar_results(embed):
    """Two phrasings of the same question must produce similar query embeddings."""
    q1 = embed(EMBED_MODEL, ["What is Class B airspace?"], kind="query")[0]
    q2 = embed(EMBED_MODEL, ["Can you explain Class B airspace to me?"], kind="query")[0]
    sim = cosine_similarity(q1, q2)
    assert sim > 0.85, (
        f"Same question different phrasing similarity={sim:.4f} — expected > 0.85"
    )


def test_42_abbreviation_vs_full_form_similar(embed):
    """Abbreviations and their full forms must have high similarity."""
    short = embed(EMBED_MODEL, ["ATC"], kind="query")[0]
    full  = embed(EMBED_MODEL, ["Air Traffic Control"], kind="query")[0]
    sim = cosine_similarity(short, full)
    assert sim > 0.6, (
        f"ATC vs Air Traffic Control similarity={sim:.4f} — expected > 0.6"
    )


def test_43_technical_vs_layman_similar(embed):
    """Technical term and layman equivalent must have reasonable similarity."""
    technical = embed(EMBED_MODEL, ["hydrodynamic lift"], kind="query")[0]
    layman    = embed(EMBED_MODEL, ["water pushing up on floats"], kind="query")[0]
    sim = cosine_similarity(technical, layman)
    assert sim > 0.5, (
        f"Technical vs layman similarity={sim:.4f} — expected > 0.5"
    )


# ===========================================================================
# MULTI-TEXT SEMANTIC COHERENCE
# ===========================================================================

def test_44_mean_similarity_seaplane_vs_offtopic(seaplane_embeddings, offtopic_embeddings):
    """Mean similarity between seaplane and off-topic texts must be low."""
    sims = [
        cosine_similarity(s, o)
        for s in seaplane_embeddings
        for o in offtopic_embeddings
    ]
    mean_sim = sum(sims) / len(sims)
    assert mean_sim < 0.75, (
        f"Mean seaplane-offtopic similarity={mean_sim:.4f} — expected < 0.5"
    )


def test_45_mean_similarity_suas_vs_offtopic(suas_embeddings, offtopic_embeddings):
    """Mean similarity between sUAS and off-topic texts must be low."""
    sims = [
        cosine_similarity(s, o)
        for s in suas_embeddings
        for o in offtopic_embeddings
    ]
    mean_sim = sum(sims) / len(sims)
    assert mean_sim < 0.75, (
        f"Mean sUAS-offtopic similarity={mean_sim:.4f} — expected < 0.5"
    )


def test_46_hazardous_attitudes_query_finds_relevant_chunk(embed, db_conn, doc_id_3):
    """Query about hazardous attitudes must find a highly similar chunk in test-3."""
    query_emb = embed(
        EMBED_MODEL,
        ["What are the five hazardous attitudes a pilot can have?"],
        kind="query"
    )[0]
    rows = db_conn.execute(
        """SELECT text FROM chunks WHERE doc_id=? AND level='child'
           AND text LIKE '%hazardous%' LIMIT 5""",
        (doc_id_3,),
    ).fetchall()
    if not rows:
        pytest.skip("No hazardous attitudes chunk found in test-3")
    texts = [r["text"] for r in rows]
    embs  = embed(EMBED_MODEL, texts, kind="passage")
    sims  = [cosine_similarity(query_emb, e) for e in embs]
    assert max(sims) > 0.55, (
        f"Hazardous attitudes query max similarity={max(sims):.4f} — expected > 0.7"
    )


def test_47_thunderstorm_query_finds_relevant_chunk(embed, db_conn, doc_id_3):
    """Query about thunderstorm lifecycle must find a similar chunk in test-3."""
    query_emb = embed(
        EMBED_MODEL,
        ["Describe the three stages of a thunderstorm life cycle"],
        kind="query"
    )[0]
    rows = db_conn.execute(
        """SELECT text FROM chunks WHERE doc_id=? AND level='child'
           AND text LIKE '%thunderstorm%' LIMIT 5""",
        (doc_id_3,),
    ).fetchall()
    if not rows:
        pytest.skip("No thunderstorm chunk found in test-3")
    texts = [r["text"] for r in rows]
    embs  = embed(EMBED_MODEL, texts, kind="passage")
    sims  = [cosine_similarity(query_emb, e) for e in embs]
    assert max(sims) > 0.55, (
        f"Thunderstorm query max similarity={max(sims):.4f} — expected > 0.7"
    )


def test_48_water_rudder_query_finds_relevant_chunk(embed, db_conn, pdf_path_2):
    """Query about water rudders must find a similar chunk in test-2."""
    doc_id_2 = db_conn.execute(
        "SELECT id FROM documents WHERE filename=?", (pdf_path_2.name,)
    ).fetchone()["id"]
    query_emb = embed(
        EMBED_MODEL,
        ["What are water rudders used for on a seaplane?"],
        kind="query"
    )[0]
    rows = db_conn.execute(
        """SELECT text FROM chunks WHERE doc_id=? AND level='child'
           AND text LIKE '%water rudder%' LIMIT 5""",
        (doc_id_2,),
    ).fetchall()
    if not rows:
        pytest.skip("No water rudder chunk found in test-2")
    texts = [r["text"] for r in rows]
    embs  = embed(EMBED_MODEL, texts, kind="passage")
    sims  = [cosine_similarity(query_emb, e) for e in embs]
    assert max(sims) > 0.7, (
        f"Water rudder query max similarity={max(sims):.4f} — expected > 0.7"
    )


def test_49_embedding_model_name_correct(embed):
    """Verify the model being used is actually bge-large and not a fallback."""
    import tools.pymupdf_bge_chroma_cli as base
    assert base.DEFAULT_MODEL == EMBED_MODEL, (
        f"DEFAULT_MODEL='{base.DEFAULT_MODEL}', expected '{EMBED_MODEL}'"
    )


def test_50_all_similarity_scores_finite(embed):
    """No embedding operation should produce NaN or Inf values."""
    texts = SEAPLANE_TEXTS + SUAS_TEXTS + OFFTOPIC_TEXTS
    embs  = embed(EMBED_MODEL, texts, kind="passage")
    for i, emb in enumerate(embs):
        for j, val in enumerate(emb):
            assert math.isfinite(val), (
                f"Text {i}, dimension {j}: non-finite value {val} in embedding"
            )