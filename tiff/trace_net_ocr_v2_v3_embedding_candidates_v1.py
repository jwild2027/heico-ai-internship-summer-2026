#!/usr/bin/env python3
"""
TRACE-Net OCR + V2 + V3 Embedding Candidates v1.

Builds one safe candidate bundle for Qdrant loading from:
- Fishnet OCR page cards.
- Repaired/accepted V2 page_context_v2 records.
- V3 page intelligence cards.

This builder does not embed and does not write to Qdrant/Postgres/OpenSearch.
It creates loader-compatible candidate records that remain retrieval guidance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_ocr_v2_v3_embedding_candidates_v1"

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/ocr_v2_v3_embedding_candidates")
DEFAULT_MANIFEST = "trace_net_ocr_v2_v3_embedding_candidates_v1.json"
DEFAULT_JSONL = "trace_net_ocr_v2_v3_embedding_candidates_v1.jsonl"
DEFAULT_SUMMARY = "trace_net_ocr_v2_v3_embedding_candidates_v1_summary.json"
DEFAULT_QUALITY = "trace_net_ocr_v2_v3_embedding_candidates_v1_quality.json"
DEFAULT_REJECTED = "trace_net_ocr_v2_v3_embedding_candidates_v1_rejected.jsonl"
# Compatibility aliases for the existing trace_net_qdrant_loader_v1 quality detector.
# The loader looks for the older embedding-candidates quality/manifest names next
# to the candidates file, even when the candidates file itself is explicitly passed.
LEGACY_EMBEDDING_QUALITY = "trace_net_embedding_candidates_v1_quality.json"
LEGACY_EMBEDDING_MANIFEST = "trace_net_embedding_candidates_v1_manifest.json"

SAFETY_CONTRACT = {
    "embedding_candidates_are_source_truth": False,
    "embedding_candidates_can_answer_directly": False,
    "embedding_candidates_can_prove_claims": False,
    "requires_source_check": True,
    "requires_citation": True,
    "safe_vector_allowed_use": ["retrieve", "rank", "route", "candidate_discovery"],
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
}

SAFE_VECTOR_ALLOWED_USE = ["retrieve", "rank", "route", "candidate_discovery"]


def norm_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("records", "cards", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(*parts: Any, length: int = 24) -> str:
    raw = "|".join(norm_text(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def stable_uuid(*parts: Any) -> str:
    raw = "trace-net/embedding/" + "|".join(norm_text(p) for p in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def page_id_from_number(page_number: int, *, prefix: str = "t_p_120_1176") -> str:
    return f"{prefix}_p{int(page_number):06d}"


def page_number_from_page_id(page_id: str) -> int | None:
    m = re.search(r"_p(\d{6})$", norm_text(page_id))
    return int(m.group(1)) if m else None


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", norm_text(text))
    return text[:limit]


def canonical_page_id(record: Mapping[str, Any], *, canonical_prefix: str = "t_p_120_1176") -> str:
    pid = norm_text(
        record.get("page_id")
        or record.get("canonical_page_id")
        or record.get("source_page_id")
        or (record.get("original_gemma_record") or {}).get("page_id")
    )
    if pid.startswith(canonical_prefix + "_p"):
        return pid
    page_number = record.get("page_number")
    if page_number not in (None, ""):
        return page_id_from_number(int(page_number), prefix=canonical_prefix)
    n = page_number_from_page_id(pid)
    if n is not None:
        return page_id_from_number(n, prefix=canonical_prefix)
    return pid


def fishnet_ocr_text(record: Mapping[str, Any], max_chars: int) -> str:
    features = record.get("page_ocr_features") or {}
    text = first_present(
        record.get("page_ocr_text"),
        record.get("ocr_text"),
        record.get("text"),
        features.get("page_ocr_text"),
        features.get("ocr_text"),
        features.get("sample_text"),
    )
    text = norm_text(text)
    if not text:
        text = (
            f"OCR status {record.get('page_ocr_status') or record.get('ocr_engine_status') or 'unknown'} "
            f"for page {record.get('page_number')}; no non-empty OCR text sample available."
        )
    return shorten(text, max_chars)


def v2_text(record: Mapping[str, Any], max_chars: int) -> str:
    original = record.get("original_gemma_record") or {}
    parts = [
        f"TRACE-Net V2 page context for {canonical_page_id(record)}.",
        f"Role: {first_present(record.get('role'), original.get('role'), 'unknown')}.",
        f"Subrole: {first_present(record.get('subrole'), original.get('subrole'), 'unknown')}.",
        norm_text(first_present(record.get("retrieval_summary"), original.get("retrieval_summary"))),
        norm_text(first_present(record.get("short_summary"), original.get("short_summary"))),
    ]
    entities = safe_list(first_present(record.get("important_entities"), original.get("important_entities")))
    parts_list = safe_list(first_present(record.get("important_parts"), original.get("important_parts")))
    questions = safe_list(first_present(record.get("answerable_questions"), original.get("answerable_questions")))
    cues = safe_list(first_present(record.get("retrieval_cues"), original.get("retrieval_cues")))
    if entities:
        parts.append("Important entities: " + ", ".join(map(str, entities[:20])))
    if parts_list:
        parts.append("Important parts: " + ", ".join(map(str, parts_list[:30])))
    if cues:
        parts.append("Retrieval cues: " + ", ".join(map(str, cues[:20])))
    if questions:
        parts.append("Question cues: " + " | ".join(map(str, questions[:10])))
    return shorten("\n".join(p for p in parts if norm_text(p)), max_chars)


def v3_text(record: Mapping[str, Any], max_chars: int) -> str:
    retrieval_profile = record.get("retrieval_profile") or {}
    text = norm_text(retrieval_profile.get("text"))
    if not text:
        route = record.get("route") or {}
        ocr = record.get("ocr") or {}
        text = "\n".join([
            f"TRACE-Net V3 page intelligence for {record.get('page_id')}.",
            f"Route: {route.get('recommended_route_candidate') or 'unknown'}.",
            f"V2 context status: {record.get('v2_context_status') or 'unknown'}.",
            f"OCR status: {ocr.get('status') or 'unknown'}; OCR chars: {ocr.get('char_count')}.",
            norm_text(record.get("v2_retrieval_summary")),
            norm_text(record.get("v2_short_summary")),
            "OCR sample: " + norm_text(ocr.get("sample_text")),
        ])
    return shorten(text, max_chars)


def base_candidate(
    *,
    source_kind: str,
    source_candidate_id: str,
    page_id: str,
    page_number: int | None,
    candidate_type: str,
    rag_bucket: str,
    embedding_text: str,
    source_path: str = "",
    source_record_id: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    content_sha = sha256_text(embedding_text)
    embedding_candidate_id = "embcand:" + stable_id(source_kind, source_candidate_id, rag_bucket, content_sha, length=28)
    traceability = {
        "page_id": page_id,
        "page_number": page_number,
        "source_kind": source_kind,
        "source_table": source_kind,
        "source_candidate_id": source_candidate_id,
        "source_record_id": source_record_id or source_candidate_id,
        "source_path": source_path,
        "source_artifact_role": "rebuildable_retrieval_index_candidate",
        "source_resolution_required": True,
        "source_resolution_hint": "Resolve this vector hit through TRACE-Net page/source artifacts before answer use.",
        "proof_boundary": "Vector payload is retrieval guidance only and cannot prove claims.",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "embedding_candidate_id": embedding_candidate_id,
        "candidate_id": embedding_candidate_id,
        "qdrant_point_id": stable_uuid(embedding_candidate_id),
        "record_type": "embedding_candidate",
        "source_kind": source_kind,
        "source_table": source_kind,
        "source_candidate_id": source_candidate_id,
        "source_record_id": source_record_id or source_candidate_id,
        "page_id": page_id,
        "page_number": page_number,
        "source_path": source_path,
        "rag_bucket": rag_bucket,
        "embedding_bucket": rag_bucket,
        "candidate_type": candidate_type,
        "evidence_layer": candidate_type,
        "embedding_text": embedding_text,
        "chunk_text": embedding_text,
        "text": embedding_text,
        "text_preview": shorten(embedding_text, 700),
        "content_sha256": content_sha,
        "safe_vector_allowed_use": SAFE_VECTOR_ALLOWED_USE,
        "allowed_use": SAFE_VECTOR_ALLOWED_USE,
        "authority": "retrieval_helper",
        "trust_tier": "retrieval_guidance",
        "final_trust_tier": "retrieval_guidance",
        "requires_source_resolution": True,
        "requires_authority_gate": True,
        "must_resolve_through_postgres": True,
        "must_pass_authority_gate": True,
        "must_use_source_citation": True,
        "requires_source_check": True,
        "requires_citation": True,
        "citation_ready": False,
        "source_trace_ready": True,
        "traceability": traceability,
        "guidance_only": True,
        "canonical_source_truth": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "qdrant_is_source_truth": False,
        "qdrant_can_answer_directly": False,
        "qdrant_can_prove_claims": False,
        "embedding_answer_authority_allowed": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "answer_permission_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "safety_reasons": [],
        "metadata": dict(metadata or {}),
    }

def build_ocr_candidate(record: Mapping[str, Any], *, canonical_prefix: str, max_text_chars: int) -> dict[str, Any]:
    page_id = canonical_page_id(record, canonical_prefix=canonical_prefix)
    page_number = record.get("page_number")
    if not page_id and page_number not in (None, ""):
        page_id = page_id_from_number(int(page_number), prefix=canonical_prefix)
    text = "\n".join([
        f"TRACE-Net OCR page text for {page_id}.",
        f"OCR status: {record.get('page_ocr_status') or record.get('ocr_engine_status') or 'unknown'}.",
        f"Recommended route: {record.get('recommended_route_candidate') or 'unknown'}.",
        fishnet_ocr_text(record, max_text_chars),
    ])
    return base_candidate(
        source_kind="ocr_page_text",
        source_candidate_id=f"ocr:{page_id}",
        page_id=page_id,
        page_number=int(page_number) if page_number not in (None, "") else page_number_from_page_id(page_id),
        candidate_type="ocr_page_text",
        rag_bucket="context_helper",
        embedding_text=shorten(text, max_text_chars),
        source_path=norm_text(record.get("source_path")),
        source_record_id=norm_text(record.get("page_id")),
        metadata={
            "ocr_status": record.get("page_ocr_status") or record.get("ocr_engine_status"),
            "ocr_char_count": (record.get("page_ocr_features") or {}).get("ocr_char_count"),
            "ocr_word_count": (record.get("page_ocr_features") or {}).get("ocr_word_count"),
            "recommended_route_candidate": record.get("recommended_route_candidate"),
        },
    )


def build_v2_candidate(record: Mapping[str, Any], *, canonical_prefix: str, max_text_chars: int) -> dict[str, Any]:
    page_id = canonical_page_id(record, canonical_prefix=canonical_prefix)
    return base_candidate(
        source_kind="page_context_v2",
        source_candidate_id=norm_text(record.get("context_id") or record.get("id") or f"page_context_v2:{page_id}"),
        page_id=page_id,
        page_number=page_number_from_page_id(page_id),
        candidate_type="page_context_v2",
        rag_bucket="context_helper",
        embedding_text=v2_text(record, max_text_chars),
        source_path="",
        source_record_id=norm_text(record.get("id") or record.get("context_id")),
        metadata={
            "context_version": "v2",
            "generation_model": record.get("generation_model"),
            "role": first_present(record.get("role"), (record.get("original_gemma_record") or {}).get("role")),
            "subrole": first_present(record.get("subrole"), (record.get("original_gemma_record") or {}).get("subrole")),
            "confidence": first_present(record.get("confidence"), (record.get("original_gemma_record") or {}).get("confidence")),
        },
    )


def build_v3_candidate(record: Mapping[str, Any], *, canonical_prefix: str, max_text_chars: int) -> dict[str, Any]:
    page_id = canonical_page_id(record, canonical_prefix=canonical_prefix)
    route = record.get("route") or {}
    return base_candidate(
        source_kind="v3_page_intelligence",
        source_candidate_id=norm_text(record.get("v3_id") or record.get("id") or f"v3_page_intelligence::{page_id}"),
        page_id=page_id,
        page_number=int(record.get("page_number")) if record.get("page_number") not in (None, "") else page_number_from_page_id(page_id),
        candidate_type="v3_page_intelligence",
        rag_bucket="context_helper",
        embedding_text=v3_text(record, max_text_chars),
        source_path=norm_text(record.get("source_path")),
        source_record_id=norm_text(record.get("id") or record.get("v3_id")),
        metadata={
            "context_version": "v3",
            "v2_context_status": record.get("v2_context_status"),
            "v2_context_available": record.get("v2_context_available"),
            "recommended_route_candidate": route.get("recommended_route_candidate"),
            "review_required": route.get("review_required"),
        },
    )


def reject(reason: str, source_kind: str, record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "rejected_embedding_candidate_source",
        "source_kind": source_kind,
        "reason": reason,
        "page_id": record.get("page_id"),
        "page_number": record.get("page_number"),
        "source_record_id": record.get("id") or record.get("context_id") or record.get("v3_id"),
    }


def validate_candidate(candidate: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in ("embedding_candidate_id", "qdrant_point_id", "source_candidate_id", "page_id", "embedding_text"):
        if not norm_text(candidate.get(key)):
            reasons.append(f"missing_{key}")
    if candidate.get("canonical_source_truth") is True:
        reasons.append("candidate_marked_source_truth")
    if candidate.get("can_answer_directly") is True:
        reasons.append("candidate_can_answer_directly")
    if candidate.get("can_prove_claims") is True:
        reasons.append("candidate_can_prove_claims")
    if candidate.get("source_truth_mutation_allowed") is True:
        reasons.append("candidate_allows_source_truth_mutation")
    if not candidate.get("traceability"):
        reasons.append("missing_traceability")
    if candidate.get("requires_source_resolution") is not True:
        reasons.append("requires_source_resolution_not_true")
    if candidate.get("must_pass_authority_gate") is not True:
        reasons.append("must_pass_authority_gate_not_true")
    if candidate.get("must_use_source_citation") is not True:
        reasons.append("must_use_source_citation_not_true")
    return reasons


def build_candidate_bundle(
    *,
    fishnet_report: Path,
    page_context_v2: Path,
    v3_cards: Path,
    output_dir: Path | None = None,
    canonical_prefix: str = "t_p_120_1176",
    max_text_chars: int = 4096,
    min_records: int = 1524,
    expected_records: int | None = 1524,
    min_pages_with_candidates: int = 509,
) -> dict[str, Any]:
    fishnet_records = as_records(read_json(fishnet_report))
    v2_records = as_records(read_json(page_context_v2))
    v3_records = as_records(read_json(v3_cards))
    if not fishnet_records:
        raise ValueError(f"No fishnet records found in {fishnet_report}")
    if not v2_records:
        raise ValueError(f"No V2 records found in {page_context_v2}")
    if not v3_records:
        raise ValueError(f"No V3 records found in {v3_cards}")

    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    builders: list[tuple[str, Iterable[Mapping[str, Any]], Any]] = [
        ("ocr_page_text", fishnet_records, build_ocr_candidate),
        ("page_context_v2", v2_records, build_v2_candidate),
        ("v3_page_intelligence", v3_records, build_v3_candidate),
    ]

    seen_ids: set[str] = set()
    for source_kind, records, builder in builders:
        for source in records:
            try:
                cand = builder(source, canonical_prefix=canonical_prefix, max_text_chars=max_text_chars)
                reasons = validate_candidate(cand)
                if cand["embedding_candidate_id"] in seen_ids:
                    reasons.append("duplicate_embedding_candidate_id")
                if reasons:
                    rej = reject(";".join(reasons), source_kind, source)
                    rej["candidate_preview"] = cand
                    rejected.append(rej)
                    continue
                seen_ids.add(cand["embedding_candidate_id"])
                candidates.append(cand)
            except Exception as exc:
                rej = reject(f"{type(exc).__name__}:{str(exc)[:500]}", source_kind, source)
                rejected.append(rej)

    candidates.sort(key=lambda r: (r.get("page_number") or 10**9, str(r.get("source_kind")), str(r.get("embedding_candidate_id"))))
    rejected.sort(key=lambda r: (r.get("page_number") or 10**9, str(r.get("source_kind"))))

    summary = summarize_candidates(candidates, rejected)
    summary.update({
        "fishnet_report": str(fishnet_report),
        "page_context_v2": str(page_context_v2),
        "v3_cards": str(v3_cards),
        "max_text_chars": max_text_chars,
    })
    quality_status, failure_reasons = evaluate_quality(
        summary,
        min_records=min_records,
        expected_records=expected_records,
        min_pages_with_candidates=min_pages_with_candidates,
        max_unsafe=0,
    )

    return {
        "module": SCHEMA_VERSION,
        "version": "v1",
        "status": "OCR_V2_V3_EMBEDDING_CANDIDATES_BUILT",
        "quality_status": quality_status,
        "failure_reasons": failure_reasons,
        "summary": summary,
        "safety_contract": SAFETY_CONTRACT,
        "records": candidates,
        "rejected": rejected,
    }


def summarize_candidates(records: list[Mapping[str, Any]], rejected: list[Mapping[str, Any]]) -> dict[str, Any]:
    source_kind_counts = Counter(r.get("source_kind") for r in records)
    bucket_counts = Counter(r.get("rag_bucket") for r in records)
    page_ids = {r.get("page_id") for r in records if r.get("page_id")}
    ids = [r.get("embedding_candidate_id") for r in records if r.get("embedding_candidate_id")]
    duplicate_ids = sorted({x for x in ids if ids.count(x) > 1})
    return {
        "schema_version": SCHEMA_VERSION,
        "embedding_candidate_count": len(records),
        "safe_embedding_candidate_count": len(records),
        "rejected_embedding_candidate_count": len(rejected),
        "page_count": len(page_ids),
        "source_kind_counts": dict(sorted(source_kind_counts.items(), key=lambda kv: str(kv[0]))),
        "bucket_counts": dict(sorted(bucket_counts.items(), key=lambda kv: str(kv[0]))),
        "ocr_page_text_candidate_count": source_kind_counts.get("ocr_page_text", 0),
        "page_context_v2_candidate_count": source_kind_counts.get("page_context_v2", 0),
        "v3_page_intelligence_candidate_count": source_kind_counts.get("v3_page_intelligence", 0),
        "context_helper_embedding_count": source_kind_counts.get("page_context_v2", 0) + source_kind_counts.get("v3_page_intelligence", 0),
        "missing_page_id_count": sum(1 for r in records if not r.get("page_id")),
        "missing_source_candidate_id_count": sum(1 for r in records if not r.get("source_candidate_id")),
        "missing_embedding_text_count": sum(1 for r in records if not norm_text(r.get("embedding_text"))),
        "duplicate_embedding_candidate_id_count": len(duplicate_ids),
        "duplicate_embedding_candidate_ids": duplicate_ids[:20],
        "guidance_only_count": sum(1 for r in records if r.get("guidance_only") is True),
        "canonical_source_truth_count": sum(1 for r in records if r.get("canonical_source_truth") is True),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission") is True),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly") is True),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims") is True),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed") is True),
        "postgres_write_attempt_count": sum(int(r.get("postgres_write_attempt_count") or 0) for r in records),
        "qdrant_write_attempt_count": sum(int(r.get("qdrant_write_attempt_count") or 0) for r in records),
        "opensearch_write_attempt_count": sum(int(r.get("opensearch_write_attempt_count") or 0) for r in records),
        "missing_traceability_count": sum(1 for r in records if not r.get("traceability")),
        "requires_source_resolution_false_count": sum(1 for r in records if r.get("requires_source_resolution") is not True),
        "must_pass_authority_gate_false_count": sum(1 for r in records if r.get("must_pass_authority_gate") is not True),
        "must_use_source_citation_false_count": sum(1 for r in records if r.get("must_use_source_citation") is not True),
        "unsafe_embedding_candidate_count": sum(
            1
            for r in records
            if r.get("canonical_source_truth")
            or r.get("can_answer_directly")
            or r.get("can_prove_claims")
            or r.get("source_truth_mutation_allowed")
            or r.get("embedding_answer_authority_allowed")
        ),
    }


def evaluate_quality(
    summary: Mapping[str, Any],
    *,
    min_records: int,
    expected_records: int | None,
    min_pages_with_candidates: int,
    max_unsafe: int,
) -> tuple[str, list[str]]:
    failures: list[str] = []
    if int(summary.get("safe_embedding_candidate_count") or 0) < min_records:
        failures.append(f"safe_embedding_candidate_count_below_min:{summary.get('safe_embedding_candidate_count')}<{min_records}")
    if expected_records is not None and int(summary.get("safe_embedding_candidate_count") or 0) != expected_records:
        failures.append(f"safe_embedding_candidate_count_not_expected:{summary.get('safe_embedding_candidate_count')}!={expected_records}")
    if int(summary.get("page_count") or 0) < min_pages_with_candidates:
        failures.append(f"page_count_below_min:{summary.get('page_count')}<{min_pages_with_candidates}")
    for key in (
        "missing_page_id_count",
        "missing_source_candidate_id_count",
        "missing_embedding_text_count",
        "duplicate_embedding_candidate_id_count",
        "missing_traceability_count",
        "requires_source_resolution_false_count",
        "must_pass_authority_gate_false_count",
        "must_use_source_citation_false_count",
    ):
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key}_nonzero")
    if int(summary.get("unsafe_embedding_candidate_count") or 0) > max_unsafe:
        failures.append(f"unsafe_embedding_candidate_count_too_high:{summary.get('unsafe_embedding_candidate_count')}>{max_unsafe}")
    for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count", "source_truth_mutation_allowed_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key}_nonzero")
    return ("PASS" if not failures else "FAIL"), failures


def write_bundle(bundle: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / DEFAULT_MANIFEST
    jsonl = output_dir / DEFAULT_JSONL
    summary = output_dir / DEFAULT_SUMMARY
    quality = output_dir / DEFAULT_QUALITY
    rejected_path = output_dir / DEFAULT_REJECTED

    write_json(manifest, dict(bundle))
    with jsonl.open("w", encoding="utf-8") as f:
        for rec in bundle.get("records", []):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    write_json(summary, bundle.get("summary", {}))
    quality_payload = {
        "status": bundle.get("quality_status"),
        "quality_status": bundle.get("quality_status"),
        "failure_reasons": bundle.get("failure_reasons", []),
        "summary": bundle.get("summary", {}),
        "safety_contract": bundle.get("safety_contract", {}),
    }
    write_json(quality, quality_payload)

    # Legacy aliases for trace_net_qdrant_loader_v1 --require-candidate-quality-pass.
    legacy_quality = output_dir / LEGACY_EMBEDDING_QUALITY
    legacy_manifest = output_dir / LEGACY_EMBEDDING_MANIFEST
    write_json(legacy_quality, quality_payload)
    write_json(legacy_manifest, {
        "schema_version": "trace_net_embedding_candidates_v1",
        "compatibility_source_schema_version": SCHEMA_VERSION,
        "quality_status": bundle.get("quality_status"),
        "status": bundle.get("quality_status"),
        "candidate_record_count": len(bundle.get("records", [])),
        "candidates_path": str(manifest),
        "summary": bundle.get("summary", {}),
    })

    with rejected_path.open("w", encoding="utf-8") as f:
        for rec in bundle.get("rejected", []):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {
        "manifest": manifest,
        "jsonl": jsonl,
        "summary": summary,
        "quality": quality,
        "legacy_quality": legacy_quality,
        "legacy_manifest": legacy_manifest,
        "rejected": rejected_path,
    }


def check_candidate_manifest(
    manifest: Path,
    *,
    min_records: int,
    expected_records: int | None,
    min_pages_with_candidates: int,
    require_quality_pass: bool,
    max_unsafe: int,
) -> dict[str, Any]:
    bundle = read_json(manifest)
    records = as_records(bundle)
    rejected = bundle.get("rejected", []) if isinstance(bundle, dict) else []
    summary = summarize_candidates(records, rejected)
    if isinstance(bundle, dict):
        summary["source_quality_status"] = bundle.get("quality_status")
        summary["source_failure_reasons"] = bundle.get("failure_reasons", [])
    status, failures = evaluate_quality(
        summary,
        min_records=min_records,
        expected_records=expected_records,
        min_pages_with_candidates=min_pages_with_candidates,
        max_unsafe=max_unsafe,
    )
    if require_quality_pass and isinstance(bundle, dict) and bundle.get("quality_status") != "PASS":
        status = "FAIL"
        failures.append("source_manifest_quality_status_not_pass")
    return {
        "quality_status": "PASS" if status == "PASS" and not failures else "FAIL",
        "failure_reasons": failures,
        "summary": summary,
    }


def build_cli_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build safe TRACE-Net OCR + V2 + V3 embedding candidates v1.")
    p.add_argument("--fishnet-report", type=Path, required=True)
    p.add_argument("--page-context-v2", type=Path, required=True)
    p.add_argument("--v3-cards", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--canonical-prefix", default="t_p_120_1176")
    p.add_argument("--max-text-chars", type=int, default=4096)
    p.add_argument("--min-records", type=int, default=1524)
    p.add_argument("--expected-records", type=int, default=1524)
    p.add_argument("--min-pages-with-candidates", type=int, default=509)
    p.add_argument("--require-quality-pass", action="store_true")
    args = p.parse_args(argv)

    bundle = build_candidate_bundle(
        fishnet_report=args.fishnet_report,
        page_context_v2=args.page_context_v2,
        v3_cards=args.v3_cards,
        output_dir=args.output_dir,
        canonical_prefix=args.canonical_prefix,
        max_text_chars=args.max_text_chars,
        min_records=args.min_records,
        expected_records=args.expected_records,
        min_pages_with_candidates=args.min_pages_with_candidates,
    )
    paths = write_bundle(bundle, args.output_dir)

    print(f"Status: {bundle['status']}")
    print(f"Quality status: {bundle['quality_status']}")
    print("Summary:", json.dumps(bundle["summary"], ensure_ascii=False, sort_keys=True))
    for path in paths.values():
        print("Wrote:", path)
    if args.require_quality_pass and bundle["quality_status"] != "PASS":
        return 2
    return 0 if bundle["quality_status"] == "PASS" else 2


def check_cli_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Check safe TRACE-Net OCR + V2 + V3 embedding candidates v1 quality.")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--write-json", action="store_true")
    p.add_argument("--min-records", type=int, default=1524)
    p.add_argument("--expected-records", type=int, default=1524)
    p.add_argument("--min-pages-with-candidates", type=int, default=509)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    args = p.parse_args(argv)

    result = check_candidate_manifest(
        args.manifest,
        min_records=args.min_records,
        expected_records=args.expected_records,
        min_pages_with_candidates=args.min_pages_with_candidates,
        require_quality_pass=args.require_quality_pass,
        max_unsafe=args.max_unsafe,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    if result["failure_reasons"]:
        print("Failure reasons:", result["failure_reasons"])
    if args.write_json or args.output:
        out = args.output or args.manifest.parent / DEFAULT_QUALITY
        write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(build_cli_main())
