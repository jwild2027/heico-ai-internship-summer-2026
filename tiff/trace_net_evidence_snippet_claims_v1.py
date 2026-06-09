"""TRACE-Net Evidence Snippet / Claim Materializer v1.

Step 11.5 consumes the Step 10 answer context pack and the Step 11 citation
answer draft, then materializes snippet-backed claim records. It is deliberately
not a final answer gate.

Safety contract:

* only source_text_evidence and verified_part_evidence draft claims may become
  snippet claims;
* every snippet claim must resolve back to a Step 10 context-pack source record;
* every snippet claim must have page_id, citation, authority, source snippet,
  source resolution, citation requirement, and authority-gate requirement;
* page_retrieval_profile, context_retrieval_helper, source_evidence, and
  derived_context are retrieval-only and cannot become snippet claims;
* every snippet claim remains final-answer-blocked until a later final-answer
  gate explicitly authorizes it.
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

SCHEMA_VERSION = "trace_net_evidence_snippet_claims_v1"
DEFAULT_CITATION_DRAFT = Path(
    "local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1.json"
)
DEFAULT_CONTEXT_PACK = Path(
    "local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json"
)
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/evidence_snippet_claims")
DEFAULT_REPORT_FILE = "trace_net_evidence_snippet_claims_v1.json"
DEFAULT_CLAIMS_FILE = "trace_net_evidence_snippet_claims_v1_claims.jsonl"
DEFAULT_BLOCKED_FILE = "trace_net_evidence_snippet_claims_v1_blocked_records.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_evidence_snippet_claims_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_evidence_snippet_claims_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_evidence_snippet_claims_v1_quality.json"
DEFAULT_MD_FILE = "trace_net_evidence_snippet_claims_v1.md"
DEFAULT_HTML_FILE = "trace_net_evidence_snippet_claims_v1.html"

ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
RETRIEVAL_ONLY_BUCKETS = {
    "page_retrieval_profile",
    "context_retrieval_helper",
    "source_evidence",
    "derived_context",
}
BANNED_SNIPPET_BUCKETS = RETRIEVAL_ONLY_BUCKETS | {
    "raw_ocr",
    "raw_ocr_unfiltered",
    "raw_visual_text",
    "raw_visual_extraction",
    "raw_table_extraction",
    "table_candidate",
    "table_candidates",
    "table_tile",
    "table_tiles",
    "feedback_only",
    "prompt",
    "debug",
    "unsafe",
    "excluded",
}
FORBIDDEN_USE = [
    "final_answer_without_final_gate",
    "uncited_snippet_claim",
    "snippet_claim_from_page_profile",
    "snippet_claim_from_context_retrieval_helper",
    "snippet_claim_from_source_evidence_locator",
    "snippet_claim_from_derived_context",
    "snippet_claim_from_raw_ocr_or_raw_visual_extraction",
    "snippet_claim_without_context_pack_record",
    "snippet_claim_without_source_resolution",
    "snippet_claim_without_authority_gate",
    "source_truth_mutation",
    "trust_tier_override",
    "citation_replacement",
    "llm_freeform_claim_generation",
]


class EvidenceSnippetClaimsError(RuntimeError):
    """Raised when snippet claim materialization cannot complete safely."""


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


def sha256_text(text: str) -> str:
    return hashlib.sha256(as_text(text).encode("utf-8")).hexdigest()


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


def load_mapping_artifact(path: Path, *, name: str) -> dict[str, Any]:
    payload = read_json(Path(path))
    if not isinstance(payload, Mapping):
        raise EvidenceSnippetClaimsError(f"{name} is not a JSON object: {path}")
    return dict(payload)


def artifact_quality_status(payload: Mapping[str, Any]) -> str:
    quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return as_text(quality.get("status") or payload.get("quality_status") or summary.get("quality_status"))


def artifact_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(payload.get("summary") or {}) if isinstance(payload.get("summary"), Mapping) else {}


def record_bucket(record: Mapping[str, Any]) -> str:
    return normalize_bucket(record.get("rag_bucket") or record.get("bucket") or record.get("safety_bucket"))


def citation_ids_from(record: Mapping[str, Any]) -> list[str]:
    raw = record.get("citation_ids")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        ids = [as_text(item) for item in raw if as_text(item)]
    else:
        ids = []
    if as_text(record.get("citation_id")):
        ids.append(as_text(record.get("citation_id")))
    return sorted(set(ids))


def first_citation_id(record: Mapping[str, Any]) -> str:
    ids = citation_ids_from(record)
    return ids[0] if ids else ""


def page_label(page_id: str, page_number: Any = None) -> str:
    if page_number not in (None, ""):
        return f"page {page_number} ({page_id})"
    if page_id:
        tail = page_id.rsplit("p", 1)[-1]
        if tail.isdigit():
            return f"page {int(tail)} ({page_id})"
        return page_id
    return "an unresolved page"


def iter_context_records(context_pack: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    groups = context_pack.get("groups") or []
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes, bytearray)):
        return
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        records: list[Any] = []
        if isinstance(group.get("all_records"), Sequence) and not isinstance(group.get("all_records"), (str, bytes, bytearray)):
            records.extend(group.get("all_records") or [])
        else:
            for key in ("answer_support_records", "retrieval_only_records", "blocked_records"):
                if isinstance(group.get(key), Sequence) and not isinstance(group.get(key), (str, bytes, bytearray)):
                    records.extend(group.get(key) or [])
        for raw in records:
            if isinstance(raw, Mapping):
                merged = {"context_group_id": as_text(group.get("context_group_id")), "context_group_rank": group.get("rank"), **dict(raw)}
                yield merged


def build_context_indexes(context_pack: Mapping[str, Any]) -> dict[str, Any]:
    by_context_id: dict[str, dict[str, Any]] = {}
    by_citation_id: dict[str, dict[str, Any]] = {}
    by_source_candidate_id: dict[str, dict[str, Any]] = {}
    by_embedding_candidate_id: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for record in iter_context_records(context_pack):
        records.append(record)
        context_id = as_text(record.get("context_record_id"))
        if context_id:
            by_context_id[context_id] = record
        citation_id = as_text(record.get("citation_id"))
        if citation_id:
            by_citation_id[citation_id] = record
        source_candidate_id = as_text(record.get("source_candidate_id"))
        if source_candidate_id:
            by_source_candidate_id[source_candidate_id] = record
        embedding_candidate_id = as_text(record.get("embedding_candidate_id"))
        if embedding_candidate_id:
            by_embedding_candidate_id[embedding_candidate_id] = record
    return {
        "records": records,
        "by_context_id": by_context_id,
        "by_citation_id": by_citation_id,
        "by_source_candidate_id": by_source_candidate_id,
        "by_embedding_candidate_id": by_embedding_candidate_id,
        "record_count": len(records),
    }


def find_context_record_for_claim(claim: Mapping[str, Any], indexes: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    by_context_id = indexes.get("by_context_id") if isinstance(indexes.get("by_context_id"), Mapping) else {}
    by_citation_id = indexes.get("by_citation_id") if isinstance(indexes.get("by_citation_id"), Mapping) else {}
    by_source_candidate_id = indexes.get("by_source_candidate_id") if isinstance(indexes.get("by_source_candidate_id"), Mapping) else {}
    by_embedding_candidate_id = indexes.get("by_embedding_candidate_id") if isinstance(indexes.get("by_embedding_candidate_id"), Mapping) else {}

    context_id = as_text(claim.get("source_context_record_id") or claim.get("context_record_id"))
    if context_id and context_id in by_context_id:
        return dict(by_context_id[context_id]), []
    if context_id:
        reasons.append("context_record_id_not_found")

    citation_id = first_citation_id(claim)
    if citation_id and citation_id in by_citation_id:
        return dict(by_citation_id[citation_id]), []
    if citation_id:
        reasons.append("citation_id_not_found_in_context_pack")

    source_candidate_id = as_text(claim.get("source_candidate_id"))
    if source_candidate_id and source_candidate_id in by_source_candidate_id:
        return dict(by_source_candidate_id[source_candidate_id]), []
    if source_candidate_id:
        reasons.append("source_candidate_id_not_found_in_context_pack")

    embedding_candidate_id = as_text(claim.get("embedding_candidate_id"))
    if embedding_candidate_id and embedding_candidate_id in by_embedding_candidate_id:
        return dict(by_embedding_candidate_id[embedding_candidate_id]), []
    if embedding_candidate_id:
        reasons.append("embedding_candidate_id_not_found_in_context_pack")

    reasons.append("missing_context_pack_source_record")
    return None, sorted(set(reasons))


def source_snippet_for_claim(claim: Mapping[str, Any], context_record: Mapping[str, Any] | None, *, max_chars: int = 700) -> str:
    values: list[Any] = []
    if context_record:
        values.extend(
            [
                context_record.get("text_preview"),
                context_record.get("source_snippet"),
                context_record.get("evidence_preview"),
                context_record.get("embedding_text"),
                context_record.get("summary"),
                context_record.get("text"),
            ]
        )
    values.extend([claim.get("evidence_preview"), claim.get("source_snippet"), claim.get("claim_text")])
    for value in values:
        text = compact_text(value, max_chars=max_chars)
        if text:
            return text
    return ""


def snippet_block_reasons(
    *,
    draft_claim: Mapping[str, Any],
    context_record: Mapping[str, Any] | None,
    context_resolution_reasons: Sequence[str],
    source_snippet: str,
) -> list[str]:
    bucket = record_bucket(draft_claim)
    reasons: list[str] = []
    if bucket not in ANSWER_SUPPORT_BUCKETS:
        reasons.append("draft_claim_bucket_not_answer_support")
    if bucket in BANNED_SNIPPET_BUCKETS:
        reasons.append("banned_bucket_for_snippet_claim")
    if not context_record:
        reasons.extend(context_resolution_reasons or ["missing_context_pack_source_record"])
    else:
        context_bucket = record_bucket(context_record)
        if context_bucket != bucket:
            reasons.append("context_pack_bucket_mismatch")
        if as_text(context_record.get("context_pack_role")) != "answer_support_candidate":
            reasons.append("context_record_not_answer_support_candidate")
        if as_bool(context_record.get("resolved_to_artifact"), default=False) is not True:
            reasons.append("context_record_not_resolved_to_artifact")
    if not as_text(draft_claim.get("page_id")):
        reasons.append("missing_page_id")
    if not first_citation_id(draft_claim):
        reasons.append("missing_citation_id")
    if not as_text(draft_claim.get("authority")):
        reasons.append("missing_authority")
    if not as_text(source_snippet):
        reasons.append("missing_source_snippet")
    if as_bool(draft_claim.get("requires_source_resolution"), default=False) is not True:
        reasons.append("requires_source_resolution_false")
    if as_bool(draft_claim.get("requires_citation"), default=False) is not True:
        reasons.append("requires_citation_false")
    if as_bool(draft_claim.get("requires_authority_gate"), default=False) is not True:
        reasons.append("requires_authority_gate_false")
    if as_bool(draft_claim.get("final_answer_allowed"), default=False):
        reasons.append("draft_claim_final_answer_allowed")
    if as_bool(draft_claim.get("llm_freeform_answer_allowed"), default=False):
        reasons.append("draft_claim_llm_freeform_allowed")
    if as_bool(draft_claim.get("can_answer_directly"), default=False):
        reasons.append("draft_claim_can_answer_directly")
    if as_bool(draft_claim.get("can_prove_claims"), default=False):
        reasons.append("draft_claim_can_prove_claims_directly")
    if as_bool(draft_claim.get("can_mutate_source_truth"), default=False) or as_bool(draft_claim.get("source_truth_mutation_allowed"), default=False):
        reasons.append("draft_claim_can_mutate_source_truth")
    if as_bool(draft_claim.get("canonical_source_truth"), default=False):
        reasons.append("draft_claim_marked_canonical_source_truth")
    if as_bool(draft_claim.get("embedding_answer_authority_allowed"), default=False):
        reasons.append("embedding_answer_authority_allowed")
    return sorted(set(as_text(reason) for reason in reasons if as_text(reason)))


def materialized_claim_text(*, draft_claim: Mapping[str, Any], source_snippet: str) -> str:
    bucket = record_bucket(draft_claim)
    page = page_label(as_text(draft_claim.get("page_id")), draft_claim.get("page_number"))
    snippet = compact_text(source_snippet, max_chars=420)
    if bucket == "source_text_evidence":
        return f'{page} has cited source-text evidence excerpt: "{snippet}"'
    if bucket == "verified_part_evidence":
        return f'{page} has cited verified part/page evidence excerpt: "{snippet}"'
    return f'{page} has cited answer-support evidence excerpt: "{snippet}"'


def build_snippet_claim(
    *,
    draft_claim: Mapping[str, Any],
    context_record: Mapping[str, Any],
    source_snippet: str,
    snippet_rank: int,
) -> dict[str, Any]:
    bucket = record_bucket(draft_claim)
    citation_ids = citation_ids_from(draft_claim)
    citation_id = citation_ids[0] if citation_ids else ""
    context_record_id = as_text(context_record.get("context_record_id"))
    claim_id = stable_id(
        "snippet_claim",
        draft_claim.get("claim_id"),
        context_record_id,
        draft_claim.get("page_id"),
        citation_id,
        source_snippet,
    )
    return {
        "snippet_claim_id": claim_id,
        "schema_version": SCHEMA_VERSION,
        "snippet_claim_rank": snippet_rank,
        "snippet_claim_status": "SNIPPET_CLAIM_MATERIALIZED",
        "answer_status": "SNIPPET_CLAIMS_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "requires_final_answer_gate": True,
        "claim_type": "source_snippet_summary" if bucket == "source_text_evidence" else "verified_part_snippet_summary",
        "query": as_text(draft_claim.get("query")),
        "materialized_claim_text": materialized_claim_text(draft_claim=draft_claim, source_snippet=source_snippet),
        "draft_claim_text": as_text(draft_claim.get("claim_text")),
        "source_snippet": source_snippet,
        "source_snippet_sha256": sha256_text(source_snippet),
        "source_snippet_char_count": len(source_snippet),
        "page_id": as_text(draft_claim.get("page_id")),
        "page_number": draft_claim.get("page_number"),
        "document_id": as_text(draft_claim.get("document_id")),
        "ata_code": as_text(draft_claim.get("ata_code")),
        "rag_bucket": bucket,
        "authority": as_text(draft_claim.get("authority")),
        "trust_tier": as_text(draft_claim.get("trust_tier")),
        "citation_ids": citation_ids,
        "citation_id": citation_id,
        "source_url": as_text(draft_claim.get("source_url") or context_record.get("source_url")),
        "tiff_path": as_text(draft_claim.get("tiff_path") or context_record.get("tiff_path")),
        "ocr_path": as_text(draft_claim.get("ocr_path") or context_record.get("ocr_path")),
        "source_path": as_text(draft_claim.get("source_path") or context_record.get("source_path")),
        "draft_claim_id": as_text(draft_claim.get("claim_id")),
        "draft_claim_rank": as_int(draft_claim.get("claim_rank")),
        "source_context_record_id": as_text(draft_claim.get("source_context_record_id") or context_record.get("context_record_id")),
        "context_record_id": context_record_id,
        "context_group_id": as_text(draft_claim.get("context_group_id") or context_record.get("context_group_id")),
        "context_group_rank": as_int(draft_claim.get("context_group_rank") or context_record.get("context_group_rank")),
        "embedding_candidate_id": as_text(draft_claim.get("embedding_candidate_id") or context_record.get("embedding_candidate_id")),
        "source_candidate_id": as_text(draft_claim.get("source_candidate_id") or context_record.get("source_candidate_id")),
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "canonical_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "source_truth_mutation_allowed": False,
        "retrieval_only_source_used_as_claim": False,
        "context_pack_role": as_text(context_record.get("context_pack_role")),
        "context_pack_expansion_source": as_text(context_record.get("context_pack_expansion_source")),
        "materialization_policy": "snippet_claim_only_requires_final_answer_gate",
        "forbidden_use": list(FORBIDDEN_USE),
        "unsafe_reasons": [],
    }


def build_blocked_materialization(
    *,
    draft_claim: Mapping[str, Any],
    context_record: Mapping[str, Any] | None,
    source_snippet: str,
    block_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "blocked_materialization_id": stable_id(
            "blocked_snippet_src",
            draft_claim.get("claim_id"),
            draft_claim.get("page_id"),
            first_citation_id(draft_claim),
            draft_claim.get("source_context_record_id"),
        ),
        "schema_version": SCHEMA_VERSION,
        "blocked_from_snippet_claim": True,
        "block_reasons": sorted(set(as_text(reason) for reason in block_reasons if as_text(reason))),
        "draft_claim_id": as_text(draft_claim.get("claim_id")),
        "draft_claim_rank": as_int(draft_claim.get("claim_rank")),
        "draft_claim_text": as_text(draft_claim.get("claim_text")),
        "page_id": as_text(draft_claim.get("page_id")),
        "rag_bucket": record_bucket(draft_claim),
        "authority": as_text(draft_claim.get("authority")),
        "citation_id": first_citation_id(draft_claim),
        "source_context_record_id": as_text(draft_claim.get("source_context_record_id")),
        "resolved_context_record_id": as_text(context_record.get("context_record_id")) if context_record else "",
        "source_snippet_present": bool(as_text(source_snippet)),
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
    }


def build_snippet_claims_from_artifacts(
    *,
    citation_draft: Mapping[str, Any],
    context_pack: Mapping[str, Any],
    max_claims: int = 12,
    max_snippet_chars: int = 700,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexes = build_context_indexes(context_pack)
    raw_claims = citation_draft.get("claims") or []
    claims = [dict(item) for item in raw_claims if isinstance(item, Mapping)]
    snippet_claims: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for draft_claim in claims:
        context_record, resolution_reasons = find_context_record_for_claim(draft_claim, indexes)
        source_snippet = source_snippet_for_claim(draft_claim, context_record, max_chars=max_snippet_chars)
        reasons = snippet_block_reasons(
            draft_claim=draft_claim,
            context_record=context_record,
            context_resolution_reasons=resolution_reasons,
            source_snippet=source_snippet,
        )
        if reasons:
            blocked.append(
                build_blocked_materialization(
                    draft_claim=draft_claim,
                    context_record=context_record,
                    source_snippet=source_snippet,
                    block_reasons=reasons,
                )
            )
            continue
        assert context_record is not None  # for type checkers; enforced by reasons above
        source_key = "|".join(
            [
                as_text(draft_claim.get("claim_id")),
                as_text(context_record.get("context_record_id")),
                first_citation_id(draft_claim),
            ]
        )
        if source_key in seen_sources:
            continue
        snippet_claims.append(
            build_snippet_claim(
                draft_claim=draft_claim,
                context_record=context_record,
                source_snippet=source_snippet,
                snippet_rank=len(snippet_claims) + 1,
            )
        )
        seen_sources.add(source_key)
        if len(snippet_claims) >= int(max_claims):
            break
    return snippet_claims, blocked


def summarize_snippet_claims(
    *,
    citation_draft: Mapping[str, Any],
    context_pack: Mapping[str, Any],
    snippet_claims: Sequence[Mapping[str, Any]],
    blocked_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    draft_summary = artifact_summary(citation_draft)
    context_summary = artifact_summary(context_pack)
    bucket_counts = Counter(record_bucket(claim) for claim in snippet_claims)
    authority_counts = Counter(as_text(claim.get("authority")) for claim in snippet_claims)
    citation_ids = sorted({as_text(cid) for claim in snippet_claims for cid in claim.get("citation_ids") or [] if as_text(cid)})
    page_ids = sorted({as_text(claim.get("page_id")) for claim in snippet_claims if as_text(claim.get("page_id"))})
    uncited_count = sum(1 for claim in snippet_claims if not claim.get("citation_ids") or not as_text((claim.get("citation_ids") or [""])[0]))
    missing_page_id_count = sum(1 for claim in snippet_claims if not as_text(claim.get("page_id")))
    missing_citation_count = uncited_count
    missing_source_snippet_count = sum(1 for claim in snippet_claims if not as_text(claim.get("source_snippet")))
    retrieval_only_count = sum(1 for claim in snippet_claims if record_bucket(claim) in RETRIEVAL_ONLY_BUCKETS or as_bool(claim.get("retrieval_only_source_used_as_claim"), default=False))
    page_profile_count = sum(1 for claim in snippet_claims if record_bucket(claim) == "page_retrieval_profile")
    context_helper_count = sum(1 for claim in snippet_claims if record_bucket(claim) == "context_retrieval_helper")
    source_evidence_count = sum(1 for claim in snippet_claims if record_bucket(claim) == "source_evidence")
    derived_context_count = sum(1 for claim in snippet_claims if record_bucket(claim) == "derived_context")
    claim_without_authority_count = sum(1 for claim in snippet_claims if not as_text(claim.get("authority")))
    claim_without_context_record_count = sum(1 for claim in snippet_claims if not as_text(claim.get("context_record_id")))
    direct_answer_allowed_count = sum(1 for claim in snippet_claims if as_bool(claim.get("can_answer_directly"), default=False))
    claim_proof_direct_count = sum(1 for claim in snippet_claims if as_bool(claim.get("can_prove_claims"), default=False))
    source_truth_mutation_allowed_count = sum(1 for claim in snippet_claims if as_bool(claim.get("can_mutate_source_truth"), default=False) or as_bool(claim.get("source_truth_mutation_allowed"), default=False))
    final_answer_allowed_count = sum(1 for claim in snippet_claims if as_bool(claim.get("final_answer_allowed"), default=False))
    llm_freeform_answer_allowed_count = sum(1 for claim in snippet_claims if as_bool(claim.get("llm_freeform_answer_allowed"), default=False))
    missing_source_resolution_count = sum(1 for claim in snippet_claims if as_bool(claim.get("requires_source_resolution"), default=False) is not True)
    missing_authority_gate_count = sum(1 for claim in snippet_claims if as_bool(claim.get("requires_authority_gate"), default=False) is not True)
    missing_citation_requirement_count = sum(1 for claim in snippet_claims if as_bool(claim.get("requires_citation"), default=False) is not True)
    return {
        "schema_version": SCHEMA_VERSION,
        "query": as_text(citation_draft.get("query") or draft_summary.get("query") or context_summary.get("query")),
        "answer_status": "SNIPPET_CLAIMS_ONLY",
        "snippet_claim_status": "SNIPPET_CLAIMS_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "draft_quality_status": artifact_quality_status(citation_draft),
        "draft_answer_status": as_text(citation_draft.get("answer_status") or draft_summary.get("answer_status")),
        "context_pack_quality_status": artifact_quality_status(context_pack),
        "context_pack_answer_status": as_text(context_pack.get("answer_status") or context_summary.get("answer_status")),
        "context_pack_group_count": as_int(context_summary.get("context_pack_group_count")),
        "context_pack_record_count": as_int(context_summary.get("context_record_count")),
        "draft_claim_count": as_int(draft_summary.get("claim_count"), default=len(citation_draft.get("claims") or [])),
        "snippet_claim_count": len(snippet_claims),
        "cited_snippet_claim_count": len(snippet_claims) - uncited_count,
        "uncited_snippet_claim_count": uncited_count,
        "missing_page_id_count": missing_page_id_count,
        "missing_citation_count": missing_citation_count,
        "missing_source_snippet_count": missing_source_snippet_count,
        "source_snippet_present_count": len(snippet_claims) - missing_source_snippet_count,
        "retrieval_only_snippet_claim_count": retrieval_only_count,
        "page_profile_snippet_claim_count": page_profile_count,
        "context_helper_snippet_claim_count": context_helper_count,
        "source_evidence_snippet_claim_count": source_evidence_count,
        "derived_context_snippet_claim_count": derived_context_count,
        "claim_without_authority_count": claim_without_authority_count,
        "claim_without_context_record_count": claim_without_context_record_count,
        "direct_answer_allowed_claim_count": direct_answer_allowed_count,
        "claim_proof_direct_count": claim_proof_direct_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "final_answer_allowed_count": final_answer_allowed_count,
        "llm_freeform_answer_allowed_count": llm_freeform_answer_allowed_count,
        "missing_source_resolution_count": missing_source_resolution_count,
        "missing_authority_gate_count": missing_authority_gate_count,
        "missing_citation_requirement_count": missing_citation_requirement_count,
        "blocked_record_count": len(blocked_records),
        "embedding_mode": as_text(draft_summary.get("embedding_mode") or context_summary.get("embedding_mode")),
        "embedding_model_name": as_text(draft_summary.get("embedding_model_name") or context_summary.get("embedding_model_name")),
        "embedding_dim": as_int(draft_summary.get("embedding_dim") or context_summary.get("embedding_dim")),
        "page_count": len(page_ids),
        "page_ids": page_ids,
        "citation_count": len(citation_ids),
        "citation_ids": citation_ids,
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
    }


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, actual: Any, expected: Any) -> None:
    checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})


def evaluate_snippet_claims_quality(
    summary: Mapping[str, Any],
    *,
    min_snippet_claims: int = 1,
    require_draft_quality_pass: bool = True,
    require_context_pack_quality_pass: bool = True,
    require_draft_answer_status: str = "CITATION_DRAFT_ONLY",
    require_context_pack_answer_status: str = "CONTEXT_PACK_ONLY",
    require_embedding_dim: int | None = 1024,
) -> QualityResult:
    checks: list[dict[str, Any]] = []
    add_check(checks, "answer_status", as_text(summary.get("answer_status")) == "SNIPPET_CLAIMS_ONLY", summary.get("answer_status"), "SNIPPET_CLAIMS_ONLY")
    add_check(checks, "final_answer_allowed_false", as_bool(summary.get("final_answer_allowed"), default=True) is False, summary.get("final_answer_allowed"), False)
    add_check(checks, "llm_freeform_answer_allowed_false", as_bool(summary.get("llm_freeform_answer_allowed"), default=True) is False, summary.get("llm_freeform_answer_allowed"), False)
    add_check(checks, "min_snippet_claims", as_int(summary.get("snippet_claim_count")) >= min_snippet_claims, summary.get("snippet_claim_count"), f">={min_snippet_claims}")
    add_check(checks, "all_snippet_claims_cited", as_int(summary.get("uncited_snippet_claim_count")) == 0, summary.get("uncited_snippet_claim_count"), 0)
    add_check(checks, "all_snippet_claims_have_snippets", as_int(summary.get("missing_source_snippet_count")) == 0, summary.get("missing_source_snippet_count"), 0)
    add_check(checks, "cited_snippet_claim_count_equals_claim_count", as_int(summary.get("cited_snippet_claim_count")) == as_int(summary.get("snippet_claim_count")), summary.get("cited_snippet_claim_count"), summary.get("snippet_claim_count"))
    add_check(checks, "source_snippet_present_count_equals_claim_count", as_int(summary.get("source_snippet_present_count")) == as_int(summary.get("snippet_claim_count")), summary.get("source_snippet_present_count"), summary.get("snippet_claim_count"))
    if require_draft_quality_pass:
        add_check(checks, "draft_quality_pass", as_text(summary.get("draft_quality_status")) == "PASS", summary.get("draft_quality_status"), "PASS")
    if require_context_pack_quality_pass:
        add_check(checks, "context_pack_quality_pass", as_text(summary.get("context_pack_quality_status")) == "PASS", summary.get("context_pack_quality_status"), "PASS")
    if require_draft_answer_status:
        add_check(checks, "draft_answer_status", as_text(summary.get("draft_answer_status")) == require_draft_answer_status, summary.get("draft_answer_status"), require_draft_answer_status)
    if require_context_pack_answer_status:
        add_check(checks, "context_pack_answer_status", as_text(summary.get("context_pack_answer_status")) == require_context_pack_answer_status, summary.get("context_pack_answer_status"), require_context_pack_answer_status)
    if require_embedding_dim:
        add_check(checks, "embedding_dim", as_int(summary.get("embedding_dim")) == int(require_embedding_dim), summary.get("embedding_dim"), int(require_embedding_dim))
    zero_fields = [
        "missing_page_id_count",
        "missing_citation_count",
        "retrieval_only_snippet_claim_count",
        "page_profile_snippet_claim_count",
        "context_helper_snippet_claim_count",
        "source_evidence_snippet_claim_count",
        "derived_context_snippet_claim_count",
        "claim_without_authority_count",
        "claim_without_context_record_count",
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


def snippet_markdown_body(report: Mapping[str, Any]) -> str:
    lines = [
        f"TRACE-Net evidence snippet claims for query: {report.get('query')}",
        "",
        "This is a snippet-claim materialization artifact only. It is not a final answer.",
        "",
    ]
    for claim in report.get("snippet_claims") or []:
        if not isinstance(claim, Mapping):
            continue
        citations = ", ".join(claim.get("citation_ids") or [])
        lines.append(f"- {claim.get('materialized_claim_text')} [{citations}]")
    if not report.get("snippet_claims"):
        lines.append("No snippet claims were materialized.")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Evidence Snippet / Claim Materializer v1",
        "",
        f"Status: **{report.get('status')}**",
        f"Quality status: **{report.get('quality_status')}**",
        f"Answer status: `{report.get('answer_status')}`",
        f"Final answer allowed: `{report.get('final_answer_allowed')}`",
        "",
        "> This artifact materializes cited source snippets from Step 11 draft claims. It is not a final answer.",
        "",
        "## Snippet draft text",
        "",
        "```text",
        as_text(report.get("snippet_draft_text")),
        "```",
        "",
        "## Safety summary",
        "",
        f"- Snippet claims: `{summary.get('snippet_claim_count')}`",
        f"- Cited snippet claims: `{summary.get('cited_snippet_claim_count')}`",
        f"- Missing snippets: `{summary.get('missing_source_snippet_count')}`",
        f"- Retrieval-only snippet claims: `{summary.get('retrieval_only_snippet_claim_count')}`",
        f"- Source-truth mutation allowed: `{summary.get('source_truth_mutation_allowed_count')}`",
        "",
        "## Snippet claims",
        "",
    ]
    for claim in report.get("snippet_claims") or []:
        if not isinstance(claim, Mapping):
            continue
        lines.extend(
            [
                f"### Snippet Claim {claim.get('snippet_claim_rank')} - `{claim.get('page_id')}`",
                "",
                as_text(claim.get("materialized_claim_text")),
                "",
                f"Citation: `{claim.get('citation_id')}`",
                f"Authority: `{claim.get('authority')}`",
                f"Bucket: `{claim.get('rag_bucket')}`",
                f"Final answer allowed: `{claim.get('final_answer_allowed')}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_html(markdown: str) -> str:
    escaped = html.escape(markdown)
    return (
        "<!doctype html>\n<html><head><meta charset='utf-8'><title>TRACE-Net Snippet Claims v1</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;line-height:1.45;}"
        "pre{white-space:pre-wrap;background:#f7f7f7;padding:16px;border-radius:8px;}</style></head>"
        f"<body><pre>{escaped}</pre></body></html>\n"
    )


def build_trace_net_evidence_snippet_claims(
    *,
    citation_draft_path: Path = DEFAULT_CITATION_DRAFT,
    context_pack_path: Path = DEFAULT_CONTEXT_PACK,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_claims: int = 12,
    max_snippet_chars: int = 700,
    min_snippet_claims: int = 1,
    require_draft_quality_pass: bool = True,
    require_context_pack_quality_pass: bool = True,
    require_draft_answer_status: str = "CITATION_DRAFT_ONLY",
    require_context_pack_answer_status: str = "CONTEXT_PACK_ONLY",
    require_embedding_dim: int | None = 1024,
    write_quality: bool = False,
    open_result: bool = False,
) -> dict[str, Any]:
    citation_draft = load_mapping_artifact(Path(citation_draft_path), name="citation draft")
    context_pack = load_mapping_artifact(Path(context_pack_path), name="answer context pack")
    snippet_claims, blocked_records = build_snippet_claims_from_artifacts(
        citation_draft=citation_draft,
        context_pack=context_pack,
        max_claims=max_claims,
        max_snippet_chars=max_snippet_chars,
    )
    summary = summarize_snippet_claims(
        citation_draft=citation_draft,
        context_pack=context_pack,
        snippet_claims=snippet_claims,
        blocked_records=blocked_records,
    )
    quality = evaluate_snippet_claims_quality(
        summary,
        min_snippet_claims=min_snippet_claims,
        require_draft_quality_pass=require_draft_quality_pass,
        require_context_pack_quality_pass=require_context_pack_quality_pass,
        require_draft_answer_status=require_draft_answer_status,
        require_context_pack_answer_status=require_context_pack_answer_status,
        require_embedding_dim=require_embedding_dim,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "SNIPPET_CLAIMS_BUILT",
        "quality_status": quality.status,
        "created_at_utc": utc_now_iso(),
        "query": summary.get("query"),
        "answer_status": "SNIPPET_CLAIMS_ONLY",
        "final_answer_allowed": False,
        "answer_composition_mode": "snippet_claim_materialization_only",
        "llm_freeform_answer_allowed": False,
        "citation_draft_path": str(citation_draft_path),
        "context_pack_path": str(context_pack_path),
        "summary": summary,
        "snippet_draft_text": snippet_markdown_body({"query": summary.get("query"), "snippet_claims": snippet_claims}),
        "snippet_claims": snippet_claims,
        "blocked_records": blocked_records,
        "quality": {"status": quality.status, "checks": quality.checks, "summary": quality.summary},
        "forbidden_use": list(FORBIDDEN_USE),
        "warnings": [
            "This is an evidence-snippet materialization artifact only, not a final answer.",
            "Only source_text_evidence and verified_part_evidence draft claims may become snippet claims.",
            "Retrieval-only records remain excluded from proof.",
            "A future final-answer gate must still enforce citation/source/trust authority before user-visible answers.",
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
        "citation_draft_path": str(citation_draft_path),
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
        "snippet_claim_count": len(snippet_claims),
        "final_answer_allowed": False,
    }
    write_json(report_path, report)
    write_jsonl(claims_path, snippet_claims)
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


def check_trace_net_evidence_snippet_claims_quality(
    *,
    report_path: Path,
    min_snippet_claims: int = 1,
    require_draft_quality_pass: bool = True,
    require_context_pack_quality_pass: bool = True,
    require_draft_answer_status: str = "CITATION_DRAFT_ONLY",
    require_context_pack_answer_status: str = "CONTEXT_PACK_ONLY",
    require_embedding_dim: int | None = 1024,
    write_json_result: bool = False,
) -> dict[str, Any]:
    report = load_mapping_artifact(Path(report_path), name="snippet claims report")
    summary = dict(report.get("summary") or {}) if isinstance(report.get("summary"), Mapping) else {}
    quality = evaluate_snippet_claims_quality(
        summary,
        min_snippet_claims=min_snippet_claims,
        require_draft_quality_pass=require_draft_quality_pass,
        require_context_pack_quality_pass=require_context_pack_quality_pass,
        require_draft_answer_status=require_draft_answer_status,
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net Evidence Snippet / Claim Materializer v1")
    parser.add_argument("--citation-draft", type=Path, default=DEFAULT_CITATION_DRAFT)
    parser.add_argument("--context-pack", type=Path, default=DEFAULT_CONTEXT_PACK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-claims", type=int, default=12)
    parser.add_argument("--max-snippet-chars", type=int, default=700)
    parser.add_argument("--min-snippet-claims", type=int, default=1)
    parser.add_argument("--require-draft-quality-pass", action="store_true")
    parser.add_argument("--no-require-draft-quality-pass", dest="require_draft_quality_pass", action="store_false")
    parser.set_defaults(require_draft_quality_pass=True)
    parser.add_argument("--require-context-pack-quality-pass", action="store_true")
    parser.add_argument("--no-require-context-pack-quality-pass", dest="require_context_pack_quality_pass", action="store_false")
    parser.set_defaults(require_context_pack_quality_pass=True)
    parser.add_argument("--require-draft-answer-status", default="CITATION_DRAFT_ONLY")
    parser.add_argument("--require-context-pack-answer-status", default="CONTEXT_PACK_ONLY")
    parser.add_argument("--require-embedding-dim", type=int, default=1024)
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--open", action="store_true")
    return parser


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Evidence Snippet Claims v1 quality")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REPORT_FILE)
    parser.add_argument("--min-snippet-claims", type=int, default=1)
    parser.add_argument("--require-draft-quality-pass", action="store_true")
    parser.add_argument("--no-require-draft-quality-pass", dest="require_draft_quality_pass", action="store_false")
    parser.set_defaults(require_draft_quality_pass=True)
    parser.add_argument("--require-context-pack-quality-pass", action="store_true")
    parser.add_argument("--no-require-context-pack-quality-pass", dest="require_context_pack_quality_pass", action="store_false")
    parser.set_defaults(require_context_pack_quality_pass=True)
    parser.add_argument("--require-draft-answer-status", default="CITATION_DRAFT_ONLY")
    parser.add_argument("--require-context-pack-answer-status", default="CONTEXT_PACK_ONLY")
    parser.add_argument("--require-embedding-dim", type=int, default=1024)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = build_trace_net_evidence_snippet_claims(
            citation_draft_path=args.citation_draft,
            context_pack_path=args.context_pack,
            output_dir=args.output_dir,
            max_claims=args.max_claims,
            max_snippet_chars=args.max_snippet_chars,
            min_snippet_claims=args.min_snippet_claims,
            require_draft_quality_pass=args.require_draft_quality_pass,
            require_context_pack_quality_pass=args.require_context_pack_quality_pass,
            require_draft_answer_status=args.require_draft_answer_status,
            require_context_pack_answer_status=args.require_context_pack_answer_status,
            require_embedding_dim=args.require_embedding_dim,
            write_quality=args.quality,
            open_result=args.open,
        )
    except Exception as exc:
        print(f"TRACE-Net evidence snippet claims failed: {exc}", file=sys.stderr)
        return 1
    summary = report.get("summary") or {}
    print("TRACE-Net evidence snippet / claim materializer v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    print(f" query: {report.get('query')}")
    print(f" answer_status: {report.get('answer_status')}")
    print(f" draft_quality_status: {summary.get('draft_quality_status')}")
    print(f" context_pack_quality_status: {summary.get('context_pack_quality_status')}")
    print(f" embedding_mode: {summary.get('embedding_mode')}")
    print(f" embedding_model_name: {summary.get('embedding_model_name')}")
    print(f" embedding_dim: {summary.get('embedding_dim')}")
    print(f" snippet_claim_count: {summary.get('snippet_claim_count')}")
    print(f" cited_snippet_claim_count: {summary.get('cited_snippet_claim_count')}")
    print(f" missing_source_snippet_count: {summary.get('missing_source_snippet_count')}")
    print(f" retrieval_only_snippet_claim_count: {summary.get('retrieval_only_snippet_claim_count')}")
    print(f" claim_without_authority_count: {summary.get('claim_without_authority_count')}")
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
        result = check_trace_net_evidence_snippet_claims_quality(
            report_path=args.report_path,
            min_snippet_claims=args.min_snippet_claims,
            require_draft_quality_pass=args.require_draft_quality_pass,
            require_context_pack_quality_pass=args.require_context_pack_quality_pass,
            require_draft_answer_status=args.require_draft_answer_status,
            require_context_pack_answer_status=args.require_context_pack_answer_status,
            require_embedding_dim=args.require_embedding_dim,
            write_json_result=args.write_json,
        )
    except Exception as exc:
        print(f"TRACE-Net evidence snippet claims quality check failed: {exc}", file=sys.stderr)
        return 1
    summary = result.get("summary") or {}
    print("TRACE-Net evidence snippet / claim materializer v1 quality")
    print(f" Status: {result.get('status')}")
    for key in [
        "snippet_claim_count",
        "cited_snippet_claim_count",
        "uncited_snippet_claim_count",
        "missing_page_id_count",
        "missing_citation_count",
        "missing_source_snippet_count",
        "retrieval_only_snippet_claim_count",
        "page_profile_snippet_claim_count",
        "context_helper_snippet_claim_count",
        "source_evidence_snippet_claim_count",
        "claim_without_authority_count",
        "claim_without_context_record_count",
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
