"""RAG retrieval helpers for the local TIFF search database."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from .ollama_client import DEFAULT_OLLAMA_URL, OllamaClient
from .rag_chunks import build_fts_query, collapse_ws, create_rag_schema, prune_stale_rag_embeddings, table_exists
from .rag_router import classify_query

try:
    from .search_index import is_probable_part_number, normalize_part_number
except Exception:  # pragma: no cover - fallback for isolated unit tests
    def normalize_part_number(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()

    def is_probable_part_number(value: str) -> bool:
        norm = normalize_part_number(value)
        return len(norm) >= 6 and any(ch.isdigit() for ch in norm)


@dataclass(frozen=True)
class RagSource:
    source_id: str
    source_type: str
    page_id: str
    manual_id: str
    chunk_text: str
    score: float = 0.0
    publication_number: str | None = None
    ata_code: str | None = None
    page_sequence: int | None = None
    page_label: str | None = None
    page_type: str | None = None
    title: str | None = None
    tiff_path: str | None = None
    ocr_text_path: str | None = None
    rescarta_object_id: str | None = None
    rescarta_page_id: str | None = None
    rescarta_url: str | None = None
    source_url: str | None = None
    tiff_uri: str | None = None
    ocr_uri: str | None = None
    matched_part_number: str | None = None
    part_nomenclature: str | None = None
    part_item_number: str | None = None
    part_quantity: str | None = None
    evidence_text: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    sources: tuple[RagSource, ...]
    used_embeddings: bool = False
    warnings: tuple[str, ...] = ()
    answer_mode: str = "auto"
    retrieval_mode: str = "auto"
    intent: str = "auto"


@dataclass(frozen=True)
class EmbeddingBuildSummary:
    db_path: Path
    model: str
    chunks_seen: int
    embeddings_written: int
    skipped_existing: int
    stale_deleted: int = 0


def serialize_embedding(vector: Iterable[float]) -> str:
    return json.dumps([float(x) for x in vector], ensure_ascii=True)


def deserialize_embedding(value: str) -> list[float]:
    raw = json.loads(value)
    if not isinstance(raw, list):
        raise ValueError("embedding_json is not a list")
    return [float(x) for x in raw]


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    va = [float(x) for x in a]
    vb = [float(x) for x in b]
    if not va or not vb or len(va) != len(vb):
        return 0.0
    dot = sum(x * y for x, y in zip(va, vb))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(y * y for y in vb))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _row_to_source(row: sqlite3.Row, *, source_type: str, score: float = 0.0, **extra: Any) -> RagSource:
    return RagSource(
        source_id=extra.get("source_id") or row.get("chunk_id", row.get("page_id", "source")) if hasattr(row, "get") else extra.get("source_id", "source"),
        source_type=source_type,
        page_id=row["page_id"],
        manual_id=row["manual_id"],
        chunk_text=extra.get("chunk_text") or row.get("chunk_text", "") if hasattr(row, "get") else extra.get("chunk_text", ""),
        score=score,
        publication_number=row["publication_number"] if "publication_number" in row.keys() else None,
        ata_code=row["ata_code"] if "ata_code" in row.keys() else None,
        page_sequence=row["page_sequence"] if "page_sequence" in row.keys() else None,
        page_label=row["page_label"] if "page_label" in row.keys() else None,
        page_type=row["page_type"] if "page_type" in row.keys() else None,
        title=row["title"] if "title" in row.keys() else None,
        tiff_path=row["tiff_path"] if "tiff_path" in row.keys() else None,
        ocr_text_path=row["ocr_text_path"] if "ocr_text_path" in row.keys() else None,
        rescarta_object_id=row["rescarta_object_id"] if "rescarta_object_id" in row.keys() else None,
        rescarta_page_id=row["rescarta_page_id"] if "rescarta_page_id" in row.keys() else None,
        matched_part_number=extra.get("matched_part_number"),
        part_nomenclature=extra.get("part_nomenclature"),
        part_item_number=extra.get("part_item_number"),
        part_quantity=extra.get("part_quantity"),
        evidence_text=extra.get("evidence_text"),
        extra={k: v for k, v in extra.items() if k not in {"chunk_text", "matched_part_number", "part_nomenclature", "part_item_number", "part_quantity", "evidence_text", "source_id"}},
    )


# sqlite3.Row has no .get; keep a small helper instead of relying on Mapping.
def row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except Exception:
        return default


def make_source_from_row(row: sqlite3.Row, *, source_type: str, score: float = 0.0, **extra: Any) -> RagSource:
    return RagSource(
        source_id=extra.get("source_id") or row_get(row, "chunk_id") or row_get(row, "page_id") or "source",
        source_type=source_type,
        page_id=row_get(row, "page_id", ""),
        manual_id=row_get(row, "manual_id", ""),
        chunk_text=extra.get("chunk_text") or row_get(row, "chunk_text", "") or row_get(row, "evidence_text", "") or row_get(row, "ocr_text", ""),
        score=score,
        publication_number=row_get(row, "publication_number"),
        ata_code=row_get(row, "ata_code"),
        page_sequence=row_get(row, "page_sequence"),
        page_label=row_get(row, "page_label"),
        page_type=row_get(row, "page_type"),
        title=row_get(row, "title"),
        tiff_path=row_get(row, "tiff_path"),
        ocr_text_path=row_get(row, "ocr_text_path"),
        rescarta_object_id=row_get(row, "rescarta_object_id"),
        rescarta_page_id=row_get(row, "rescarta_page_id"),
        rescarta_url=row_get(row, "rescarta_url"),
        source_url=row_get(row, "source_url"),
        tiff_uri=row_get(row, "tiff_uri"),
        ocr_uri=row_get(row, "ocr_uri"),
        matched_part_number=extra.get("matched_part_number") or row_get(row, "part_number_display"),
        part_nomenclature=extra.get("part_nomenclature") or row_get(row, "nomenclature"),
        part_item_number=extra.get("part_item_number") or row_get(row, "item_number"),
        part_quantity=extra.get("part_quantity") or row_get(row, "quantity"),
        evidence_text=extra.get("evidence_text") or row_get(row, "evidence_text"),
        extra={k: v for k, v in extra.items() if k not in {"matched_part_number", "part_nomenclature", "part_item_number", "part_quantity", "evidence_text", "source_id"}},
    )




def _source_link_rows_by_page(conn: sqlite3.Connection, page_ids: Iterable[str]) -> dict[str, sqlite3.Row]:
    """Return source_links rows keyed by page_id for retrieved sources.

    The source_links table is optional. Retrieval still works before Goal 2 is
    configured, but when the table exists every RagSource receives stable
    source_url/rescarta_url fields.
    """

    ids = [str(pid) for pid in page_ids if pid]
    if not ids or not table_exists(conn, "source_links"):
        return {}
    # Keep SQLite parameter lists small enough for older builds.
    out: dict[str, sqlite3.Row] = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            "SELECT page_id, tiff_path, ocr_text_path, tiff_uri, ocr_uri, "
            "rescarta_object_id, rescarta_page_id, rescarta_url, source_url "
            f"FROM source_links WHERE page_id IN ({placeholders})",
            tuple(chunk),
        ).fetchall()
        for row in rows:
            out[str(row_get(row, "page_id", ""))] = row
    return out


def enrich_sources_with_source_links(conn: sqlite3.Connection, sources: Iterable[RagSource]) -> tuple[RagSource, ...]:
    """Attach stable source-link fields to retrieved RagSource objects."""

    source_list = list(sources)
    links = _source_link_rows_by_page(conn, [s.page_id for s in source_list])
    if not links:
        return tuple(source_list)

    enriched: list[RagSource] = []
    for source in source_list:
        link = links.get(source.page_id)
        if link is None:
            enriched.append(source)
            continue
        enriched.append(
            replace(
                source,
                tiff_path=source.tiff_path or row_get(link, "tiff_path"),
                ocr_text_path=source.ocr_text_path or row_get(link, "ocr_text_path"),
                rescarta_object_id=source.rescarta_object_id or row_get(link, "rescarta_object_id"),
                rescarta_page_id=source.rescarta_page_id or row_get(link, "rescarta_page_id"),
                rescarta_url=row_get(link, "rescarta_url"),
                source_url=row_get(link, "source_url"),
                tiff_uri=row_get(link, "tiff_uri"),
                ocr_uri=row_get(link, "ocr_uri"),
            )
        )
    return tuple(enriched)


def extract_query_part_number(query: str) -> tuple[str, str]:
    """Return (display, normalized) for the first part-like token in a question."""
    candidates = re.findall(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+){1,}", query or "")
    for candidate in candidates:
        if is_probable_part_number(candidate):
            return candidate, normalize_part_number(candidate)
    if is_probable_part_number(query):
        return query, normalize_part_number(query)
    return "", ""


NOMENCLATURE_QUERY_STOP_WORDS = {
    "A",
    "AN",
    "AND",
    "ARE",
    "AS",
    "AT",
    "BE",
    "BRING",
    "BY",
    "CALLED",
    "CAN",
    "FIND",
    "FOR",
    "FROM",
    "GET",
    "GIVE",
    "I",
    "IN",
    "IS",
    "IT",
    "LIST",
    "LISTED",
    "LOOK",
    "LOOKUP",
    "ME",
    "MENTION",
    "MENTIONED",
    "MENTIONS",
    "NAME",
    "NAMED",
    "NOMENCLATURE",
    "NUMBER",
    "OF",
    "ON",
    "OPEN",
    "PAGE",
    "PAGES",
    "PART",
    "PARTS",
    "RESULT",
    "RESULTS",
    "SEARCH",
    "SHOW",
    "SHOWN",
    "SOURCE",
    "SOURCES",
    "THE",
    "THIS",
    "TO",
    "UP",
    "WHAT",
    "WHERE",
    "WHICH",
    "WITH",
    "ABOUT",
    "AVAILABLE",
    "COMPARE",
    "COMPARISON",
    "CONCERNING",
    "DETAIL",
    "DETAILS",
    "DESCRIBE",
    "DISCUSS",
    "DISCUSSED",
    "DISCUSSES",
    "DISCUSSION",
    "DOCUMENT",
    "DOCUMENTS",
    "EXPLAIN",
    "INFO",
    "INFORMATION",
    "MANUAL",
    "MANUALS",
    "OVERVIEW",
    "RELATED",
    "RELATES",
    "RELATING",
    "SAY",
    "SAYS",
    "SUMMARIZE",
    "SUMMARY",
    "SUMMARISE",
    "TELL",
}


def nomenclature_tokens(value: str | None) -> tuple[str, ...]:
    """Return meaningful tokens for part-name/nomenclature lookup.

    This intentionally ignores question words so a user can type natural text
    such as ``where is magazine holder shown`` and still match the cleaned
    catalog value ``HOLDER, MAGAZINE``.
    """

    if not value:
        return ()
    tokens = re.findall(r"[A-Za-z0-9]+", str(value).upper())
    out: list[str] = []
    for token in tokens:
        if token in NOMENCLATURE_QUERY_STOP_WORDS:
            continue
        if len(token) <= 1:
            continue
        # Mostly numeric tokens are usually quantities/page numbers, not names.
        if token.isdigit():
            continue
        if len(token) > 4 and token.endswith("IES"):
            token = token[:-3] + "Y"
        elif len(token) > 3 and token.endswith("S") and not token.endswith("SS"):
            token = token[:-1]
        if token in NOMENCLATURE_QUERY_STOP_WORDS:
            continue
        out.append(token)
    return tuple(out)


def nomenclature_match_score(query: str, nomenclature: str | None) -> float:
    """Score whether a natural-language query matches a catalog name.

    Matches are token based so ``magazine holder`` matches the aircraft-style
    nomenclature ``HOLDER, MAGAZINE``. A score of 0 means no usable match.
    """

    q_tokens = nomenclature_tokens(query)
    n_tokens = nomenclature_tokens(nomenclature)
    if not q_tokens or not n_tokens:
        return 0.0
    q_set = set(q_tokens)
    n_set = set(n_tokens)
    overlap = q_set & n_set
    if not overlap:
        return 0.0

    # Require all query name tokens for multi-word lookups. This prevents a
    # broad query like "holder" from being treated as strongly as
    # "magazine holder".
    if len(q_set) >= 2 and not q_set.issubset(n_set):
        return 0.0

    score = 85.0 + (len(overlap) * 8.0)
    if q_set == n_set:
        score += 20.0
    elif q_set.issubset(n_set):
        score += 10.0
    name_len_penalty = max(0, len(n_set) - len(q_set)) * 1.5
    score -= min(12.0, name_len_penalty)
    return max(0.0, score)


def query_looks_like_nomenclature(query: str) -> bool:
    """Return True when the query has useful name words and no part number."""

    _, part_norm = extract_query_part_number(query)
    if part_norm:
        return False
    return len(nomenclature_tokens(query)) > 0


def ensure_rag_schema(db_path: Path | str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        create_rag_schema(conn, reset=False)
    finally:
        conn.close()


def build_rag_embeddings(
    db_path: Path | str,
    *,
    model: str = "bge-m3:latest",
    ollama_url: str = DEFAULT_OLLAMA_URL,
    batch_size: int = 16,
    reset: bool = False,
    limit: int | None = None,
) -> EmbeddingBuildSummary:
    """Embed rag_chunks with Ollama and store vectors in SQLite."""

    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Search database does not exist: {db_path}")
    client = OllamaClient(ollama_url)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        create_rag_schema(conn, reset=False)
        if reset:
            conn.execute("DELETE FROM rag_embeddings WHERE model = ?", (model,))
            conn.commit()

        stale_deleted = prune_stale_rag_embeddings(conn, model=model)
        conn.commit()

        sql = """
            SELECT c.chunk_id, c.chunk_text, c.chunk_hash
            FROM rag_chunks c
            LEFT JOIN rag_embeddings e
              ON e.chunk_id = c.chunk_id
             AND e.model = ?
             AND COALESCE(e.chunk_hash, '') = COALESCE(c.chunk_hash, '')
            WHERE e.chunk_id IS NULL
            ORDER BY c.manual_id, c.page_sequence, c.chunk_index
        """
        params: list[Any] = [model]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = conn.execute(sql, params).fetchall()
        chunks_seen = conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
        skipped_existing = max(0, chunks_seen - len(rows))
        written = 0
        for start in range(0, len(rows), max(1, batch_size)):
            batch = rows[start : start + max(1, batch_size)]
            texts = [row["chunk_text"] for row in batch]
            vectors = client.embed(model, texts)
            if len(vectors) != len(batch):
                raise RuntimeError(f"Ollama returned {len(vectors)} embeddings for {len(batch)} chunks")
            for row, vector in zip(batch, vectors):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO rag_embeddings
                    (chunk_id, model, chunk_hash, dim, embedding_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["chunk_id"], model, row["chunk_hash"], len(vector), serialize_embedding(vector)),
                )
                written += 1
            conn.commit()
        return EmbeddingBuildSummary(
            db_path=db_path,
            model=model,
            chunks_seen=chunks_seen,
            embeddings_written=written,
            skipped_existing=skipped_existing,
            stale_deleted=stale_deleted,
        )
    finally:
        conn.close()


def retrieve_part_catalog_sources(conn: sqlite3.Connection, query: str, limit: int) -> list[RagSource]:
    part_display, part_norm = extract_query_part_number(query)
    if not part_norm:
        return []

    # Prefer the cleaned/canonical catalog when it exists. This prevents the LLM
    # from seeing many noisy OCR variants such as dot leaders and effectivity codes.
    if table_exists(conn, "part_catalog_clean"):
        rows = conn.execute(
            """
            SELECT
                pcc.part_number_display,
                pcc.part_number_normalized,
                pcc.canonical_nomenclature AS nomenclature,
                NULL AS item_number,
                NULL AS quantity,
                NULL AS figure_number,
                pcc.evidence_text,
                pcc.source_count,
                pcc.variant_count,
                pcc.variants_json,
                p.page_id, p.manual_id, p.publication_number, p.ata_code,
                p.page_sequence,
                COALESCE(pcc.best_page_label, p.page_label) AS page_label,
                p.page_type, p.title,
                COALESCE(pcc.source_tiff_path, p.tiff_path) AS tiff_path,
                COALESCE(pcc.source_ocr_path, p.ocr_text_path) AS ocr_text_path,
                p.rescarta_object_id, p.rescarta_page_id,
                COALESCE(pcc.evidence_text, p.ocr_text) AS chunk_text
            FROM part_catalog_clean pcc
            JOIN pages p ON p.page_id = pcc.best_page_id
            WHERE pcc.part_number_normalized = ?
            ORDER BY pcc.source_count DESC, pcc.best_page_sequence
            LIMIT ?
            """,
            (part_norm, limit),
        ).fetchall()
        if rows:
            return [
                make_source_from_row(
                    row,
                    source_type="part_catalog_clean",
                    score=120.0,
                    source_id=f"part_catalog_clean:{row_get(row, 'part_number_normalized')}",
                    matched_part_number=row_get(row, "part_number_display"),
                    part_nomenclature=row_get(row, "nomenclature"),
                    part_item_number=row_get(row, "item_number"),
                    part_quantity=row_get(row, "quantity"),
                    evidence_text=row_get(row, "evidence_text"),
                    source_count=row_get(row, "source_count"),
                    variant_count=row_get(row, "variant_count"),
                    variants_json=row_get(row, "variants_json"),
                )
                for row in rows
            ]

    if not table_exists(conn, "part_catalog"):
        return []
    rows = conn.execute(
        """
        SELECT
            pc.part_number_display, pc.part_number_normalized, pc.nomenclature,
            pc.item_number, pc.quantity, pc.figure_number, pc.evidence_text,
            p.page_id, p.manual_id, p.publication_number, p.ata_code,
            p.page_sequence, p.page_label, p.page_type, p.title,
            p.tiff_path, p.ocr_text_path, p.rescarta_object_id, p.rescarta_page_id,
            COALESCE(pc.evidence_text, p.ocr_text) AS chunk_text
        FROM part_catalog pc
        JOIN pages p ON p.page_id = pc.page_id
        WHERE pc.part_number_normalized = ?
        ORDER BY
            CASE pc.confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END,
            p.manual_id, p.page_sequence
        LIMIT ?
        """,
        (part_norm, limit),
    ).fetchall()
    return [
        make_source_from_row(
            row,
            source_type="part_catalog",
            score=100.0,
            matched_part_number=row_get(row, "part_number_display"),
            part_nomenclature=row_get(row, "nomenclature"),
            part_item_number=row_get(row, "item_number"),
            part_quantity=row_get(row, "quantity"),
            evidence_text=row_get(row, "evidence_text"),
        )
        for row in rows
    ]


def retrieve_part_mention_sources(conn: sqlite3.Connection, query: str, limit: int) -> list[RagSource]:
    if not table_exists(conn, "part_mentions"):
        return []
    part_display, part_norm = extract_query_part_number(query)
    if not part_norm:
        return []
    rows = conn.execute(
        """
        SELECT
            pm.part_number_display, pm.part_number_normalized, pm.context AS evidence_text,
            p.page_id, p.manual_id, p.publication_number, p.ata_code,
            p.page_sequence, p.page_label, p.page_type, p.title,
            p.tiff_path, p.ocr_text_path, p.rescarta_object_id, p.rescarta_page_id,
            COALESCE(pm.context, p.ocr_text) AS chunk_text
        FROM part_mentions pm
        JOIN pages p ON p.page_id = pm.page_id
        WHERE pm.part_number_normalized = ?
        ORDER BY p.manual_id, p.page_sequence
        LIMIT ?
        """,
        (part_norm, limit),
    ).fetchall()
    return [
        make_source_from_row(
            row,
            source_type="part_mentions",
            score=80.0,
            matched_part_number=row_get(row, "part_number_display"),
            evidence_text=row_get(row, "evidence_text"),
        )
        for row in rows
    ]


def retrieve_part_mention_sources_for_parts(
    conn: sqlite3.Connection,
    part_numbers: Iterable[tuple[str, str]],
    limit_per_part: int,
) -> list[RagSource]:
    """Return pages that mention any already-resolved part number."""

    if not table_exists(conn, "part_mentions"):
        return []
    out: list[RagSource] = []
    seen: set[tuple[str, str]] = set()
    for part_display, part_norm in part_numbers:
        if not part_norm:
            continue
        rows = conn.execute(
            """
            SELECT
                pm.part_number_display, pm.part_number_normalized, pm.context AS evidence_text,
                p.page_id, p.manual_id, p.publication_number, p.ata_code,
                p.page_sequence, p.page_label, p.page_type, p.title,
                p.tiff_path, p.ocr_text_path, p.rescarta_object_id, p.rescarta_page_id,
                COALESCE(pm.context, p.ocr_text) AS chunk_text
            FROM part_mentions pm
            JOIN pages p ON p.page_id = pm.page_id
            WHERE pm.part_number_normalized = ?
            ORDER BY p.manual_id, p.page_sequence
            LIMIT ?
            """,
            (part_norm, max(1, int(limit_per_part))),
        ).fetchall()
        for row in rows:
            key = (row_get(row, "page_id"), row_get(row, "part_number_normalized"))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                make_source_from_row(
                    row,
                    source_type="part_mentions",
                    score=80.0,
                    matched_part_number=row_get(row, "part_number_display") or part_display,
                    evidence_text=row_get(row, "evidence_text"),
                )
            )
    return out


def retrieve_nomenclature_catalog_sources(conn: sqlite3.Connection, query: str, limit: int) -> list[RagSource]:
    """Resolve natural-language nomenclature to catalog part numbers.

    Example: ``magazine holder`` should match the cleaned catalog row
    ``HOLDER, MAGAZINE`` and then the retriever can expand to all pages where
    that part number appears.
    """

    if not query_looks_like_nomenclature(query):
        return []

    candidates: list[tuple[float, sqlite3.Row, str]] = []
    if table_exists(conn, "part_catalog_clean"):
        rows = conn.execute(
            """
            SELECT
                pcc.part_number_display,
                pcc.part_number_normalized,
                pcc.canonical_nomenclature AS nomenclature,
                NULL AS item_number,
                NULL AS quantity,
                NULL AS figure_number,
                pcc.evidence_text,
                pcc.source_count,
                pcc.variant_count,
                pcc.variants_json,
                p.page_id, p.manual_id, p.publication_number, p.ata_code,
                p.page_sequence,
                COALESCE(pcc.best_page_label, p.page_label) AS page_label,
                p.page_type, p.title,
                COALESCE(pcc.source_tiff_path, p.tiff_path) AS tiff_path,
                COALESCE(pcc.source_ocr_path, p.ocr_text_path) AS ocr_text_path,
                p.rescarta_object_id, p.rescarta_page_id,
                COALESCE(pcc.evidence_text, p.ocr_text) AS chunk_text
            FROM part_catalog_clean pcc
            JOIN pages p ON p.page_id = pcc.best_page_id
            ORDER BY pcc.part_number_normalized
            """
        ).fetchall()
        for row in rows:
            score = nomenclature_match_score(query, row_get(row, "nomenclature"))
            if score > 0:
                candidates.append((score + 25.0, row, "nomenclature_catalog_clean"))

    # Fallback for databases that have not been cleaned/canonicalized yet.
    if not candidates and table_exists(conn, "part_catalog"):
        rows = conn.execute(
            """
            SELECT
                pc.part_number_display, pc.part_number_normalized, pc.nomenclature,
                pc.item_number, pc.quantity, pc.figure_number, pc.evidence_text,
                p.page_id, p.manual_id, p.publication_number, p.ata_code,
                p.page_sequence, p.page_label, p.page_type, p.title,
                p.tiff_path, p.ocr_text_path, p.rescarta_object_id, p.rescarta_page_id,
                COALESCE(pc.evidence_text, p.ocr_text) AS chunk_text
            FROM part_catalog pc
            JOIN pages p ON p.page_id = pc.page_id
            WHERE pc.nomenclature IS NOT NULL AND TRIM(pc.nomenclature) <> ''
            ORDER BY pc.part_number_normalized, p.page_sequence
            """
        ).fetchall()
        best_by_part: dict[str, tuple[float, sqlite3.Row, str]] = {}
        for row in rows:
            score = nomenclature_match_score(query, row_get(row, "nomenclature"))
            if score <= 0:
                continue
            part_norm = row_get(row, "part_number_normalized") or ""
            current = best_by_part.get(part_norm)
            if current is None or score > current[0]:
                best_by_part[part_norm] = (score, row, "nomenclature_catalog")
        candidates.extend(best_by_part.values())

    candidates.sort(key=lambda item: (-item[0], row_get(item[1], "part_number_normalized") or ""))
    sources: list[RagSource] = []
    for score, row, source_type in candidates[:limit]:
        sources.append(
            make_source_from_row(
                row,
                source_type=source_type,
                score=score,
                source_id=f"{source_type}:{row_get(row, 'part_number_normalized')}",
                matched_part_number=row_get(row, "part_number_display"),
                part_nomenclature=row_get(row, "nomenclature"),
                part_item_number=row_get(row, "item_number"),
                part_quantity=row_get(row, "quantity"),
                evidence_text=row_get(row, "evidence_text"),
                query_nomenclature=" ".join(nomenclature_tokens(query)),
            )
        )
    return sources


def retrieve_keyword_sources(conn: sqlite3.Connection, query: str, limit: int) -> list[RagSource]:
    if not table_exists(conn, "rag_chunk_fts"):
        return []
    sources: list[RagSource] = []
    seen: set[str] = set()
    for joiner in ("AND", "OR"):
        fts_query = build_fts_query(query, joiner=joiner)
        if not fts_query:
            break
        try:
            rows = conn.execute(
                """
                SELECT
                    c.*,
                    snippet(rag_chunk_fts, 0, '[', ']', '...', 36) AS fts_snippet,
                    bm25(rag_chunk_fts) AS rank
                FROM rag_chunk_fts
                JOIN rag_chunks c ON c.chunk_id = rag_chunk_fts.chunk_id
                WHERE rag_chunk_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for row in rows:
            chunk_id = row_get(row, "chunk_id")
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            rank = row_get(row, "rank")
            score = 50.0 - float(rank or 0.0)
            snippet = row_get(row, "fts_snippet") or row_get(row, "chunk_text")
            sources.append(
                make_source_from_row(row, source_type=f"keyword-{joiner.lower()}", score=score, evidence_text=snippet)
            )
        if sources or joiner == "OR":
            break
    return sources[:limit]


