"""TRACE-Net Embedding Candidates v1.

Step 4 prepares safe, source-traceable records that can later be embedded and
loaded into Qdrant. This module does not call an embedding model, does not call
Qdrant, and does not let vector candidates become source truth.

Inputs:
- Postgres rag_candidate_chunks, source_citations, trust_authority_records.
- Local Context Retrieval Helper v1 artifact from step 3.
- Frozen graph baseline checkpoint from step 2.

Outputs are local JSON/JSONL artifacts under
local_data/organization/trace_net/embedding_candidates/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_embedding_candidates_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/embedding_candidates")
DEFAULT_CANDIDATES_FILE = "trace_net_embedding_candidates_v1.json"
DEFAULT_CANDIDATES_JSONL_FILE = "trace_net_embedding_candidates_v1.jsonl"
DEFAULT_REJECTED_JSONL_FILE = "trace_net_embedding_candidates_v1_rejected.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_embedding_candidates_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_embedding_candidates_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_embedding_candidates_v1_quality.json"
DEFAULT_CONTEXT_HELPERS = Path(
    "local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json"
)
DEFAULT_CONTEXT_HELPER_QUALITY_FILE = "trace_net_context_retrieval_helpers_v1_quality.json"
DEFAULT_BASELINE_CHECKPOINT = Path(
    "local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/"
    "trace_net_graph_baseline_checkpoint_v1.json"
)
DEFAULT_BASELINE_QUALITY_FILE = "trace_net_graph_baseline_checkpoint_v1_quality.json"
DEFAULT_FALLBACK_DOC = "t_p_120_1176"

PAGE_NUMBER_RE = re.compile(r"(\d+)(?!.*\d)")
SAFE_SUFFIX_RE = re.compile(r"[^A-Za-z0-9_.-]+")
WHITESPACE_RE = re.compile(r"\s+")
PROMPT_LINE_RE = re.compile(
    r"(?i)\b(system prompt|developer message|ignore previous instructions|jailbreak|prompt injection)\b"
)
SECRET_LINE_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret[_-]?key|private[_-]?key|bearer\s+[a-z0-9._-]{20,}|password\s*=)\b"
)

ALLOWED_EMBEDDING_BUCKETS = {
    "source_evidence",
    "source_text_evidence",
    "verified_part_evidence",
    "derived_context",
    "context_retrieval_helper",
}
ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
RETRIEVAL_ONLY_BUCKETS = {"source_evidence", "derived_context", "context_retrieval_helper"}
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
EXCLUDED_ACTIONS = {"exclude", "excluded", "deny", "denied", "unsafe", "blocked", "block"}
SAFE_VECTOR_ALLOWED_USE = ["retrieve", "rank", "route", "candidate_discovery"]
ANSWER_SUPPORT_ALLOWED_USE = SAFE_VECTOR_ALLOWED_USE + ["answer_support_after_postgres_resolution"]
FORBIDDEN_USE = [
    "direct_answer_from_vector_hit",
    "claim_proof_from_vector_payload",
    "canonical_source_truth",
    "source_truth_mutation",
    "citation_replacement",
    "trust_tier_override",
    "answer_without_postgres_resolution",
]


class EmbeddingCandidateError(RuntimeError):
    """Raised when embedding candidates cannot be built or checked safely."""


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
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(v) for v in value]
    return str(value)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 24) -> str:
    raw = "|".join(_as_text(part) for part in parts)
    return f"{prefix}__{sha256_text(raw)[:length]}"


def stable_uuid(*parts: Any) -> str:
    raw = "|".join(_as_text(part) for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "trace-net/embedding-candidate/" + raw))


def parse_page_range(raw: str | None) -> list[int]:
    if raw is None or not str(raw).strip():
        return []
    pages: list[int] = []
    for part in str(raw).split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            start = int(left.strip())
            end = int(right.strip())
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"invalid page range: {token}")
            pages.extend(range(start, end + 1))
        else:
            value = int(token)
            if value <= 0:
                raise ValueError("page numbers must be positive")
            pages.append(value)
    seen: set[int] = set()
    unique: list[int] = []
    for page in pages:
        if page not in seen:
            seen.add(page)
            unique.append(page)
    return unique


def extract_page_number(value: Any) -> int | None:
    text = _as_text(value)
    if not text:
        return None
    match = PAGE_NUMBER_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def canonical_page_id(value: Any, *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> str:
    text = _as_text(value).strip()
    if not text:
        return ""
    if re.search(r"_p\d{6}$", text):
        return text
    page_number = extract_page_number(text)
    if page_number is None:
        return text
    return f"{fallback_doc}_p{page_number:06d}"


def _safe_suffix(value: Any, *, fallback: str = "record") -> str:
    text = _as_text(value).strip() or fallback
    text = SAFE_SUFFIX_RE.sub("_", text).strip("_")
    return text or fallback


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True)
    return str(value)


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "allowed", "allow"}:
        return True
    if text in {"0", "false", "no", "n", "off", "blocked", "deny", "denied"}:
        return False
    return default


def _maybe_json(value: Any) -> Any:
    if isinstance(value, (Mapping, list, tuple)):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{\"":
        return value
    try:
        return json.loads(text)
    except Exception:
        return value


def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("payload", "metadata", "properties", "json", "data", "context_payload"):
        if key in row:
            parsed = _maybe_json(row.get(key))
            if isinstance(parsed, Mapping):
                return dict(parsed)
    return {}


def _field(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    payload = _payload(row)
    lowered = {str(k).lower(): k for k in row.keys()}
    payload_lowered = {str(k).lower(): k for k in payload.keys()}
    for name in names:
        if name in row:
            value = row.get(name)
            if value not in (None, "", [], {}):
                return value
        key = lowered.get(name.lower())
        if key is not None:
            value = row.get(key)
            if value not in (None, "", [], {}):
                return value
        if name in payload:
            value = payload.get(name)
            if value not in (None, "", [], {}):
                return value
        payload_key = payload_lowered.get(name.lower())
        if payload_key is not None:
            value = payload.get(payload_key)
            if value not in (None, "", [], {}):
                return value
    return default


def _first_text(*values: Any) -> str:
    for value in values:
        text = _as_text(value).strip()
        if text:
            return text
    return ""


def _coerce_list(value: Any) -> list[str]:
    value = _maybe_json(value)
    if value in (None, "", [], {}):
        return []
    if isinstance(value, Mapping):
        items: list[Any] = []
        for key, val in value.items():
            if isinstance(val, (list, tuple, set)):
                items.extend(val)
            elif val not in (None, "", [], {}):
                if str(key).isdigit():
                    items.append(val)
                else:
                    items.append(f"{key}: {val}")
        return _dedupe(items)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items: list[Any] = []
        for item in value:
            if isinstance(item, (list, tuple, set)):
                items.extend(item)
            elif isinstance(item, Mapping):
                items.extend(_coerce_list(item))
            else:
                items.append(item)
        return _dedupe(items)
    text = _as_text(value).strip()
    if not text:
        return []
    pieces = re.split(r"[\n;|]+", text)
    if len(pieces) == 1 and 0 < text.count(",") <= 12:
        pieces = text.split(",")
    return _dedupe(pieces)


def _dedupe(items: Iterable[Any], *, max_items: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = _as_text(item).strip()
        text = re.sub(r"^[\s\-:*]+", "", text).strip()
        text = WHITESPACE_RE.sub(" ", text)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if max_items is not None and len(result) >= max_items:
            break
    return result


def normalize_bucket(value: Any) -> str:
    bucket = _as_text(value).strip().lower()
    bucket = bucket.replace("-", "_").replace(" ", "_")
    aliases = {
        "source": "source_evidence",
        "source_trace": "source_evidence",
        "source_text": "source_text_evidence",
        "ocr_text": "source_text_evidence",
        "part_evidence": "verified_part_evidence",
        "verified_part": "verified_part_evidence",
        "context_v2": "context_retrieval_helper",
        "page_context_v2": "context_retrieval_helper",
        "context_helper": "context_retrieval_helper",
    }
    return aliases.get(bucket, bucket)


def _row_source_id(row: Mapping[str, Any]) -> str:
    return _first_text(
        _field(row, "chunk_id", "candidate_id", "rag_candidate_id", "helper_id", "embedding_candidate_id"),
        _field(row, "source_candidate_id", "source_record_id", "record_id", "citation_id", "context_id", "id"),
    )


def _row_page_id(row: Mapping[str, Any], *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> str:
    return canonical_page_id(
        _field(row, "page_id", "canonical_page_id", "source_page_id", "page_node_id", "page"),
        fallback_doc=fallback_doc,
    )


def _row_bucket(row: Mapping[str, Any]) -> str:
    return normalize_bucket(
        _field(row, "rag_bucket", "embedding_bucket", "candidate_type", "safety_bucket", "record_type", "bucket", default="")
    )


def _lookup_maps(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_key: dict[str, dict[str, Any]] = {}
    by_page: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        page_id = _row_page_id(row)
        for key_name in (
            "embedding_candidate_id",
            "chunk_id",
            "candidate_id",
            "rag_candidate_id",
            "source_candidate_id",
            "source_record_id",
            "record_id",
            "citation_id",
            "authority_id",
            "id",
        ):
            key = _as_text(row.get(key_name)).strip()
            if key:
                by_key.setdefault(key, row)
        if page_id:
            by_page.setdefault(page_id, []).append(row)
    return by_key, by_page


def _find_related_row(row: Mapping[str, Any], by_key: Mapping[str, Mapping[str, Any]], by_page: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    for key_name in (
        "embedding_candidate_id",
        "chunk_id",
        "candidate_id",
        "rag_candidate_id",
        "source_candidate_id",
        "source_record_id",
        "record_id",
        "citation_id",
        "authority_id",
        "id",
    ):
        key = _as_text(_field(row, key_name)).strip()
        if key and key in by_key:
            return dict(by_key[key])
    page_rows = by_page.get(_row_page_id(row), [])
    return dict(page_rows[0]) if page_rows else {}


def sanitize_embedding_text(text: Any, *, max_chars: int = 6000) -> tuple[str, list[str]]:
    raw = _as_text(text).replace("\x00", " ")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    reasons: list[str] = []
    kept_lines: list[str] = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if PROMPT_LINE_RE.search(stripped):
            reasons.append("prompt_like_line_removed")
            continue
        if SECRET_LINE_RE.search(stripped):
            reasons.append("secret_like_line_removed")
            continue
        kept_lines.append(stripped)
    text_out = WHITESPACE_RE.sub(" ", " ".join(kept_lines)).strip()
    if len(text_out) > max_chars:
        text_out = text_out[: max_chars - 3].rstrip() + "..."
        reasons.append("text_truncated")
    return text_out, _dedupe(reasons)


def _rag_text(row: Mapping[str, Any], citation: Mapping[str, Any], bucket: str) -> str:
    direct = _first_text(
        _field(row, "embedding_text", "chunk_text", "text", "content", "candidate_text"),
        _field(row, "evidence_text", "source_text", "context_text", "summary", "description"),
        _field(row, "citation_text", "source_citation_text"),
        _field(citation, "citation_text", "source_citation_text", "text", "summary"),
    )
    if direct:
        return direct

    page_id = _row_page_id(row)
    source_url = _first_text(_field(row, "source_url", "rescarta_url", "url"), _field(citation, "source_url", "rescarta_url", "url", "citation_url"))
    tiff_path = _first_text(_field(row, "tiff_path", "tiff_uri", "source_image_path"), _field(citation, "tiff_path", "tiff_uri", "source_image_path"))
    ocr_path = _first_text(_field(row, "ocr_path", "ocr_uri", "ocr_text_path"), _field(citation, "ocr_path", "ocr_uri", "ocr_text_path"))
    part_number = _first_text(_field(row, "part_number", "part_id", "part"), _field(citation, "part_number", "part_id", "part"))
    nomenclature = _first_text(_field(row, "nomenclature", "part_nomenclature", "part_name", "description"), _field(citation, "nomenclature", "part_nomenclature", "part_name"))
    item_number = _first_text(_field(row, "item_number", "item", "figure_item"), _field(citation, "item_number", "item"))
    quantity = _first_text(_field(row, "quantity", "qty"), _field(citation, "quantity", "qty"))

    if bucket == "verified_part_evidence" and (part_number or nomenclature):
        parts = ["TRACE-Net verified part evidence.", f"Page: {page_id}."]
        if part_number:
            parts.append(f"Part: {part_number}.")
        if nomenclature:
            parts.append(f"Nomenclature: {nomenclature}.")
        if item_number:
            parts.append(f"Item: {item_number}.")
        if quantity:
            parts.append(f"Quantity: {quantity}.")
        return " ".join(parts)

    if bucket == "source_evidence" and (page_id or source_url or tiff_path or ocr_path):
        parts = ["TRACE-Net source evidence locator."]
        if page_id:
            parts.append(f"Page: {page_id}.")
        if source_url:
            parts.append(f"Source URL: {source_url}.")
        if tiff_path:
            parts.append(f"TIFF path: {tiff_path}.")
        if ocr_path:
            parts.append(f"OCR path: {ocr_path}.")
        return " ".join(parts)

    # Safe last-resort locator text for already eligible RAG records.
    if page_id:
        return f"TRACE-Net {bucket or 'rag'} candidate for page {page_id}."
    return ""


def _citation_fields(row: Mapping[str, Any], citation: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source_url": _first_text(_field(row, "source_url", "rescarta_url", "url"), _field(citation, "source_url", "rescarta_url", "url", "citation_url")),
        "citation_id": _first_text(_field(row, "citation_id", "source_citation_id"), _field(citation, "citation_id", "source_citation_id", "record_id", "id")),
        "tiff_path": _first_text(_field(row, "tiff_path", "tiff_uri", "source_image_path"), _field(citation, "tiff_path", "tiff_uri", "source_image_path")),
        "ocr_path": _first_text(_field(row, "ocr_path", "ocr_uri", "ocr_text_path"), _field(citation, "ocr_path", "ocr_uri", "ocr_text_path")),
    }


def _trust_tier(row: Mapping[str, Any], authority: Mapping[str, Any], bucket: str) -> str:
    tier = _first_text(
        _field(row, "final_trust_tier", "trust_tier", "tier", "trust"),
        _field(authority, "final_trust_tier", "trust_tier", "tier", "trust"),
    )
    if tier:
        return tier
    if bucket == "context_retrieval_helper":
        return "RETRIEVAL_ONLY"
    if bucket == "derived_context":
        return "C"
    return ""


def _rag_action(row: Mapping[str, Any], authority: Mapping[str, Any]) -> str:
    return _first_text(_field(row, "final_rag_action", "rag_action", "action"), _field(authority, "final_rag_action", "rag_action", "action"))


def _answer_policy(bucket: str, authority: Mapping[str, Any]) -> dict[str, Any]:
    if bucket in RETRIEVAL_ONLY_BUCKETS:
        return {
            "answer_use_policy": "retrieval_only",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_prove_source_truth": False,
            "allowed_use": list(SAFE_VECTOR_ALLOWED_USE),
        }
    if bucket == "source_text_evidence":
        return {
            "answer_use_policy": "answer_support_after_postgres_resolution",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_prove_source_truth": False,
            "allowed_use": list(ANSWER_SUPPORT_ALLOWED_USE),
        }
    if bucket == "verified_part_evidence":
        return {
            "answer_use_policy": "part_page_support_after_postgres_resolution",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_prove_source_truth": False,
            "allowed_use": list(ANSWER_SUPPORT_ALLOWED_USE),
        }
    return {
        "answer_use_policy": "not_answer_capable",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_prove_source_truth": False,
        "allowed_use": list(SAFE_VECTOR_ALLOWED_USE),
    }


def build_rag_embedding_candidate(
    row: Mapping[str, Any],
    *,
    citation: Mapping[str, Any] | None = None,
    authority: Mapping[str, Any] | None = None,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_text_chars: int = 6000,
) -> tuple[dict[str, Any], list[str]]:
    citation = dict(citation or {})
    authority = dict(authority or {})
    page_id = _row_page_id(row, fallback_doc=fallback_doc)
    bucket = _row_bucket(row)
    source_candidate_id = _row_source_id(row) or stable_id("rag_source", page_id, bucket, sha256_json(dict(row)), length=16)
    raw_text = _rag_text(row, citation, bucket)
    text, sanitize_reasons = sanitize_embedding_text(raw_text, max_chars=max_text_chars)
    citation_fields = _citation_fields(row, citation)
    tier = _trust_tier(row, authority, bucket)
    action = _rag_action(row, authority).lower()
    policy = _answer_policy(bucket, authority)
    row_hash = sha256_json(dict(row))

    reasons: list[str] = []
    if bucket not in ALLOWED_EMBEDDING_BUCKETS:
        reasons.append("bucket_not_allowed_for_embedding")
    if bucket in BANNED_BUCKETS:
        reasons.append("banned_bucket")
    if not page_id:
        reasons.append("missing_page_id")
    if not source_candidate_id:
        reasons.append("missing_source_candidate_id")
    if not text:
        reasons.append("empty_embedding_text")
    if tier.upper() == "D":
        reasons.append("D_tier_not_allowed")
    if action in EXCLUDED_ACTIONS:
        reasons.append("excluded_rag_action")
    evidence_layer = normalize_bucket(_field(row, "evidence_layer", "layer", default=bucket))
    candidate_type = normalize_bucket(_field(row, "candidate_type", "record_type", default=bucket)) or bucket
    if evidence_layer in BANNED_BUCKETS or candidate_type in BANNED_BUCKETS:
        reasons.append("raw_or_preprocessing_layer_not_allowed")
    if bucket in ANSWER_SUPPORT_BUCKETS and not any(citation_fields.values()):
        reasons.append("answer_support_candidate_missing_citation_or_source")
    reasons.extend(sanitize_reasons)
    reasons = _dedupe(reasons)

    embedding_candidate_id = stable_id("embcand", "rag", source_candidate_id, bucket, sha256_text(text), length=24)
    record = {
        "schema_version": SCHEMA_VERSION,
        "embedding_candidate_id": embedding_candidate_id,
        "qdrant_point_id": stable_uuid(embedding_candidate_id),
        "record_type": "embedding_candidate",
        "source_kind": "rag_candidate_chunk",
        "source_table": "rag_candidate_chunks",
        "source_candidate_id": source_candidate_id,
        "source_row_sha256": row_hash,
        "page_id": page_id,
        "page_number": extract_page_number(page_id),
        "document_id": _first_text(_field(row, "document_id", "manual_id", "source_document_id")),
        "ata_code": _first_text(_field(row, "ata_code", "ata", "ata_section")),
        "rag_bucket": bucket,
        "embedding_bucket": bucket,
        "candidate_type": candidate_type or bucket,
        "evidence_layer": evidence_layer or bucket,
        "embedding_text": text,
        "text": text,
        "text_chars": len(text),
        "content_sha256": sha256_text(text),
        "trust_tier": tier,
        "final_trust_tier": tier,
        "final_rag_action": _rag_action(row, authority),
        "authority": _first_text(_field(authority, "authority", "claim_authority", "answer_authority"), policy["answer_use_policy"]),
        "answer_use_policy": policy["answer_use_policy"],
        "allowed_use": policy["allowed_use"],
        "forbidden_use": list(FORBIDDEN_USE),
        "can_embed": True,
        "can_retrieve": True,
        "can_answer_directly": policy["can_answer_directly"],
        "can_prove_claims": policy["can_prove_claims"],
        "can_prove_source_truth": policy["can_prove_source_truth"],
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "can_override_trust": False,
        "can_replace_citation": False,
        "retrieval_only": bucket in RETRIEVAL_ONLY_BUCKETS,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_answer_authority_allowed": False,
        "source_url": citation_fields["source_url"],
        "citation_id": citation_fields["citation_id"],
        "tiff_path": citation_fields["tiff_path"],
        "ocr_path": citation_fields["ocr_path"],
        "safety_status": "safe" if not [r for r in reasons if not r.endswith("_removed") and r != "text_truncated"] else "rejected",
        "safety_reasons": reasons,
        "traceability": {
            "source_kind": "rag_candidate_chunk",
            "source_table": "rag_candidate_chunks",
            "source_candidate_id": source_candidate_id,
            "source_row_sha256": row_hash,
            "page_id": page_id,
            "citation_id": citation_fields["citation_id"],
            "source_url": citation_fields["source_url"],
            "tiff_path": citation_fields["tiff_path"],
            "ocr_path": citation_fields["ocr_path"],
            "must_resolve_through_postgres": True,
        },
        "qdrant_payload_preview": {
            "embedding_candidate_id": embedding_candidate_id,
            "source_candidate_id": source_candidate_id,
            "page_id": page_id,
            "rag_bucket": bucket,
            "trust_tier": tier,
            "citation_id": citation_fields["citation_id"],
            "source_url": citation_fields["source_url"],
            "requires_source_resolution": True,
            "can_answer_directly": False,
        },
        "created_at_utc": utc_now_iso(),
    }
    return record, reasons


def build_context_helper_embedding_candidate(
    helper: Mapping[str, Any],
    *,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_text_chars: int = 6000,
) -> tuple[dict[str, Any], list[str]]:
    page_id = _row_page_id(helper, fallback_doc=fallback_doc)
    helper_id = _first_text(_field(helper, "helper_id", "source_candidate_id", "record_id", "context_id", "id"))
    source_context_id = _first_text(_field(helper, "source_context_id", "context_id", "record_id", "id"))
    raw_text = _first_text(_field(helper, "embedding_text", "helper_text", "text", "summary"))
    text, sanitize_reasons = sanitize_embedding_text(raw_text, max_chars=max_text_chars)
    row_hash = sha256_json(dict(helper))
    source_candidate_id = helper_id or stable_id("ctx_helper_source", page_id, source_context_id, row_hash, length=16)
    bucket = "context_retrieval_helper"
    reasons: list[str] = []
    if not page_id:
        reasons.append("missing_page_id")
    if not source_candidate_id:
        reasons.append("missing_source_candidate_id")
    if not text:
        reasons.append("empty_embedding_text")
    if _as_bool(_field(helper, "can_answer_directly"), default=False):
        reasons.append("context_helper_marked_answerable")
    if _as_bool(_field(helper, "can_prove_claims"), default=False):
        reasons.append("context_helper_marked_claim_proof")
    if _as_bool(_field(helper, "canonical_source_truth"), default=False):
        reasons.append("context_helper_marked_source_truth")
    if _as_bool(_field(helper, "can_mutate_source_truth"), default=False):
        reasons.append("context_helper_can_mutate_source_truth")
    if _field(helper, "authority", default="retrieval_helper_only") != "retrieval_helper_only":
        reasons.append("context_helper_wrong_authority")
    reasons.extend(sanitize_reasons)
    reasons = _dedupe(reasons)

    embedding_candidate_id = stable_id("embcand", "ctx", source_candidate_id, bucket, sha256_text(text), length=24)
    record = {
        "schema_version": SCHEMA_VERSION,
        "embedding_candidate_id": embedding_candidate_id,
        "qdrant_point_id": stable_uuid(embedding_candidate_id),
        "record_type": "embedding_candidate",
        "source_kind": "context_retrieval_helper",
        "source_table": "trace_net_context_retrieval_helpers_v1",
        "source_candidate_id": source_candidate_id,
        "source_context_id": source_context_id,
        "source_row_sha256": row_hash,
        "page_id": page_id,
        "page_number": extract_page_number(page_id),
        "document_id": _first_text(_field(helper, "document_id", "manual_id")),
        "ata_code": _first_text(_field(helper, "ata_code", "ata", "ata_section")),
        "rag_bucket": bucket,
        "embedding_bucket": bucket,
        "candidate_type": bucket,
        "evidence_layer": bucket,
        "embedding_text": text,
        "text": text,
        "text_chars": len(text),
        "content_sha256": sha256_text(text),
        "trust_tier": _first_text(_field(helper, "trust_tier", "final_trust_tier"), "RETRIEVAL_ONLY"),
        "final_trust_tier": _first_text(_field(helper, "trust_tier", "final_trust_tier"), "RETRIEVAL_ONLY"),
        "final_rag_action": "retrieval_helper_only",
        "authority": "retrieval_helper_only",
        "answer_use_policy": "retrieval_only",
        "allowed_use": list(SAFE_VECTOR_ALLOWED_USE),
        "forbidden_use": list(FORBIDDEN_USE),
        "can_embed": True,
        "can_retrieve": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_prove_source_truth": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "can_override_trust": False,
        "can_replace_citation": False,
        "retrieval_only": True,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_answer_authority_allowed": False,
        "source_url": _first_text(_field(helper, "source_url", "rescarta_url", "url")),
        "citation_id": _first_text(_field(helper, "citation_id", "source_citation_id")),
        "tiff_path": _first_text(_field(helper, "tiff_path", "tiff_uri")),
        "ocr_path": _first_text(_field(helper, "ocr_path", "ocr_uri")),
        "query_tunnel_terms": _coerce_list(_field(helper, "query_tunnel_terms"))[:80],
        "retrieval_cues": _coerce_list(_field(helper, "retrieval_cues"))[:80],
        "safety_status": "safe" if not [r for r in reasons if not r.endswith("_removed") and r != "text_truncated"] else "rejected",
        "safety_reasons": reasons,
        "traceability": {
            "source_kind": "context_retrieval_helper",
            "source_table": "trace_net_context_retrieval_helpers_v1",
            "source_candidate_id": source_candidate_id,
            "source_context_id": source_context_id,
            "source_row_sha256": row_hash,
            "page_id": page_id,
            "must_resolve_through_postgres": True,
        },
        "qdrant_payload_preview": {
            "embedding_candidate_id": embedding_candidate_id,
            "source_candidate_id": source_candidate_id,
            "page_id": page_id,
            "rag_bucket": bucket,
            "trust_tier": "RETRIEVAL_ONLY",
            "citation_id": "",
            "source_url": "",
            "requires_source_resolution": True,
            "can_answer_directly": False,
        },
        "created_at_utc": utc_now_iso(),
    }
    return record, reasons


def build_embedding_candidate_records(
    rag_rows: Sequence[Mapping[str, Any]],
    context_helper_rows: Sequence[Mapping[str, Any]],
    *,
    citation_rows: Sequence[Mapping[str, Any]] | None = None,
    authority_rows: Sequence[Mapping[str, Any]] | None = None,
    include_rag_candidates: bool = True,
    include_context_helpers: bool = True,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_text_chars: int = 6000,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    citation_by_key, citation_by_page = _lookup_maps(list(citation_rows or []))
    authority_by_key, authority_by_page = _lookup_maps(list(authority_rows or []))
    safe: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    if include_rag_candidates:
        for row in rag_rows:
            citation = _find_related_row(row, citation_by_key, citation_by_page)
            authority = _find_related_row(row, authority_by_key, authority_by_page)
            record, _reasons = build_rag_embedding_candidate(
                row,
                citation=citation,
                authority=authority,
                fallback_doc=fallback_doc,
                max_text_chars=max_text_chars,
            )
            if record["safety_status"] == "safe":
                safe.append(record)
            else:
                rejected.append(record)

    if include_context_helpers:
        for helper in context_helper_rows:
            record, _reasons = build_context_helper_embedding_candidate(
                helper,
                fallback_doc=fallback_doc,
                max_text_chars=max_text_chars,
            )
            if record["safety_status"] == "safe":
                safe.append(record)
            else:
                rejected.append(record)

    # Stable de-duplication: keep first candidate for same source/bucket/content.
    deduped: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for record in safe:
        key = f"{record.get('source_kind')}|{record.get('source_candidate_id')}|{record.get('rag_bucket')}|{record.get('content_sha256')}"
        if key in deduped:
            dup = dict(record)
            dup["safety_status"] = "rejected"
            dup["safety_reasons"] = _dedupe(list(dup.get("safety_reasons", [])) + ["duplicate_safe_candidate"])
            duplicates.append(dup)
        else:
            deduped[key] = record
    safe = list(deduped.values())
    rejected.extend(duplicates)
    safe.sort(key=lambda rec: ((rec.get("page_number") or 10**9), str(rec.get("rag_bucket") or ""), str(rec.get("embedding_candidate_id") or "")))
    rejected.sort(key=lambda rec: ((rec.get("page_number") or 10**9), str(rec.get("rag_bucket") or ""), str(rec.get("embedding_candidate_id") or "")))
    return safe, rejected


def required_page_coverage(required_pages: Sequence[int], records: Sequence[Mapping[str, Any]], *, bucket: str | None = None) -> dict[str, Any]:
    filtered = [rec for rec in records if bucket is None or rec.get("rag_bucket") == bucket]
    pages_present = {extract_page_number(rec.get("page_id")) for rec in filtered}
    pages_present.discard(None)
    missing = [page for page in required_pages if page not in pages_present]
    covered = [page for page in required_pages if page in pages_present]
    return {
        "required_page_numbers": list(required_pages),
        "covered_page_numbers": covered,
        "missing_page_numbers": missing,
        "covered_page_count": len(covered),
        "missing_page_count": len(missing),
        "bucket": bucket or "any",
    }


def summarize_embedding_candidates(
    records: Sequence[Mapping[str, Any]],
    rejected: Sequence[Mapping[str, Any]] | None = None,
    *,
    required_pages: Sequence[int] | None = None,
) -> dict[str, Any]:
    rejected = list(rejected or [])
    required_pages = list(required_pages or [])
    ids = [str(rec.get("embedding_candidate_id") or "") for rec in records]
    duplicate_ids = sorted({candidate_id for candidate_id in ids if candidate_id and ids.count(candidate_id) > 1})
    bucket_counts = Counter(str(rec.get("rag_bucket") or "") for rec in records)
    source_kind_counts = Counter(str(rec.get("source_kind") or "") for rec in records)
    trust_counts = Counter(str(rec.get("trust_tier") or "") for rec in records)

    def bad_bool(name: str) -> int:
        return sum(1 for rec in records if _as_bool(rec.get(name), default=False))

    missing_source_trace_count = sum(
        1
        for rec in records
        if not isinstance(rec.get("traceability"), Mapping)
        or not rec["traceability"].get("must_resolve_through_postgres")
        or not rec.get("source_candidate_id")
        or not rec.get("page_id")
    )
    answer_support_missing_citation_or_source_count = sum(
        1
        for rec in records
        if rec.get("rag_bucket") in ANSWER_SUPPORT_BUCKETS
        and not (rec.get("citation_id") or rec.get("source_url") or rec.get("tiff_path") or rec.get("ocr_path"))
    )
    retrieval_only_answerable_count = sum(
        1 for rec in records if rec.get("rag_bucket") in RETRIEVAL_ONLY_BUCKETS and _as_bool(rec.get("can_answer_directly"))
    )
    context_helper_can_prove_count = sum(
        1
        for rec in records
        if rec.get("rag_bucket") == "context_retrieval_helper"
        and (_as_bool(rec.get("can_prove_claims")) or _as_bool(rec.get("can_prove_source_truth")))
    )
    summary = {
        "safe_embedding_candidate_count": len(records),
        "rejected_embedding_candidate_count": len(rejected),
        "page_count": len({str(rec.get("page_id") or "") for rec in records if rec.get("page_id")}),
        "missing_page_id_count": sum(1 for rec in records if not rec.get("page_id")),
        "missing_source_candidate_id_count": sum(1 for rec in records if not rec.get("source_candidate_id")),
        "missing_embedding_text_count": sum(1 for rec in records if not _as_text(rec.get("embedding_text") or rec.get("text")).strip()),
        "duplicate_embedding_candidate_id_count": len(duplicate_ids),
        "duplicate_embedding_candidate_ids": duplicate_ids[:20],
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "source_kind_counts": dict(sorted(source_kind_counts.items())),
        "trust_tier_counts": dict(sorted(trust_counts.items())),
        "rag_candidate_embedding_count": source_kind_counts.get("rag_candidate_chunk", 0),
        "context_helper_embedding_count": bucket_counts.get("context_retrieval_helper", 0),
        "source_text_evidence_count": bucket_counts.get("source_text_evidence", 0),
        "verified_part_evidence_count": bucket_counts.get("verified_part_evidence", 0),
        "derived_context_count": bucket_counts.get("derived_context", 0),
        "source_evidence_count": bucket_counts.get("source_evidence", 0),
        "bucket_not_allowed_count": sum(1 for rec in records if rec.get("rag_bucket") not in ALLOWED_EMBEDDING_BUCKETS),
        "banned_bucket_count": sum(1 for rec in records if rec.get("rag_bucket") in BANNED_BUCKETS),
        "D_tier_count": sum(1 for rec in records if _as_text(rec.get("trust_tier")).upper() == "D"),
        "excluded_action_count": sum(1 for rec in records if _as_text(rec.get("final_rag_action")).lower() in EXCLUDED_ACTIONS),
        "unsafe_status_count": sum(1 for rec in records if rec.get("safety_status") != "safe"),
        "can_answer_directly_true_count": bad_bool("can_answer_directly"),
        "can_prove_claims_true_count": bad_bool("can_prove_claims"),
        "can_prove_source_truth_true_count": bad_bool("can_prove_source_truth"),
        "canonical_source_truth_true_count": bad_bool("canonical_source_truth"),
        "source_truth_mutation_allowed_count": bad_bool("can_mutate_source_truth"),
        "trust_override_allowed_count": bad_bool("can_override_trust"),
        "citation_replacement_allowed_count": bad_bool("can_replace_citation"),
        "embedding_answer_authority_allowed_count": bad_bool("embedding_answer_authority_allowed"),
        "requires_source_resolution_false_count": sum(1 for rec in records if not _as_bool(rec.get("requires_source_resolution"), default=True)),
        "requires_citation_false_count": sum(1 for rec in records if not _as_bool(rec.get("requires_citation"), default=True)),
        "requires_authority_gate_false_count": sum(1 for rec in records if not _as_bool(rec.get("requires_authority_gate"), default=True)),
        "missing_source_trace_count": missing_source_trace_count,
        "answer_support_missing_citation_or_source_count": answer_support_missing_citation_or_source_count,
        "retrieval_only_answerable_count": retrieval_only_answerable_count,
        "context_helper_can_prove_count": context_helper_can_prove_count,
    }
    summary["unsafe_embedding_candidate_count"] = sum(
        int(summary[key])
        for key in (
            "missing_page_id_count",
            "missing_source_candidate_id_count",
            "missing_embedding_text_count",
            "duplicate_embedding_candidate_id_count",
            "bucket_not_allowed_count",
            "banned_bucket_count",
            "D_tier_count",
            "excluded_action_count",
            "unsafe_status_count",
            "can_answer_directly_true_count",
            "can_prove_claims_true_count",
            "can_prove_source_truth_true_count",
            "canonical_source_truth_true_count",
            "source_truth_mutation_allowed_count",
            "trust_override_allowed_count",
            "citation_replacement_allowed_count",
            "embedding_answer_authority_allowed_count",
            "requires_source_resolution_false_count",
            "requires_citation_false_count",
            "requires_authority_gate_false_count",
            "missing_source_trace_count",
            "answer_support_missing_citation_or_source_count",
            "retrieval_only_answerable_count",
            "context_helper_can_prove_count",
        )
    )
    coverage = required_page_coverage(required_pages, records)
    context_coverage = required_page_coverage(required_pages, records, bucket="context_retrieval_helper")
    summary["required_page_coverage"] = coverage
    summary["required_page_missing_count"] = coverage["missing_page_count"]
    summary["required_context_helper_page_coverage"] = context_coverage
    summary["required_context_helper_page_missing_count"] = context_coverage["missing_page_count"]
    return summary


def _check(checks: list[dict[str, Any]], name: str, actual: Any, op: str, expected: Any, passed: bool) -> None:
    checks.append({"name": name, "actual": actual, "op": op, "expected": expected, "passed": bool(passed)})


def _sibling_quality_status(path: Path, default_name: str) -> str:
    quality_path = path.with_name(default_name)
    if not quality_path.exists():
        return "UNKNOWN"
    try:
        payload = json.loads(quality_path.read_text(encoding="utf-8"))
        status = _as_text(payload.get("status")).upper()
        return status if status in {"PASS", "FAIL"} else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def baseline_quality_status_from_checkpoint(checkpoint: Mapping[str, Any] | None, checkpoint_path: Path | None = None) -> str:
    if not checkpoint:
        return "UNKNOWN"
    direct = _as_text(checkpoint.get("quality_status") or checkpoint.get("status")).upper()
    if direct in {"PASS", "FAIL"}:
        return direct
    if checkpoint_path:
        return _sibling_quality_status(checkpoint_path, DEFAULT_BASELINE_QUALITY_FILE)
    return "UNKNOWN"


def context_helper_quality_status(context_helpers_path: Path | None) -> str:
    if not context_helpers_path:
        return "UNKNOWN"
    return _sibling_quality_status(context_helpers_path, DEFAULT_CONTEXT_HELPER_QUALITY_FILE)


def evaluate_embedding_candidate_quality(
    records: Sequence[Mapping[str, Any]],
    rejected: Sequence[Mapping[str, Any]] | None = None,
    *,
    baseline_checkpoint: Mapping[str, Any] | None = None,
    baseline_checkpoint_path: Path | None = None,
    context_helpers_path: Path | None = None,
    min_safe_candidates: int = 967,
    min_rag_candidates: int = 917,
    min_context_helper_candidates: int = 50,
    min_pages_with_candidates: int = 50,
    require_pages: Sequence[int] | None = None,
    require_baseline_quality_pass: bool = False,
    require_context_helper_quality_pass: bool = False,
) -> QualityResult:
    required_pages = list(require_pages or [])
    summary = summarize_embedding_candidates(records, rejected or [], required_pages=required_pages)
    checks: list[dict[str, Any]] = []
    _check(checks, "safe_embedding_candidate_count", summary["safe_embedding_candidate_count"], ">=", min_safe_candidates, summary["safe_embedding_candidate_count"] >= min_safe_candidates)
    _check(checks, "rag_candidate_embedding_count", summary["rag_candidate_embedding_count"], ">=", min_rag_candidates, summary["rag_candidate_embedding_count"] >= min_rag_candidates)
    _check(checks, "context_helper_embedding_count", summary["context_helper_embedding_count"], ">=", min_context_helper_candidates, summary["context_helper_embedding_count"] >= min_context_helper_candidates)
    _check(checks, "pages_with_candidates", summary["page_count"], ">=", min_pages_with_candidates, summary["page_count"] >= min_pages_with_candidates)
    _check(checks, "required_page_missing_count", summary["required_page_missing_count"], "==", 0, summary["required_page_missing_count"] == 0)
    _check(checks, "required_context_helper_page_missing_count", summary["required_context_helper_page_missing_count"], "==", 0, summary["required_context_helper_page_missing_count"] == 0)
    _check(checks, "unsafe_embedding_candidate_count", summary["unsafe_embedding_candidate_count"], "==", 0, summary["unsafe_embedding_candidate_count"] == 0)
    if require_baseline_quality_pass:
        status = baseline_quality_status_from_checkpoint(baseline_checkpoint, baseline_checkpoint_path).upper()
        summary["baseline_quality_status"] = status
        _check(checks, "baseline_quality_status", status, "==", "PASS", status == "PASS")
    else:
        summary["baseline_quality_status"] = baseline_quality_status_from_checkpoint(baseline_checkpoint, baseline_checkpoint_path).upper()
    if require_context_helper_quality_pass:
        status = context_helper_quality_status(context_helpers_path).upper()
        summary["context_helper_quality_status"] = status
        _check(checks, "context_helper_quality_status", status, "==", "PASS", status == "PASS")
    else:
        summary["context_helper_quality_status"] = context_helper_quality_status(context_helpers_path).upper() if context_helpers_path else "UNKNOWN"
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=summary)


def load_json_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise EmbeddingCandidateError(f"JSON artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise EmbeddingCandidateError(f"expected JSON object at {path}")
    return dict(payload)


def load_records_from_path(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise EmbeddingCandidateError(f"record artifact not found: {path}")
    if path.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records, {"records": records}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping) and isinstance(payload.get("records"), list):
        return list(payload["records"]), dict(payload)
    if isinstance(payload, list):
        return list(payload), {"records": payload}
    raise EmbeddingCandidateError(f"unsupported record artifact shape: {path}")


def load_baseline_checkpoint(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return load_json_artifact(path)


def _table_exists(conn: Any, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s)", (f"public.{table_name}",))
        row = cur.fetchone()
        return bool(row and row[0])


def _table_columns(conn: Any, table_name: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public' and table_name = %s
            order by ordinal_position
            """,
            (table_name,),
        )
        return [row[0] for row in cur.fetchall()]


