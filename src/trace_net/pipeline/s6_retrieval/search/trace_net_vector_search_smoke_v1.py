"""TRACE-Net Vector Search Smoke v1.

Step 6 verifies that the TRACE-Net Qdrant vector layer can retrieve safe,
traceable hits from both semantic vector collections:

* trace_net_embedding_candidates_v1: safe evidence/helper candidates.
* trace_net_page_retrieval_profiles_v1: page-level routing profiles.

This module intentionally does not answer questions. A smoke hit only proves
that vector retrieval works and that payloads preserve the TRACE-Net safety
contract. Every hit must still resolve back through Postgres/source/citation/
trust gates before answer use.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from tiff import trace_net_qdrant_loader_v1 as qdrant_loader

SCHEMA_VERSION = "trace_net_vector_search_smoke_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/vector_search_smoke")
DEFAULT_SMOKE_FILE = "trace_net_vector_search_smoke_v1.json"
DEFAULT_HITS_JSONL_FILE = "trace_net_vector_search_smoke_v1_hits.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_vector_search_smoke_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_vector_search_smoke_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_vector_search_smoke_v1_quality.json"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_CANDIDATE_COLLECTION = "trace_net_embedding_candidates_v1"
DEFAULT_PAGE_PROFILE_COLLECTION = "trace_net_page_retrieval_profiles_v1"
DEFAULT_EMBEDDING_MODE = "ollama"
DEFAULT_EMBEDDING_MODEL = "bge-m3:latest"
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_ENDPOINT = "/api/embed"
DEFAULT_OLLAMA_TIMEOUT = 120.0
DEFAULT_LIMIT = 5
DEFAULT_MIN_SCORE = None

DEFAULT_QUERIES = [
    {
        "query_id": "q_revision_history",
        "query_text": "T.P. 120/1176 manual revision history Revision 4 Embraer title block",
        "purpose": "context_v2_page_route_smoke",
    },
    {
        "query_id": "q_ata_25_21_00",
        "query_text": "ATA 25-21-00 placards decals warning labels aircraft interior manual",
        "purpose": "ata_page_route_smoke",
    },
    {
        "query_id": "q_part_nomenclature",
        "query_text": "part number nomenclature description item quantity illustrated parts catalog",
        "purpose": "part_nomenclature_candidate_smoke",
    },
    {
        "query_id": "q_source_trace_page",
        "query_text": "source trace TIFF OCR citation page 000001 technical manual source evidence",
        "purpose": "source_trace_candidate_smoke",
    },
    {
        "query_id": "q_table_diagram_safe_route",
        "query_text": "manual page table diagram figure callout component identification safe source citation",
        "purpose": "visual_table_route_smoke",
    },
]

RETRIEVAL_ONLY_BUCKETS = {"source_evidence", "derived_context", "context_retrieval_helper", "page_retrieval_profile"}
ANSWER_CAPABLE_FLAGS = [
    "can_answer_directly",
    "qdrant_can_answer_directly",
    "embedding_answer_authority_allowed",
]
CLAIM_PROOF_FLAGS = [
    "can_prove_claims",
    "qdrant_can_prove_claims",
    "can_prove_source_truth",
]
SOURCE_TRUTH_FLAGS = [
    "qdrant_is_source_truth",
    "canonical_source_truth",
    "can_mutate_source_truth",
    "can_override_trust",
    "can_replace_citation",
]
REQUIRED_TRUE_FLAGS = [
    "must_resolve_through_postgres",
    "must_pass_authority_gate",
    "must_use_source_citation",
    "requires_source_resolution",
    "requires_citation",
    "requires_authority_gate",
]


class VectorSmokeError(RuntimeError):
    """Raised when TRACE-Net vector smoke testing fails."""


@dataclass(frozen=True)
class QualityResult:
    status: str
    checks: list[dict[str, Any]]
    summary: dict[str, Any]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    return qdrant_loader.json_safe(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(json_safe(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def as_text(value: Any) -> str:
    return qdrant_loader.as_text(value)


def as_bool(value: Any, *, default: bool = False) -> bool:
    return qdrant_loader.as_bool(value, default=default)


def normalized_embedding_mode(mode: str | None) -> str:
    return qdrant_loader.normalized_embedding_mode(mode)


def default_queries() -> list[dict[str, str]]:
    return [dict(item) for item in DEFAULT_QUERIES]


def parse_query_items(values: Sequence[str] | None) -> list[dict[str, str]]:
    if not values:
        return default_queries()
    rows: list[dict[str, str]] = []
    for index, value in enumerate(values, start=1):
        text = as_text(value).strip()
        if not text:
            continue
        if "::" in text:
            query_id, query_text = text.split("::", 1)
            query_id = query_id.strip() or f"q_custom_{index:03d}"
            query_text = query_text.strip()
        else:
            query_id = f"q_custom_{index:03d}"
            query_text = text
        if query_text:
            rows.append({"query_id": query_id, "query_text": query_text, "purpose": "custom"})
    return rows or default_queries()


def query_vector(
    query_text: str,
    *,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_device: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    ollama_timeout: float = DEFAULT_OLLAMA_TIMEOUT,
) -> tuple[list[float], str]:
    mode = normalized_embedding_mode(embedding_mode)
    text = qdrant_loader.clean_text_for_embedding(query_text)
    if not text:
        raise VectorSmokeError("query text is empty")
    if mode == "hash":
        return qdrant_loader.deterministic_hash_embedding(text, dim=embedding_dim), "trace_net_hash_embed_v1"
    if qdrant_loader.is_ollama_mode(mode):
        model_name = as_text(embedding_model or qdrant_loader.DEFAULT_OLLAMA_EMBEDDING_MODEL).strip() or qdrant_loader.DEFAULT_OLLAMA_EMBEDDING_MODEL
        vector = qdrant_loader.ollama_embeddings(
            [text],
            model_name=model_name,
            expected_dim=embedding_dim,
            ollama_url=ollama_url,
            endpoint=ollama_endpoint,
            timeout=ollama_timeout,
            batch_size=1,
        )[0]
        return vector, model_name
    if qdrant_loader.is_sentence_transformer_mode(mode):
        model_name = as_text(embedding_model or qdrant_loader.DEFAULT_REAL_EMBEDDING_MODEL).strip() or qdrant_loader.DEFAULT_REAL_EMBEDDING_MODEL
        vector = qdrant_loader.sentence_transformer_embeddings(
            [text],
            model_name=model_name,
            expected_dim=embedding_dim,
            device=embedding_device,
            batch_size=1,
        )[0]
        return vector, model_name
    raise VectorSmokeError(f"unsupported embedding mode for smoke test: {embedding_mode}")


class SearchClient(qdrant_loader.QdrantRestClient):
    """Qdrant REST client with search/query helpers for smoke tests."""

    def search_points(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        limit: int = DEFAULT_LIMIT,
        score_threshold: float | None = DEFAULT_MIN_SCORE,
        with_payload: bool = True,
    ) -> list[dict[str, Any]]:
        search_payload: dict[str, Any] = {
            "vector": [float(item) for item in vector],
            "limit": int(limit),
            "with_payload": bool(with_payload),
            "with_vector": False,
        }
        if score_threshold is not None:
            search_payload["score_threshold"] = float(score_threshold)
        try:
            response = self.request(
                "POST",
                f"/collections/{quote(collection, safe='')}/points/search",
                search_payload,
            )
        except KeyError:
            query_payload: dict[str, Any] = {
                "query": [float(item) for item in vector],
                "limit": int(limit),
                "with_payload": bool(with_payload),
                "with_vector": False,
            }
            if score_threshold is not None:
                query_payload["score_threshold"] = float(score_threshold)
            response = self.request(
                "POST",
                f"/collections/{quote(collection, safe='')}/points/query",
                query_payload,
            )
        result = response.get("result")
        if isinstance(result, Mapping):
            points = result.get("points") or result.get("result") or []
        else:
            points = result or []
        if not isinstance(points, Sequence) or isinstance(points, (str, bytes, bytearray)):
            raise VectorSmokeError(f"Qdrant search returned an unexpected result shape for collection {collection}")
        return [dict(item) for item in points if isinstance(item, Mapping)]


def collection_vector_size(client: SearchClient, collection: str) -> int | None:
    info = client.get_collection(collection)
    if not info:
        return None
    return qdrant_loader.extract_collection_vector_size(info)


def collection_count(client: SearchClient, collection: str) -> int | None:
    try:
        return client.count_points(collection, exact=True)
    except Exception:
        return None


def unsafe_payload_reasons(payload: Mapping[str, Any], *, collection_role: str) -> list[str]:
    reasons: list[str] = []
    page_id = as_text(payload.get("page_id")).strip()
    if not page_id:
        reasons.append("missing_page_id")
    if collection_role == "candidate" and not as_text(payload.get("embedding_candidate_id")).strip():
        reasons.append("missing_embedding_candidate_id")
    if collection_role == "page_profile" and not as_text(payload.get("profile_id") or payload.get("embedding_candidate_id")).strip():
        reasons.append("missing_profile_or_embedding_candidate_id")
    for flag in ANSWER_CAPABLE_FLAGS:
        if as_bool(payload.get(flag), default=False):
            reasons.append(f"{flag}_true")
    for flag in CLAIM_PROOF_FLAGS:
        if as_bool(payload.get(flag), default=False):
            reasons.append(f"{flag}_true")
    for flag in SOURCE_TRUTH_FLAGS:
        if as_bool(payload.get(flag), default=False):
            reasons.append(f"{flag}_true")
    for flag in REQUIRED_TRUE_FLAGS:
        if as_bool(payload.get(flag), default=True) is not True:
            reasons.append(f"{flag}_false")
    bucket = qdrant_loader.normalize_bucket(payload.get("rag_bucket") or payload.get("record_type") or payload.get("candidate_type"))
    if bucket == "context_retrieval_helper":
        if as_bool(payload.get("can_answer_directly"), default=False):
            reasons.append("context_helper_can_answer")
        if as_bool(payload.get("can_prove_claims"), default=False):
            reasons.append("context_helper_can_prove")
    if bucket == "source_evidence":
        authority = as_text(payload.get("authority")).strip().lower()
        if authority != "source_exists_only":
            reasons.append("source_evidence_authority_not_source_exists_only")
        if as_bool(payload.get("can_answer_directly"), default=False):
            reasons.append("source_evidence_can_answer")
        if as_bool(payload.get("can_prove_claims"), default=False):
            reasons.append("source_evidence_can_prove")
    if bucket == "page_retrieval_profile":
        authority = as_text(payload.get("authority")).strip().lower()
        if authority != "page_route_only":
            reasons.append("page_profile_authority_not_page_route_only")
        if as_bool(payload.get("page_route_only"), default=True) is not True:
            reasons.append("page_profile_page_route_only_false")
    if as_text(payload.get("trust_tier")).strip().upper() == "D":
        reasons.append("D_tier_vector_hit")
    return sorted(set(reasons))


def normalized_hit(
    *,
    query: Mapping[str, Any],
    collection: str,
    collection_role: str,
    rank: int,
    hit: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(hit.get("payload") or {})
    reasons = unsafe_payload_reasons(payload, collection_role=collection_role)
    bucket = qdrant_loader.normalize_bucket(payload.get("rag_bucket") or payload.get("record_type") or payload.get("candidate_type"))
    return {
        "schema_version": SCHEMA_VERSION,
        "query_id": as_text(query.get("query_id")),
        "query_text": as_text(query.get("query_text")),
        "query_purpose": as_text(query.get("purpose")),
        "collection": collection,
        "collection_role": collection_role,
        "rank": int(rank),
        "point_id": as_text(hit.get("id")),
        "score": hit.get("score"),
        "page_id": as_text(payload.get("page_id")),
        "page_number": payload.get("page_number"),
        "document_id": as_text(payload.get("document_id")),
        "ata_code": as_text(payload.get("ata_code")),
        "embedding_candidate_id": as_text(payload.get("embedding_candidate_id")),
        "profile_id": as_text(payload.get("profile_id")),
        "source_candidate_id": as_text(payload.get("source_candidate_id")),
        "rag_bucket": bucket,
        "authority": as_text(payload.get("authority")),
        "trust_tier": as_text(payload.get("trust_tier")),
        "citation_id": as_text(payload.get("citation_id")),
        "source_url": as_text(payload.get("source_url")),
        "embedding_mode": as_text(payload.get("embedding_mode")),
        "embedding_model_name": as_text(payload.get("embedding_model_name")),
        "embedding_dim": payload.get("embedding_dim"),
        "qdrant_is_source_truth": as_bool(payload.get("qdrant_is_source_truth"), default=False),
        "qdrant_can_answer_directly": as_bool(payload.get("qdrant_can_answer_directly"), default=False),
        "qdrant_can_prove_claims": as_bool(payload.get("qdrant_can_prove_claims"), default=False),
        "can_answer_directly": as_bool(payload.get("can_answer_directly"), default=False),
        "can_prove_claims": as_bool(payload.get("can_prove_claims"), default=False),
        "requires_source_resolution": as_bool(payload.get("requires_source_resolution"), default=True),
        "requires_citation": as_bool(payload.get("requires_citation"), default=True),
        "requires_authority_gate": as_bool(payload.get("requires_authority_gate"), default=True),
        "embedding_answer_authority_allowed": as_bool(payload.get("embedding_answer_authority_allowed"), default=False),
        "unsafe_reasons": reasons,
        "safe_for_smoke_retrieval": len(reasons) == 0,
        "answer_use_allowed_from_vector_hit": False,
        "must_resolve_through_postgres_before_answer": True,
        "payload_preview": as_text(payload.get("embedding_text_preview"))[:500],
    }


def summarize_hits(
    *,
    queries: Sequence[Mapping[str, Any]],
    hits: Sequence[Mapping[str, Any]],
    candidate_collection: str,
    page_profile_collection: str,
    candidate_collection_count: int | None,
    page_profile_collection_count: int | None,
    candidate_collection_vector_size: int | None,
    page_profile_collection_vector_size: int | None,
    embedding_mode: str,
    embedding_model_name: str,
    embedding_dim: int,
) -> dict[str, Any]:
    query_count = len(queries)
    hit_rows = [dict(hit) for hit in hits]
    by_role: Counter[str] = Counter(as_text(hit.get("collection_role")) for hit in hit_rows)
    by_bucket: Counter[str] = Counter(as_text(hit.get("rag_bucket")) for hit in hit_rows)
    by_authority: Counter[str] = Counter(as_text(hit.get("authority")) for hit in hit_rows)
    by_query_role: dict[str, set[str]] = defaultdict(set)
    for hit in hit_rows:
        by_query_role[as_text(hit.get("query_id"))].add(as_text(hit.get("collection_role")))
    queries_with_candidate_hits = sum(1 for roles in by_query_role.values() if "candidate" in roles)
    queries_with_page_profile_hits = sum(1 for roles in by_query_role.values() if "page_profile" in roles)
    unsafe_hits = [hit for hit in hit_rows if hit.get("unsafe_reasons")]
    page_profile_hits = [hit for hit in hit_rows if hit.get("collection_role") == "page_profile"]
    context_helper_hits = [hit for hit in hit_rows if hit.get("rag_bucket") == "context_retrieval_helper"]
    source_evidence_hits = [hit for hit in hit_rows if hit.get("rag_bucket") == "source_evidence"]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "smoke_query_count": query_count,
        "total_hit_count": len(hit_rows),
        "candidate_hit_count": by_role.get("candidate", 0),
        "page_profile_hit_count": by_role.get("page_profile", 0),
        "queries_with_candidate_hits": queries_with_candidate_hits,
        "queries_with_page_profile_hits": queries_with_page_profile_hits,
        "missing_page_id_count": sum(1 for hit in hit_rows if not as_text(hit.get("page_id")).strip()),
        "missing_candidate_id_count": sum(1 for hit in hit_rows if hit.get("collection_role") == "candidate" and not as_text(hit.get("embedding_candidate_id")).strip()),
        "missing_profile_id_count": sum(1 for hit in hit_rows if hit.get("collection_role") == "page_profile" and not as_text(hit.get("profile_id") or hit.get("embedding_candidate_id")).strip()),
        "unsafe_hit_payload_count": len(unsafe_hits),
        "direct_answer_allowed_hit_count": sum(1 for hit in hit_rows if as_bool(hit.get("can_answer_directly"), default=False) or as_bool(hit.get("qdrant_can_answer_directly"), default=False)),
        "claim_proof_allowed_hit_count": sum(1 for hit in hit_rows if as_bool(hit.get("can_prove_claims"), default=False) or as_bool(hit.get("qdrant_can_prove_claims"), default=False)),
        "qdrant_source_truth_hit_count": sum(1 for hit in hit_rows if as_bool(hit.get("qdrant_is_source_truth"), default=False)),
        "answer_authority_allowed_hit_count": sum(1 for hit in hit_rows if as_bool(hit.get("embedding_answer_authority_allowed"), default=False)),
        "answer_capable_page_profile_count": sum(1 for hit in page_profile_hits if as_bool(hit.get("can_answer_directly"), default=False) or as_bool(hit.get("qdrant_can_answer_directly"), default=False) or as_bool(hit.get("embedding_answer_authority_allowed"), default=False)),
        "context_helper_answer_allowed_count": sum(1 for hit in context_helper_hits if as_bool(hit.get("can_answer_directly"), default=False) or as_bool(hit.get("embedding_answer_authority_allowed"), default=False)),
        "source_evidence_answer_allowed_count": sum(1 for hit in source_evidence_hits if as_bool(hit.get("can_answer_directly"), default=False) or as_bool(hit.get("embedding_answer_authority_allowed"), default=False)),
        "source_evidence_claim_proof_allowed_count": sum(1 for hit in source_evidence_hits if as_bool(hit.get("can_prove_claims"), default=False)),
        "retrieval_only_hit_count": sum(1 for hit in hit_rows if as_text(hit.get("rag_bucket")) in RETRIEVAL_ONLY_BUCKETS),
        "candidate_collection": candidate_collection,
        "page_profile_collection": page_profile_collection,
        "candidate_collection_count": candidate_collection_count,
        "page_profile_collection_count": page_profile_collection_count,
        "candidate_collection_vector_size": candidate_collection_vector_size,
        "page_profile_collection_vector_size": page_profile_collection_vector_size,
        "embedding_mode": normalized_embedding_mode(embedding_mode),
        "embedding_model_name": embedding_model_name,
        "embedding_dim": int(embedding_dim),
        "bucket_counts": dict(sorted(by_bucket.items())),
        "authority_counts": dict(sorted(by_authority.items())),
        "unsafe_reason_counts": dict(sorted(Counter(reason for hit in unsafe_hits for reason in (hit.get("unsafe_reasons") or [])).items())),
    }


def check_vector_search_smoke_quality(
    summary: Mapping[str, Any],
    *,
    min_smoke_queries: int = 1,
    min_total_hits: int = 1,
    min_candidate_hits: int = 1,
    min_page_profile_hits: int = 1,
    min_queries_with_candidate_hits: int = 1,
    min_queries_with_page_profile_hits: int = 1,
    min_candidate_collection_count: int = 1,
    min_page_profile_collection_count: int = 1,
    require_candidate_count: int | None = None,
    require_page_profile_count: int | None = None,
    require_embedding_dim: int | None = None,
) -> QualityResult:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, expected: Any, actual: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "expected": expected, "actual": actual})

    add_check("min_smoke_queries", int(summary.get("smoke_query_count") or 0) >= min_smoke_queries, f">= {min_smoke_queries}", summary.get("smoke_query_count"))
    add_check("min_total_hits", int(summary.get("total_hit_count") or 0) >= min_total_hits, f">= {min_total_hits}", summary.get("total_hit_count"))
    add_check("min_candidate_hits", int(summary.get("candidate_hit_count") or 0) >= min_candidate_hits, f">= {min_candidate_hits}", summary.get("candidate_hit_count"))
    add_check("min_page_profile_hits", int(summary.get("page_profile_hit_count") or 0) >= min_page_profile_hits, f">= {min_page_profile_hits}", summary.get("page_profile_hit_count"))
    add_check("min_queries_with_candidate_hits", int(summary.get("queries_with_candidate_hits") or 0) >= min_queries_with_candidate_hits, f">= {min_queries_with_candidate_hits}", summary.get("queries_with_candidate_hits"))
    add_check("min_queries_with_page_profile_hits", int(summary.get("queries_with_page_profile_hits") or 0) >= min_queries_with_page_profile_hits, f">= {min_queries_with_page_profile_hits}", summary.get("queries_with_page_profile_hits"))
    add_check("missing_page_id_count", int(summary.get("missing_page_id_count") or 0) == 0, 0, summary.get("missing_page_id_count"))
    add_check("missing_candidate_id_count", int(summary.get("missing_candidate_id_count") or 0) == 0, 0, summary.get("missing_candidate_id_count"))
    add_check("missing_profile_id_count", int(summary.get("missing_profile_id_count") or 0) == 0, 0, summary.get("missing_profile_id_count"))
    add_check("unsafe_hit_payload_count", int(summary.get("unsafe_hit_payload_count") or 0) == 0, 0, summary.get("unsafe_hit_payload_count"))
    add_check("direct_answer_allowed_hit_count", int(summary.get("direct_answer_allowed_hit_count") or 0) == 0, 0, summary.get("direct_answer_allowed_hit_count"))
    add_check("claim_proof_allowed_hit_count", int(summary.get("claim_proof_allowed_hit_count") or 0) == 0, 0, summary.get("claim_proof_allowed_hit_count"))
    add_check("qdrant_source_truth_hit_count", int(summary.get("qdrant_source_truth_hit_count") or 0) == 0, 0, summary.get("qdrant_source_truth_hit_count"))
    add_check("answer_authority_allowed_hit_count", int(summary.get("answer_authority_allowed_hit_count") or 0) == 0, 0, summary.get("answer_authority_allowed_hit_count"))
    add_check("answer_capable_page_profile_count", int(summary.get("answer_capable_page_profile_count") or 0) == 0, 0, summary.get("answer_capable_page_profile_count"))
    add_check("context_helper_answer_allowed_count", int(summary.get("context_helper_answer_allowed_count") or 0) == 0, 0, summary.get("context_helper_answer_allowed_count"))
    add_check("source_evidence_answer_allowed_count", int(summary.get("source_evidence_answer_allowed_count") or 0) == 0, 0, summary.get("source_evidence_answer_allowed_count"))
    add_check("source_evidence_claim_proof_allowed_count", int(summary.get("source_evidence_claim_proof_allowed_count") or 0) == 0, 0, summary.get("source_evidence_claim_proof_allowed_count"))
    candidate_collection_count = summary.get("candidate_collection_count")
    page_profile_collection_count = summary.get("page_profile_collection_count")
    add_check("min_candidate_collection_count", int(candidate_collection_count or 0) >= min_candidate_collection_count, f">= {min_candidate_collection_count}", candidate_collection_count)
    add_check("min_page_profile_collection_count", int(page_profile_collection_count or 0) >= min_page_profile_collection_count, f">= {min_page_profile_collection_count}", page_profile_collection_count)
    if require_candidate_count is not None:
        add_check("candidate_collection_count_exact", int(candidate_collection_count or 0) == int(require_candidate_count), int(require_candidate_count), candidate_collection_count)
    if require_page_profile_count is not None:
        add_check("page_profile_collection_count_exact", int(page_profile_collection_count or 0) == int(require_page_profile_count), int(require_page_profile_count), page_profile_collection_count)
    if require_embedding_dim is not None:
        add_check("candidate_collection_vector_size", int(summary.get("candidate_collection_vector_size") or 0) == int(require_embedding_dim), int(require_embedding_dim), summary.get("candidate_collection_vector_size"))
        add_check("page_profile_collection_vector_size", int(summary.get("page_profile_collection_vector_size") or 0) == int(require_embedding_dim), int(require_embedding_dim), summary.get("page_profile_collection_vector_size"))
        add_check("query_embedding_dim", int(summary.get("embedding_dim") or 0) == int(require_embedding_dim), int(require_embedding_dim), summary.get("embedding_dim"))
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def run_vector_search_smoke(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    api_key: str | None = None,
    candidate_collection: str = DEFAULT_CANDIDATE_COLLECTION,
    page_profile_collection: str = DEFAULT_PAGE_PROFILE_COLLECTION,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_device: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    ollama_timeout: float = DEFAULT_OLLAMA_TIMEOUT,
    queries: Sequence[Mapping[str, Any]] | None = None,
    limit: int = DEFAULT_LIMIT,
    score_threshold: float | None = DEFAULT_MIN_SCORE,
    client: SearchClient | None = None,
    min_smoke_queries: int = 1,
    min_total_hits: int = 1,
    min_candidate_hits: int = 1,
    min_page_profile_hits: int = 1,
    min_queries_with_candidate_hits: int = 1,
    min_queries_with_page_profile_hits: int = 1,
    min_candidate_collection_count: int = 1,
    min_page_profile_collection_count: int = 1,
    require_candidate_count: int | None = None,
    require_page_profile_count: int | None = None,
    require_embedding_dim: int | None = None,
    quality: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    query_rows = [dict(query) for query in (queries or default_queries())]
    if not query_rows:
        raise VectorSmokeError("no smoke queries were provided")
    client = client or SearchClient(qdrant_url, api_key=api_key)
    candidate_count = collection_count(client, candidate_collection)
    page_profile_count = collection_count(client, page_profile_collection)
    candidate_vector_size = collection_vector_size(client, candidate_collection)
    page_profile_vector_size = collection_vector_size(client, page_profile_collection)
    all_hits: list[dict[str, Any]] = []
    model_names: list[str] = []
    for query in query_rows:
        vector, model_name = query_vector(
            as_text(query.get("query_text")),
            embedding_mode=embedding_mode,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            embedding_device=embedding_device,
            ollama_url=ollama_url,
            ollama_endpoint=ollama_endpoint,
            ollama_timeout=ollama_timeout,
        )
        model_names.append(model_name)
        candidate_hits = client.search_points(
            candidate_collection,
            vector,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        page_hits = client.search_points(
            page_profile_collection,
            vector,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        for rank, hit in enumerate(candidate_hits, start=1):
            all_hits.append(normalized_hit(query=query, collection=candidate_collection, collection_role="candidate", rank=rank, hit=hit))
        for rank, hit in enumerate(page_hits, start=1):
            all_hits.append(normalized_hit(query=query, collection=page_profile_collection, collection_role="page_profile", rank=rank, hit=hit))
    embedding_model_name = model_names[0] if model_names else qdrant_loader.embedding_model_name_for_mode(embedding_mode, embedding_model)
    summary = summarize_hits(
        queries=query_rows,
        hits=all_hits,
        candidate_collection=candidate_collection,
        page_profile_collection=page_profile_collection,
        candidate_collection_count=candidate_count,
        page_profile_collection_count=page_profile_count,
        candidate_collection_vector_size=candidate_vector_size,
        page_profile_collection_vector_size=page_profile_vector_size,
        embedding_mode=embedding_mode,
        embedding_model_name=embedding_model_name,
        embedding_dim=embedding_dim,
    )
    quality_result = check_vector_search_smoke_quality(
        summary,
        min_smoke_queries=min_smoke_queries,
        min_total_hits=min_total_hits,
        min_candidate_hits=min_candidate_hits,
        min_page_profile_hits=min_page_profile_hits,
        min_queries_with_candidate_hits=min_queries_with_candidate_hits,
        min_queries_with_page_profile_hits=min_queries_with_page_profile_hits,
        min_candidate_collection_count=min_candidate_collection_count,
        min_page_profile_collection_count=min_page_profile_collection_count,
        require_candidate_count=require_candidate_count,
        require_page_profile_count=require_page_profile_count,
        require_embedding_dim=require_embedding_dim,
    )
    smoke_path = output_dir / DEFAULT_SMOKE_FILE
    hits_path = output_dir / DEFAULT_HITS_JSONL_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "SMOKE_RAN",
        "quality_status": quality_result.status,
        "generated_at_utc": utc_now_iso(),
        "qdrant_url": qdrant_url,
        "candidate_collection": candidate_collection,
        "page_profile_collection": page_profile_collection,
        "embedding_mode": normalized_embedding_mode(embedding_mode),
        "embedding_model_name": embedding_model_name,
        "embedding_dim": int(embedding_dim),
        "smoke_path": str(smoke_path),
        "hits_jsonl_path": str(hits_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "smoke_query_count": summary.get("smoke_query_count"),
        "total_hit_count": summary.get("total_hit_count"),
        "candidate_collection_count": candidate_count,
        "page_profile_collection_count": page_profile_count,
    }
    smoke_payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "SMOKE_RAN",
        "quality_status": quality_result.status,
        "queries": query_rows,
        "hits": all_hits,
        "summary": summary,
        "manifest": manifest,
        "quality": {"status": quality_result.status, "checks": quality_result.checks, "summary": summary},
    }
    write_json(smoke_path, smoke_payload)
    write_jsonl(hits_path, all_hits)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    if quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality_result.status, "checks": quality_result.checks, "summary": summary})
    return {
        "status": "SMOKE_RAN",
        "quality_status": quality_result.status,
        "summary": summary,
        "manifest": manifest,
        "paths": {
            "smoke_path": str(smoke_path),
            "hits_jsonl_path": str(hits_path),
            "summary_path": str(summary_path),
            "manifest_path": str(manifest_path),
            "quality_path": str(quality_path),
        },
        "quality": quality_result,
    }


def check_vector_search_smoke_quality_from_file(
    *,
    smoke_path: Path | None = None,
    summary_path: Path | None = None,
    min_smoke_queries: int = 1,
    min_total_hits: int = 1,
    min_candidate_hits: int = 1,
    min_page_profile_hits: int = 1,
    min_queries_with_candidate_hits: int = 1,
    min_queries_with_page_profile_hits: int = 1,
    min_candidate_collection_count: int = 1,
    min_page_profile_collection_count: int = 1,
    require_candidate_count: int | None = None,
    require_page_profile_count: int | None = None,
    require_embedding_dim: int | None = None,
    write_json_output: bool = False,
) -> tuple[QualityResult, Path]:
    if summary_path is not None:
        summary = read_json(Path(summary_path))
        base_path = Path(summary_path).parent
    elif smoke_path is not None:
        payload = read_json(Path(smoke_path))
        summary = dict(payload.get("summary") or {})
        base_path = Path(smoke_path).parent
    else:
        raise VectorSmokeError("provide --smoke-path or --summary-path")
    quality_result = check_vector_search_smoke_quality(
        summary,
        min_smoke_queries=min_smoke_queries,
        min_total_hits=min_total_hits,
        min_candidate_hits=min_candidate_hits,
        min_page_profile_hits=min_page_profile_hits,
        min_queries_with_candidate_hits=min_queries_with_candidate_hits,
        min_queries_with_page_profile_hits=min_queries_with_page_profile_hits,
        min_candidate_collection_count=min_candidate_collection_count,
        min_page_profile_collection_count=min_page_profile_collection_count,
        require_candidate_count=require_candidate_count,
        require_page_profile_count=require_page_profile_count,
        require_embedding_dim=require_embedding_dim,
    )
    quality_path = base_path / DEFAULT_QUALITY_FILE
    if write_json_output:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality_result.status, "checks": quality_result.checks, "summary": quality_result.summary})
    return quality_result, quality_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TRACE-Net vector search smoke tests against Qdrant.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL))
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY"))
    parser.add_argument("--candidate-collection", default=os.environ.get("TRACE_NET_QDRANT_COLLECTION", DEFAULT_CANDIDATE_COLLECTION))
    parser.add_argument("--page-profile-collection", default=os.environ.get("TRACE_NET_PAGE_PROFILE_QDRANT_COLLECTION", DEFAULT_PAGE_PROFILE_COLLECTION))
    parser.add_argument("--embedding-mode", default=os.environ.get("TRACE_NET_EMBEDDING_MODE", DEFAULT_EMBEDDING_MODE), choices=["hash", "sentence-transformers", "sentence_transformers", "bge-m3", "bge_m3", "real", "ollama", "ollama-embed", "ollama_embed", "ollama-embeddings", "ollama_embeddings"])
    parser.add_argument("--embedding-model", default=os.environ.get("TRACE_NET_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL))
    parser.add_argument("--embedding-device", default=os.environ.get("TRACE_NET_EMBEDDING_DEVICE", ""))
    parser.add_argument("--embedding-dim", type=int, default=int(os.environ.get("TRACE_NET_EMBEDDING_DIM", DEFAULT_EMBEDDING_DIM)))
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", os.environ.get("TRACE_NET_OLLAMA_URL", DEFAULT_OLLAMA_URL)))
    parser.add_argument("--ollama-endpoint", default=os.environ.get("OLLAMA_EMBED_ENDPOINT", os.environ.get("TRACE_NET_OLLAMA_EMBED_ENDPOINT", DEFAULT_OLLAMA_ENDPOINT)))
    parser.add_argument("--ollama-timeout", type=float, default=float(os.environ.get("TRACE_NET_OLLAMA_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT)))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--score-threshold", type=float, default=None)
    parser.add_argument("--query", action="append", default=[], help="Custom query text or query_id::query text. Repeatable.")
    parser.add_argument("--min-smoke-queries", type=int, default=1)
    parser.add_argument("--min-total-hits", type=int, default=1)
    parser.add_argument("--min-candidate-hits", type=int, default=1)
    parser.add_argument("--min-page-profile-hits", type=int, default=1)
    parser.add_argument("--min-queries-with-candidate-hits", type=int, default=1)
    parser.add_argument("--min-queries-with-page-profile-hits", type=int, default=1)
    parser.add_argument("--min-candidate-collection-count", type=int, default=1)
    parser.add_argument("--min-page-profile-collection-count", type=int, default=1)
    parser.add_argument("--require-candidate-count", type=int, default=None)
    parser.add_argument("--require-page-profile-count", type=int, default=None)
    parser.add_argument("--require-embedding-dim", type=int, default=None)
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    result = run_vector_search_smoke(
        output_dir=args.output_dir,
        qdrant_url=args.qdrant_url,
        api_key=args.api_key,
        candidate_collection=args.candidate_collection,
        page_profile_collection=args.page_profile_collection,
        embedding_mode=args.embedding_mode,
        embedding_model=args.embedding_model,
        embedding_dim=args.embedding_dim,
        embedding_device=args.embedding_device or None,
        ollama_url=args.ollama_url,
        ollama_endpoint=args.ollama_endpoint,
        ollama_timeout=args.ollama_timeout,
        queries=parse_query_items(args.query),
        limit=args.limit,
        score_threshold=args.score_threshold,
        min_smoke_queries=args.min_smoke_queries,
        min_total_hits=args.min_total_hits,
        min_candidate_hits=args.min_candidate_hits,
        min_page_profile_hits=args.min_page_profile_hits,
        min_queries_with_candidate_hits=args.min_queries_with_candidate_hits,
        min_queries_with_page_profile_hits=args.min_queries_with_page_profile_hits,
        min_candidate_collection_count=args.min_candidate_collection_count,
        min_page_profile_collection_count=args.min_page_profile_collection_count,
        require_candidate_count=args.require_candidate_count,
        require_page_profile_count=args.require_page_profile_count,
        require_embedding_dim=args.require_embedding_dim,
        quality=args.quality,
    )
    summary = result["summary"]
    print("TRACE-Net vector search smoke v1")
    print(" Status: SMOKE_RAN")
    print(f" Quality status: {result['quality_status']}")
    print(f" embedding_mode: {summary.get('embedding_mode')}")
    print(f" embedding_model_name: {summary.get('embedding_model_name')}")
    print(f" embedding_dim: {summary.get('embedding_dim')}")
    print(f" smoke_query_count: {summary.get('smoke_query_count')}")
    print(f" total_hit_count: {summary.get('total_hit_count')}")
    print(f" candidate_hit_count: {summary.get('candidate_hit_count')}")
    print(f" page_profile_hit_count: {summary.get('page_profile_hit_count')}")
    print(f" candidate_collection_count: {summary.get('candidate_collection_count')}")
    print(f" page_profile_collection_count: {summary.get('page_profile_collection_count')}")
    print(f" unsafe_hit_payload_count: {summary.get('unsafe_hit_payload_count')}")
    print(f" direct_answer_allowed_hit_count: {summary.get('direct_answer_allowed_hit_count')}")
    print(f" claim_proof_allowed_hit_count: {summary.get('claim_proof_allowed_hit_count')}")
    print(f" smoke_path: {result['paths']['smoke_path']}")
    print(f" hits_jsonl_path: {result['paths']['hits_jsonl_path']}")
    print(f" manifest_path: {result['paths']['manifest_path']}")
    if args.quality:
        print(f" quality_path: {result['paths']['quality_path']}")
    return 0 if (not args.quality or result["quality"].passed) else 1


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net vector search smoke quality.")
    parser.add_argument("--smoke-path", type=Path, default=None)
    parser.add_argument("--summary-path", type=Path, default=None)
    parser.add_argument("--min-smoke-queries", type=int, default=1)
    parser.add_argument("--min-total-hits", type=int, default=1)
    parser.add_argument("--min-candidate-hits", type=int, default=1)
    parser.add_argument("--min-page-profile-hits", type=int, default=1)
    parser.add_argument("--min-queries-with-candidate-hits", type=int, default=1)
    parser.add_argument("--min-queries-with-page-profile-hits", type=int, default=1)
    parser.add_argument("--min-candidate-collection-count", type=int, default=1)
    parser.add_argument("--min-page-profile-collection-count", type=int, default=1)
    parser.add_argument("--require-candidate-count", type=int, default=None)
    parser.add_argument("--require-page-profile-count", type=int, default=None)
    parser.add_argument("--require-embedding-dim", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = build_quality_arg_parser()
    args = parser.parse_args(argv)
    if args.smoke_path is None and args.summary_path is None:
        args.smoke_path = DEFAULT_OUTPUT_DIR / DEFAULT_SMOKE_FILE
    quality_result, quality_path = check_vector_search_smoke_quality_from_file(
        smoke_path=args.smoke_path,
        summary_path=args.summary_path,
        min_smoke_queries=args.min_smoke_queries,
        min_total_hits=args.min_total_hits,
        min_candidate_hits=args.min_candidate_hits,
        min_page_profile_hits=args.min_page_profile_hits,
        min_queries_with_candidate_hits=args.min_queries_with_candidate_hits,
        min_queries_with_page_profile_hits=args.min_queries_with_page_profile_hits,
        min_candidate_collection_count=args.min_candidate_collection_count,
        min_page_profile_collection_count=args.min_page_profile_collection_count,
        require_candidate_count=args.require_candidate_count,
        require_page_profile_count=args.require_page_profile_count,
        require_embedding_dim=args.require_embedding_dim,
        write_json_output=args.write_json,
    )
    summary = quality_result.summary
    print("TRACE-Net vector search smoke v1 quality")
    print(f" Status: {quality_result.status}")
    print(f" smoke_query_count: {summary.get('smoke_query_count')}")
    print(f" total_hit_count: {summary.get('total_hit_count')}")
    print(f" candidate_hit_count: {summary.get('candidate_hit_count')}")
    print(f" page_profile_hit_count: {summary.get('page_profile_hit_count')}")
    print(f" candidate_collection_count: {summary.get('candidate_collection_count')}")
    print(f" page_profile_collection_count: {summary.get('page_profile_collection_count')}")
    print(f" unsafe_hit_payload_count: {summary.get('unsafe_hit_payload_count')}")
    print(f" direct_answer_allowed_hit_count: {summary.get('direct_answer_allowed_hit_count')}")
    print(f" claim_proof_allowed_hit_count: {summary.get('claim_proof_allowed_hit_count')}")
    if args.write_json:
        print(f" quality_path: {quality_path}")
    return 0 if quality_result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