def retrieve_embedding_sources(
    conn: sqlite3.Connection,
    query: str,
    *,
    model: str,
    ollama_url: str,
    limit: int,
) -> tuple[list[RagSource], bool, list[str]]:
    warnings: list[str] = []
    if not table_exists(conn, "rag_embeddings"):
        return [], False, warnings
    rows = conn.execute(
        """
        SELECT c.*, e.embedding_json
        FROM rag_embeddings e
        JOIN rag_chunks c ON c.chunk_id = e.chunk_id
        WHERE e.model = ?
        """,
        (model,),
    ).fetchall()
    if not rows:
        return [], False, warnings
    try:
        query_vector = OllamaClient(ollama_url).embed(model, query)[0]
    except Exception as exc:
        warnings.append(f"Embedding retrieval skipped: {exc}")
        return [], False, warnings
    scored: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        try:
            vector = deserialize_embedding(row["embedding_json"])
        except Exception:
            continue
        score = cosine_similarity(query_vector, vector)
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    sources = [
        make_source_from_row(row, source_type="vector", score=score, evidence_text=collapse_ws(row_get(row, "chunk_text", "")[:320]))
        for score, row in scored[:limit]
    ]
    return sources, True, warnings


def dedupe_sources(sources: Iterable[RagSource], limit: int) -> list[RagSource]:
    """Deduplicate sources while preserving useful source roles.

    For exact part lookups, a part_catalog_clean/part_catalog row is the
    nomenclature source. part_mentions rows are additional appearances. If a
    mention points to the same page as the catalog source, keep the catalog row
    and drop the duplicate mention so the answer does not imply that every
    mention source proves the nomenclature.
    """

    out: list[RagSource] = []
    seen_source: set[tuple[str, str]] = set()
    catalog_pages: set[str] = set()
    mention_pages: set[str] = set()
    keyword_pages: set[str] = set()
    vector_pages: set[str] = set()

    for source in sources:
        source_key = (source.source_type, source.source_id)
        if source_key in seen_source:
            continue

        page_id = source.page_id or ""
        if source.source_type in {"part_catalog_clean", "part_catalog", "nomenclature_catalog_clean", "nomenclature_catalog"}:
            if page_id and page_id in catalog_pages:
                continue
            catalog_pages.add(page_id)
        elif source.source_type == "part_mentions":
            if page_id and (page_id in catalog_pages or page_id in mention_pages):
                continue
            mention_pages.add(page_id)
        elif source.source_type.startswith("keyword"):
            if page_id and (page_id in catalog_pages or page_id in mention_pages or page_id in keyword_pages):
                continue
            keyword_pages.add(page_id)
        elif source.source_type == "vector":
            if page_id and (page_id in catalog_pages or page_id in mention_pages or page_id in keyword_pages or page_id in vector_pages):
                continue
            vector_pages.add(page_id)

        seen_source.add(source_key)
        out.append(source)
        if len(out) >= limit:
            break
    return out