def load_table_rows(database_url: str, table_name: str, *, required: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise EmbeddingCandidateError("psycopg is required. Install with: pip install 'psycopg[binary]'.") from exc
    with psycopg.connect(database_url) as conn:
        if not _table_exists(conn, table_name):
            if required:
                raise EmbeddingCandidateError(f"Postgres table {table_name} does not exist.")
            return []
        columns = _table_columns(conn, table_name)
        order_parts = [name for name in ("page_id", "chunk_id", "candidate_id", "helper_id", "record_id", "id") if name in columns]
        sql = f"select * from {table_name}"
        params: tuple[Any, ...] = ()
        if order_parts:
            sql += " order by " + ", ".join(order_parts)
        if limit is not None:
            sql += " limit %s"
            params = (limit,)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            names = [desc[0] for desc in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]


def build_embedding_candidate_bundle(
    rag_rows: Sequence[Mapping[str, Any]],
    context_helper_rows: Sequence[Mapping[str, Any]],
    *,
    citation_rows: Sequence[Mapping[str, Any]] | None = None,
    authority_rows: Sequence[Mapping[str, Any]] | None = None,
    baseline_checkpoint: Mapping[str, Any] | None = None,
    baseline_checkpoint_path: Path | None = None,
    context_helpers_path: Path | None = None,
    require_pages: Sequence[int] | None = None,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_text_chars: int = 6000,
) -> dict[str, Any]:
    records, rejected = build_embedding_candidate_records(
        rag_rows,
        context_helper_rows,
        citation_rows=citation_rows,
        authority_rows=authority_rows,
        fallback_doc=fallback_doc,
        max_text_chars=max_text_chars,
    )
    required_pages = list(require_pages or [])
    summary = summarize_embedding_candidates(records, rejected, required_pages=required_pages)
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "read_only": True,
        "record_count": len(records),
        "rejected_record_count": len(rejected),
        "records": records,
        "rejected_records": rejected,
        "rejected_records_sample": rejected[:50],
        "summary": summary,
        "baseline_checkpoint": {
            "path": str(baseline_checkpoint_path) if baseline_checkpoint_path else "",
            "checkpoint_name": _as_text((baseline_checkpoint or {}).get("checkpoint_name")),
            "checkpoint_sha256": _as_text((baseline_checkpoint or {}).get("checkpoint_sha256")),
            "quality_status": baseline_quality_status_from_checkpoint(baseline_checkpoint, baseline_checkpoint_path),
        },
        "context_helper_artifact": {
            "path": str(context_helpers_path) if context_helpers_path else "",
            "quality_status": context_helper_quality_status(context_helpers_path) if context_helpers_path else "UNKNOWN",
        },
        "trace_net_boundary_rules": {
            "embedding_candidates_are_source_truth": False,
            "embedding_candidates_can_answer_directly": False,
            "vector_payload_can_prove_claims": False,
            "context_helpers_are_retrieval_only": True,
            "qdrant_is_index_not_authority": True,
            "postgres_graph_trust_citation_remain_authority": True,
            "all_answer_use_requires_source_resolution": True,
            "all_answer_use_requires_citation": True,
            "source_truth_mutations_allowed": False,
        },
    }
    return bundle


