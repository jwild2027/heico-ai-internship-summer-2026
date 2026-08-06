"""TRACE-Net Hybrid Retrieval Simulation v1.

Step 7 combines the two TRACE-Net vector layers without wiring them into ask:

* page profile vectors: coarse routing across all 509 pages.
* embedding candidate vectors: source/citation/context helper candidates.

This module runs query embeddings, searches both Qdrant collections, resolves hits
against local TRACE-Net artifacts, groups by page, and writes a read-only
simulation report. It intentionally does not answer questions, does not mutate
source truth, and does not treat Qdrant payloads as proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from tiff.trace_net_qdrant_loader_v1 import (  # type: ignore
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_EMBED_ENDPOINT,
    DEFAULT_OLLAMA_TIMEOUT,
    DEFAULT_OLLAMA_URL,
    DEFAULT_QDRANT_URL,
    DEFAULT_REAL_EMBEDDING_DIM,
    DEFAULT_REAL_EMBEDDING_MODEL,
    QdrantLoaderError,
    QdrantRestClient,
    as_bool,
    as_text,
    deterministic_hash_embedding,
    is_ollama_mode,
    is_sentence_transformer_mode,
    json_safe,
    normalized_embedding_mode,
    ollama_embeddings,
    sentence_transformer_embeddings,
)

SCHEMA_VERSION = "trace_net_hybrid_retrieval_sim_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/hybrid_retrieval_sim")
DEFAULT_CANDIDATE_COLLECTION = "trace_net_embedding_candidates_v1"
DEFAULT_PAGE_PROFILE_COLLECTION = "trace_net_page_retrieval_profiles_v1"
DEFAULT_EMBEDDING_CANDIDATES = Path(
    "local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json"
)
DEFAULT_PAGE_PROFILES = Path(
    "local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json"
)
DEFAULT_VECTOR_SMOKE_REPORT = Path(
    "local_data/organization/trace_net/vector_search_smoke/trace_net_vector_search_smoke_v1.json"
)
DEFAULT_REPORT_FILE = "trace_net_hybrid_retrieval_sim_v1.json"
DEFAULT_RESULTS_FILE = "trace_net_hybrid_retrieval_sim_v1_results.jsonl"
DEFAULT_GROUPS_FILE = "trace_net_hybrid_retrieval_sim_v1_groups.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_hybrid_retrieval_sim_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_hybrid_retrieval_sim_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_hybrid_retrieval_sim_v1_quality.json"
DEFAULT_EMBEDDING_MODE = "ollama"
DEFAULT_EMBEDDING_MODEL = DEFAULT_OLLAMA_EMBEDDING_MODEL
DEFAULT_EMBEDDING_DIM = DEFAULT_REAL_EMBEDDING_DIM
DEFAULT_TOP_K = 8
DEFAULT_QUERY_BATCH_SIZE = 16

PAGE_PROFILE_BUCKET = "page_retrieval_profile"
CONTEXT_HELPER_BUCKET = "context_retrieval_helper"
SOURCE_EVIDENCE_BUCKET = "source_evidence"
ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
RETRIEVAL_ONLY_BUCKETS = {
    "source_evidence",
    "derived_context",
    "context_retrieval_helper",
    PAGE_PROFILE_BUCKET,
}
SAFE_CANDIDATE_BUCKETS = {
    "source_evidence",
    "source_text_evidence",
    "verified_part_evidence",
    "derived_context",
    "context_retrieval_helper",
}
SAFE_PAGE_BUCKETS = {PAGE_PROFILE_BUCKET}
BANNED_BUCKETS = {
    "raw_ocr",
    "raw_ocr_unfiltered",
    "raw_visual_text",
    "raw_visual_extraction",
    "raw_table_extraction",
    "table_candidate",
    "table_candidates",
    "table_tile",
    "table_tiles",
    "excluded",
    "unsafe",
    "prompt",
    "debug",
    "feedback_only",
}
TRUST_BOOSTS = {
    "A": 0.22,
    "A+": 0.25,
    "B": 0.16,
    "B+": 0.18,
    "C": 0.08,
    "RETRIEVAL_ONLY": 0.02,
    "SOURCE_EXISTS_ONLY": 0.02,
}

DEFAULT_HYBRID_QUERIES = [
    {
        "query_id": "manual_revision_history",
        "query": "T.P. 120/1176 Revision 4 Embraer manual revision history title block supersedes",
        "intent": "route_to_revision_source_page",
    },
    {
        "query_id": "ata_25_21_placards",
        "query": "ATA 25-21-00 placards decals warning labels cabin interior equipment manual",
        "intent": "route_to_ata_or_page_evidence",
    },
    {
        "query_id": "part_nomenclature_lookup",
        "query": "part number item quantity nomenclature figure table source evidence",
        "intent": "route_to_part_and_nomenclature_evidence",
    },
    {
        "query_id": "source_trace_page_000001",
        "query": "source trace page 000001 ResCarta TIFF OCR technical manual page evidence",
        "intent": "route_to_page_source_trace",
    },
    {
        "query_id": "technical_publication_evidence",
        "query": "Embraer aircraft technical publication manual evidence source citation page reference",
        "intent": "route_to_source_backed_candidates",
    },
]


class HybridRetrievalSimError(RuntimeError):
    """Raised when hybrid retrieval simulation cannot complete safely."""


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


def _json_safe(value: Any) -> Any:
    try:
        return json_safe(value)
    except Exception:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {str(k): _json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [_json_safe(v) for v in value]
        return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(_json_safe(payload), handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(_json_safe(row), sort_keys=True, ensure_ascii=False))
            handle.write("\n")


def sha256_json(value: Any) -> str:
    payload = json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact_text(value: Any, *, max_chars: int = 6000) -> str:
    text = as_text(value).replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def normalize_bucket(value: Any) -> str:
    return as_text(value).strip().lower().replace("-", "_").replace(" ", "_")


def payload_bucket(payload: Mapping[str, Any]) -> str:
    return normalize_bucket(
        payload.get("rag_bucket")
        or payload.get("embedding_bucket")
        or payload.get("record_type")
        or payload.get("candidate_type")
    )


def stable_hit_key(hit: Mapping[str, Any]) -> str:
    parts = [
        as_text(hit.get("collection_role")),
        as_text(hit.get("id")),
        as_text(hit.get("embedding_candidate_id")),
        as_text(hit.get("profile_id")),
        as_text(hit.get("source_candidate_id")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def parse_query_file(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = read_json(Path(path))
    raw = payload.get("queries") if isinstance(payload, Mapping) else payload
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise HybridRetrievalSimError(f"query file must be a list or contain a queries list: {path}")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, Mapping):
            query = compact_text(item.get("query") or item.get("text"))
            if query:
                rows.append(
                    {
                        "query_id": as_text(item.get("query_id") or item.get("id") or f"query_{index:03d}"),
                        "query": query,
                        "intent": as_text(item.get("intent")),
                    }
                )
        else:
            query = compact_text(item)
            if query:
                rows.append({"query_id": f"query_{index:03d}", "query": query, "intent": ""})
    return rows


def load_queries(queries_path: Path | None = None, inline_queries: Sequence[str] | None = None) -> list[dict[str, Any]]:
    rows = parse_query_file(queries_path)
    offset = len(rows)
    for index, query_text in enumerate(inline_queries or [], start=1):
        query = compact_text(query_text)
        if query:
            rows.append({"query_id": f"inline_{offset + index:03d}", "query": query, "intent": ""})
    return rows or [dict(item) for item in DEFAULT_HYBRID_QUERIES]


def load_records_artifact(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = read_json(Path(path))
    if isinstance(payload, Mapping):
        raw = payload.get("records") or payload.get("profiles") or payload.get("candidates") or []
    else:
        raw = payload
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise HybridRetrievalSimError(f"artifact does not contain a records list: {path}")
    records = [dict(item) for item in raw if isinstance(item, Mapping)]
    meta = dict(payload) if isinstance(payload, Mapping) else {"record_count": len(records)}
    return records, meta


def build_resolution_indexes(
    candidate_records: Sequence[Mapping[str, Any]],
    page_profile_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidates_by_embedding_id: dict[str, dict[str, Any]] = {}
    candidates_by_source_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidates_by_page_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profiles_by_profile_id: dict[str, dict[str, Any]] = {}
    profiles_by_page_id: dict[str, dict[str, Any]] = {}
    for record in candidate_records:
        item = dict(record)
        embedding_id = as_text(item.get("embedding_candidate_id"))
        source_id = as_text(item.get("source_candidate_id"))
        page_id = as_text(item.get("page_id"))
        if embedding_id:
            candidates_by_embedding_id[embedding_id] = item
        if source_id:
            candidates_by_source_id[source_id].append(item)
        if page_id:
            candidates_by_page_id[page_id].append(item)
    for record in page_profile_records:
        item = dict(record)
        profile_id = as_text(item.get("profile_id"))
        page_id = as_text(item.get("page_id"))
        if profile_id:
            profiles_by_profile_id[profile_id] = item
        if page_id:
            profiles_by_page_id[page_id] = item
    return {
        "candidates_by_embedding_id": candidates_by_embedding_id,
        "candidates_by_source_id": dict(candidates_by_source_id),
        "candidates_by_page_id": dict(candidates_by_page_id),
        "profiles_by_profile_id": profiles_by_profile_id,
        "profiles_by_page_id": profiles_by_page_id,
        "candidate_count": len(candidate_records),
        "page_profile_count": len(page_profile_records),
    }


def embed_query_texts(
    texts: Sequence[str],
    *,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_device: str | None = None,
    batch_size: int = DEFAULT_QUERY_BATCH_SIZE,
    ollama_url: str | None = None,
    ollama_endpoint: str | None = None,
    ollama_timeout: float | None = None,
) -> tuple[list[list[float]], str]:
    mode = normalized_embedding_mode(embedding_mode)
    clean_texts = [compact_text(text) for text in texts]
    if mode == "hash":
        return [deterministic_hash_embedding(text, dim=embedding_dim) for text in clean_texts], "trace_net_hash_embed_v1"
    if is_ollama_mode(mode):
        model_name = as_text(embedding_model or DEFAULT_OLLAMA_EMBEDDING_MODEL).strip() or DEFAULT_OLLAMA_EMBEDDING_MODEL
        return ollama_embeddings(
            clean_texts,
            model_name=model_name,
            expected_dim=embedding_dim,
            ollama_url=ollama_url or DEFAULT_OLLAMA_URL,
            endpoint=ollama_endpoint or DEFAULT_OLLAMA_EMBED_ENDPOINT,
            timeout=float(ollama_timeout or DEFAULT_OLLAMA_TIMEOUT),
            batch_size=batch_size,
        ), model_name
    if is_sentence_transformer_mode(mode):
        model_name = as_text(embedding_model or DEFAULT_REAL_EMBEDDING_MODEL).strip() or DEFAULT_REAL_EMBEDDING_MODEL
        return (
            sentence_transformer_embeddings(
                clean_texts,
                model_name=model_name,
                expected_dim=embedding_dim,
                device=embedding_device,
                batch_size=batch_size,
            ),
            model_name,
        )
    raise HybridRetrievalSimError(f"unsupported embedding mode: {embedding_mode}")


class QdrantHybridClient(QdrantRestClient):
    """Small Qdrant search client used by hybrid simulation."""

    def search_points(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        limit: int = DEFAULT_TOP_K,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        payload = {
            "vector": [float(value) for value in vector],
            "limit": int(limit),
            "with_payload": True,
            "with_vector": False,
        }
        if score_threshold is not None:
            payload["score_threshold"] = float(score_threshold)
        try:
            response = self.request("POST", f"/collections/{quote(collection, safe='')}/points/search", payload)
        except (KeyError, QdrantLoaderError) as exc:
            if isinstance(exc, QdrantLoaderError) and "HTTP 404" not in str(exc):
                raise
            response = self.request(
                "POST",
                f"/collections/{quote(collection, safe='')}/points/query",
                {
                    "query": [float(value) for value in vector],
                    "limit": int(limit),
                    "with_payload": True,
                    "with_vector": False,
                },
            )
        return normalize_qdrant_hits(response)


def normalize_qdrant_hits(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = response.get("result")
    if isinstance(result, list):
        raw_hits = result
    elif isinstance(result, Mapping):
        raw_hits = result.get("points") or result.get("hits") or result.get("result") or []
    else:
        raw_hits = []
    hits: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_hits, start=1):
        if not isinstance(raw, Mapping):
            continue
        payload = raw.get("payload") if isinstance(raw.get("payload"), Mapping) else {}
        score = raw.get("score")
        if score is None:
            score = raw.get("similarity") or raw.get("distance") or 0.0
        hits.append({"rank": index, "id": raw.get("id"), "score": float(score or 0.0), "payload": dict(payload)})
    return hits


def unsafe_payload_reasons(payload: Mapping[str, Any], *, collection_role: str) -> list[str]:
    reasons: list[str] = []
    bucket = payload_bucket(payload)
    if not as_text(payload.get("page_id")):
        reasons.append("missing_page_id")
    if collection_role == "page_profile":
        if bucket not in SAFE_PAGE_BUCKETS:
            reasons.append("page_profile_bucket_not_safe")
        if not as_text(payload.get("profile_id")):
            reasons.append("missing_profile_id")
        if as_text(payload.get("authority")) != "page_route_only":
            reasons.append("page_profile_authority_not_route_only")
    else:
        if bucket not in SAFE_CANDIDATE_BUCKETS:
            reasons.append("candidate_bucket_not_safe")
        if not as_text(payload.get("embedding_candidate_id")):
            reasons.append("missing_embedding_candidate_id")
        if not as_text(payload.get("source_candidate_id")):
            reasons.append("missing_source_candidate_id")
    if bucket in BANNED_BUCKETS:
        reasons.append("banned_bucket")
    if as_bool(payload.get("qdrant_is_source_truth"), default=False):
        reasons.append("qdrant_is_source_truth")
    if as_bool(payload.get("qdrant_can_answer_directly"), default=False):
        reasons.append("qdrant_can_answer_directly")
    if as_bool(payload.get("qdrant_can_prove_claims"), default=False):
        reasons.append("qdrant_can_prove_claims")
    if as_bool(payload.get("can_answer_directly"), default=False):
        reasons.append("payload_can_answer_directly")
    if as_bool(payload.get("can_prove_claims"), default=False):
        reasons.append("payload_can_prove_claims")
    if as_bool(payload.get("canonical_source_truth"), default=False):
        reasons.append("payload_marked_canonical_source_truth")
    if as_bool(payload.get("can_mutate_source_truth"), default=False):
        reasons.append("payload_can_mutate_source_truth")
    if as_bool(payload.get("embedding_answer_authority_allowed"), default=False):
        reasons.append("embedding_answer_authority_allowed")
    if as_bool(payload.get("must_resolve_through_postgres"), default=True) is not True:
        reasons.append("must_resolve_through_postgres_false")
    if as_bool(payload.get("requires_source_resolution"), default=False) is not True:
        reasons.append("requires_source_resolution_false")
    if as_bool(payload.get("requires_citation"), default=False) is not True:
        reasons.append("requires_citation_false")
    if as_bool(payload.get("requires_authority_gate"), default=False) is not True:
        reasons.append("requires_authority_gate_false")
    return reasons


def resolve_candidate_hit(payload: Mapping[str, Any], indexes: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    embedding_id = as_text(payload.get("embedding_candidate_id"))
    source_id = as_text(payload.get("source_candidate_id"))
    page_id = as_text(payload.get("page_id"))
    candidates_by_embedding = indexes.get("candidates_by_embedding_id") or {}
    candidates_by_source = indexes.get("candidates_by_source_id") or {}
    candidates_by_page = indexes.get("candidates_by_page_id") or {}
    if embedding_id and embedding_id in candidates_by_embedding:
        return dict(candidates_by_embedding[embedding_id]), []
    if source_id and candidates_by_source.get(source_id):
        return dict(candidates_by_source[source_id][0]), ["resolved_by_source_candidate_id"]
    if page_id and candidates_by_page.get(page_id):
        return dict(candidates_by_page[page_id][0]), ["resolved_by_page_fallback"]
    return None, ["candidate_not_resolved_to_local_artifact"]


def resolve_page_profile_hit(payload: Mapping[str, Any], indexes: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    profile_id = as_text(payload.get("profile_id"))
    page_id = as_text(payload.get("page_id"))
    profiles_by_profile = indexes.get("profiles_by_profile_id") or {}
    profiles_by_page = indexes.get("profiles_by_page_id") or {}
    if profile_id and profile_id in profiles_by_profile:
        return dict(profiles_by_profile[profile_id]), []
    if page_id and page_id in profiles_by_page:
        return dict(profiles_by_page[page_id]), ["resolved_by_page_id"]
    return None, ["page_profile_not_resolved_to_local_artifact"]


def compact_hit(hit: Mapping[str, Any], *, collection_role: str, collection: str, indexes: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(hit.get("payload") or {})
    bucket = payload_bucket(payload)
    resolution_record: dict[str, Any] | None
    resolution_reasons: list[str]
    if collection_role == "page_profile":
        resolution_record, resolution_reasons = resolve_page_profile_hit(payload, indexes)
        resolved = resolution_record is not None
        resolution_kind = "page_profile_artifact" if resolved else "unresolved_page_profile"
    else:
        resolution_record, resolution_reasons = resolve_candidate_hit(payload, indexes)
        resolved = resolution_record is not None
        resolution_kind = "embedding_candidate_artifact" if resolved else "unresolved_candidate"
    source = resolution_record or payload
    reasons = unsafe_payload_reasons(payload, collection_role=collection_role)
    if not resolved:
        reasons.extend(resolution_reasons)
    trace = source.get("traceability") if isinstance(source.get("traceability"), Mapping) else {}
    citation_id = as_text(source.get("citation_id") or payload.get("citation_id") or trace.get("citation_id"))
    source_url = as_text(source.get("source_url") or payload.get("source_url") or trace.get("source_url"))
    tiff_path = as_text(source.get("tiff_path") or payload.get("tiff_path") or trace.get("tiff_path"))
    ocr_path = as_text(source.get("ocr_path") or payload.get("ocr_path") or trace.get("ocr_path"))
    text_preview = compact_text(
        source.get("embedding_text") or source.get("text") or source.get("summary") or source.get("payload_preview") or "",
        max_chars=280,
    )
    return {
        "collection": collection,
        "collection_role": collection_role,
        "rank": int(hit.get("rank") or 0),
        "id": as_text(hit.get("id")),
        "score": float(hit.get("score") or 0.0),
        "page_id": as_text(payload.get("page_id") or source.get("page_id")),
        "page_number": payload.get("page_number") or source.get("page_number"),
        "document_id": as_text(payload.get("document_id") or source.get("document_id")),
        "ata_code": as_text(payload.get("ata_code") or source.get("ata_code")),
        "rag_bucket": bucket,
        "authority": as_text(payload.get("authority") or source.get("authority")),
        "trust_tier": as_text(payload.get("trust_tier") or payload.get("final_trust_tier") or source.get("trust_tier") or source.get("final_trust_tier")),
        "embedding_candidate_id": as_text(payload.get("embedding_candidate_id") or source.get("embedding_candidate_id")),
        "source_candidate_id": as_text(payload.get("source_candidate_id") or source.get("source_candidate_id")),
        "profile_id": as_text(payload.get("profile_id") or source.get("profile_id")),
        "citation_id": citation_id,
        "source_url": source_url,
        "tiff_path": tiff_path,
        "ocr_path": ocr_path,
        "context_v2_present": as_bool(payload.get("context_v2_present") or source.get("context_v2_present"), default=False),
        "source_trace_present": as_bool(payload.get("source_trace_present") or source.get("source_trace_present"), default=False),
        "can_answer_directly": as_bool(payload.get("can_answer_directly") or source.get("can_answer_directly"), default=False),
        "can_prove_claims": as_bool(payload.get("can_prove_claims") or source.get("can_prove_claims"), default=False),
        "can_prove_source_truth": as_bool(payload.get("can_prove_source_truth") or source.get("can_prove_source_truth"), default=False),
        "requires_source_resolution": as_bool(payload.get("requires_source_resolution") or source.get("requires_source_resolution"), default=False),
        "requires_citation": as_bool(payload.get("requires_citation") or source.get("requires_citation"), default=False),
        "requires_authority_gate": as_bool(payload.get("requires_authority_gate") or source.get("requires_authority_gate"), default=False),
        "embedding_answer_authority_allowed": as_bool(
            payload.get("embedding_answer_authority_allowed") or source.get("embedding_answer_authority_allowed"),
            default=False,
        ),
        "qdrant_is_source_truth": as_bool(payload.get("qdrant_is_source_truth"), default=False),
        "resolved_to_artifact": resolved,
        "resolution_kind": resolution_kind,
        "resolution_reasons": resolution_reasons,
        "unsafe_reasons": reasons,
        "is_safe_hit": len(reasons) == 0,
        "answer_support_candidate": bucket in ANSWER_SUPPORT_BUCKETS,
        "retrieval_only": bucket in RETRIEVAL_ONLY_BUCKETS,
        "text_preview": text_preview,
    }


def group_hits_for_query(
    query_result: Mapping[str, Any],
    *,
    candidate_weight: float = 1.0,
    page_weight: float = 0.75,
    same_page_boost: float = 0.25,
    citation_boost: float = 0.18,
    context_tunnel_boost: float = 0.08,
    max_groups: int = 8,
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    all_hits: list[dict[str, Any]] = []
    all_hits.extend([dict(hit) for hit in query_result.get("page_profile_hits") or [] if isinstance(hit, Mapping)])
    all_hits.extend([dict(hit) for hit in query_result.get("candidate_hits") or [] if isinstance(hit, Mapping)])
    for hit in all_hits:
        page_id = as_text(hit.get("page_id")) or "__missing_page_id__"
        group = groups.setdefault(
            page_id,
            {
                "page_id": page_id,
                "page_number": hit.get("page_number"),
                "document_id": as_text(hit.get("document_id")),
                "ata_code": as_text(hit.get("ata_code")),
                "page_profile_hits": [],
                "candidate_hits": [],
                "score_components": defaultdict(float),
                "unsafe_reasons": [],
                "citation_ids": set(),
                "source_urls": set(),
                "buckets": Counter(),
                "authorities": Counter(),
                "trust_tiers": Counter(),
            },
        )
        role = as_text(hit.get("collection_role"))
        score = float(hit.get("score") or 0.0)
        if role == "page_profile":
            group["page_profile_hits"].append(hit)
            group["score_components"]["page_profile_vector_score"] += score * page_weight
        else:
            group["candidate_hits"].append(hit)
            group["score_components"]["candidate_vector_score"] += score * candidate_weight
        if as_text(hit.get("citation_id")):
            group["citation_ids"].add(as_text(hit.get("citation_id")))
            group["score_components"]["citation_present_boost"] += citation_boost
        if as_text(hit.get("source_url")):
            group["source_urls"].add(as_text(hit.get("source_url")))
        if as_bool(hit.get("context_v2_present"), default=False) or as_text(hit.get("rag_bucket")) == CONTEXT_HELPER_BUCKET:
            group["score_components"]["context_tunnel_boost"] += context_tunnel_boost
        tier = as_text(hit.get("trust_tier")).upper()
        if tier:
            group["trust_tiers"][tier] += 1
            group["score_components"]["trust_tier_boost"] += TRUST_BOOSTS.get(tier, 0.0)
        bucket = as_text(hit.get("rag_bucket"))
        authority = as_text(hit.get("authority"))
        if bucket:
            group["buckets"][bucket] += 1
        if authority:
            group["authorities"][authority] += 1
        for reason in hit.get("unsafe_reasons") or []:
            group["unsafe_reasons"].append(as_text(reason))
    final_groups: list[dict[str, Any]] = []
    for page_id, group in groups.items():
        has_page_hit = bool(group["page_profile_hits"])
        has_candidate_hit = bool(group["candidate_hits"])
        if has_page_hit and has_candidate_hit:
            group["score_components"]["same_page_cross_collection_boost"] += same_page_boost
        answer_support_hits = [hit for hit in group["candidate_hits"] if hit.get("answer_support_candidate")]
        retrieval_only_hits = [hit for hit in group["page_profile_hits"] + group["candidate_hits"] if hit.get("retrieval_only")]
        unsafe_reasons = sorted(set(group["unsafe_reasons"]))
        score_components = {key: round(float(value), 6) for key, value in dict(group["score_components"]).items()}
        hybrid_score = round(sum(score_components.values()), 6)
        final_groups.append(
            {
                "query_id": as_text(query_result.get("query_id")),
                "query": as_text(query_result.get("query")),
                "page_id": page_id,
                "page_number": group.get("page_number"),
                "document_id": group.get("document_id"),
                "ata_code": group.get("ata_code"),
                "hybrid_score": hybrid_score,
                "score_components": score_components,
                "page_profile_hit_count": len(group["page_profile_hits"]),
                "candidate_hit_count": len(group["candidate_hits"]),
                "answer_support_candidate_count": len(answer_support_hits),
                "retrieval_only_hit_count": len(retrieval_only_hits),
                "citation_ids": sorted(group["citation_ids"]),
                "source_urls": sorted(group["source_urls"]),
                "bucket_counts": dict(sorted(group["buckets"].items())),
                "authority_counts": dict(sorted(group["authorities"].items())),
                "trust_tier_counts": dict(sorted(group["trust_tiers"].items())),
                "unsafe_reasons": unsafe_reasons,
                "safety_status": "retrieval_safe" if not unsafe_reasons else "unsafe",
                "answer_allowed": False,
                "answer_use_policy": "simulation_only_requires_postgres_source_citation_trust_gate",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
                "requires_source_resolution": True,
                "requires_citation": True,
                "requires_authority_gate": True,
                "hybrid_can_rank": True,
                "hybrid_can_answer": False,
                "page_profile_hits": sorted(group["page_profile_hits"], key=lambda item: int(item.get("rank") or 0))[:5],
                "candidate_hits": sorted(group["candidate_hits"], key=lambda item: int(item.get("rank") or 0))[:5],
            }
        )
    final_groups.sort(key=lambda item: float(item.get("hybrid_score") or 0.0), reverse=True)
    for index, group in enumerate(final_groups, start=1):
        group["rank"] = index
    return final_groups[:max_groups]


def summarize_hybrid_results(
    query_results: Sequence[Mapping[str, Any]],
    *,
    candidate_collection: str,
    page_profile_collection: str,
    candidate_collection_count: int,
    page_profile_collection_count: int,
    candidate_artifact_count: int,
    page_profile_artifact_count: int,
    embedding_mode: str,
    embedding_model_name: str,
    embedding_dim: int,
    vector_smoke_status: str = "",
) -> dict[str, Any]:
    all_groups: list[dict[str, Any]] = []
    all_page_hits: list[dict[str, Any]] = []
    all_candidate_hits: list[dict[str, Any]] = []
    for result in query_results:
        all_groups.extend([dict(group) for group in result.get("ranked_groups") or [] if isinstance(group, Mapping)])
        all_page_hits.extend([dict(hit) for hit in result.get("page_profile_hits") or [] if isinstance(hit, Mapping)])
        all_candidate_hits.extend([dict(hit) for hit in result.get("candidate_hits") or [] if isinstance(hit, Mapping)])
    all_hits = all_page_hits + all_candidate_hits
    unsafe_groups = [group for group in all_groups if group.get("unsafe_reasons")]
    unsafe_hits = [hit for hit in all_hits if hit.get("unsafe_reasons")]
    pages = {as_text(group.get("page_id")) for group in all_groups if as_text(group.get("page_id"))}
    bucket_counts = Counter(as_text(hit.get("rag_bucket")) for hit in all_hits)
    authority_counts = Counter(as_text(hit.get("authority")) for hit in all_hits)
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_collection": candidate_collection,
        "page_profile_collection": page_profile_collection,
        "embedding_mode": normalized_embedding_mode(embedding_mode),
        "embedding_model_name": embedding_model_name,
        "embedding_dim": int(embedding_dim),
        "vector_smoke_status": vector_smoke_status,
        "hybrid_query_count": len(query_results),
        "queries_with_results_count": sum(1 for item in query_results if int(item.get("ranked_group_count") or 0) > 0),
        "queries_with_candidate_hits_count": sum(1 for item in query_results if int(item.get("candidate_hit_count") or 0) > 0),
        "queries_with_page_profile_hits_count": sum(1 for item in query_results if int(item.get("page_profile_hit_count") or 0) > 0),
        "grouped_result_count": len(all_groups),
        "unique_group_page_count": len(pages),
        "candidate_hit_count": len(all_candidate_hits),
        "page_profile_hit_count": len(all_page_hits),
        "total_hit_count": len(all_hits),
        "resolved_candidate_hit_count": sum(1 for hit in all_candidate_hits if as_bool(hit.get("resolved_to_artifact"), default=False)),
        "resolved_page_profile_hit_count": sum(1 for hit in all_page_hits if as_bool(hit.get("resolved_to_artifact"), default=False)),
        "unresolved_candidate_hit_count": sum(1 for hit in all_candidate_hits if not as_bool(hit.get("resolved_to_artifact"), default=False)),
        "unresolved_page_profile_hit_count": sum(1 for hit in all_page_hits if not as_bool(hit.get("resolved_to_artifact"), default=False)),
        "missing_page_id_count": sum(1 for hit in all_hits if not as_text(hit.get("page_id"))),
        "unsafe_result_count": len(unsafe_groups),
        "unsafe_hit_payload_count": len(unsafe_hits),
        "direct_answer_allowed_result_count": sum(1 for group in all_groups if as_bool(group.get("answer_allowed"), default=False) or as_bool(group.get("can_answer_directly"), default=False)),
        "claim_proof_allowed_without_authority_count": sum(1 for group in all_groups if as_bool(group.get("can_prove_claims"), default=False)),
        "source_truth_mutation_allowed_count": sum(1 for group in all_groups if as_bool(group.get("can_mutate_source_truth"), default=False)),
        "answer_capable_page_profile_hit_count": sum(1 for hit in all_page_hits if as_bool(hit.get("can_answer_directly"), default=False)),
        "context_helper_answer_allowed_hit_count": sum(
            1 for hit in all_candidate_hits if as_text(hit.get("rag_bucket")) == CONTEXT_HELPER_BUCKET and as_bool(hit.get("can_answer_directly"), default=False)
        ),
        "source_evidence_answer_allowed_hit_count": sum(
            1 for hit in all_candidate_hits if as_text(hit.get("rag_bucket")) == SOURCE_EVIDENCE_BUCKET and as_bool(hit.get("can_answer_directly"), default=False)
        ),
        "requires_source_resolution_false_count": sum(1 for hit in all_hits if as_bool(hit.get("requires_source_resolution"), default=False) is not True),
        "requires_citation_false_count": sum(1 for hit in all_hits if as_bool(hit.get("requires_citation"), default=False) is not True),
        "requires_authority_gate_false_count": sum(1 for hit in all_hits if as_bool(hit.get("requires_authority_gate"), default=False) is not True),
        "candidate_collection_count": int(candidate_collection_count or 0),
        "page_profile_collection_count": int(page_profile_collection_count or 0),
        "candidate_artifact_count": int(candidate_artifact_count or 0),
        "page_profile_artifact_count": int(page_profile_artifact_count or 0),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "unsafe_reason_counts": dict(sorted(Counter(reason for hit in unsafe_hits for reason in hit.get("unsafe_reasons") or []).items())),
    }


def build_quality_report(
    summary: Mapping[str, Any],
    *,
    min_hybrid_queries: int = 1,
    min_queries_with_results: int = 1,
    min_grouped_results: int = 1,
    min_candidate_hits: int = 1,
    min_page_profile_hits: int = 1,
    min_resolved_candidate_hits: int = 1,
    min_resolved_page_profile_hits: int = 1,
    min_candidate_collection_count: int = 0,
    min_page_profile_collection_count: int = 0,
    require_candidate_count: int = 0,
    require_page_profile_count: int = 0,
    require_embedding_dim: int = 0,
    require_vector_smoke_quality_pass: bool = False,
) -> QualityResult:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any, expected: Any, severity: str = "error") -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected, "severity": severity})

    add("hybrid_query_count_min", int(summary.get("hybrid_query_count") or 0) >= min_hybrid_queries, summary.get("hybrid_query_count"), f">={min_hybrid_queries}")
    add("queries_with_results_min", int(summary.get("queries_with_results_count") or 0) >= min_queries_with_results, summary.get("queries_with_results_count"), f">={min_queries_with_results}")
    add("grouped_result_count_min", int(summary.get("grouped_result_count") or 0) >= min_grouped_results, summary.get("grouped_result_count"), f">={min_grouped_results}")
    add("candidate_hit_count_min", int(summary.get("candidate_hit_count") or 0) >= min_candidate_hits, summary.get("candidate_hit_count"), f">={min_candidate_hits}")
    add("page_profile_hit_count_min", int(summary.get("page_profile_hit_count") or 0) >= min_page_profile_hits, summary.get("page_profile_hit_count"), f">={min_page_profile_hits}")
    add("resolved_candidate_hit_count_min", int(summary.get("resolved_candidate_hit_count") or 0) >= min_resolved_candidate_hits, summary.get("resolved_candidate_hit_count"), f">={min_resolved_candidate_hits}")
    add("resolved_page_profile_hit_count_min", int(summary.get("resolved_page_profile_hit_count") or 0) >= min_resolved_page_profile_hits, summary.get("resolved_page_profile_hit_count"), f">={min_resolved_page_profile_hits}")
    add("missing_page_id_count_zero", int(summary.get("missing_page_id_count") or 0) == 0, summary.get("missing_page_id_count"), 0)
    add("unsafe_result_count_zero", int(summary.get("unsafe_result_count") or 0) == 0, summary.get("unsafe_result_count"), 0)
    add("unsafe_hit_payload_count_zero", int(summary.get("unsafe_hit_payload_count") or 0) == 0, summary.get("unsafe_hit_payload_count"), 0)
    add("direct_answer_allowed_result_count_zero", int(summary.get("direct_answer_allowed_result_count") or 0) == 0, summary.get("direct_answer_allowed_result_count"), 0)
    add("claim_proof_allowed_without_authority_count_zero", int(summary.get("claim_proof_allowed_without_authority_count") or 0) == 0, summary.get("claim_proof_allowed_without_authority_count"), 0)
    add("source_truth_mutation_allowed_count_zero", int(summary.get("source_truth_mutation_allowed_count") or 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("answer_capable_page_profile_hit_count_zero", int(summary.get("answer_capable_page_profile_hit_count") or 0) == 0, summary.get("answer_capable_page_profile_hit_count"), 0)
    add("context_helper_answer_allowed_hit_count_zero", int(summary.get("context_helper_answer_allowed_hit_count") or 0) == 0, summary.get("context_helper_answer_allowed_hit_count"), 0)
    add("source_evidence_answer_allowed_hit_count_zero", int(summary.get("source_evidence_answer_allowed_hit_count") or 0) == 0, summary.get("source_evidence_answer_allowed_hit_count"), 0)
    add("requires_source_resolution_false_count_zero", int(summary.get("requires_source_resolution_false_count") or 0) == 0, summary.get("requires_source_resolution_false_count"), 0)
    add("requires_citation_false_count_zero", int(summary.get("requires_citation_false_count") or 0) == 0, summary.get("requires_citation_false_count"), 0)
    add("requires_authority_gate_false_count_zero", int(summary.get("requires_authority_gate_false_count") or 0) == 0, summary.get("requires_authority_gate_false_count"), 0)
    add("candidate_collection_count_min", int(summary.get("candidate_collection_count") or 0) >= min_candidate_collection_count, summary.get("candidate_collection_count"), f">={min_candidate_collection_count}")
    add("page_profile_collection_count_min", int(summary.get("page_profile_collection_count") or 0) >= min_page_profile_collection_count, summary.get("page_profile_collection_count"), f">={min_page_profile_collection_count}")
    if require_candidate_count:
        add("candidate_collection_count_exact", int(summary.get("candidate_collection_count") or 0) == require_candidate_count, summary.get("candidate_collection_count"), require_candidate_count)
    if require_page_profile_count:
        add("page_profile_collection_count_exact", int(summary.get("page_profile_collection_count") or 0) == require_page_profile_count, summary.get("page_profile_collection_count"), require_page_profile_count)
    if require_embedding_dim:
        add("embedding_dim_exact", int(summary.get("embedding_dim") or 0) == require_embedding_dim, summary.get("embedding_dim"), require_embedding_dim)
    if require_vector_smoke_quality_pass:
        add("vector_smoke_status_pass", as_text(summary.get("vector_smoke_status")) == "PASS", summary.get("vector_smoke_status"), "PASS")
    status = "PASS" if all(check["passed"] or check.get("severity") == "warning" for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def read_vector_smoke_status(path: Path | None) -> str:
    if not path:
        return ""
    try:
        payload = read_json(Path(path))
    except Exception:
        return ""
    if isinstance(payload, Mapping):
        quality = payload.get("quality")
        if isinstance(quality, Mapping) and as_text(quality.get("status")):
            return as_text(quality.get("status"))
        return as_text(payload.get("quality_status") or payload.get("status"))
    return ""


def run_query_against_collections(
    *,
    client: Any,
    query: Mapping[str, Any],
    vector: Sequence[float],
    candidate_collection: str,
    page_profile_collection: str,
    indexes: Mapping[str, Any],
    top_k: int,
    score_threshold: float | None = None,
    max_groups: int = 8,
) -> dict[str, Any]:
    page_raw = client.search_points(page_profile_collection, vector, limit=top_k, score_threshold=score_threshold)
    candidate_raw = client.search_points(candidate_collection, vector, limit=top_k, score_threshold=score_threshold)
    page_hits = [compact_hit(hit, collection_role="page_profile", collection=page_profile_collection, indexes=indexes) for hit in page_raw]
    candidate_hits = [compact_hit(hit, collection_role="candidate", collection=candidate_collection, indexes=indexes) for hit in candidate_raw]
    base = {
        "schema_version": SCHEMA_VERSION,
        "query_id": as_text(query.get("query_id")),
        "query": as_text(query.get("query")),
        "intent": as_text(query.get("intent")),
        "query_vector_sha256": sha256_json([round(float(v), 8) for v in vector]),
        "page_profile_hits": page_hits,
        "candidate_hits": candidate_hits,
        "page_profile_hit_count": len(page_hits),
        "candidate_hit_count": len(candidate_hits),
    }
    groups = group_hits_for_query(base, max_groups=max_groups)
    base["ranked_groups"] = groups
    base["ranked_group_count"] = len(groups)
    base["all_groups_retrieval_safe"] = all(group.get("safety_status") == "retrieval_safe" for group in groups)
    return base


def run_hybrid_retrieval_sim(
    *,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    api_key: str | None = None,
    candidate_collection: str = DEFAULT_CANDIDATE_COLLECTION,
    page_profile_collection: str = DEFAULT_PAGE_PROFILE_COLLECTION,
    embedding_candidates_path: Path = DEFAULT_EMBEDDING_CANDIDATES,
    page_profiles_path: Path = DEFAULT_PAGE_PROFILES,
    vector_smoke_report_path: Path | None = DEFAULT_VECTOR_SMOKE_REPORT,
    queries_path: Path | None = None,
    inline_queries: Sequence[str] | None = None,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_device: str | None = None,
    query_batch_size: int = DEFAULT_QUERY_BATCH_SIZE,
    ollama_url: str | None = None,
    ollama_endpoint: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    max_groups: int = 8,
    score_threshold: float | None = None,
    timeout: float = 60.0,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    min_hybrid_queries: int = 1,
    min_queries_with_results: int = 1,
    min_grouped_results: int = 1,
    min_candidate_hits: int = 1,
    min_page_profile_hits: int = 1,
    min_resolved_candidate_hits: int = 1,
    min_resolved_page_profile_hits: int = 1,
    min_candidate_collection_count: int = 0,
    min_page_profile_collection_count: int = 0,
    require_candidate_count: int = 0,
    require_page_profile_count: int = 0,
    require_embedding_dim: int = 0,
    require_vector_smoke_quality_pass: bool = False,
    write_quality: bool = False,
    progress: bool = False,
    client: Any | None = None,
    query_vectors: Sequence[Sequence[float]] | None = None,
) -> dict[str, Any]:
    started = time.time()
    if ollama_url:
        os.environ["OLLAMA_URL"] = as_text(ollama_url)
    if ollama_endpoint:
        os.environ["OLLAMA_EMBED_ENDPOINT"] = as_text(ollama_endpoint)
    candidate_records, candidate_meta = load_records_artifact(embedding_candidates_path)
    page_profile_records, page_profile_meta = load_records_artifact(page_profiles_path)
    indexes = build_resolution_indexes(candidate_records, page_profile_records)
    queries = load_queries(queries_path, inline_queries)
    if query_vectors is None:
        vectors, embedding_model_name = embed_query_texts(
            [as_text(query.get("query")) for query in queries],
            embedding_mode=embedding_mode,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            embedding_device=embedding_device,
            batch_size=query_batch_size,
            ollama_url=ollama_url,
            ollama_endpoint=ollama_endpoint,
            ollama_timeout=timeout,
        )
    else:
        vectors = [[float(v) for v in row] for row in query_vectors]
        embedding_model_name = as_text(embedding_model)
        if len(vectors) != len(queries):
            raise HybridRetrievalSimError("query_vectors length must match query count")
    search_client = client or QdrantHybridClient(qdrant_url, api_key=api_key or "", timeout=timeout)
    candidate_collection_count = int(search_client.count_points(candidate_collection, exact=True))
    page_profile_collection_count = int(search_client.count_points(page_profile_collection, exact=True))
    query_results: list[dict[str, Any]] = []
    for index, (query, vector) in enumerate(zip(queries, vectors, strict=True), start=1):
        if progress:
            print(f"TRACE-Net hybrid retrieval progress: query {index}/{len(queries)} {query.get('query_id')}", flush=True)
        query_results.append(
            run_query_against_collections(
                client=search_client,
                query=query,
                vector=vector,
                candidate_collection=candidate_collection,
                page_profile_collection=page_profile_collection,
                indexes=indexes,
                top_k=top_k,
                score_threshold=score_threshold,
                max_groups=max_groups,
            )
        )
    vector_smoke_status = read_vector_smoke_status(vector_smoke_report_path)
    summary = summarize_hybrid_results(
        query_results,
        candidate_collection=candidate_collection,
        page_profile_collection=page_profile_collection,
        candidate_collection_count=candidate_collection_count,
        page_profile_collection_count=page_profile_collection_count,
        candidate_artifact_count=len(candidate_records),
        page_profile_artifact_count=len(page_profile_records),
        embedding_mode=embedding_mode,
        embedding_model_name=embedding_model_name,
        embedding_dim=embedding_dim,
        vector_smoke_status=vector_smoke_status,
    )
    quality = build_quality_report(
        summary,
        min_hybrid_queries=min_hybrid_queries,
        min_queries_with_results=min_queries_with_results,
        min_grouped_results=min_grouped_results,
        min_candidate_hits=min_candidate_hits,
        min_page_profile_hits=min_page_profile_hits,
        min_resolved_candidate_hits=min_resolved_candidate_hits,
        min_resolved_page_profile_hits=min_resolved_page_profile_hits,
        min_candidate_collection_count=min_candidate_collection_count,
        min_page_profile_collection_count=min_page_profile_collection_count,
        require_candidate_count=require_candidate_count,
        require_page_profile_count=require_page_profile_count,
        require_embedding_dim=require_embedding_dim,
        require_vector_smoke_quality_pass=require_vector_smoke_quality_pass,
    )
    output_dir = Path(output_dir)
    report_path = output_dir / DEFAULT_REPORT_FILE
    results_path = output_dir / DEFAULT_RESULTS_FILE
    groups_path = output_dir / DEFAULT_GROUPS_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    all_groups = [group for result in query_results for group in result.get("ranked_groups") or []]
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if quality.passed else "FAIL",
        "generated_at_utc": utc_now_iso(),
        "duration_seconds": round(time.time() - started, 3),
        "simulation_only": True,
        "ask_integration": False,
        "qdrant_url": qdrant_url,
        "candidate_collection": candidate_collection,
        "page_profile_collection": page_profile_collection,
        "embedding_mode": normalized_embedding_mode(embedding_mode),
        "embedding_model_name": embedding_model_name,
        "embedding_dim": embedding_dim,
        "top_k": top_k,
        "max_groups": max_groups,
        "summary": summary,
        "results": query_results,
        "quality": {"status": quality.status, "checks": quality.checks},
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": report["status"],
        "generated_at_utc": report["generated_at_utc"],
        "read_only": True,
        "simulation_only": True,
        "ask_integration": False,
        "candidate_collection": candidate_collection,
        "page_profile_collection": page_profile_collection,
        "embedding_mode": normalized_embedding_mode(embedding_mode),
        "embedding_model_name": embedding_model_name,
        "embedding_dim": embedding_dim,
        "candidate_collection_count": candidate_collection_count,
        "page_profile_collection_count": page_profile_collection_count,
        "candidate_artifact_count": len(candidate_records),
        "page_profile_artifact_count": len(page_profile_records),
        "report_file": DEFAULT_REPORT_FILE,
        "results_file": DEFAULT_RESULTS_FILE,
        "groups_file": DEFAULT_GROUPS_FILE,
        "summary_file": DEFAULT_SUMMARY_FILE,
        "quality_file": DEFAULT_QUALITY_FILE if write_quality else "",
    }
    write_json(report_path, report)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    write_jsonl(results_path, query_results)
    write_jsonl(groups_path, all_groups)
    if write_quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality.status, "summary": summary, "checks": quality.checks})
    if progress:
        print(
            f"TRACE-Net hybrid retrieval progress: complete status={quality.status} "
            f"groups={summary.get('grouped_result_count')} candidate_hits={summary.get('candidate_hit_count')} page_hits={summary.get('page_profile_hit_count')}",
            flush=True,
        )
    return {
        "status": "PASS" if quality.passed else "FAIL",
        "report_path": str(report_path),
        "results_path": str(results_path),
        "groups_path": str(groups_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path) if write_quality else "",
        "summary": summary,
        "quality": {"status": quality.status, "checks": quality.checks},
    }


def check_hybrid_retrieval_sim_quality(
    *,
    report_path: Path,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    api_key: str | None = None,
    candidate_collection: str = DEFAULT_CANDIDATE_COLLECTION,
    page_profile_collection: str = DEFAULT_PAGE_PROFILE_COLLECTION,
    min_hybrid_queries: int = 1,
    min_queries_with_results: int = 1,
    min_grouped_results: int = 1,
    min_candidate_hits: int = 1,
    min_page_profile_hits: int = 1,
    min_resolved_candidate_hits: int = 1,
    min_resolved_page_profile_hits: int = 1,
    min_candidate_collection_count: int = 0,
    min_page_profile_collection_count: int = 0,
    require_candidate_count: int = 0,
    require_page_profile_count: int = 0,
    require_embedding_dim: int = 0,
    require_vector_smoke_quality_pass: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    payload = read_json(report_path)
    if not isinstance(payload, Mapping):
        raise HybridRetrievalSimError(f"hybrid report is not a JSON object: {report_path}")
    summary = dict(payload.get("summary") or {})
    if qdrant_url:
        client = QdrantHybridClient(qdrant_url, api_key=api_key or "")
        try:
            summary["candidate_collection_count"] = int(client.count_points(candidate_collection, exact=True))
            summary["page_profile_collection_count"] = int(client.count_points(page_profile_collection, exact=True))
        except Exception as exc:
            summary["qdrant_count_error"] = str(exc)
    quality = build_quality_report(
        summary,
        min_hybrid_queries=min_hybrid_queries,
        min_queries_with_results=min_queries_with_results,
        min_grouped_results=min_grouped_results,
        min_candidate_hits=min_candidate_hits,
        min_page_profile_hits=min_page_profile_hits,
        min_resolved_candidate_hits=min_resolved_candidate_hits,
        min_resolved_page_profile_hits=min_resolved_page_profile_hits,
        min_candidate_collection_count=min_candidate_collection_count,
        min_page_profile_collection_count=min_page_profile_collection_count,
        require_candidate_count=require_candidate_count,
        require_page_profile_count=require_page_profile_count,
        require_embedding_dim=require_embedding_dim,
        require_vector_smoke_quality_pass=require_vector_smoke_quality_pass,
    )
    output = {"schema_version": SCHEMA_VERSION, "status": quality.status, "summary": summary, "checks": quality.checks}
    if write_json_report:
        quality_path = Path(report_path).parent / DEFAULT_QUALITY_FILE
        write_json(quality_path, output)
        output["quality_path"] = str(quality_path)
    return output


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TRACE-Net Hybrid Retrieval Simulation v1.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL") or DEFAULT_QDRANT_URL)
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY") or "")
    parser.add_argument("--candidate-collection", default=DEFAULT_CANDIDATE_COLLECTION)
    parser.add_argument("--page-profile-collection", default=DEFAULT_PAGE_PROFILE_COLLECTION)
    parser.add_argument("--embedding-candidates", type=Path, default=DEFAULT_EMBEDDING_CANDIDATES)
    parser.add_argument("--page-profiles", type=Path, default=DEFAULT_PAGE_PROFILES)
    parser.add_argument("--vector-smoke-report", type=Path, default=DEFAULT_VECTOR_SMOKE_REPORT)
    parser.add_argument("--require-vector-smoke-quality-pass", action="store_true")
    parser.add_argument("--queries-path", type=Path, default=None)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--embedding-mode", default=DEFAULT_EMBEDDING_MODE)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-dim", type=positive_int, default=DEFAULT_EMBEDDING_DIM)
    parser.add_argument("--embedding-device", default=None)
    parser.add_argument("--query-batch-size", type=positive_int, default=DEFAULT_QUERY_BATCH_SIZE)
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL") or "")
    parser.add_argument("--ollama-endpoint", default=os.environ.get("OLLAMA_EMBED_ENDPOINT") or "")
    parser.add_argument("--top-k", "--limit", dest="top_k", type=positive_int, default=DEFAULT_TOP_K)
    parser.add_argument("--max-groups", type=positive_int, default=8)
    parser.add_argument("--score-threshold", type=float, default=None)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--min-hybrid-queries", type=int, default=5)
    parser.add_argument("--min-queries-with-results", type=int, default=5)
    parser.add_argument("--min-grouped-results", type=int, default=5)
    parser.add_argument("--min-candidate-hits", type=int, default=25)
    parser.add_argument("--min-page-profile-hits", type=int, default=25)
    parser.add_argument("--min-resolved-candidate-hits", type=int, default=25)
    parser.add_argument("--min-resolved-page-profile-hits", type=int, default=25)
    parser.add_argument("--min-candidate-collection-count", type=int, default=1476)
    parser.add_argument("--min-page-profile-collection-count", type=int, default=509)
    parser.add_argument("--require-candidate-count", type=int, default=1476)
    parser.add_argument("--require-page-profile-count", type=int, default=509)
    parser.add_argument("--require-embedding-dim", type=int, default=1024)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_run_parser()
    args = parser.parse_args(argv)
    try:
        result = run_hybrid_retrieval_sim(
            qdrant_url=args.qdrant_url,
            api_key=args.api_key,
            candidate_collection=args.candidate_collection,
            page_profile_collection=args.page_profile_collection,
            embedding_candidates_path=args.embedding_candidates,
            page_profiles_path=args.page_profiles,
            vector_smoke_report_path=args.vector_smoke_report,
            queries_path=args.queries_path,
            inline_queries=args.query,
            embedding_mode=args.embedding_mode,
            embedding_model=args.embedding_model,
            embedding_dim=args.embedding_dim,
            embedding_device=args.embedding_device,
            query_batch_size=args.query_batch_size,
            ollama_url=args.ollama_url,
            ollama_endpoint=args.ollama_endpoint,
            top_k=args.top_k,
            max_groups=args.max_groups,
            score_threshold=args.score_threshold,
            timeout=args.timeout,
            output_dir=args.output_dir,
            min_hybrid_queries=args.min_hybrid_queries,
            min_queries_with_results=args.min_queries_with_results,
            min_grouped_results=args.min_grouped_results,
            min_candidate_hits=args.min_candidate_hits,
            min_page_profile_hits=args.min_page_profile_hits,
            min_resolved_candidate_hits=args.min_resolved_candidate_hits,
            min_resolved_page_profile_hits=args.min_resolved_page_profile_hits,
            min_candidate_collection_count=args.min_candidate_collection_count,
            min_page_profile_collection_count=args.min_page_profile_collection_count,
            require_candidate_count=args.require_candidate_count,
            require_page_profile_count=args.require_page_profile_count,
            require_embedding_dim=args.require_embedding_dim,
            require_vector_smoke_quality_pass=args.require_vector_smoke_quality_pass,
            write_quality=args.quality,
            progress=args.progress,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = result["summary"]
    print("TRACE-Net hybrid retrieval simulation v1")
    print(" Status: SIM_RAN")
    print(f" Quality status: {result['quality']['status']}")
    for key in [
        "embedding_mode",
        "embedding_model_name",
        "embedding_dim",
        "hybrid_query_count",
        "queries_with_results_count",
        "grouped_result_count",
        "candidate_hit_count",
        "page_profile_hit_count",
        "resolved_candidate_hit_count",
        "resolved_page_profile_hit_count",
        "candidate_collection_count",
        "page_profile_collection_count",
        "unsafe_result_count",
        "unsafe_hit_payload_count",
        "direct_answer_allowed_result_count",
        "claim_proof_allowed_without_authority_count",
        "source_truth_mutation_allowed_count",
    ]:
        if key in summary:
            print(f" {key}: {summary[key]}")
    print(f" report_path: {result['report_path']}")
    print(f" results_path: {result['results_path']}")
    print(f" groups_path: {result['groups_path']}")
    print(f" manifest_path: {result['manifest_path']}")
    if result.get("quality_path"):
        print(f" quality_path: {result['quality_path']}")
    return 0 if result["quality"]["status"] == "PASS" else 1


def build_quality_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Hybrid Retrieval Simulation v1 quality.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REPORT_FILE)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL") or DEFAULT_QDRANT_URL)
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY") or "")
    parser.add_argument("--candidate-collection", default=DEFAULT_CANDIDATE_COLLECTION)
    parser.add_argument("--page-profile-collection", default=DEFAULT_PAGE_PROFILE_COLLECTION)
    parser.add_argument("--min-hybrid-queries", type=int, default=5)
    parser.add_argument("--min-queries-with-results", type=int, default=5)
    parser.add_argument("--min-grouped-results", type=int, default=5)
    parser.add_argument("--min-candidate-hits", type=int, default=25)
    parser.add_argument("--min-page-profile-hits", type=int, default=25)
    parser.add_argument("--min-resolved-candidate-hits", type=int, default=25)
    parser.add_argument("--min-resolved-page-profile-hits", type=int, default=25)
    parser.add_argument("--min-candidate-collection-count", type=int, default=1476)
    parser.add_argument("--min-page-profile-collection-count", type=int, default=509)
    parser.add_argument("--require-candidate-count", type=int, default=1476)
    parser.add_argument("--require-page-profile-count", type=int, default=509)
    parser.add_argument("--require-embedding-dim", type=int, default=1024)
    parser.add_argument("--require-vector-smoke-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = build_quality_parser()
    args = parser.parse_args(argv)
    try:
        result = check_hybrid_retrieval_sim_quality(
            report_path=args.report_path,
            qdrant_url=args.qdrant_url,
            api_key=args.api_key,
            candidate_collection=args.candidate_collection,
            page_profile_collection=args.page_profile_collection,
            min_hybrid_queries=args.min_hybrid_queries,
            min_queries_with_results=args.min_queries_with_results,
            min_grouped_results=args.min_grouped_results,
            min_candidate_hits=args.min_candidate_hits,
            min_page_profile_hits=args.min_page_profile_hits,
            min_resolved_candidate_hits=args.min_resolved_candidate_hits,
            min_resolved_page_profile_hits=args.min_resolved_page_profile_hits,
            min_candidate_collection_count=args.min_candidate_collection_count,
            min_page_profile_collection_count=args.min_page_profile_collection_count,
            require_candidate_count=args.require_candidate_count,
            require_page_profile_count=args.require_page_profile_count,
            require_embedding_dim=args.require_embedding_dim,
            require_vector_smoke_quality_pass=args.require_vector_smoke_quality_pass,
            write_json_report=args.write_json,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("TRACE-Net hybrid retrieval simulation v1 quality")
    print(f" Status: {result['status']}")
    summary = result["summary"]
    for key in [
        "hybrid_query_count",
        "queries_with_results_count",
        "grouped_result_count",
        "candidate_hit_count",
        "page_profile_hit_count",
        "resolved_candidate_hit_count",
        "resolved_page_profile_hit_count",
        "candidate_collection_count",
        "page_profile_collection_count",
        "unsafe_result_count",
        "unsafe_hit_payload_count",
        "direct_answer_allowed_result_count",
        "claim_proof_allowed_without_authority_count",
        "source_truth_mutation_allowed_count",
    ]:
        if key in summary:
            print(f" {key}: {summary[key]}")
    if result.get("quality_path"):
        print(f" quality_path: {result['quality_path']}")
    failed = [check for check in result.get("checks", []) if not check.get("passed")]
    for check in failed[:10]:
        print(f" FAIL {check['name']}: {check['actual']} expected {check['expected']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