def _source_page_key(source: RagSource) -> tuple[str, str, str]:
    return (source.manual_id or "", source.page_id or "", source.source_type or "")


def dedupe_sources_for_nomenclature_lookup(
    sources: Iterable[RagSource],
    *,
    mention_limit_per_part: int,
    max_matching_parts: int,
) -> list[RagSource]:
    """Deduplicate reverse nomenclature results without letting one part dominate.

    A name search such as ``magazine holder`` can resolve to several different
    part numbers. The ordinary global ``top_k`` behavior can fill the source
    list with mention pages for the first part number and leave the later part
    numbers with no appearance pages. For reverse lookup, treat ``top_k`` as the
    per-part mention cap instead: keep the matching catalog rows first, then add
    up to ``mention_limit_per_part`` mention pages for each matched part number.
    """

    raw = list(sources)
    matches: list[RagSource] = []
    seen_parts: set[str] = set()
    seen_pages: set[tuple[str, str, str]] = set()

    for source in raw:
        if source.source_type not in {"nomenclature_catalog_clean", "nomenclature_catalog"}:
            continue
        if not source.matched_part_number:
            continue
        part_norm = normalize_part_number(source.matched_part_number)
        if not part_norm or part_norm in seen_parts:
            continue
        seen_parts.add(part_norm)
        matches.append(source)
        seen_pages.add(_source_page_key(source))
        if len(matches) >= max(1, int(max_matching_parts)):
            break

    if not matches:
        return dedupe_sources(raw, max(1, int(mention_limit_per_part)))

    out: list[RagSource] = list(matches)

    for match in matches:
        part_norm = normalize_part_number(match.matched_part_number or "")
        added_for_part = 0
        catalog_page = (match.manual_id or "", match.page_id or "")
        for source in raw:
            if source.source_type != "part_mentions":
                continue
            if normalize_part_number(source.matched_part_number or "") != part_norm:
                continue
            # Do not add a mention row for the exact same catalog source page;
            # the catalog row is better because it carries nomenclature.
            mention_page = (source.manual_id or "", source.page_id or "")
            if mention_page == catalog_page:
                continue
            page_key = _source_page_key(source)
            if page_key in seen_pages:
                continue
            seen_pages.add(page_key)
            out.append(source)
            added_for_part += 1
            if added_for_part >= max(0, int(mention_limit_per_part)):
                break

    # Add keyword/vector context only when it points to new pages and there is
    # still room under a conservative soft cap. This keeps name lookups focused
    # on catalog + part-number appearances.
    soft_cap = len(matches) + (len(matches) * max(0, int(mention_limit_per_part)))
    for source in raw:
        if source.source_type in {"nomenclature_catalog_clean", "nomenclature_catalog", "part_mentions"}:
            continue
        page_key = _source_page_key(source)
        if page_key in seen_pages:
            continue
        seen_pages.add(page_key)
        out.append(source)
        if len(out) >= soft_cap:
            break

    return out



