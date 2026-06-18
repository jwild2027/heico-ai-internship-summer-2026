"""TRACE-Net Source-Resolved Answer Context Pack v1.

Step 10 converts ask/hybrid retrieval output into a guarded answer-context
artifact. It is the bridge between retrieval and future answer composition, but
it deliberately does not compose an answer.

Safety contract:

* page retrieval profiles are route-only;
* context retrieval helpers are route-only;
* source evidence records are source-existence/location-only;
* source text / verified part records may become answer-support records only
  after citation/source/authority checks;
* no record in this pack can answer directly, prove claims directly, or mutate
  source truth.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tiff.trace_net_route_dispatch_contract_loader_v1 import load_route_dispatch_processor_contract

SCHEMA_VERSION = "trace_net_answer_context_pack_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/answer_context_pack")
DEFAULT_ASK_REPORT = Path("local_data/organization/trace_net/ask_hybrid_flag/trace_net_ask_hybrid_flag_v1.json")
DEFAULT_EMBEDDING_CANDIDATES = Path(
    "local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json"
)
DEFAULT_PAGE_PROFILES = Path(
    "local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json"
)
DEFAULT_HYBRID_REPORT_CANDIDATES = [
    Path("local_data/organization/trace_net/ask_hybrid_flag/hybrid_runtime/trace_net_hybrid_retrieval_sim_v1.json"),
    Path("local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json"),
]
DEFAULT_REPORT_FILE = "trace_net_answer_context_pack_v1.json"
DEFAULT_GROUPS_FILE = "trace_net_answer_context_pack_v1_groups.jsonl"
DEFAULT_RECORDS_FILE = "trace_net_answer_context_pack_v1_records.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_answer_context_pack_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_answer_context_pack_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_answer_context_pack_v1_quality.json"
DEFAULT_MD_FILE = "trace_net_answer_context_pack_v1.md"
DEFAULT_HTML_FILE = "trace_net_answer_context_pack_v1.html"

PAGE_PROFILE_BUCKET = "page_retrieval_profile"
CONTEXT_HELPER_BUCKET = "context_retrieval_helper"
SOURCE_EVIDENCE_BUCKET = "source_evidence"
DERIVED_CONTEXT_BUCKET = "derived_context"
ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
RETRIEVAL_ONLY_BUCKETS = {
    PAGE_PROFILE_BUCKET,
    CONTEXT_HELPER_BUCKET,
    SOURCE_EVIDENCE_BUCKET,
    DERIVED_CONTEXT_BUCKET,
}
SAFE_BUCKETS = RETRIEVAL_ONLY_BUCKETS | ANSWER_SUPPORT_BUCKETS
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
FORBIDDEN_USE = [
    "direct_answer_from_vector_hit",
    "claim_proof_from_retrieval_only_record",
    "source_truth_mutation",
    "trust_tier_override",
    "citation_replacement",
    "answer_without_source_resolution",
    "answer_from_context_v2_summary_only",
    "answer_from_page_profile_only",
]

DEFAULT_MAX_PAGE_ANSWER_SUPPORT_RECORDS = 3
ANSWER_SUPPORT_EXPANSION_SOURCE = "same_page_answer_support_expansion"


class AnswerContextPackError(RuntimeError):
    """Raised when an answer context pack cannot be built safely."""


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


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = as_text(value).lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return default


def as_int(value: Any, *, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def normalize_bucket(value: Any) -> str:
    return as_text(value).strip().lower().replace("-", "_").replace(" ", "_")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(v) for v in value]
    return str(value)


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(json_safe(payload), handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(json_safe(row), sort_keys=True, ensure_ascii=False))
            handle.write("\n")


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_text(value: Any, *, max_chars: int = 1200) -> str:
    text = " ".join(as_text(value).replace("\x00", " ").split())
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def stable_id(prefix: str, *parts: Any, length: int = 20) -> str:
    text = "|".join(as_text(part) for part in parts)
    return f"{prefix}__{hashlib.sha256(text.encode('utf-8')).hexdigest()[:length]}"


def load_records_artifact(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = read_json(Path(path))
    if isinstance(payload, Mapping):
        raw = payload.get("records") or payload.get("profiles") or payload.get("candidates") or []
    else:
        raw = payload
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise AnswerContextPackError(f"artifact does not contain a records list: {path}")
    records = [dict(item) for item in raw if isinstance(item, Mapping)]
    meta = dict(payload) if isinstance(payload, Mapping) else {"record_count": len(records)}
    return records, meta


def build_resolution_indexes(
    candidate_records: Sequence[Mapping[str, Any]],
    page_profile_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidates_by_embedding_id: dict[str, dict[str, Any]] = {}
    candidates_by_source_id: dict[str, dict[str, Any]] = {}
    candidates_by_page_id: dict[str, list[dict[str, Any]]] = {}
    profiles_by_profile_id: dict[str, dict[str, Any]] = {}
    profiles_by_page_id: dict[str, dict[str, Any]] = {}
    for raw in candidate_records:
        record = dict(raw)
        embedding_id = as_text(record.get("embedding_candidate_id"))
        source_id = as_text(record.get("source_candidate_id"))
        page_id = as_text(record.get("page_id"))
        if embedding_id:
            candidates_by_embedding_id[embedding_id] = record
        if source_id:
            candidates_by_source_id[source_id] = record
        if page_id:
            candidates_by_page_id.setdefault(page_id, []).append(record)
    for raw in page_profile_records:
        record = dict(raw)
        profile_id = as_text(record.get("profile_id"))
        page_id = as_text(record.get("page_id"))
        if profile_id:
            profiles_by_profile_id[profile_id] = record
        if page_id:
            profiles_by_page_id[page_id] = record
    return {
        "candidates_by_embedding_id": candidates_by_embedding_id,
        "candidates_by_source_id": candidates_by_source_id,
        "candidates_by_page_id": candidates_by_page_id,
        "profiles_by_profile_id": profiles_by_profile_id,
        "profiles_by_page_id": profiles_by_page_id,
        "candidate_count": len(candidate_records),
        "page_profile_count": len(page_profile_records),
    }


def load_ask_report(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise AnswerContextPackError(f"ask report is not a JSON object: {path}")
    return dict(payload)


def ask_quality_status(ask_report: Mapping[str, Any]) -> str:
    quality = ask_report.get("quality") if isinstance(ask_report.get("quality"), Mapping) else {}
    return as_text(quality.get("status") or ask_report.get("quality_status") or (ask_report.get("summary") or {}).get("quality_status"))


def ask_summary(ask_report: Mapping[str, Any]) -> dict[str, Any]:
    return dict(ask_report.get("summary") or {}) if isinstance(ask_report.get("summary"), Mapping) else {}


def discover_hybrid_report_path(ask_report: Mapping[str, Any], explicit_path: Path | None = None) -> Path | None:
    if explicit_path:
        return explicit_path
    candidates: list[Path] = []
    for key in ["hybrid_report_path", "report_path"]:
        text = as_text(ask_report.get(key))
        if text:
            path = Path(text)
            lowered = str(path).lower()
            # Avoid accidentally treating the ask report itself as the hybrid report.
            # The actual Step 7 artifact name/path contains hybrid_retrieval_sim;
            # the Step 9 ask report path only contains ask_hybrid_flag.
            if "hybrid_retrieval_sim" in lowered:
                candidates.append(path)
    candidates.extend(DEFAULT_HYBRID_REPORT_CANDIDATES)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_hybrid_report(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise AnswerContextPackError(f"hybrid report is not a JSON object: {path}")
    return dict(payload)


def hybrid_quality_status(hybrid_report: Mapping[str, Any]) -> str:
    quality = hybrid_report.get("quality") if isinstance(hybrid_report.get("quality"), Mapping) else {}
    summary = hybrid_report.get("summary") if isinstance(hybrid_report.get("summary"), Mapping) else {}
    return as_text(quality.get("status") or hybrid_report.get("quality_status") or summary.get("hybrid_quality_status") or hybrid_report.get("status"))


def normalize_results_from_hybrid(hybrid_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = hybrid_report.get("query_results") or hybrid_report.get("results") or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def normalize_results_from_ask(ask_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = ask_report.get("top_groups") or []
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes, bytearray)):
        groups = []
    clean_groups = [dict(group) for group in groups if isinstance(group, Mapping)]
    query = as_text(ask_report.get("query"))
    return [
        {
            "query_id": "ask_inline_001",
            "query": query,
            "ranked_groups": clean_groups,
            "ranked_group_count": len(clean_groups),
        }
    ] if clean_groups else []


def choose_query_results(ask_report: Mapping[str, Any], hybrid_report: Mapping[str, Any], *, query: str = "") -> list[dict[str, Any]]:
    query_text = as_text(query or ask_report.get("query"))
    results = normalize_results_from_hybrid(hybrid_report) or normalize_results_from_ask(ask_report)
    if not query_text:
        return results
    lowered = query_text.lower()
    exact: list[dict[str, Any]] = []
    for result in results:
        result_query = as_text(result.get("query")).lower()
        if result_query and (result_query == lowered or lowered in result_query or result_query in lowered):
            exact.append(result)
    return exact or results[:1]


def record_bucket(record: Mapping[str, Any]) -> str:
    return normalize_bucket(
        record.get("rag_bucket")
        or record.get("embedding_bucket")
        or record.get("record_type")
        or record.get("candidate_type")
    )


def hit_collection_role(hit: Mapping[str, Any]) -> str:
    role = as_text(hit.get("collection_role"))
    if role:
        return role
    if as_text(hit.get("profile_id")) or record_bucket(hit) == PAGE_PROFILE_BUCKET:
        return "page_profile"
    return "candidate"


def resolve_candidate_record(hit: Mapping[str, Any], indexes: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    candidates_by_embedding_id = indexes.get("candidates_by_embedding_id") or {}
    candidates_by_source_id = indexes.get("candidates_by_source_id") or {}
    candidates_by_page_id = indexes.get("candidates_by_page_id") or {}
    embedding_id = as_text(hit.get("embedding_candidate_id"))
    source_id = as_text(hit.get("source_candidate_id"))
    page_id = as_text(hit.get("page_id"))
    if embedding_id and embedding_id in candidates_by_embedding_id:
        return dict(candidates_by_embedding_id[embedding_id]), []
    if source_id and source_id in candidates_by_source_id:
        return dict(candidates_by_source_id[source_id]), []
    # For compact ask groups, fall back to the first same-page candidate. This
    # keeps the pack useful, but marks the resolution as page-level fallback.
    if page_id and page_id in candidates_by_page_id and candidates_by_page_id[page_id]:
        return dict(candidates_by_page_id[page_id][0]), ["candidate_resolved_by_page_fallback"]
    return None, ["candidate_not_resolved_to_artifact"]


def resolve_page_profile_record(hit: Mapping[str, Any], indexes: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    profiles_by_profile_id = indexes.get("profiles_by_profile_id") or {}
    profiles_by_page_id = indexes.get("profiles_by_page_id") or {}
    profile_id = as_text(hit.get("profile_id"))
    page_id = as_text(hit.get("page_id"))
    if profile_id and profile_id in profiles_by_profile_id:
        return dict(profiles_by_profile_id[profile_id]), []
    if page_id and page_id in profiles_by_page_id:
        return dict(profiles_by_page_id[page_id]), []
    return None, ["page_profile_not_resolved_to_artifact"]


def source_trace_from(record: Mapping[str, Any], hit: Mapping[str, Any]) -> dict[str, Any]:
    trace = record.get("traceability") if isinstance(record.get("traceability"), Mapping) else {}
    return {
        "citation_id": as_text(record.get("citation_id") or hit.get("citation_id") or trace.get("citation_id")),
        "source_url": as_text(record.get("source_url") or hit.get("source_url") or trace.get("source_url")),
        "tiff_path": as_text(record.get("tiff_path") or hit.get("tiff_path") or trace.get("tiff_path")),
        "ocr_path": as_text(record.get("ocr_path") or hit.get("ocr_path") or trace.get("ocr_path")),
        "source_path": as_text(record.get("source_path") or hit.get("source_path") or trace.get("source_path")),
    }


def unsafe_record_reasons(record: Mapping[str, Any], *, context_pack_role: str) -> list[str]:
    bucket = record_bucket(record)
    reasons: list[str] = []
    if not as_text(record.get("page_id")):
        reasons.append("missing_page_id")
    if bucket not in SAFE_BUCKETS:
        reasons.append("bucket_not_allowed_in_context_pack")
    if bucket in BANNED_BUCKETS:
        reasons.append("banned_bucket")
    if as_bool(record.get("can_answer_directly"), default=False):
        reasons.append("record_can_answer_directly")
    if as_bool(record.get("can_prove_claims"), default=False):
        reasons.append("record_can_prove_claims")
    if as_bool(record.get("canonical_source_truth"), default=False):
        reasons.append("record_marked_canonical_source_truth")
    if as_bool(record.get("can_mutate_source_truth"), default=False):
        reasons.append("record_can_mutate_source_truth")
    if as_bool(record.get("embedding_answer_authority_allowed"), default=False):
        reasons.append("embedding_answer_authority_allowed")
    if as_bool(record.get("requires_source_resolution"), default=False) is not True:
        reasons.append("requires_source_resolution_false")
    if as_bool(record.get("requires_citation"), default=False) is not True:
        reasons.append("requires_citation_false")
    if as_bool(record.get("requires_authority_gate"), default=False) is not True:
        reasons.append("requires_authority_gate_false")
    if context_pack_role == "retrieval_only" and bucket in ANSWER_SUPPORT_BUCKETS:
        reasons.append("answer_support_bucket_marked_retrieval_only")
    return reasons


def classify_context_record(record: Mapping[str, Any], hit: Mapping[str, Any]) -> dict[str, Any]:
    bucket = record_bucket(record)
    citation_id = as_text(record.get("citation_id") or hit.get("citation_id"))
    source_url = as_text(record.get("source_url") or hit.get("source_url"))
    has_trace = bool(citation_id or source_url or as_text(record.get("tiff_path") or hit.get("tiff_path")))
    answer_support_candidate = bucket in ANSWER_SUPPORT_BUCKETS
    answer_support_eligible = (
        answer_support_candidate
        and has_trace
        and as_bool(record.get("requires_source_resolution"), default=False) is True
        and as_bool(record.get("requires_citation"), default=False) is True
        and as_bool(record.get("requires_authority_gate"), default=False) is True
        and as_bool(record.get("can_answer_directly"), default=False) is False
        and as_bool(record.get("can_prove_claims"), default=False) is False
        and as_bool(record.get("can_mutate_source_truth"), default=False) is False
    )
    if answer_support_eligible:
        role = "answer_support_candidate"
        status = "eligible_for_future_answer_after_citation_authority_gate"
    elif answer_support_candidate:
        role = "blocked_answer_support_candidate"
        status = "blocked_until_source_citation_authority_requirements_pass"
    else:
        role = "retrieval_only"
        status = "route_or_context_only_not_answer_support"
    return {
        "context_pack_role": role,
        "answer_use_status": status,
        "answer_support_eligible": bool(answer_support_eligible),
        "retrieval_only": role == "retrieval_only",
        "can_route_retrieval": bucket in SAFE_BUCKETS,
        "can_be_supplied_to_future_answer_composer": bool(answer_support_eligible),
    }


def record_identity(record: Mapping[str, Any]) -> str:
    return "|".join(
        [
            as_text(record.get("embedding_candidate_id")),
            as_text(record.get("source_candidate_id")),
            as_text(record.get("profile_id")),
            as_text(record.get("page_id")),
            record_bucket(record),
        ]
    )


def record_has_source_trace(record: Mapping[str, Any]) -> bool:
    trace = record.get("traceability") if isinstance(record.get("traceability"), Mapping) else {}
    return bool(
        as_text(record.get("citation_id") or trace.get("citation_id"))
        or as_text(record.get("source_url") or trace.get("source_url"))
        or as_text(record.get("tiff_path") or trace.get("tiff_path"))
        or as_text(record.get("source_path") or trace.get("source_path"))
    )


def looks_like_safe_page_answer_support(record: Mapping[str, Any]) -> bool:
    bucket = record_bucket(record)
    if bucket not in ANSWER_SUPPORT_BUCKETS:
        return False
    if not as_text(record.get("page_id")):
        return False
    if not record_has_source_trace(record):
        return False
    if as_bool(record.get("can_answer_directly"), default=False):
        return False
    if as_bool(record.get("can_prove_claims"), default=False):
        return False
    if as_bool(record.get("canonical_source_truth"), default=False):
        return False
    if as_bool(record.get("can_mutate_source_truth"), default=False):
        return False
    if as_bool(record.get("embedding_answer_authority_allowed"), default=False):
        return False
    if as_bool(record.get("requires_source_resolution"), default=False) is not True:
        return False
    if as_bool(record.get("requires_citation"), default=False) is not True:
        return False
    if as_bool(record.get("requires_authority_gate"), default=False) is not True:
        return False
    return True


def build_expansion_hit_from_candidate(record: Mapping[str, Any], *, rank_offset: int) -> dict[str, Any]:
    return {
        "collection_role": "candidate",
        "rank": rank_offset,
        "score": 0.0,
        "page_id": as_text(record.get("page_id")),
        "page_number": record.get("page_number"),
        "document_id": as_text(record.get("document_id")),
        "ata_code": as_text(record.get("ata_code")),
        "rag_bucket": record_bucket(record),
        "embedding_candidate_id": as_text(record.get("embedding_candidate_id")),
        "source_candidate_id": as_text(record.get("source_candidate_id")),
        "citation_id": as_text(record.get("citation_id")),
        "source_url": as_text(record.get("source_url")),
        "tiff_path": as_text(record.get("tiff_path")),
        "ocr_path": as_text(record.get("ocr_path")),
        "source_path": as_text(record.get("source_path")),
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "unsafe_reasons": [],
        "context_pack_expansion_source": ANSWER_SUPPORT_EXPANSION_SOURCE,
    }


def select_same_page_answer_support_hits(
    *,
    group: Mapping[str, Any],
    indexes: Mapping[str, Any],
    existing_records: Sequence[Mapping[str, Any]],
    max_records: int = DEFAULT_MAX_PAGE_ANSWER_SUPPORT_RECORDS,
) -> list[dict[str, Any]]:
    if max_records <= 0:
        return []
    page_id = as_text(group.get("page_id"))
    if not page_id:
        return []
    candidates_by_page_id = indexes.get("candidates_by_page_id") or {}
    page_candidates = [dict(record) for record in candidates_by_page_id.get(page_id, []) if isinstance(record, Mapping)]
    existing = {record_identity(record) for record in existing_records}
    selected: list[dict[str, Any]] = []
    rank_offset = 10001
    # Prefer source_text_evidence before verified_part_evidence for broad manual queries.
    def sort_key(record: Mapping[str, Any]) -> tuple[int, str, str]:
        bucket = record_bucket(record)
        bucket_rank = 0 if bucket == "source_text_evidence" else 1
        return (bucket_rank, as_text(record.get("source_candidate_id")), as_text(record.get("embedding_candidate_id")))

    for record in sorted(page_candidates, key=sort_key):
        if not looks_like_safe_page_answer_support(record):
            continue
        identity = record_identity(record)
        if identity in existing:
            continue
        selected.append(build_expansion_hit_from_candidate(record, rank_offset=rank_offset))
        existing.add(identity)
        rank_offset += 1
        if len(selected) >= max_records:
            break
    return selected


def build_context_record(
    *,
    hit: Mapping[str, Any],
    group: Mapping[str, Any],
    query_id: str,
    query: str,
    indexes: Mapping[str, Any],
) -> dict[str, Any]:
    role = hit_collection_role(hit)
    if role == "page_profile":
        resolved, resolution_reasons = resolve_page_profile_record(hit, indexes)
        resolution_kind = "page_profile_artifact" if resolved else "unresolved_page_profile"
    else:
        resolved, resolution_reasons = resolve_candidate_record(hit, indexes)
        resolution_kind = "embedding_candidate_artifact" if resolved else "unresolved_candidate"
    source = dict(resolved or hit)
    # Preserve hit fields when the resolved artifact lacks them.
    merged = {**dict(hit), **source}
    bucket = record_bucket(merged)
    trace = source_trace_from(merged, hit)
    classification = classify_context_record({**merged, **trace}, hit)
    unsafe_reasons = list(hit.get("unsafe_reasons") or [])
    unsafe_reasons.extend(resolution_reasons if resolved is None else [])
    unsafe_reasons.extend(unsafe_record_reasons({**merged, **trace}, context_pack_role=classification["context_pack_role"]))
    # Source text/verified part evidence without citation/source is not unsafe
    # globally, but it cannot be used as answer support in this pack.
    if bucket in ANSWER_SUPPORT_BUCKETS and not (trace["citation_id"] or trace["source_url"]):
        unsafe_reasons.append("answer_support_missing_citation_or_source")
    unsafe_reasons = sorted(set(as_text(reason) for reason in unsafe_reasons if as_text(reason)))
    text_preview = compact_text(
        merged.get("text_preview")
        or merged.get("embedding_text")
        or merged.get("summary")
        or merged.get("text")
        or merged.get("payload_preview")
        or "",
        max_chars=900,
    )
    record_id = stable_id(
        "ctxpack_rec",
        query_id,
        group.get("page_id"),
        role,
        merged.get("embedding_candidate_id"),
        merged.get("source_candidate_id"),
        merged.get("profile_id"),
        hit.get("rank"),
        hit.get("score"),
    )
    return {
        "context_record_id": record_id,
        "schema_version": SCHEMA_VERSION,
        "query_id": as_text(query_id),
        "query": as_text(query),
        "group_rank": as_int(group.get("rank")),
        "group_page_id": as_text(group.get("page_id")),
        "collection_role": role,
        "source_record_kind": "page_profile" if role == "page_profile" else "embedding_candidate",
        "resolution_kind": resolution_kind,
        "resolved_to_artifact": bool(resolved is not None),
        "resolution_reasons": resolution_reasons,
        "context_pack_expansion_source": as_text(hit.get("context_pack_expansion_source")),
        "rank": as_int(hit.get("rank")),
        "score": as_float(hit.get("score")),
        "page_id": as_text(merged.get("page_id") or group.get("page_id")),
        "page_number": merged.get("page_number") or group.get("page_number"),
        "document_id": as_text(merged.get("document_id") or group.get("document_id")),
        "ata_code": as_text(merged.get("ata_code") or group.get("ata_code")),
        "rag_bucket": bucket,
        "authority": as_text(merged.get("authority")),
        "trust_tier": as_text(merged.get("trust_tier") or merged.get("final_trust_tier")),
        "embedding_candidate_id": as_text(merged.get("embedding_candidate_id")),
        "source_candidate_id": as_text(merged.get("source_candidate_id")),
        "profile_id": as_text(merged.get("profile_id")),
        "citation_id": trace["citation_id"],
        "source_url": trace["source_url"],
        "tiff_path": trace["tiff_path"],
        "ocr_path": trace["ocr_path"],
        "source_path": trace["source_path"],
        "text_preview": text_preview,
        "retrieval_cues": list(merged.get("retrieval_cues") or [])[:12] if isinstance(merged.get("retrieval_cues"), Sequence) and not isinstance(merged.get("retrieval_cues"), (str, bytes, bytearray)) else [],
        "query_tunnel_terms": list(merged.get("query_tunnel_terms") or [])[:12] if isinstance(merged.get("query_tunnel_terms"), Sequence) and not isinstance(merged.get("query_tunnel_terms"), (str, bytes, bytearray)) else [],
        "known_parts": list(merged.get("known_parts") or [])[:12] if isinstance(merged.get("known_parts"), Sequence) and not isinstance(merged.get("known_parts"), (str, bytes, bytearray)) else [],
        "known_nomenclature": list(merged.get("known_nomenclature") or [])[:12] if isinstance(merged.get("known_nomenclature"), Sequence) and not isinstance(merged.get("known_nomenclature"), (str, bytes, bytearray)) else [],
        "context_v2_present": as_bool(merged.get("context_v2_present"), default=False),
        "source_trace_present": as_bool(merged.get("source_trace_present"), default=bool(trace["citation_id"] or trace["source_url"] or trace["tiff_path"])),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "canonical_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_answer_authority_allowed": False,
        "answer_composition_allowed": False,
        "llm_context_allowed": bool(classification["answer_support_eligible"]),
        "forbidden_use": list(FORBIDDEN_USE),
        "unsafe_reasons": unsafe_reasons,
        "safety_status": "context_record_safe" if not unsafe_reasons else "blocked_or_needs_review",
        **classification,
    }


def build_group_context(
    *,
    query_result: Mapping[str, Any],
    group: Mapping[str, Any],
    indexes: Mapping[str, Any],
    max_page_answer_support_records: int = DEFAULT_MAX_PAGE_ANSWER_SUPPORT_RECORDS,
) -> dict[str, Any]:
    query_id = as_text(query_result.get("query_id"))
    query = as_text(query_result.get("query"))
    page_hits = [dict(hit) for hit in group.get("page_profile_hits") or group.get("page_profile_hit_preview") or [] if isinstance(hit, Mapping)]
    candidate_hits = [dict(hit) for hit in group.get("candidate_hits") or group.get("candidate_hit_preview") or [] if isinstance(hit, Mapping)]
    base_hits = page_hits + candidate_hits
    records = [
        build_context_record(hit=hit, group=group, query_id=query_id, query=query, indexes=indexes)
        for hit in base_hits
    ]
    expansion_hits = select_same_page_answer_support_hits(
        group=group,
        indexes=indexes,
        existing_records=records,
        max_records=max_page_answer_support_records,
    )
    if expansion_hits:
        records.extend(
            build_context_record(hit=hit, group=group, query_id=query_id, query=query, indexes=indexes)
            for hit in expansion_hits
        )
    answer_support = [record for record in records if record.get("context_pack_role") == "answer_support_candidate"]
    retrieval_only = [record for record in records if record.get("context_pack_role") == "retrieval_only"]
    blocked = [record for record in records if record.get("context_pack_role") == "blocked_answer_support_candidate" or record.get("unsafe_reasons")]
    citation_ids = sorted({as_text(record.get("citation_id")) for record in answer_support if as_text(record.get("citation_id"))})
    source_urls = sorted({as_text(record.get("source_url")) for record in records if as_text(record.get("source_url"))})
    unsafe_reasons = sorted({reason for record in records for reason in record.get("unsafe_reasons") or []})
    return {
        "context_group_id": stable_id("ctxpack_group", query_id, group.get("rank"), group.get("page_id")),
        "schema_version": SCHEMA_VERSION,
        "query_id": query_id,
        "query": query,
        "rank": as_int(group.get("rank")),
        "page_id": as_text(group.get("page_id")),
        "page_number": group.get("page_number"),
        "document_id": as_text(group.get("document_id")),
        "ata_code": as_text(group.get("ata_code")),
        "hybrid_score": as_float(group.get("hybrid_score")),
        "hybrid_safety_status": as_text(group.get("safety_status")),
        "context_pack_safety_status": "context_pack_safe" if not unsafe_reasons else "blocked_or_needs_review",
        "answer_status": "CONTEXT_PACK_ONLY",
        "answer_composition_allowed": False,
        "llm_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "record_count": len(records),
        "answer_support_record_count": len(answer_support),
        "retrieval_only_record_count": len(retrieval_only),
        "blocked_record_count": len(blocked),
        "answer_support_expansion_record_count": sum(1 for record in records if record.get("context_pack_expansion_source") == ANSWER_SUPPORT_EXPANSION_SOURCE),
        "page_profile_record_count": sum(1 for record in records if record.get("rag_bucket") == PAGE_PROFILE_BUCKET),
        "context_helper_record_count": sum(1 for record in records if record.get("rag_bucket") == CONTEXT_HELPER_BUCKET),
        "source_evidence_record_count": sum(1 for record in records if record.get("rag_bucket") == SOURCE_EVIDENCE_BUCKET),
        "citation_ids": citation_ids,
        "source_urls": source_urls,
        "unsafe_reasons": unsafe_reasons,
        "retrieval_only_records": retrieval_only,
        "answer_support_records": answer_support,
        "blocked_records": blocked,
        "all_records": records,
        "forbidden_use": list(FORBIDDEN_USE),
    }


def summarize_context_pack(
    groups: Sequence[Mapping[str, Any]],
    *,
    ask_report: Mapping[str, Any],
    hybrid_report: Mapping[str, Any],
    candidate_artifact_count: int,
    page_profile_artifact_count: int,
    embedding_candidates_quality_status: str = "",
    page_profiles_quality_status: str = "",
) -> dict[str, Any]:
    records = [record for group in groups for record in group.get("all_records") or [] if isinstance(record, Mapping)]
    retrieval_only = [record for record in records if record.get("context_pack_role") == "retrieval_only"]
    answer_support = [record for record in records if record.get("context_pack_role") == "answer_support_candidate"]
    blocked = [record for record in records if record.get("context_pack_role") == "blocked_answer_support_candidate" or record.get("unsafe_reasons")]
    bucket_counts = Counter(as_text(record.get("rag_bucket")) for record in records)
    authority_counts = Counter(as_text(record.get("authority")) for record in records)
    ask_sum = ask_summary(ask_report)
    hybrid_summary = hybrid_report.get("summary") if isinstance(hybrid_report.get("summary"), Mapping) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "query": as_text(ask_report.get("query")),
        "retrieval_mode": as_text(ask_sum.get("retrieval_mode")),
        "ask_quality_status": ask_quality_status(ask_report),
        "hybrid_quality_status": hybrid_quality_status(hybrid_report) or as_text(ask_sum.get("hybrid_quality_status")),
        "regression_quality_status": as_text(ask_sum.get("regression_quality_status")),
        "embedding_mode": as_text(ask_sum.get("embedding_mode") or hybrid_summary.get("embedding_mode")),
        "embedding_model_name": as_text(ask_sum.get("embedding_model_name") or hybrid_summary.get("embedding_model_name")),
        "embedding_dim": as_int(ask_sum.get("embedding_dim") or hybrid_summary.get("embedding_dim")),
        "candidate_artifact_count": int(candidate_artifact_count),
        "page_profile_artifact_count": int(page_profile_artifact_count),
        "embedding_candidates_quality_status": embedding_candidates_quality_status,
        "page_profiles_quality_status": page_profiles_quality_status,
        "context_pack_group_count": len(groups),
        "context_record_count": len(records),
        "safe_group_count": sum(1 for group in groups if not group.get("unsafe_reasons")),
        "unsafe_group_count": sum(1 for group in groups if group.get("unsafe_reasons")),
        "answer_support_record_count": len(answer_support),
        "retrieval_only_record_count": len(retrieval_only),
        "blocked_record_count": len(blocked),
        "answer_support_expansion_record_count": sum(1 for record in records if record.get("context_pack_expansion_source") == ANSWER_SUPPORT_EXPANSION_SOURCE),
        "page_profile_record_count": sum(1 for record in records if record.get("rag_bucket") == PAGE_PROFILE_BUCKET),
        "context_helper_record_count": sum(1 for record in records if record.get("rag_bucket") == CONTEXT_HELPER_BUCKET),
        "source_evidence_record_count": sum(1 for record in records if record.get("rag_bucket") == SOURCE_EVIDENCE_BUCKET),
        "source_text_evidence_record_count": sum(1 for record in records if record.get("rag_bucket") == "source_text_evidence"),
        "verified_part_evidence_record_count": sum(1 for record in records if record.get("rag_bucket") == "verified_part_evidence"),
        "records_resolved_to_artifact_count": sum(1 for record in records if as_bool(record.get("resolved_to_artifact"), default=False)),
        "records_not_resolved_to_artifact_count": sum(1 for record in records if not as_bool(record.get("resolved_to_artifact"), default=False)),
        "missing_page_id_count": sum(1 for record in records if not as_text(record.get("page_id"))) + sum(1 for group in groups if not as_text(group.get("page_id"))),
        "missing_source_candidate_id_count": sum(1 for record in records if record.get("source_record_kind") == "embedding_candidate" and not as_text(record.get("source_candidate_id"))),
        "missing_citation_required_count": sum(
            1
            for record in answer_support
            if as_bool(record.get("requires_citation"), default=False) and not (as_text(record.get("citation_id")) or as_text(record.get("source_url")))
        ),
        "retrieval_only_answer_allowed_count": sum(
            1
            for record in retrieval_only
            if as_bool(record.get("can_answer_directly"), default=False)
            or as_bool(record.get("can_prove_claims"), default=False)
            or as_bool(record.get("answer_support_eligible"), default=False)
        ),
        "page_profile_answer_allowed_count": sum(1 for record in records if record.get("rag_bucket") == PAGE_PROFILE_BUCKET and as_bool(record.get("answer_support_eligible"), default=False)),
        "context_helper_answer_allowed_count": sum(1 for record in records if record.get("rag_bucket") == CONTEXT_HELPER_BUCKET and as_bool(record.get("answer_support_eligible"), default=False)),
        "source_evidence_answer_allowed_count": sum(1 for record in records if record.get("rag_bucket") == SOURCE_EVIDENCE_BUCKET and as_bool(record.get("answer_support_eligible"), default=False)),
        "direct_answer_allowed_record_count": sum(1 for record in records if as_bool(record.get("can_answer_directly"), default=False)),
        "claim_proof_without_authority_count": sum(1 for record in records if as_bool(record.get("can_prove_claims"), default=False)),
        "source_truth_mutation_allowed_count": sum(1 for record in records if as_bool(record.get("can_mutate_source_truth"), default=False)),
        "answer_composition_allowed_count": sum(1 for group in groups if as_bool(group.get("answer_composition_allowed"), default=False))
        + sum(1 for record in records if as_bool(record.get("answer_composition_allowed"), default=False)),
        "llm_answer_allowed_count": sum(1 for group in groups if as_bool(group.get("llm_answer_allowed"), default=False)),
        "unsafe_record_count": sum(1 for record in records if record.get("unsafe_reasons")),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "top_page_id": as_text(groups[0].get("page_id")) if groups else "",
        "answer_status": "CONTEXT_PACK_ONLY",
        "answer_composition_allowed": False,
        "llm_answer_allowed": False,
        "source_truth_mutations_performed": 0,
    }


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, actual: Any, expected: Any) -> None:
    checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})


def evaluate_context_pack_quality(
    summary: Mapping[str, Any],
    *,
    min_context_groups: int = 1,
    min_context_records: int = 1,
    min_answer_support_records: int = 1,
    min_retrieval_only_records: int = 1,
    require_ask_quality_pass: bool = True,
    require_hybrid_quality_pass: bool = True,
    require_regression_quality_pass: bool = True,
    require_embedding_dim: int | None = 1024,
) -> QualityResult:
    checks: list[dict[str, Any]] = []
    add_check(checks, "min_context_groups", as_int(summary.get("context_pack_group_count")) >= min_context_groups, summary.get("context_pack_group_count"), f">={min_context_groups}")
    add_check(checks, "min_context_records", as_int(summary.get("context_record_count")) >= min_context_records, summary.get("context_record_count"), f">={min_context_records}")
    add_check(checks, "min_answer_support_records", as_int(summary.get("answer_support_record_count")) >= min_answer_support_records, summary.get("answer_support_record_count"), f">={min_answer_support_records}")
    add_check(checks, "min_retrieval_only_records", as_int(summary.get("retrieval_only_record_count")) >= min_retrieval_only_records, summary.get("retrieval_only_record_count"), f">={min_retrieval_only_records}")
    if require_ask_quality_pass:
        add_check(checks, "ask_quality_pass", as_text(summary.get("ask_quality_status")) == "PASS", summary.get("ask_quality_status"), "PASS")
    if require_hybrid_quality_pass:
        add_check(checks, "hybrid_quality_pass", as_text(summary.get("hybrid_quality_status")) == "PASS", summary.get("hybrid_quality_status"), "PASS")
    if require_regression_quality_pass:
        add_check(checks, "regression_quality_pass", as_text(summary.get("regression_quality_status")) == "PASS", summary.get("regression_quality_status"), "PASS")
    if require_embedding_dim:
        add_check(checks, "embedding_dim", as_int(summary.get("embedding_dim")) == int(require_embedding_dim), summary.get("embedding_dim"), int(require_embedding_dim))
    zero_fields = [
        "missing_page_id_count",
        "missing_source_candidate_id_count",
        "missing_citation_required_count",
        "retrieval_only_answer_allowed_count",
        "page_profile_answer_allowed_count",
        "context_helper_answer_allowed_count",
        "route_dispatch_processor_contract_available",
        "route_dispatch_processor_contract_quality_status",
        "normal_text_route_allowed_input_count",
        "normal_text_route_blocked_input_count",
        "normal_text_route_allowed_record_count",
        "normal_text_route_blocked_record_count",
        "source_evidence_answer_allowed_count",
        "direct_answer_allowed_record_count",
        "claim_proof_without_authority_count",
        "source_truth_mutation_allowed_count",
        "answer_composition_allowed_count",
        "llm_answer_allowed_count",
        "unsafe_group_count",
    ]
    for field in zero_fields:
        add_check(checks, field, as_int(summary.get(field)) == 0, summary.get(field), 0)
    # Unsafe records can be zero in normal operation. This is a hard gate for Step 10.
    add_check(checks, "unsafe_record_count", as_int(summary.get("unsafe_record_count")) == 0, summary.get("unsafe_record_count"), 0)
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Answer Context Pack v1",
        "",
        f"Status: **{report.get('status')}**",
        f"Quality status: **{report.get('quality_status')}**",
        f"Query: `{report.get('query')}`",
        f"Answer status: `{summary.get('answer_status')}`",
        "",
        "> This artifact is an answer context pack only. It is not a final answer, and no LLM answer has been composed.",
        "",
        "## Safety summary",
        "",
        f"- Context groups: `{summary.get('context_pack_group_count')}`",
        f"- Context records: `{summary.get('context_record_count')}`",
        f"- Answer-support records: `{summary.get('answer_support_record_count')}`",
        f"- Retrieval-only records: `{summary.get('retrieval_only_record_count')}`",
        f"- Unsafe records: `{summary.get('unsafe_record_count')}`",
        f"- Direct answer allowed records: `{summary.get('direct_answer_allowed_record_count')}`",
        f"- Claim proof without authority: `{summary.get('claim_proof_without_authority_count')}`",
        f"- Source-truth mutation allowed: `{summary.get('source_truth_mutation_allowed_count')}`",
        "",
        "## Top groups",
        "",
    ]
    for group in report.get("groups") or []:
        if not isinstance(group, Mapping):
            continue
        lines.extend(
            [
                f"### Rank {group.get('rank')} - `{group.get('page_id')}`",
                "",
                f"Hybrid score: `{group.get('hybrid_score')}`",
                f"Context safety: `{group.get('context_pack_safety_status')}`",
                f"Answer-support records: `{group.get('answer_support_record_count')}`",
                f"Retrieval-only records: `{group.get('retrieval_only_record_count')}`",
                f"Citations: `{', '.join(group.get('citation_ids') or [])}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_html(markdown: str) -> str:
    escaped = html.escape(markdown)
    return (
        "<!doctype html>\n<html><head><meta charset='utf-8'><title>TRACE-Net Answer Context Pack v1</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;line-height:1.45;}"
        "pre{white-space:pre-wrap;background:#f7f7f7;padding:16px;border-radius:8px;}</style></head>"
        f"<body><pre>{escaped}</pre></body></html>\n"
    )


def build_trace_net_answer_context_pack(
    *,
    ask_report_path: Path = DEFAULT_ASK_REPORT,
    hybrid_report_path: Path | None = None,
    embedding_candidates_path: Path = DEFAULT_EMBEDDING_CANDIDATES,
    page_profiles_path: Path = DEFAULT_PAGE_PROFILES,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    query: str = "",
    max_groups: int = 8,
    max_page_answer_support_records: int = DEFAULT_MAX_PAGE_ANSWER_SUPPORT_RECORDS,
    min_context_groups: int = 1,
    min_context_records: int = 1,
    min_answer_support_records: int = 1,
    min_retrieval_only_records: int = 1,
    require_ask_quality_pass: bool = True,
    require_hybrid_quality_pass: bool = True,
    require_regression_quality_pass: bool = True,
    require_embedding_dim: int | None = 1024,
    write_quality: bool = False,
    open_result: bool = False,
    route_dispatch_processor_contract: str | Path | None = None,
) -> dict[str, Any]:
    ask_report = load_ask_report(Path(ask_report_path))
    discovered_hybrid_path = discover_hybrid_report_path(ask_report, hybrid_report_path)
    hybrid_report = load_hybrid_report(discovered_hybrid_path)
    candidate_records, candidate_meta = load_records_artifact(Path(embedding_candidates_path))
    page_profile_records, page_profile_meta = load_records_artifact(Path(page_profiles_path))
    indexes = build_resolution_indexes(candidate_records, page_profile_records)
    route_dispatch_contract = None
    route_dispatch_contract_quality_status = None
    if route_dispatch_processor_contract:
        route_dispatch_payload = read_json(Path(route_dispatch_processor_contract))
        route_dispatch_contract_quality_status = route_dispatch_payload.get("quality_status") or (route_dispatch_payload.get("summary") or {}).get("quality_status")
        route_dispatch_contract = load_route_dispatch_processor_contract(route_dispatch_processor_contract)

    route_dispatch_contract_available = route_dispatch_contract is not None
    normal_text_route_allowed_input_count = 0
    normal_text_route_blocked_input_count = 0
    normal_text_route_allowed_record_count = 0
    normal_text_route_blocked_record_count = 0

    query_results = choose_query_results(ask_report, hybrid_report, query=query)
    groups: list[dict[str, Any]] = []
    for query_result in query_results:
        ranked = [dict(group) for group in query_result.get("ranked_groups") or [] if isinstance(group, Mapping)]
        for group in ranked[: int(max_groups)]:
            groups.append(
                build_group_context(
                    query_result=query_result,
                    group=group,
                    indexes=indexes,
                    max_page_answer_support_records=max_page_answer_support_records,
                )
            )
        if groups:
            break
    if route_dispatch_contract_available:
        filtered_groups: list[dict[str, Any]] = []
        for group in groups:
            page_id = as_text(group.get("page_id"))
            all_records = [record for record in group.get("all_records") or [] if isinstance(record, Mapping)]
            if page_id and route_dispatch_contract.is_normal_text_allowed(page_id):
                normal_text_route_allowed_input_count += 1
                normal_text_route_allowed_record_count += len(all_records)
                group["route_dispatch_processor_contract_available"] = True
                group["normal_text_route_dispatch_allowed"] = True
                group["route_dispatch_review_required"] = bool(route_dispatch_contract.is_review_required(page_id))
                for record in all_records:
                    record["route_dispatch_processor_contract_available"] = True
                    record["normal_text_route_dispatch_allowed"] = True
                    record["route_dispatch_review_required"] = bool(route_dispatch_contract.is_review_required(record.get("page_id") or page_id))
                filtered_groups.append(group)
            else:
                normal_text_route_blocked_input_count += 1
                normal_text_route_blocked_record_count += len(all_records)
        groups = filtered_groups

    summary = summarize_context_pack(
        groups,
        ask_report=ask_report,
        hybrid_report=hybrid_report,
        candidate_artifact_count=len(candidate_records),
        page_profile_artifact_count=len(page_profile_records),
        embedding_candidates_quality_status=as_text((candidate_meta.get("quality") or {}).get("status") if isinstance(candidate_meta.get("quality"), Mapping) else candidate_meta.get("quality_status")),
        page_profiles_quality_status=as_text((page_profile_meta.get("quality") or {}).get("status") if isinstance(page_profile_meta.get("quality"), Mapping) else page_profile_meta.get("quality_status")),
    )
    summary["route_dispatch_processor_contract_available"] = bool(route_dispatch_processor_contract)
    summary["route_dispatch_processor_contract_path"] = str(route_dispatch_processor_contract) if route_dispatch_processor_contract else None
    summary["route_dispatch_processor_contract_quality_status"] = route_dispatch_contract_quality_status
    summary["normal_text_route_allowed_input_count"] = normal_text_route_allowed_input_count
    summary["normal_text_route_blocked_input_count"] = normal_text_route_blocked_input_count
    summary["normal_text_route_allowed_record_count"] = normal_text_route_allowed_record_count
    summary["normal_text_route_blocked_record_count"] = normal_text_route_blocked_record_count
    quality = evaluate_context_pack_quality(
        summary,
        min_context_groups=min_context_groups,
        min_context_records=min_context_records,
        min_answer_support_records=min_answer_support_records,
        min_retrieval_only_records=min_retrieval_only_records,
        require_ask_quality_pass=require_ask_quality_pass,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_regression_quality_pass=require_regression_quality_pass,
        require_embedding_dim=require_embedding_dim,
    )
    records = [record for group in groups for record in group.get("all_records") or [] if isinstance(record, Mapping)]
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "CONTEXT_PACK_BUILT",
        "quality_status": quality.status,
        "created_at_utc": utc_now_iso(),
        "query": as_text(query or ask_report.get("query")),
        "answer_status": "CONTEXT_PACK_ONLY",
        "answer_composition_allowed": False,
        "llm_answer_allowed": False,
        "ask_report_path": str(ask_report_path),
        "hybrid_report_path": str(discovered_hybrid_path) if discovered_hybrid_path else "",
        "embedding_candidates_path": str(embedding_candidates_path),
        "page_profiles_path": str(page_profiles_path),
        "route_dispatch_processor_contract_path": str(route_dispatch_processor_contract or ""),
        "summary": summary,
        "groups": groups,
        "records": records,
        "quality": {"status": quality.status, "checks": quality.checks, "summary": quality.summary},
        "forbidden_use": list(FORBIDDEN_USE),
        "warnings": [
            "This is an answer context pack only, not a final answer.",
            "Retrieval-only records are separated from answer-support records.",
            "Future answer composition must still enforce citation and trust authority gates.",
        ],
    }
    output_dir = Path(output_dir)
    report_path = output_dir / DEFAULT_REPORT_FILE
    groups_path = output_dir / DEFAULT_GROUPS_FILE
    records_path = output_dir / DEFAULT_RECORDS_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    md_path = output_dir / DEFAULT_MD_FILE
    html_path = output_dir / DEFAULT_HTML_FILE
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": report["status"],
        "quality_status": quality.status,
        "created_at_utc": utc_now_iso(),
        "query": report["query"],
        "report_path": str(report_path),
        "groups_jsonl_path": str(groups_path),
        "records_jsonl_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "report_sha256": sha256_json(report),
        "summary_sha256": sha256_json(summary),
    }
    write_json(report_path, report)
    write_jsonl(groups_path, groups)
    write_jsonl(records_path, records)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    markdown = render_markdown(report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8", newline="\n")
    html_path.write_text(render_html(markdown), encoding="utf-8", newline="\n")
    if write_quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality.status, "checks": quality.checks, "summary": quality.summary})
    report.update(
        {
            "report_path": str(report_path),
            "groups_jsonl_path": str(groups_path),
            "records_jsonl_path": str(records_path),
            "summary_path": str(summary_path),
            "manifest_path": str(manifest_path),
            "quality_path": str(quality_path),
            "markdown_path": str(md_path),
            "html_path": str(html_path),
        }
    )
    if open_result:
        try:
            import webbrowser

            webbrowser.open(html_path.resolve().as_uri())
        except Exception as exc:  # pragma: no cover
            report.setdefault("warnings", []).append(f"Could not open HTML report: {exc}")
            write_json(report_path, report)
    return report


def check_trace_net_answer_context_pack_quality(
    *,
    report_path: Path,
    min_context_groups: int = 1,
    min_context_records: int = 1,
    min_answer_support_records: int = 1,
    min_retrieval_only_records: int = 1,
    require_ask_quality_pass: bool = True,
    require_hybrid_quality_pass: bool = True,
    require_regression_quality_pass: bool = True,
    require_embedding_dim: int | None = 1024,
    write_json_report: bool = False,
) -> dict[str, Any]:
    payload = read_json(Path(report_path))
    if not isinstance(payload, Mapping):
        raise AnswerContextPackError(f"context pack report is not a JSON object: {report_path}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else payload
    quality = evaluate_context_pack_quality(
        summary,
        min_context_groups=min_context_groups,
        min_context_records=min_context_records,
        min_answer_support_records=min_answer_support_records,
        min_retrieval_only_records=min_retrieval_only_records,
        require_ask_quality_pass=require_ask_quality_pass,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_regression_quality_pass=require_regression_quality_pass,
        require_embedding_dim=require_embedding_dim,
    )
    output = {"schema_version": SCHEMA_VERSION, "status": quality.status, "checks": quality.checks, "summary": quality.summary}
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


def optional_positive_int(value: str) -> int | None:
    if value is None or str(value).strip().lower() in {"", "none", "null", "0"}:
        return None
    return positive_int(value)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net answer context pack v1")
    parser.add_argument("--ask-report", type=Path, default=DEFAULT_ASK_REPORT)
    parser.add_argument("--hybrid-report", type=Path, default=None)
    parser.add_argument("--embedding-candidates", type=Path, default=DEFAULT_EMBEDDING_CANDIDATES)
    parser.add_argument("--page-profiles", type=Path, default=DEFAULT_PAGE_PROFILES)
    parser.add_argument("--route-dispatch-processor-contract", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--query", default="")
    parser.add_argument("--max-groups", type=positive_int, default=8)
    parser.add_argument("--max-page-answer-support-records", type=int, default=DEFAULT_MAX_PAGE_ANSWER_SUPPORT_RECORDS)
    parser.add_argument("--min-context-groups", type=int, default=1)
    parser.add_argument("--min-context-records", type=int, default=1)
    parser.add_argument("--min-answer-support-records", type=int, default=1)
    parser.add_argument("--min-retrieval-only-records", type=int, default=1)
    parser.add_argument("--require-ask-quality-pass", action="store_true")
    parser.add_argument("--no-require-ask-quality-pass", dest="require_ask_quality_pass", action="store_false")
    parser.set_defaults(require_ask_quality_pass=True)
    parser.add_argument("--require-hybrid-quality-pass", action="store_true")
    parser.add_argument("--no-require-hybrid-quality-pass", dest="require_hybrid_quality_pass", action="store_false")
    parser.set_defaults(require_hybrid_quality_pass=True)
    parser.add_argument("--require-regression-quality-pass", action="store_true")
    parser.add_argument("--no-require-regression-quality-pass", dest="require_regression_quality_pass", action="store_false")
    parser.set_defaults(require_regression_quality_pass=True)
    parser.add_argument("--require-embedding-dim", type=optional_positive_int, default=1024)
    parser.add_argument("--quality", action="store_true", help="write quality JSON while building")
    parser.add_argument("--open", action="store_true", dest="open_result")
    return parser


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net answer context pack v1 quality")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REPORT_FILE)
    parser.add_argument("--min-context-groups", type=int, default=1)
    parser.add_argument("--min-context-records", type=int, default=1)
    parser.add_argument("--min-answer-support-records", type=int, default=1)
    parser.add_argument("--min-retrieval-only-records", type=int, default=1)
    parser.add_argument("--require-ask-quality-pass", action="store_true")
    parser.add_argument("--no-require-ask-quality-pass", dest="require_ask_quality_pass", action="store_false")
    parser.set_defaults(require_ask_quality_pass=True)
    parser.add_argument("--require-hybrid-quality-pass", action="store_true")
    parser.add_argument("--no-require-hybrid-quality-pass", dest="require_hybrid_quality_pass", action="store_false")
    parser.set_defaults(require_hybrid_quality_pass=True)
    parser.add_argument("--require-regression-quality-pass", action="store_true")
    parser.add_argument("--no-require-regression-quality-pass", dest="require_regression_quality_pass", action="store_false")
    parser.set_defaults(require_regression_quality_pass=True)
    parser.add_argument("--require-embedding-dim", type=optional_positive_int, default=1024)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        report = build_trace_net_answer_context_pack(
            ask_report_path=args.ask_report,
            hybrid_report_path=args.hybrid_report,
            embedding_candidates_path=args.embedding_candidates,
            page_profiles_path=args.page_profiles,
        route_dispatch_processor_contract=args.route_dispatch_processor_contract,
            output_dir=args.output_dir,
            query=args.query,
            max_groups=args.max_groups,
            max_page_answer_support_records=args.max_page_answer_support_records,
            min_context_groups=args.min_context_groups,
            min_context_records=args.min_context_records,
            min_answer_support_records=args.min_answer_support_records,
            min_retrieval_only_records=args.min_retrieval_only_records,
            require_ask_quality_pass=args.require_ask_quality_pass,
            require_hybrid_quality_pass=args.require_hybrid_quality_pass,
            require_regression_quality_pass=args.require_regression_quality_pass,
            require_embedding_dim=args.require_embedding_dim,
            write_quality=args.quality,
            open_result=args.open_result,
        )
    except Exception as exc:
        print(f"TRACE-Net answer context pack failed: {exc}", file=sys.stderr)
        return 1
    summary = report.get("summary") or {}
    print("TRACE-Net answer context pack v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "query",
        "retrieval_mode",
        "ask_quality_status",
        "hybrid_quality_status",
        "regression_quality_status",
        "embedding_mode",
        "embedding_model_name",
        "embedding_dim",
        "context_pack_group_count",
        "context_record_count",
        "answer_support_record_count",
        "answer_support_expansion_record_count",
        "retrieval_only_record_count",
        "blocked_record_count",
        "unsafe_record_count",
        "missing_citation_required_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        value = report.get(key) if key == "query" else summary.get(key)
        print(f" {key}: {value}")
    print(f" report_path: {report.get('report_path')}")
    print(f" records_path: {report.get('records_jsonl_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    return 0 if report.get("quality_status") == "PASS" else 1


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = build_quality_arg_parser()
    args = parser.parse_args(argv)
    try:
        output = check_trace_net_answer_context_pack_quality(
            report_path=args.report_path,
            min_context_groups=args.min_context_groups,
            min_context_records=args.min_context_records,
            min_answer_support_records=args.min_answer_support_records,
            min_retrieval_only_records=args.min_retrieval_only_records,
            require_ask_quality_pass=args.require_ask_quality_pass,
            require_hybrid_quality_pass=args.require_hybrid_quality_pass,
            require_regression_quality_pass=args.require_regression_quality_pass,
            require_embedding_dim=args.require_embedding_dim,
            write_json_report=args.write_json,
        )
    except Exception as exc:
        print(f"TRACE-Net answer context pack quality check failed: {exc}", file=sys.stderr)
        return 1
    summary = output.get("summary") or {}
    print("TRACE-Net answer context pack v1 quality")
    print(f" Status: {output.get('status')}")
    for key in [
        "context_pack_group_count",
        "context_record_count",
        "answer_support_record_count",
        "answer_support_expansion_record_count",
        "retrieval_only_record_count",
        "blocked_record_count",
        "unsafe_record_count",
        "missing_citation_required_count",
        "retrieval_only_answer_allowed_count",
        "page_profile_answer_allowed_count",
        "context_helper_answer_allowed_count",
        "source_evidence_answer_allowed_count",
        "direct_answer_allowed_record_count",
        "claim_proof_without_authority_count",
        "source_truth_mutation_allowed_count",
        "answer_composition_allowed_count",
        "embedding_dim",
    ]:
        print(f" {key}: {summary.get(key)}")
    if output.get("quality_path"):
        print(f" quality_path: {output.get('quality_path')}")
    return 0 if output.get("status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
