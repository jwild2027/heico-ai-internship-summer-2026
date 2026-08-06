"""TRACE-Net Citation/Authority Answer Composer Dry Run v1.

Step 11 consumes the Step 10 source-resolved answer context pack and builds a
citation-backed draft artifact. It deliberately does not create a final answer.

Safety contract:

* only Step 10 answer_support_records may become draft claims;
* page_retrieval_profile, context_retrieval_helper, source_evidence, and
  derived_context records are never used as proof;
* every draft claim must have a page_id, citation_id, authority, source
  resolution, citation requirement, and authority-gate requirement;
* no claim may be marked final-answer-ready, direct-answer-capable, claim-proof
  capable, or source-truth-mutating;
* the artifact is for review / dry run only.
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

SCHEMA_VERSION = "trace_net_citation_answer_draft_v1"
DEFAULT_CONTEXT_PACK = Path("local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/citation_answer_draft")
DEFAULT_REPORT_FILE = "trace_net_citation_answer_draft_v1.json"
DEFAULT_CLAIMS_FILE = "trace_net_citation_answer_draft_v1_claims.jsonl"
DEFAULT_BLOCKED_FILE = "trace_net_citation_answer_draft_v1_blocked_records.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_citation_answer_draft_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_citation_answer_draft_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_citation_answer_draft_v1_quality.json"
DEFAULT_MD_FILE = "trace_net_citation_answer_draft_v1.md"
DEFAULT_HTML_FILE = "trace_net_citation_answer_draft_v1.html"

ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
RETRIEVAL_ONLY_BUCKETS = {
    "page_retrieval_profile",
    "context_retrieval_helper",
    "source_evidence",
    "derived_context",
}
BANNED_PROOF_BUCKETS = RETRIEVAL_ONLY_BUCKETS | {
    "raw_ocr",
    "raw_ocr_unfiltered",
    "raw_visual_text",
    "raw_visual_extraction",
    "raw_table_extraction",
    "table_candidate",
    "table_candidates",
    "feedback_only",
    "prompt",
    "debug",
    "unsafe",
    "excluded",
}
FORBIDDEN_USE = [
    "final_answer_without_final_gate",
    "uncited_claim",
    "claim_from_page_profile",
    "claim_from_context_retrieval_helper",
    "claim_from_source_evidence_locator",
    "claim_from_derived_context",
    "claim_from_raw_ocr_or_raw_visual_extraction",
    "claim_without_source_resolution",
    "claim_without_authority_gate",
    "source_truth_mutation",
    "trust_tier_override",
    "citation_replacement",
    "llm_freeform_claim_generation",
]


class CitationAnswerDraftError(RuntimeError):
    """Raised when a citation answer draft cannot be built safely."""


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


def stable_id(prefix: str, *parts: Any, length: int = 20) -> str:
    text = "|".join(as_text(part) for part in parts)
    return f"{prefix}__{hashlib.sha256(text.encode('utf-8')).hexdigest()[:length]}"


def compact_text(value: Any, *, max_chars: int = 900) -> str:
    text = " ".join(as_text(value).replace("\x00", " ").split())
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def load_context_pack(path: Path) -> dict[str, Any]:
    payload = read_json(Path(path))
    if not isinstance(payload, Mapping):
        raise CitationAnswerDraftError(f"context pack is not a JSON object: {path}")
    return dict(payload)


def context_pack_quality_status(context_pack: Mapping[str, Any]) -> str:
    quality = context_pack.get("quality") if isinstance(context_pack.get("quality"), Mapping) else {}
    summary = context_pack.get("summary") if isinstance(context_pack.get("summary"), Mapping) else {}
    return as_text(quality.get("status") or context_pack.get("quality_status") or summary.get("quality_status"))


def context_pack_summary(context_pack: Mapping[str, Any]) -> dict[str, Any]:
    return dict(context_pack.get("summary") or {}) if isinstance(context_pack.get("summary"), Mapping) else {}


def record_bucket(record: Mapping[str, Any]) -> str:
    return normalize_bucket(record.get("rag_bucket") or record.get("bucket") or record.get("safety_bucket"))


def record_text_preview(record: Mapping[str, Any]) -> str:
    return compact_text(
        record.get("text_preview")
        or record.get("embedding_text")
        or record.get("summary")
        or record.get("text")
        or record.get("payload_preview")
        or "",
        max_chars=900,
    )


def page_label(page_id: str, page_number: Any = None) -> str:
    if page_number not in (None, ""):
        return f"page {page_number} ({page_id})"
    if page_id:
        tail = page_id.rsplit("p", 1)[-1]
        if tail.isdigit():
            return f"page {int(tail)} ({page_id})"
        return page_id
    return "an unresolved page"


def support_record_block_reasons(record: Mapping[str, Any]) -> list[str]:
    bucket = record_bucket(record)
    reasons: list[str] = []
    if bucket not in ANSWER_SUPPORT_BUCKETS:
        reasons.append("record_bucket_not_answer_support")
    if bucket in BANNED_PROOF_BUCKETS:
        reasons.append("banned_bucket_for_claim_proof")
    if as_text(record.get("context_pack_role")) and as_text(record.get("context_pack_role")) != "answer_support_candidate":
        reasons.append("context_pack_role_not_answer_support_candidate")
    if not as_text(record.get("page_id")):
        reasons.append("missing_page_id")
    if not as_text(record.get("citation_id")):
        reasons.append("missing_citation_id")
    if not as_text(record.get("authority")):
        reasons.append("missing_authority")
    if as_bool(record.get("requires_source_resolution"), default=False) is not True:
        reasons.append("requires_source_resolution_false")
    if as_bool(record.get("requires_citation"), default=False) is not True:
        reasons.append("requires_citation_false")
    if as_bool(record.get("requires_authority_gate"), default=False) is not True:
        reasons.append("requires_authority_gate_false")
    if as_bool(record.get("can_answer_directly"), default=False):
        reasons.append("record_can_answer_directly")
    if as_bool(record.get("can_prove_claims"), default=False):
        reasons.append("record_can_prove_claims_directly")
    if as_bool(record.get("can_mutate_source_truth"), default=False):
        reasons.append("record_can_mutate_source_truth")
    if as_bool(record.get("canonical_source_truth"), default=False):
        reasons.append("record_marked_canonical_source_truth")
    if as_bool(record.get("embedding_answer_authority_allowed"), default=False):
        reasons.append("embedding_answer_authority_allowed")
    if as_bool(record.get("answer_composition_allowed"), default=False):
        reasons.append("source_record_answer_composition_allowed")
    if record.get("unsafe_reasons"):
        reasons.append("source_record_has_unsafe_reasons")
    return sorted(set(reasons))


def iter_context_records(context_pack: Mapping[str, Any], *, max_groups: int = 8) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    groups = [dict(group) for group in context_pack.get("groups") or [] if isinstance(group, Mapping)]
    for group in groups[: max(0, int(max_groups))]:
        for record in group.get("all_records") or []:
            if isinstance(record, Mapping):
                yield group, dict(record)
        # Some older/local reports may expose split records but not all_records.
        if not group.get("all_records"):
            for key in ("answer_support_records", "retrieval_only_records", "blocked_records"):
                for record in group.get(key) or []:
                    if isinstance(record, Mapping):
                        yield group, dict(record)


def claim_text_for_record(record: Mapping[str, Any]) -> str:
    bucket = record_bucket(record)
    page = page_label(as_text(record.get("page_id")), record.get("page_number"))
    if bucket == "source_text_evidence":
        return f"{page} has citation-backed source-text evidence relevant to the query."
    if bucket == "verified_part_evidence":
        return f"{page} has citation-backed verified part/page relationship evidence relevant to the query."
    return f"{page} has citation-backed answer-support evidence relevant to the query."


def build_claim_from_record(
    *,
    record: Mapping[str, Any],
    group: Mapping[str, Any],
    query: str,
    claim_rank: int,
) -> dict[str, Any]:
    bucket = record_bucket(record)
    page_id = as_text(record.get("page_id") or group.get("page_id"))
    citation_id = as_text(record.get("citation_id"))
    authority = as_text(record.get("authority"))
    claim_id = stable_id(
        "draft_claim",
        query,
        page_id,
        citation_id,
        bucket,
        record.get("source_candidate_id"),
        record.get("embedding_candidate_id"),
    )
    return {
        "claim_id": claim_id,
        "schema_version": SCHEMA_VERSION,
        "claim_rank": claim_rank,
        "claim_status": "CITATION_DRAFT_ONLY",
        "claim_allowed_for_draft": True,
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "claim_text": claim_text_for_record({**dict(record), "page_id": page_id}),
        "claim_type": "citation_backed_source_text_presence" if bucket == "source_text_evidence" else "citation_backed_verified_part_relationship_presence",
        "query": as_text(query),
        "page_id": page_id,
        "page_number": record.get("page_number") or group.get("page_number"),
        "document_id": as_text(record.get("document_id") or group.get("document_id")),
        "ata_code": as_text(record.get("ata_code") or group.get("ata_code")),
        "context_group_id": as_text(group.get("context_group_id")),
        "context_group_rank": as_int(group.get("rank")),
        "hybrid_score": as_float(group.get("hybrid_score")),
        "source_context_record_id": as_text(record.get("context_record_id")),
        "embedding_candidate_id": as_text(record.get("embedding_candidate_id")),
        "source_candidate_id": as_text(record.get("source_candidate_id")),
        "rag_bucket": bucket,
        "authority": authority,
        "trust_tier": as_text(record.get("trust_tier")),
        "citation_ids": [citation_id],
        "citation_id": citation_id,
        "source_url": as_text(record.get("source_url")),
        "tiff_path": as_text(record.get("tiff_path")),
        "ocr_path": as_text(record.get("ocr_path")),
        "source_path": as_text(record.get("source_path")),
        "evidence_preview": record_text_preview(record),
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "canonical_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "retrieval_only_source_used_as_claim": False,
        "source_truth_mutation_allowed": False,
        "use_policy": "citation_draft_only_requires_final_answer_gate",
        "forbidden_use": list(FORBIDDEN_USE),
    }


def build_blocked_record(
    *,
    record: Mapping[str, Any],
    group: Mapping[str, Any],
    query: str,
    block_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "blocked_record_id": stable_id(
            "blocked_claim_src",
            query,
            group.get("page_id"),
            record.get("context_record_id"),
            record.get("source_candidate_id"),
            record.get("citation_id"),
        ),
        "schema_version": SCHEMA_VERSION,
        "query": as_text(query),
        "page_id": as_text(record.get("page_id") or group.get("page_id")),
        "context_group_rank": as_int(group.get("rank")),
        "context_record_id": as_text(record.get("context_record_id")),
        "rag_bucket": record_bucket(record),
        "authority": as_text(record.get("authority")),
        "citation_id": as_text(record.get("citation_id")),
        "source_candidate_id": as_text(record.get("source_candidate_id")),
        "embedding_candidate_id": as_text(record.get("embedding_candidate_id")),
        "context_pack_role": as_text(record.get("context_pack_role")),
        "blocked_from_claim": True,
        "block_reasons": sorted(set(as_text(reason) for reason in block_reasons if as_text(reason))),
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
    }


def build_retrieval_only_note(*, record: Mapping[str, Any], group: Mapping[str, Any], query: str) -> dict[str, Any]:
    return {
        "note_id": stable_id("retrieval_only_note", query, group.get("page_id"), record.get("context_record_id")),
        "schema_version": SCHEMA_VERSION,
        "query": as_text(query),
        "page_id": as_text(record.get("page_id") or group.get("page_id")),
        "context_group_rank": as_int(group.get("rank")),
        "context_record_id": as_text(record.get("context_record_id")),
        "rag_bucket": record_bucket(record),
        "authority": as_text(record.get("authority")),
        "use_status": "retrieval_only_excluded_from_claims",
        "can_route_retrieval": True,
        "can_support_draft_claim": False,
        "final_answer_allowed": False,
        "reason": "Retrieval-only records may help route or contextualize search but cannot prove a draft claim.",
    }


def build_claims_from_context_pack(
    context_pack: Mapping[str, Any],
    *,
    max_groups: int = 8,
    max_claims: int = 12,
    max_claims_per_page: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    query = as_text(context_pack.get("query") or context_pack_summary(context_pack).get("query"))
    claims: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    retrieval_only_notes: list[dict[str, Any]] = []
    page_claim_counts: Counter[str] = Counter()
    seen_claim_sources: set[str] = set()

    for group, record in iter_context_records(context_pack, max_groups=max_groups):
        bucket = record_bucket(record)
        role = as_text(record.get("context_pack_role"))
        if bucket in RETRIEVAL_ONLY_BUCKETS or role == "retrieval_only":
            retrieval_only_notes.append(build_retrieval_only_note(record=record, group=group, query=query))
            continue
        reasons = support_record_block_reasons(record)
        if reasons:
            blocked.append(build_blocked_record(record=record, group=group, query=query, block_reasons=reasons))
            continue
        page_id = as_text(record.get("page_id") or group.get("page_id"))
        if max_claims_per_page > 0 and page_claim_counts[page_id] >= int(max_claims_per_page):
            blocked.append(
                build_blocked_record(
                    record=record,
                    group=group,
                    query=query,
                    block_reasons=["max_claims_per_page_reached"],
                )
            )
            continue
        source_key = "|".join(
            [
                as_text(record.get("context_record_id")),
                as_text(record.get("source_candidate_id")),
                as_text(record.get("embedding_candidate_id")),
                as_text(record.get("citation_id")),
            ]
        )
        if source_key in seen_claim_sources:
            continue
        claims.append(build_claim_from_record(record=record, group=group, query=query, claim_rank=len(claims) + 1))
        page_claim_counts[page_id] += 1
        seen_claim_sources.add(source_key)
        if len(claims) >= int(max_claims):
            break
    return claims, blocked, retrieval_only_notes


def summarize_draft(
    *,
    context_pack: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
    blocked_records: Sequence[Mapping[str, Any]],
    retrieval_only_notes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    context_summary = context_pack_summary(context_pack)
    bucket_counts = Counter(record_bucket(claim) for claim in claims)
    authority_counts = Counter(as_text(claim.get("authority")) for claim in claims)
    citation_ids = sorted({as_text(cid) for claim in claims for cid in claim.get("citation_ids") or [] if as_text(cid)})
    page_ids = sorted({as_text(claim.get("page_id")) for claim in claims if as_text(claim.get("page_id"))})
    uncited_claim_count = sum(1 for claim in claims if not claim.get("citation_ids") or not as_text((claim.get("citation_ids") or [""])[0]))
    retrieval_only_claim_count = sum(1 for claim in claims if record_bucket(claim) in RETRIEVAL_ONLY_BUCKETS or as_bool(claim.get("retrieval_only_source_used_as_claim"), default=False))
    page_profile_claim_count = sum(1 for claim in claims if record_bucket(claim) == "page_retrieval_profile")
    context_helper_claim_count = sum(1 for claim in claims if record_bucket(claim) == "context_retrieval_helper")
    source_evidence_claim_count = sum(1 for claim in claims if record_bucket(claim) == "source_evidence")
    claim_without_authority_count = sum(1 for claim in claims if not as_text(claim.get("authority")))
    claim_without_page_id_count = sum(1 for claim in claims if not as_text(claim.get("page_id")))
    claim_without_citation_count = uncited_claim_count
    direct_answer_allowed_claim_count = sum(1 for claim in claims if as_bool(claim.get("can_answer_directly"), default=False))
    claim_proof_direct_count = sum(1 for claim in claims if as_bool(claim.get("can_prove_claims"), default=False))
    source_truth_mutation_allowed_count = sum(1 for claim in claims if as_bool(claim.get("can_mutate_source_truth"), default=False) or as_bool(claim.get("source_truth_mutation_allowed"), default=False))
    final_answer_allowed_count = sum(1 for claim in claims if as_bool(claim.get("final_answer_allowed"), default=False))
    llm_freeform_answer_allowed_count = sum(1 for claim in claims if as_bool(claim.get("llm_freeform_answer_allowed"), default=False))
    missing_source_resolution_count = sum(1 for claim in claims if as_bool(claim.get("requires_source_resolution"), default=False) is not True)
    missing_authority_gate_count = sum(1 for claim in claims if as_bool(claim.get("requires_authority_gate"), default=False) is not True)
    missing_citation_requirement_count = sum(1 for claim in claims if as_bool(claim.get("requires_citation"), default=False) is not True)
    return {
        "schema_version": SCHEMA_VERSION,
        "query": as_text(context_pack.get("query") or context_summary.get("query")),
        "draft_status": "CITATION_DRAFT_ONLY",
        "answer_status": "CITATION_DRAFT_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "context_pack_quality_status": context_pack_quality_status(context_pack),
        "context_pack_answer_status": as_text(context_pack.get("answer_status") or context_summary.get("answer_status")),
        "context_pack_group_count": as_int(context_summary.get("context_pack_group_count"), default=len(context_pack.get("groups") or [])),
        "context_pack_record_count": as_int(context_summary.get("context_record_count")),
        "context_pack_answer_support_record_count": as_int(context_summary.get("answer_support_record_count")),
        "claim_count": len(claims),
        "cited_claim_count": len(claims) - uncited_claim_count,
        "uncited_claim_count": uncited_claim_count,
        "blocked_record_count": len(blocked_records),
        "retrieval_only_note_count": len(retrieval_only_notes),
        "retrieval_only_claim_count": retrieval_only_claim_count,
        "page_profile_claim_count": page_profile_claim_count,
        "context_helper_claim_count": context_helper_claim_count,
        "source_evidence_claim_count": source_evidence_claim_count,
        "claim_without_authority_count": claim_without_authority_count,
        "claim_without_page_id_count": claim_without_page_id_count,
        "claim_without_citation_count": claim_without_citation_count,
        "direct_answer_allowed_claim_count": direct_answer_allowed_claim_count,
        "claim_proof_direct_count": claim_proof_direct_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "final_answer_allowed_count": final_answer_allowed_count,
        "llm_freeform_answer_allowed_count": llm_freeform_answer_allowed_count,
        "missing_source_resolution_count": missing_source_resolution_count,
        "missing_authority_gate_count": missing_authority_gate_count,
        "missing_citation_requirement_count": missing_citation_requirement_count,
        "embedding_mode": as_text(context_summary.get("embedding_mode")),
        "embedding_model_name": as_text(context_summary.get("embedding_model_name")),
        "embedding_dim": as_int(context_summary.get("embedding_dim")),
        "citation_count": len(citation_ids),
        "page_count": len(page_ids),
        "citation_ids": citation_ids,
        "page_ids": page_ids,
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
    }


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, actual: Any, expected: Any) -> None:
    checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})


def evaluate_draft_quality(
    summary: Mapping[str, Any],
    *,
    min_claims: int = 1,
    require_context_pack_quality_pass: bool = True,
    require_context_pack_answer_status: str = "CONTEXT_PACK_ONLY",
    require_embedding_dim: int | None = 1024,
) -> QualityResult:
    checks: list[dict[str, Any]] = []
    add_check(checks, "answer_status", as_text(summary.get("answer_status")) == "CITATION_DRAFT_ONLY", summary.get("answer_status"), "CITATION_DRAFT_ONLY")
    add_check(checks, "final_answer_allowed_false", as_bool(summary.get("final_answer_allowed"), default=True) is False, summary.get("final_answer_allowed"), False)
    add_check(checks, "llm_freeform_answer_allowed_false", as_bool(summary.get("llm_freeform_answer_allowed"), default=True) is False, summary.get("llm_freeform_answer_allowed"), False)
    add_check(checks, "min_claims", as_int(summary.get("claim_count")) >= min_claims, summary.get("claim_count"), f">={min_claims}")
    add_check(checks, "all_claims_cited", as_int(summary.get("uncited_claim_count")) == 0, summary.get("uncited_claim_count"), 0)
    add_check(checks, "cited_claim_count_equals_claim_count", as_int(summary.get("cited_claim_count")) == as_int(summary.get("claim_count")), summary.get("cited_claim_count"), summary.get("claim_count"))
    if require_context_pack_quality_pass:
        add_check(checks, "context_pack_quality_pass", as_text(summary.get("context_pack_quality_status")) == "PASS", summary.get("context_pack_quality_status"), "PASS")
    if require_context_pack_answer_status:
        add_check(checks, "context_pack_answer_status", as_text(summary.get("context_pack_answer_status")) == require_context_pack_answer_status, summary.get("context_pack_answer_status"), require_context_pack_answer_status)
    if require_embedding_dim:
        add_check(checks, "embedding_dim", as_int(summary.get("embedding_dim")) == int(require_embedding_dim), summary.get("embedding_dim"), int(require_embedding_dim))
    zero_fields = [
        "retrieval_only_claim_count",
        "page_profile_claim_count",
        "context_helper_claim_count",
        "source_evidence_claim_count",
        "claim_without_authority_count",
        "claim_without_page_id_count",
        "claim_without_citation_count",
        "direct_answer_allowed_claim_count",
        "claim_proof_direct_count",
        "source_truth_mutation_allowed_count",
        "final_answer_allowed_count",
        "llm_freeform_answer_allowed_count",
        "missing_source_resolution_count",
        "missing_authority_gate_count",
        "missing_citation_requirement_count",
    ]
    for field in zero_fields:
        add_check(checks, field, as_int(summary.get(field)) == 0, summary.get(field), 0)
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def draft_markdown_body(report: Mapping[str, Any]) -> str:
    lines = [
        f"TRACE-Net citation draft for query: {report.get('query')}",
        "",
        "This is a dry-run citation draft only. It is not a final answer.",
        "",
    ]
    claims = [claim for claim in report.get("claims") or [] if isinstance(claim, Mapping)]
    if not claims:
        lines.append("No citation-backed draft claims were produced.")
    for claim in claims:
        citations = ", ".join(claim.get("citation_ids") or [])
        lines.append(f"- {claim.get('claim_text')} [{citations}]")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Citation/Authority Answer Draft v1",
        "",
        f"Status: **{report.get('status')}**",
        f"Quality status: **{report.get('quality_status')}**",
        f"Answer status: `{report.get('answer_status')}`",
        f"Final answer allowed: `{report.get('final_answer_allowed')}`",
        "",
        "> This artifact is a dry-run citation draft only. It is not a final answer and does not permit free-form LLM claims.",
        "",
        "## Draft text",
        "",
        "```text",
        as_text(report.get("draft_text")),
        "```",
        "",
        "## Safety summary",
        "",
        f"- Claims: `{summary.get('claim_count')}`",
        f"- Cited claims: `{summary.get('cited_claim_count')}`",
        f"- Uncited claims: `{summary.get('uncited_claim_count')}`",
        f"- Retrieval-only claims: `{summary.get('retrieval_only_claim_count')}`",
        f"- Claim without authority: `{summary.get('claim_without_authority_count')}`",
        f"- Source-truth mutation allowed: `{summary.get('source_truth_mutation_allowed_count')}`",
        "",
        "## Claims",
        "",
    ]
    for claim in report.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        lines.extend(
            [
                f"### Claim {claim.get('claim_rank')} - `{claim.get('page_id')}`",
                "",
                as_text(claim.get("claim_text")),
                "",
                f"Citation: `{claim.get('citation_id')}`",
                f"Authority: `{claim.get('authority')}`",
                f"Bucket: `{claim.get('rag_bucket')}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_html(markdown: str) -> str:
    escaped = html.escape(markdown)
    return (
        "<!doctype html>\n<html><head><meta charset='utf-8'><title>TRACE-Net Citation Draft v1</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;line-height:1.45;}"
        "pre{white-space:pre-wrap;background:#f7f7f7;padding:16px;border-radius:8px;}</style></head>"
        f"<body><pre>{escaped}</pre></body></html>\n"
    )


def build_trace_net_citation_answer_draft(
    *,
    context_pack_path: Path = DEFAULT_CONTEXT_PACK,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_groups: int = 8,
    max_claims: int = 12,
    max_claims_per_page: int = 3,
    min_claims: int = 1,
    require_context_pack_quality_pass: bool = True,
    require_context_pack_answer_status: str = "CONTEXT_PACK_ONLY",
    require_embedding_dim: int | None = 1024,
    write_quality: bool = False,
    open_result: bool = False,
) -> dict[str, Any]:
    context_pack = load_context_pack(Path(context_pack_path))
    claims, blocked_records, retrieval_only_notes = build_claims_from_context_pack(
        context_pack,
        max_groups=max_groups,
        max_claims=max_claims,
        max_claims_per_page=max_claims_per_page,
    )
    summary = summarize_draft(
        context_pack=context_pack,
        claims=claims,
        blocked_records=blocked_records,
        retrieval_only_notes=retrieval_only_notes,
    )
    quality = evaluate_draft_quality(
        summary,
        min_claims=min_claims,
        require_context_pack_quality_pass=require_context_pack_quality_pass,
        require_context_pack_answer_status=require_context_pack_answer_status,
        require_embedding_dim=require_embedding_dim,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "CITATION_DRAFT_BUILT",
        "quality_status": quality.status,
        "created_at_utc": utc_now_iso(),
        "query": summary.get("query"),
        "answer_status": "CITATION_DRAFT_ONLY",
        "final_answer_allowed": False,
        "answer_composition_mode": "dry_run_citation_authority_only",
        "llm_freeform_answer_allowed": False,
        "context_pack_path": str(context_pack_path),
        "summary": summary,
        "draft_text": draft_markdown_body({"query": summary.get("query"), "claims": claims}),
        "claims": claims,
        "blocked_records": blocked_records,
        "retrieval_only_notes": retrieval_only_notes,
        "quality": {"status": quality.status, "checks": quality.checks, "summary": quality.summary},
        "forbidden_use": list(FORBIDDEN_USE),
        "warnings": [
            "This is a citation draft only, not a final answer.",
            "Only answer-support records from the context pack were converted into draft claims.",
            "Retrieval-only records remain excluded from proof.",
            "A future final-answer gate must still enforce citation/source/trust authority.",
        ],
    }
    output_dir = Path(output_dir)
    report_path = output_dir / DEFAULT_REPORT_FILE
    claims_path = output_dir / DEFAULT_CLAIMS_FILE
    blocked_path = output_dir / DEFAULT_BLOCKED_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    md_path = output_dir / DEFAULT_MD_FILE
    html_path = output_dir / DEFAULT_HTML_FILE
    markdown = render_markdown(report)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": report["created_at_utc"],
        "context_pack_path": str(context_pack_path),
        "report_path": str(report_path),
        "claims_path": str(claims_path),
        "blocked_path": str(blocked_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "report_sha256": sha256_json(report),
        "quality_status": quality.status,
        "claim_count": len(claims),
        "final_answer_allowed": False,
    }
    write_json(report_path, report)
    write_jsonl(claims_path, claims)
    write_jsonl(blocked_path, blocked_records)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8", newline="\n")
    html_path.write_text(render_html(markdown), encoding="utf-8", newline="\n")
    if write_quality:
        write_json(quality_path, {"status": quality.status, "checks": quality.checks, "summary": quality.summary})
    report.update(
        {
            "report_path": str(report_path),
            "claims_path": str(claims_path),
            "blocked_path": str(blocked_path),
            "summary_path": str(summary_path),
            "manifest_path": str(manifest_path),
            "quality_path": str(quality_path) if write_quality else "",
            "markdown_path": str(md_path),
            "html_path": str(html_path),
        }
    )
    if open_result:
        try:
            os.startfile(str(html_path))  # type: ignore[attr-defined]
        except Exception:
            pass
    return report


def check_trace_net_citation_answer_draft_quality(
    *,
    report_path: Path,
    min_claims: int = 1,
    require_context_pack_quality_pass: bool = True,
    require_context_pack_answer_status: str = "CONTEXT_PACK_ONLY",
    require_embedding_dim: int | None = 1024,
    write_json_result: bool = False,
) -> dict[str, Any]:
    report = read_json(Path(report_path))
    if not isinstance(report, Mapping):
        raise CitationAnswerDraftError(f"draft report is not a JSON object: {report_path}")
    summary = dict(report.get("summary") or {}) if isinstance(report.get("summary"), Mapping) else {}
    quality = evaluate_draft_quality(
        summary,
        min_claims=min_claims,
        require_context_pack_quality_pass=require_context_pack_quality_pass,
        require_context_pack_answer_status=require_context_pack_answer_status,
        require_embedding_dim=require_embedding_dim,
    )
    result = {"status": quality.status, "checks": quality.checks, "summary": quality.summary}
    if write_json_result:
        quality_path = Path(report_path).parent / DEFAULT_QUALITY_FILE
        write_json(quality_path, result)
        result["quality_path"] = str(quality_path)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Citation/Authority Answer Composer Dry Run v1")
    parser.add_argument("--context-pack", type=Path, default=DEFAULT_CONTEXT_PACK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-groups", type=int, default=8)
    parser.add_argument("--max-claims", type=int, default=12)
    parser.add_argument("--max-claims-per-page", type=int, default=3)
    parser.add_argument("--min-claims", type=int, default=1)
    parser.add_argument("--require-context-pack-quality-pass", action="store_true")
    parser.add_argument("--no-require-context-pack-quality-pass", dest="require_context_pack_quality_pass", action="store_false")
    parser.set_defaults(require_context_pack_quality_pass=True)
    parser.add_argument("--require-context-pack-answer-status", default="CONTEXT_PACK_ONLY")
    parser.add_argument("--require-embedding-dim", type=int, default=1024)
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--open", action="store_true")
    return parser


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Citation/Authority Answer Draft v1 quality")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REPORT_FILE)
    parser.add_argument("--min-claims", type=int, default=1)
    parser.add_argument("--require-context-pack-quality-pass", action="store_true")
    parser.add_argument("--no-require-context-pack-quality-pass", dest="require_context_pack_quality_pass", action="store_false")
    parser.set_defaults(require_context_pack_quality_pass=True)
    parser.add_argument("--require-context-pack-answer-status", default="CONTEXT_PACK_ONLY")
    parser.add_argument("--require-embedding-dim", type=int, default=1024)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = build_trace_net_citation_answer_draft(
            context_pack_path=args.context_pack,
            output_dir=args.output_dir,
            max_groups=args.max_groups,
            max_claims=args.max_claims,
            max_claims_per_page=args.max_claims_per_page,
            min_claims=args.min_claims,
            require_context_pack_quality_pass=args.require_context_pack_quality_pass,
            require_context_pack_answer_status=args.require_context_pack_answer_status,
            require_embedding_dim=args.require_embedding_dim,
            write_quality=args.quality,
            open_result=args.open,
        )
    except Exception as exc:
        print(f"TRACE-Net citation answer draft failed: {exc}", file=sys.stderr)
        return 1
    summary = report.get("summary") or {}
    print("TRACE-Net citation/authority answer draft v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    print(f" query: {report.get('query')}")
    print(f" answer_status: {report.get('answer_status')}")
    print(f" context_pack_quality_status: {summary.get('context_pack_quality_status')}")
    print(f" context_pack_answer_status: {summary.get('context_pack_answer_status')}")
    print(f" embedding_mode: {summary.get('embedding_mode')}")
    print(f" embedding_model_name: {summary.get('embedding_model_name')}")
    print(f" embedding_dim: {summary.get('embedding_dim')}")
    print(f" claim_count: {summary.get('claim_count')}")
    print(f" cited_claim_count: {summary.get('cited_claim_count')}")
    print(f" uncited_claim_count: {summary.get('uncited_claim_count')}")
    print(f" retrieval_only_claim_count: {summary.get('retrieval_only_claim_count')}")
    print(f" claim_without_authority_count: {summary.get('claim_without_authority_count')}")
    print(f" claim_without_citation_count: {summary.get('claim_without_citation_count')}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count')}")
    print(f" final_answer_allowed_count: {summary.get('final_answer_allowed_count')}")
    print(f" report_path: {report.get('report_path')}")
    print(f" claims_path: {report.get('claims_path')}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")
    return 0 if report.get("quality_status") == "PASS" else 2


def quality_main(argv: Sequence[str] | None = None) -> int:
    args = build_quality_arg_parser().parse_args(argv)
    try:
        result = check_trace_net_citation_answer_draft_quality(
            report_path=args.report_path,
            min_claims=args.min_claims,
            require_context_pack_quality_pass=args.require_context_pack_quality_pass,
            require_context_pack_answer_status=args.require_context_pack_answer_status,
            require_embedding_dim=args.require_embedding_dim,
            write_json_result=args.write_json,
        )
    except Exception as exc:
        print(f"TRACE-Net citation answer draft quality check failed: {exc}", file=sys.stderr)
        return 1
    summary = result.get("summary") or {}
    print("TRACE-Net citation/authority answer draft v1 quality")
    print(f" Status: {result.get('status')}")
    for key in [
        "claim_count",
        "cited_claim_count",
        "uncited_claim_count",
        "retrieval_only_claim_count",
        "page_profile_claim_count",
        "context_helper_claim_count",
        "source_evidence_claim_count",
        "claim_without_authority_count",
        "claim_without_page_id_count",
        "claim_without_citation_count",
        "direct_answer_allowed_claim_count",
        "claim_proof_direct_count",
        "source_truth_mutation_allowed_count",
        "final_answer_allowed_count",
        "llm_freeform_answer_allowed_count",
        "embedding_dim",
    ]:
        print(f" {key}: {summary.get(key)}")
    if result.get("quality_path"):
        print(f" quality_path: {result.get('quality_path')}")
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