def dedupe_sources_for_hybrid_summary(
    sources: Iterable[RagSource],
    *,
    mention_limit_per_part: int,
    max_matching_parts: int,
    context_limit: int,
) -> list[RagSource]:
    """Blend catalog, nomenclature, mention, keyword, and vector evidence.

    Broad questions need a mixed evidence pack. This keeps structured catalog
    rows first, adds a balanced number of mention pages for each resolved part,
    then appends keyword and vector OCR context from new pages.
    """

    raw = sorted(list(sources), key=lambda s: (-float(s.score or 0.0), s.source_type, s.page_label or ""))
    out: list[RagSource] = []
    seen_pages: set[tuple[str, str, str]] = set()
    seen_source: set[tuple[str, str]] = set()

    def add(source: RagSource) -> bool:
        source_key = (source.source_type, source.source_id)
        page_key = _source_page_key(source)
        if source_key in seen_source or page_key in seen_pages:
            return False
        seen_source.add(source_key)
        seen_pages.add(page_key)
        out.append(source)
        return True

    catalog_types = {"part_catalog_clean", "part_catalog", "nomenclature_catalog_clean", "nomenclature_catalog"}
    catalog: list[RagSource] = []
    seen_parts: set[str] = set()
    for source in raw:
        if source.source_type not in catalog_types or not source.matched_part_number:
            continue
        part_norm = normalize_part_number(source.matched_part_number)
        if part_norm in seen_parts:
            continue
        seen_parts.add(part_norm)
        catalog.append(source)
        if len(catalog) >= max(1, int(max_matching_parts)):
            break

    for source in catalog:
        add(source)

    for match in catalog:
        part_norm = normalize_part_number(match.matched_part_number or "")
        added = 0
        for source in raw:
            if source.source_type != "part_mentions":
                continue
            if normalize_part_number(source.matched_part_number or "") != part_norm:
                continue
            if (source.manual_id or "", source.page_id or "") == (match.manual_id or "", match.page_id or ""):
                continue
            if add(source):
                added += 1
            if added >= max(0, int(mention_limit_per_part)):
                break

    # If no catalog/name match existed, still include direct mentions.
    if not catalog:
        added = 0
        for source in raw:
            if source.source_type != "part_mentions":
                continue
            if add(source):
                added += 1
            if added >= max(1, int(context_limit)):
                break

    keyword_added = 0
    for source in raw:
        if not source.source_type.startswith("keyword"):
            continue
        if add(source):
            keyword_added += 1
        if keyword_added >= max(0, int(context_limit)):
            break

    vector_added = 0
    for source in raw:
        if source.source_type != "vector":
            continue
        if add(source):
            vector_added += 1
        if vector_added >= max(0, int(context_limit)):
            break

    if not out:
        return dedupe_sources(raw, max(1, int(context_limit)))
    return out[:30]