def write_embedding_candidate_outputs(bundle: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = output_dir / DEFAULT_CANDIDATES_FILE
    jsonl_path = output_dir / DEFAULT_CANDIDATES_JSONL_FILE
    rejected_path = output_dir / DEFAULT_REJECTED_JSONL_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE

    candidates_path.write_text(json.dumps(json_safe(bundle), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in bundle.get("records", []):
            handle.write(json.dumps(json_safe(record), ensure_ascii=False, sort_keys=True) + "\n")
    with rejected_path.open("w", encoding="utf-8") as handle:
        for record in bundle.get("rejected_records", bundle.get("rejected_records_sample", [])):
            handle.write(json.dumps(json_safe(record), ensure_ascii=False, sort_keys=True) + "\n")
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": bundle.get("generated_at_utc"),
        "read_only": True,
        "record_count": bundle.get("record_count"),
        "rejected_record_count": bundle.get("rejected_record_count"),
        "summary": bundle.get("summary", {}),
        "baseline_checkpoint": bundle.get("baseline_checkpoint", {}),
        "context_helper_artifact": bundle.get("context_helper_artifact", {}),
        "trace_net_boundary_rules": bundle.get("trace_net_boundary_rules", {}),
    }
    summary_path.write_text(json.dumps(json_safe(summary_payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": bundle.get("generated_at_utc"),
        "read_only": True,
        "files": {
            DEFAULT_CANDIDATES_FILE: {"path": str(candidates_path), "sha256": sha256_file(candidates_path)},
            DEFAULT_CANDIDATES_JSONL_FILE: {"path": str(jsonl_path), "sha256": sha256_file(jsonl_path)},
            DEFAULT_REJECTED_JSONL_FILE: {"path": str(rejected_path), "sha256": sha256_file(rejected_path)},
            DEFAULT_SUMMARY_FILE: {"path": str(summary_path), "sha256": sha256_file(summary_path)},
        },
        "record_count": bundle.get("record_count"),
        "rejected_record_count": bundle.get("rejected_record_count"),
    }
    manifest_path.write_text(json.dumps(json_safe(manifest_payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "candidates_path": candidates_path,
        "jsonl_path": jsonl_path,
        "rejected_path": rejected_path,
        "summary_path": summary_path,
        "manifest_path": manifest_path,
    }


def write_quality_result(quality: QualityResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": quality.status,
        "summary": quality.summary,
        "checks": quality.checks,
    }
    output_path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _print_quality(quality: QualityResult) -> None:
    print("TRACE-Net embedding candidates v1 quality")
    print(f" Status: {quality.status}")
    for key in [
        "safe_embedding_candidate_count",
        "rag_candidate_embedding_count",
        "context_helper_embedding_count",
        "page_count",
        "required_page_missing_count",
        "required_context_helper_page_missing_count",
        "unsafe_embedding_candidate_count",
        "rejected_embedding_candidate_count",
        "baseline_quality_status",
        "context_helper_quality_status",
    ]:
        if key in quality.summary:
            print(f" {key}: {quality.summary[key]}")
    failed = [check for check in quality.checks if not check["passed"]]
    for check in failed[:10]:
        print(f" FAIL {check['name']}: {check['actual']} {check['op']} {check['expected']}")


def main_build(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build safe TRACE-Net Embedding Candidates v1 artifacts.")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""))
    parser.add_argument("--context-helpers", type=Path, default=DEFAULT_CONTEXT_HELPERS)
    parser.add_argument("--baseline-checkpoint", type=Path, default=DEFAULT_BASELINE_CHECKPOINT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--require-baseline-quality-pass", action="store_true")
    parser.add_argument("--require-context-helper-quality-pass", action="store_true")
    parser.add_argument("--require-first-pages", default="1-50")
    parser.add_argument("--fallback-doc", default=DEFAULT_FALLBACK_DOC)
    parser.add_argument("--max-text-chars", type=int, default=6000)
    parser.add_argument("--limit-rag", type=int, default=None)
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--min-safe-candidates", type=int, default=967)
    parser.add_argument("--min-rag-candidates", type=int, default=917)
    parser.add_argument("--min-context-helper-candidates", type=int, default=50)
    parser.add_argument("--min-pages-with-candidates", type=int, default=50)
    args = parser.parse_args(argv)

    if not args.database_url:
        print("ERROR: --database-url or TRACE_NET_DATABASE_URL is required", file=sys.stderr)
        return 2

    required_pages = parse_page_range(args.require_first_pages)
    baseline = load_baseline_checkpoint(args.baseline_checkpoint)
    helper_records, _helper_payload = load_records_from_path(args.context_helpers)
    rag_rows = load_table_rows(args.database_url, "rag_candidate_chunks", required=True, limit=args.limit_rag)
    citation_rows = load_table_rows(args.database_url, "source_citations", required=False)
    authority_rows = load_table_rows(args.database_url, "trust_authority_records", required=False)

    bundle = build_embedding_candidate_bundle(
        rag_rows,
        helper_records,
        citation_rows=citation_rows,
        authority_rows=authority_rows,
        baseline_checkpoint=baseline,
        baseline_checkpoint_path=args.baseline_checkpoint,
        context_helpers_path=args.context_helpers,
        require_pages=required_pages,
        fallback_doc=args.fallback_doc,
        max_text_chars=args.max_text_chars,
    )
    paths = write_embedding_candidate_outputs(bundle, args.output_dir)

    print("TRACE-Net embedding candidates v1")
    print(" Status: BUILT")
    summary = bundle["summary"]
    for key in [
        "safe_embedding_candidate_count",
        "rag_candidate_embedding_count",
        "context_helper_embedding_count",
        "page_count",
        "unsafe_embedding_candidate_count",
        "rejected_embedding_candidate_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" candidates_path: {paths['candidates_path']}")
    print(f" jsonl_path: {paths['jsonl_path']}")
    print(f" rejected_path: {paths['rejected_path']}")
    print(f" summary_path: {paths['summary_path']}")
    print(f" manifest_path: {paths['manifest_path']}")

    if args.quality:
        quality = evaluate_embedding_candidate_quality(
            bundle["records"],
            bundle.get("rejected_records", bundle.get("rejected_records_sample", [])),
            baseline_checkpoint=baseline,
            baseline_checkpoint_path=args.baseline_checkpoint,
            context_helpers_path=args.context_helpers,
            min_safe_candidates=args.min_safe_candidates,
            min_rag_candidates=args.min_rag_candidates,
            min_context_helper_candidates=args.min_context_helper_candidates,
            min_pages_with_candidates=args.min_pages_with_candidates,
            require_pages=required_pages,
            require_baseline_quality_pass=args.require_baseline_quality_pass,
            require_context_helper_quality_pass=args.require_context_helper_quality_pass,
        )
        quality_path = args.output_dir / DEFAULT_QUALITY_FILE
        write_quality_result(quality, quality_path)
        print(f" Quality status: {quality.status}")
        print(f" quality_path: {quality_path}")
        if not quality.passed:
            _print_quality(quality)
            return 1
    return 0


def main_quality(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quality-check TRACE-Net Embedding Candidates v1 artifacts.")
    parser.add_argument("--candidates-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_CANDIDATES_FILE)
    parser.add_argument("--rejected-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REJECTED_JSONL_FILE)
    parser.add_argument("--baseline-checkpoint", type=Path, default=DEFAULT_BASELINE_CHECKPOINT)
    parser.add_argument("--context-helpers", type=Path, default=DEFAULT_CONTEXT_HELPERS)
    parser.add_argument("--require-baseline-quality-pass", action="store_true")
    parser.add_argument("--require-context-helper-quality-pass", action="store_true")
    parser.add_argument("--require-first-pages", default="1-50")
    parser.add_argument("--min-safe-candidates", type=int, default=967)
    parser.add_argument("--min-rag-candidates", type=int, default=917)
    parser.add_argument("--min-context-helper-candidates", type=int, default=50)
    parser.add_argument("--min-pages-with-candidates", type=int, default=50)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--quality-path", type=Path, default=None)
    args = parser.parse_args(argv)

    records, _payload = load_records_from_path(args.candidates_path)
    try:
        rejected, _rejected_payload = load_records_from_path(args.rejected_path)
    except EmbeddingCandidateError:
        rejected = []
    baseline = load_baseline_checkpoint(args.baseline_checkpoint)
    required_pages = parse_page_range(args.require_first_pages)
    quality = evaluate_embedding_candidate_quality(
        records,
        rejected,
        baseline_checkpoint=baseline,
        baseline_checkpoint_path=args.baseline_checkpoint,
        context_helpers_path=args.context_helpers,
        min_safe_candidates=args.min_safe_candidates,
        min_rag_candidates=args.min_rag_candidates,
        min_context_helper_candidates=args.min_context_helper_candidates,
        min_pages_with_candidates=args.min_pages_with_candidates,
        require_pages=required_pages,
        require_baseline_quality_pass=args.require_baseline_quality_pass,
        require_context_helper_quality_pass=args.require_context_helper_quality_pass,
    )
    _print_quality(quality)
    if args.write_json:
        quality_path = args.quality_path or (args.candidates_path.parent / DEFAULT_QUALITY_FILE)
        write_quality_result(quality, quality_path)
        print(f" quality_path: {quality_path}")
    return 0 if quality.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())


# Backwards-compatible alias used by the Step 4 unit tests and README.
write_embedding_outputs = write_embedding_candidate_outputs