def retrieve_rag_context(
    db_path: Path | str,
    query: str,
    *,
    top_k: int = 6,
    embed_model: str = "bge-m3:latest",
    ollama_url: str = DEFAULT_OLLAMA_URL,
    use_embeddings: bool = True,
    answer_mode: str = "auto",
    retrieval_mode: str = "auto",
    force_embeddings: bool = False,
) -> RetrievalResult:
    """Retrieve source-backed context for a local RAG answer.

    Exact part lookups remain source-first and deterministic. Broad summary and
    compare questions now use hybrid retrieval: part catalog, nomenclature
    resolver, keyword OCR, and embeddings when available.
    """

    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Search database does not exist: {db_path}")
    route = classify_query(query, answer_mode=answer_mode, retrieval_mode=retrieval_mode)
    mode = route.retrieval_mode

    # Safety rule: deterministic structured lookups must stay structured even
    # when local_config.yaml sets retrieval_mode: hybrid globally. Otherwise an
    # exact part-number question can pull keyword/vector sources and report
    # ``Embeddings used: True`` even though the clean catalog already has the
    # answer. Users can still force semantic evidence with --force-embeddings.
    if route.allow_structured_answer and not force_embeddings:
        mode = "structured"

    hybrid = mode == "hybrid" or (
        route.answer_mode in {"summarize", "nomenclature_summary", "compare", "broad"}
        and mode != "structured"
    )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        warnings: list[str] = []
        sources: list[RagSource] = []
        retrieval_limit = max(top_k, top_k * 2)

        include_structured = mode in {"structured", "keyword", "hybrid"}
        include_keyword = mode in {"keyword", "hybrid"} or route.answer_mode == "nomenclature_locate"
        include_vector = mode in {"semantic", "hybrid"}

        if include_structured:
            sources.extend(retrieve_part_catalog_sources(conn, query, retrieval_limit))
            sources.extend(retrieve_part_mention_sources(conn, query, retrieval_limit))

            nomenclature_sources = []
            if route.should_try_nomenclature:
                nomenclature_sources = retrieve_nomenclature_catalog_sources(conn, query, retrieval_limit)
                sources.extend(nomenclature_sources)
                if nomenclature_sources:
                    resolved_parts = [
                        (s.matched_part_number or "", normalize_part_number(s.matched_part_number or ""))
                        for s in nomenclature_sources
                        if s.matched_part_number
                    ]
                    per_part_limit = retrieval_limit if not hybrid else max(2, min(4, top_k))
                    sources.extend(retrieve_part_mention_sources_for_parts(conn, resolved_parts, per_part_limit))
        else:
            nomenclature_sources = []

        if include_keyword:
            keyword_limit = retrieval_limit if hybrid else top_k
            sources.extend(retrieve_keyword_sources(conn, query, keyword_limit))

        used_embeddings = False
        should_try_vectors = bool(use_embeddings) and (
            force_embeddings
            or (route.should_try_embeddings and include_vector)
            or (mode != "structured" and route.should_try_embeddings and len(sources) < top_k)
        )
        if should_try_vectors:
            vector_sources, used_embeddings, vector_warnings = retrieve_embedding_sources(
                conn,
                query,
                model=embed_model,
                ollama_url=ollama_url,
                limit=retrieval_limit if hybrid else top_k,
            )
            warnings.extend(vector_warnings)
            sources.extend(vector_sources)

        if mode == "semantic" and not use_embeddings:
            warnings.append("Semantic retrieval requested, but embeddings are disabled.")

        if hybrid:
            final_sources = dedupe_sources_for_hybrid_summary(
                sources,
                mention_limit_per_part=max(1, min(4, int(top_k))),
                max_matching_parts=max(1, min(int(top_k), 10)),
                context_limit=max(1, int(top_k)),
            )
        elif nomenclature_sources:
            final_sources = dedupe_sources_for_nomenclature_lookup(
                sources,
                mention_limit_per_part=max(1, int(top_k)),
                max_matching_parts=max(1, int(top_k)),
            )
        else:
            final_sources = dedupe_sources(sources, top_k)

        final_sources = enrich_sources_with_source_links(conn, final_sources)

        return RetrievalResult(
            query=query,
            sources=tuple(final_sources),
            used_embeddings=used_embeddings,
            warnings=tuple(warnings),
            answer_mode=route.answer_mode,
            retrieval_mode=mode,
            intent=route.reason,
        )
    finally:
        conn.close()

def source_to_dict(source: RagSource) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "score": source.score,
        "page_id": source.page_id,
        "manual_id": source.manual_id,
        "publication_number": source.publication_number,
        "ata_code": source.ata_code,
        "page_sequence": source.page_sequence,
        "page_label": source.page_label,
        "page_type": source.page_type,
        "title": source.title,
        "tiff_path": source.tiff_path,
        "ocr_text_path": source.ocr_text_path,
        "rescarta_object_id": source.rescarta_object_id,
        "rescarta_page_id": source.rescarta_page_id,
        "rescarta_url": source.rescarta_url,
        "source_url": source.source_url,
        "tiff_uri": source.tiff_uri,
        "ocr_uri": source.ocr_uri,
        "matched_part_number": source.matched_part_number,
        "part_nomenclature": source.part_nomenclature,
        "part_item_number": source.part_item_number,
        "part_quantity": source.part_quantity,
        "evidence_text": source.evidence_text,
        "chunk_text": source.chunk_text,
        "extra": source.extra,
    }
