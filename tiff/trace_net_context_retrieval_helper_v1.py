"""TRACE-Net Context Retrieval Helper v1.

Step 3 in the TRACE-Net retrieval path turns PageContextV2 records into
safe retrieval-helper records. These records are allowed to route, expand,
and rank search, but they are never allowed to answer directly or mutate
source truth.

This module is read-only with respect to Postgres. It reads
page_context_v2_records and writes local JSON/JSONL artifacts under
local_data/organization/trace_net/context_retrieval_helpers/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_context_retrieval_helper_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/context_retrieval_helpers")
DEFAULT_HELPERS_FILE = "trace_net_context_retrieval_helpers_v1.json"
DEFAULT_HELPERS_JSONL_FILE = "trace_net_context_retrieval_helpers_v1.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_context_retrieval_helpers_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_context_retrieval_helpers_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_context_retrieval_helpers_v1_quality.json"
DEFAULT_BASELINE_CHECKPOINT = Path(
    "local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/"
    "trace_net_graph_baseline_checkpoint_v1.json"
)
DEFAULT_BASELINE_QUALITY_FILE = "trace_net_graph_baseline_checkpoint_v1_quality.json"
DEFAULT_FALLBACK_DOC = "t_p_120_1176"

PAGE_NUMBER_RE = re.compile(r"(\d+)(?!.*\d)")
SAFE_SUFFIX_RE = re.compile(r"[^A-Za-z0-9_.-]+")

ALLOWED_USE = ["retrieve", "route", "rank_boost", "query_expansion", "candidate_discovery"]
FORBIDDEN_USE = [
    "direct_answer",
    "claim_proof",
    "canonical_source_truth",
    "source_truth_mutation",
    "citation_replacement",
    "trust_tier_override",
]


class ContextRetrievalHelperError(RuntimeError):
    """Raised when safe helper records cannot be built or checked."""


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
    """Convert DB values into deterministic JSON-safe values."""
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


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_page_range(raw: str | None) -> list[int]:
    """Parse a page range string such as "1-50,75,80-82"."""
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
            if start <= 0 or end <= 0:
                raise ValueError("page numbers must be positive")
            if end < start:
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


def expected_page_id_aliases(page_number: int, *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> set[str]:
    return {
        f"{fallback_doc}_p{page_number:06d}",
        f"zip_page_{page_number:06d}",
        f"page_{page_number:06d}",
        f"page_{page_number}",
        str(page_number),
    }


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
    if not text:
        return value
    if text[0] not in "[{\"":
        return value
    try:
        return json.loads(text)
    except Exception:
        return value


def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("payload", "context_payload", "json", "metadata", "data"):
        if key in row:
            parsed = _maybe_json(row.get(key))
            if isinstance(parsed, Mapping):
                return dict(parsed)
    return {}


def _field(row: Mapping[str, Any], *names: str) -> Any:
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
    return None


def _first_text(*values: Any) -> str:
    for value in values:
        text = _as_text(value).strip()
        if text:
            return text
    return ""


def _dedupe(items: Iterable[Any], *, max_items: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = _as_text(item).strip()
        text = re.sub(r"^[\s\-:*•]+", "", text).strip()
        text = re.sub(r"\s+", " ", text)
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


def _coerce_list(value: Any) -> list[str]:
    value = _maybe_json(value)
    if value in (None, "", [], {}):
        return []
    if isinstance(value, Mapping):
        items: list[Any] = []
        for key, val in value.items():
            if isinstance(val, (list, tuple)):
                items.extend(val)
            elif val not in (None, "", [], {}):
                if str(key).isdigit():
                    items.append(val)
                else:
                    items.append(f"{key}: {val}")
        return _dedupe(items)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = []
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
    if len(pieces) == 1 and text.count(",") and text.count(",") <= 12:
        pieces = [p.strip() for p in text.split(",")]
    return _dedupe(pieces)


def _context_page_id(row: Mapping[str, Any], *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> str:
    value = _field(row, "page_id", "canonical_page_id", "source_page_id", "document_page_id", "page")
    if value in (None, "", [], {}):
        value = _field(row, "context_id", "record_id", "id", "node_id")
    return canonical_page_id(value, fallback_doc=fallback_doc)


def _context_record_id(row: Mapping[str, Any], page_id: str) -> str:
    return _first_text(_field(row, "context_id", "record_id", "id", "node_id"), f"context_v2:{page_id}")


def _summary_text(row: Mapping[str, Any]) -> str:
    return _first_text(
        _field(row, "summary", "context_summary", "short_summary", "page_summary"),
        _field(row, "what_this_page_can_help_answer", "can_help_answer", "answerable_questions"),
        _field(row, "retrieval_cues", "important_entities"),
    )


def _context_sections(row: Mapping[str, Any]) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    scalar_fields = [
        "role",
        "subrole",
        "summary",
        "what_this_page_can_help_answer",
        "nearby_context",
        "not_good_for_guardrails",
        "guardrails",
        "model",
        "confidence",
    ]
    list_fields = [
        "answerable_questions",
        "retrieval_cues",
        "important_entities",
        "component_families",
        "source_grounding_phrases",
    ]
    for key in scalar_fields:
        value = _field(row, key)
        if value not in (None, "", [], {}):
            sections[key] = _as_text(value).strip()
    if "summary" not in sections:
        summary = _summary_text(row)
        if summary:
            sections["summary"] = summary
    for key in list_fields:
        values = _coerce_list(_field(row, key))
        if values:
            sections[key] = values
    return sections


def make_query_tunnel_terms(sections: Mapping[str, Any], *, max_terms: int = 80) -> list[str]:
    candidates: list[Any] = []
    for key in (
        "retrieval_cues",
        "important_entities",
        "component_families",
        "source_grounding_phrases",
        "answerable_questions",
    ):
        candidates.extend(_coerce_list(sections.get(key)))
    for key in ("role", "subrole"):
        if sections.get(key):
            candidates.append(sections.get(key))
    return _dedupe(candidates, max_items=max_terms)


def make_helper_text(page_id: str, sections: Mapping[str, Any], tunnel_terms: Sequence[str], *, max_chars: int = 6000) -> str:
    lines: list[str] = [
        "TRACE-Net context retrieval helper.",
        "Use: route search to likely pages/evidence. Do not use as direct answer proof.",
        f"Page: {page_id}",
    ]
    label_map = {
        "role": "Role",
        "subrole": "Subrole",
        "summary": "Summary",
        "what_this_page_can_help_answer": "Can help answer",
        "answerable_questions": "Answerable question cues",
        "retrieval_cues": "Retrieval cues",
        "important_entities": "Important entities",
        "component_families": "Component families",
        "nearby_context": "Nearby context",
        "source_grounding_phrases": "Source grounding phrases",
        "not_good_for_guardrails": "Not good for",
        "guardrails": "Guardrails",
    }
    for key, label in label_map.items():
        value = sections.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            text = "; ".join(_coerce_list(value))
        else:
            text = _as_text(value).strip()
        if text:
            lines.append(f"{label}: {text}")
    if tunnel_terms:
        lines.append("Query tunnel terms: " + "; ".join(tunnel_terms))
    helper_text = "\n".join(lines).strip()
    if len(helper_text) > max_chars:
        return helper_text[: max_chars - 3].rstrip() + "..."
    return helper_text


def build_helper_record(
    row: Mapping[str, Any],
    *,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_helper_text_chars: int = 6000,
) -> dict[str, Any]:
    """Convert one PageContextV2 row into a retrieval-only helper record."""
    safe_row = json_safe(dict(row))
    page_id = _context_page_id(row, fallback_doc=fallback_doc)
    context_id = _context_record_id(row, page_id or "unknown_page")
    row_hash = sha256_json(safe_row)
    helper_id = f"ctx_helper__{_safe_suffix(page_id or 'missing_page')}__{row_hash[:12]}"
    sections = _context_sections(row)
    tunnel_terms = make_query_tunnel_terms(sections)
    helper_text = make_helper_text(page_id, sections, tunnel_terms, max_chars=max_helper_text_chars)

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "helper_id": helper_id,
        "record_type": "context_retrieval_helper",
        "safety_bucket": "context_retrieval_helper",
        "embedding_bucket": "context_retrieval_helper",
        "source_table": "page_context_v2_records",
        "source_context_id": context_id,
        "source_row_sha256": row_hash,
        "page_id": page_id,
        "page_number": extract_page_number(page_id),
        "authority": "retrieval_helper_only",
        "allowed_use": list(ALLOWED_USE),
        "forbidden_use": list(FORBIDDEN_USE),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "can_override_trust": False,
        "can_replace_citation": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "requires_final_evidence_record": True,
        "retrieval_only": True,
        "eligible_for_embedding_candidate": True,
        "embedding_answer_authority_allowed": False,
        "summary": sections.get("summary", ""),
        "retrieval_cues": _coerce_list(sections.get("retrieval_cues")),
        "answerable_questions": _coerce_list(sections.get("answerable_questions")),
        "important_entities": _coerce_list(sections.get("important_entities")),
        "component_families": _coerce_list(sections.get("component_families")),
        "source_grounding_phrases": _coerce_list(sections.get("source_grounding_phrases")),
        "not_good_for_guardrails": sections.get("not_good_for_guardrails", ""),
        "query_tunnel_terms": tunnel_terms,
        "helper_text": helper_text,
        "embedding_text": helper_text,
        "traceability": {
            "page_id": page_id,
            "source_table": "page_context_v2_records",
            "source_context_id": context_id,
            "source_row_sha256": row_hash,
            "must_resolve_through_postgres": True,
        },
        "trust_policy": {
            "authority": "retrieval_helper_only",
            "claim_proof_allowed": False,
            "answer_allowed": False,
            "retrieval_allowed": True,
            "citation_required_before_answer": True,
            "source_resolution_required_before_answer": True,
        },
    }
    for key in ("role", "subrole", "nearby_context", "guardrails", "model", "confidence"):
        value = sections.get(key)
        if value not in (None, "", [], {}):
            record[key] = value
    return record


def build_helper_records(
    rows: Sequence[Mapping[str, Any]],
    *,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_helper_text_chars: int = 6000,
) -> list[dict[str, Any]]:
    records = [
        build_helper_record(row, fallback_doc=fallback_doc, max_helper_text_chars=max_helper_text_chars)
        for row in rows
    ]
    records.sort(key=lambda rec: ((rec.get("page_number") or 10**9), str(rec.get("page_id") or ""), str(rec.get("helper_id") or "")))
    return records


def required_page_coverage(required_pages: Sequence[int], records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pages_present = {extract_page_number(rec.get("page_id")) for rec in records}
    pages_present.discard(None)
    missing = [page for page in required_pages if page not in pages_present]
    covered = [page for page in required_pages if page in pages_present]
    return {
        "required_page_numbers": list(required_pages),
        "covered_page_numbers": covered,
        "missing_page_numbers": missing,
        "covered_page_count": len(covered),
        "missing_page_count": len(missing),
    }


def summarize_records(records: Sequence[Mapping[str, Any]], *, required_pages: Sequence[int] | None = None) -> dict[str, Any]:
    required_pages = list(required_pages or [])
    helper_ids = [str(rec.get("helper_id") or "") for rec in records]
    duplicate_helper_ids = sorted({helper_id for helper_id in helper_ids if helper_ids.count(helper_id) > 1 and helper_id})
    page_ids = [str(rec.get("page_id") or "") for rec in records if rec.get("page_id")]
    summary = {
        "helper_count": len(records),
        "page_count": len(set(page_ids)),
        "missing_page_id_count": sum(1 for rec in records if not rec.get("page_id")),
        "duplicate_helper_id_count": len(duplicate_helper_ids),
        "duplicate_helper_ids": duplicate_helper_ids[:20],
        "records_with_summary_count": sum(1 for rec in records if _as_text(rec.get("summary")).strip()),
        "records_with_retrieval_cues_count": sum(1 for rec in records if _coerce_list(rec.get("retrieval_cues"))),
        "records_with_query_tunnel_terms_count": sum(1 for rec in records if _coerce_list(rec.get("query_tunnel_terms"))),
        "records_with_helper_text_count": sum(1 for rec in records if _as_text(rec.get("helper_text")).strip()),
        "authority_not_retrieval_helper_only_count": sum(
            1 for rec in records if rec.get("authority") != "retrieval_helper_only"
        ),
        "can_answer_directly_true_count": sum(1 for rec in records if _as_bool(rec.get("can_answer_directly"))),
        "can_prove_claims_true_count": sum(1 for rec in records if _as_bool(rec.get("can_prove_claims"))),
        "canonical_source_truth_true_count": sum(1 for rec in records if _as_bool(rec.get("canonical_source_truth"))),
        "source_truth_mutation_allowed_count": sum(1 for rec in records if _as_bool(rec.get("can_mutate_source_truth"))),
        "trust_override_allowed_count": sum(1 for rec in records if _as_bool(rec.get("can_override_trust"))),
        "citation_replacement_allowed_count": sum(1 for rec in records if _as_bool(rec.get("can_replace_citation"))),
        "requires_source_resolution_false_count": sum(
            1 for rec in records if not _as_bool(rec.get("requires_source_resolution"), default=True)
        ),
        "requires_citation_false_count": sum(1 for rec in records if not _as_bool(rec.get("requires_citation"), default=True)),
        "requires_authority_gate_false_count": sum(
            1 for rec in records if not _as_bool(rec.get("requires_authority_gate"), default=True)
        ),
        "embedding_answer_authority_allowed_count": sum(
            1 for rec in records if _as_bool(rec.get("embedding_answer_authority_allowed"))
        ),
        "wrong_record_type_count": sum(1 for rec in records if rec.get("record_type") != "context_retrieval_helper"),
        "wrong_safety_bucket_count": sum(1 for rec in records if rec.get("safety_bucket") != "context_retrieval_helper"),
    }
    summary["unsafe_helper_count"] = sum(
        int(summary[key])
        for key in (
            "authority_not_retrieval_helper_only_count",
            "can_answer_directly_true_count",
            "can_prove_claims_true_count",
            "canonical_source_truth_true_count",
            "source_truth_mutation_allowed_count",
            "trust_override_allowed_count",
            "citation_replacement_allowed_count",
            "requires_source_resolution_false_count",
            "requires_citation_false_count",
            "requires_authority_gate_false_count",
            "embedding_answer_authority_allowed_count",
            "wrong_record_type_count",
            "wrong_safety_bucket_count",
        )
    )
    if required_pages:
        coverage = required_page_coverage(required_pages, records)
    else:
        coverage = {"required_page_numbers": [], "covered_page_numbers": [], "missing_page_numbers": [], "covered_page_count": 0, "missing_page_count": 0}
    summary["required_page_coverage"] = coverage
    summary["required_page_missing_count"] = coverage["missing_page_count"]
    return summary


def _check(checks: list[dict[str, Any]], name: str, actual: Any, op: str, expected: Any, passed: bool) -> None:
    checks.append({"name": name, "actual": actual, "op": op, "expected": expected, "passed": bool(passed)})


def baseline_quality_status_from_checkpoint(checkpoint: Mapping[str, Any] | None, checkpoint_path: Path | None = None) -> str:
    if not checkpoint:
        return "UNKNOWN"
    direct = _as_text(checkpoint.get("quality_status") or checkpoint.get("status")).upper()
    if direct in {"PASS", "FAIL"}:
        return direct
    if checkpoint_path:
        sibling = checkpoint_path.with_name(DEFAULT_BASELINE_QUALITY_FILE)
        if sibling.exists():
            try:
                payload = json.loads(sibling.read_text(encoding="utf-8"))
                status = _as_text(payload.get("status")).upper()
                if status in {"PASS", "FAIL"}:
                    return status
            except Exception:
                return "UNKNOWN"
    artifact = checkpoint.get("artifact_baseline")
    if isinstance(artifact, Mapping):
        graph_quality = artifact.get("graph_explorer_v2_nomenclature_quality")
        if isinstance(graph_quality, Mapping):
            status = _as_text(graph_quality.get("status")).upper()
            if status in {"PASS", "FAIL"}:
                return status
    return "UNKNOWN"


def evaluate_helper_quality(
    records: Sequence[Mapping[str, Any]],
    *,
    baseline_checkpoint: Mapping[str, Any] | None = None,
    baseline_checkpoint_path: Path | None = None,
    min_helper_records: int = 50,
    min_pages_with_helpers: int = 50,
    min_records_with_summary: int = 40,
    min_records_with_retrieval_cues: int = 40,
    min_records_with_query_tunnel_terms: int = 40,
    require_pages: Sequence[int] | None = None,
    require_baseline_quality_pass: bool = False,
) -> QualityResult:
    summary = summarize_records(records, required_pages=list(require_pages or []))
    checks: list[dict[str, Any]] = []
    _check(checks, "helper_count", summary["helper_count"], ">=", min_helper_records, summary["helper_count"] >= min_helper_records)
    _check(checks, "pages_with_helpers", summary["page_count"], ">=", min_pages_with_helpers, summary["page_count"] >= min_pages_with_helpers)
    _check(checks, "records_with_summary", summary["records_with_summary_count"], ">=", min_records_with_summary, summary["records_with_summary_count"] >= min_records_with_summary)
    _check(checks, "records_with_retrieval_cues", summary["records_with_retrieval_cues_count"], ">=", min_records_with_retrieval_cues, summary["records_with_retrieval_cues_count"] >= min_records_with_retrieval_cues)
    _check(checks, "records_with_query_tunnel_terms", summary["records_with_query_tunnel_terms_count"], ">=", min_records_with_query_tunnel_terms, summary["records_with_query_tunnel_terms_count"] >= min_records_with_query_tunnel_terms)
    _check(checks, "missing_page_id_count", summary["missing_page_id_count"], "==", 0, summary["missing_page_id_count"] == 0)
    _check(checks, "duplicate_helper_id_count", summary["duplicate_helper_id_count"], "==", 0, summary["duplicate_helper_id_count"] == 0)
    _check(checks, "unsafe_helper_count", summary["unsafe_helper_count"], "==", 0, summary["unsafe_helper_count"] == 0)
    _check(checks, "required_page_missing_count", summary["required_page_missing_count"], "==", 0, summary["required_page_missing_count"] == 0)
    if require_baseline_quality_pass:
        status = baseline_quality_status_from_checkpoint(baseline_checkpoint, baseline_checkpoint_path).upper()
        summary["baseline_quality_status"] = status
        _check(checks, "baseline_quality_status", status, "==", "PASS", status == "PASS")
    else:
        summary["baseline_quality_status"] = baseline_quality_status_from_checkpoint(baseline_checkpoint, baseline_checkpoint_path).upper()
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=summary)


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


def load_context_v2_rows(database_url: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise ContextRetrievalHelperError("psycopg is required. Install with: pip install 'psycopg[binary]'.") from exc
    with psycopg.connect(database_url) as conn:
        if not _table_exists(conn, "page_context_v2_records"):
            raise ContextRetrievalHelperError("Postgres table page_context_v2_records does not exist.")
        columns = _table_columns(conn, "page_context_v2_records")
        order_parts = [name for name in ("page_id", "context_id", "record_id", "id") if name in columns]
        sql = "select * from page_context_v2_records"
        params: tuple[Any, ...] = ()
        if order_parts:
            sql += " order by " + ", ".join(order_parts)
        if limit is not None:
            sql += " limit %s"
            params = (limit,)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            names = [desc.name if hasattr(desc, "name") else desc[0] for desc in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]


def load_baseline_checkpoint(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def baseline_summary(checkpoint: Mapping[str, Any] | None, path: Path | None = None) -> dict[str, Any]:
    if not checkpoint:
        return {"present": False, "checkpoint_path": str(path) if path else ""}
    graph = checkpoint.get("graph_baseline") if isinstance(checkpoint.get("graph_baseline"), Mapping) else {}
    retrieval = checkpoint.get("retrieval_safety_baseline") if isinstance(checkpoint.get("retrieval_safety_baseline"), Mapping) else {}
    return {
        "present": True,
        "checkpoint_path": str(path) if path else "",
        "checkpoint_name": checkpoint.get("checkpoint_name", ""),
        "checkpoint_sha256": checkpoint.get("checkpoint_sha256", ""),
        "quality_status": baseline_quality_status_from_checkpoint(checkpoint, path),
        "page_count": graph.get("page_count"),
        "page_context_v2_page_count": graph.get("page_context_v2_page_count"),
        "has_context_v2_edge_count": graph.get("has_context_v2_edge_count"),
        "nomenclature_node_count": graph.get("nomenclature_node_count"),
        "has_nomenclature_edge_count": graph.get("has_nomenclature_edge_count"),
        "rag_candidate_count": retrieval.get("rag_candidate_count"),
        "source_citation_count": retrieval.get("source_citation_count"),
    }


def build_helper_bundle(
    rows: Sequence[Mapping[str, Any]],
    *,
    baseline_checkpoint: Mapping[str, Any] | None = None,
    baseline_checkpoint_path: Path | None = None,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    require_pages: Sequence[int] | None = None,
    max_helper_text_chars: int = 6000,
) -> dict[str, Any]:
    records = build_helper_records(rows, fallback_doc=fallback_doc, max_helper_text_chars=max_helper_text_chars)
    required_pages = list(require_pages or [])
    summary = summarize_records(records, required_pages=required_pages)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "read_only": True,
        "source_table": "page_context_v2_records",
        "record_count": len(records),
        "trace_net_boundary_rules": {
            "context_can_route_search": True,
            "context_can_answer_directly": False,
            "context_can_prove_claims": False,
            "context_can_mutate_source_truth": False,
            "context_requires_source_resolution_before_answer": True,
            "context_requires_citation_before_answer": True,
        },
        "baseline_checkpoint": baseline_summary(baseline_checkpoint, baseline_checkpoint_path),
        "summary": summary,
        "records": records,
    }


def write_helper_outputs(bundle: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    helpers_path = output_dir / DEFAULT_HELPERS_FILE
    jsonl_path = output_dir / DEFAULT_HELPERS_JSONL_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE

    helpers_path.write_text(json.dumps(json_safe(bundle), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in bundle.get("records", []):
            handle.write(json.dumps(json_safe(record), ensure_ascii=False, sort_keys=True) + "\n")
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": bundle.get("generated_at_utc"),
        "read_only": True,
        "record_count": bundle.get("record_count"),
        "summary": bundle.get("summary", {}),
        "baseline_checkpoint": bundle.get("baseline_checkpoint", {}),
        "trace_net_boundary_rules": bundle.get("trace_net_boundary_rules", {}),
    }
    summary_path.write_text(json.dumps(json_safe(summary_payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": bundle.get("generated_at_utc"),
        "read_only": True,
        "files": {
            DEFAULT_HELPERS_FILE: {"path": str(helpers_path), "sha256": sha256_file(helpers_path)},
            DEFAULT_HELPERS_JSONL_FILE: {"path": str(jsonl_path), "sha256": sha256_file(jsonl_path)},
            DEFAULT_SUMMARY_FILE: {"path": str(summary_path), "sha256": sha256_file(summary_path)},
        },
        "record_count": bundle.get("record_count"),
    }
    manifest_path.write_text(json.dumps(json_safe(manifest_payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "helpers_path": helpers_path,
        "jsonl_path": jsonl_path,
        "summary_path": summary_path,
        "manifest_path": manifest_path,
    }


def load_helper_records_from_path(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise ContextRetrievalHelperError(f"helper artifact not found: {path}")
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
    raise ContextRetrievalHelperError(f"unsupported helper artifact shape: {path}")


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
    print("TRACE-Net context retrieval helper v1 quality")
    print(f" Status: {quality.status}")
    for key in [
        "helper_count",
        "page_count",
        "records_with_summary_count",
        "records_with_retrieval_cues_count",
        "records_with_query_tunnel_terms_count",
        "required_page_missing_count",
        "unsafe_helper_count",
        "baseline_quality_status",
    ]:
        if key in quality.summary:
            print(f" {key}: {quality.summary[key]}")
    failed = [check for check in quality.checks if not check["passed"]]
    for check in failed[:10]:
        print(f" FAIL {check['name']}: {check['actual']} {check['op']} {check['expected']}")


def main_build(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Context Retrieval Helper v1 artifacts from PageContextV2.")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--baseline-checkpoint", type=Path, default=DEFAULT_BASELINE_CHECKPOINT)
    parser.add_argument("--require-baseline-quality-pass", action="store_true")
    parser.add_argument("--require-first-pages", default="1-50")
    parser.add_argument("--fallback-doc", default=DEFAULT_FALLBACK_DOC)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-helper-text-chars", type=int, default=6000)
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--min-helper-records", type=int, default=50)
    parser.add_argument("--min-pages-with-helpers", type=int, default=50)
    parser.add_argument("--min-records-with-summary", type=int, default=40)
    parser.add_argument("--min-records-with-retrieval-cues", type=int, default=40)
    parser.add_argument("--min-records-with-query-tunnel-terms", type=int, default=40)
    args = parser.parse_args(argv)

    if not args.database_url:
        print("ERROR: --database-url or TRACE_NET_DATABASE_URL is required", file=sys.stderr)
        return 2

    required_pages = parse_page_range(args.require_first_pages)
    baseline = load_baseline_checkpoint(args.baseline_checkpoint)
    rows = load_context_v2_rows(args.database_url, limit=args.limit)
    bundle = build_helper_bundle(
        rows,
        baseline_checkpoint=baseline,
        baseline_checkpoint_path=args.baseline_checkpoint,
        fallback_doc=args.fallback_doc,
        require_pages=required_pages,
        max_helper_text_chars=args.max_helper_text_chars,
    )
    paths = write_helper_outputs(bundle, args.output_dir)

    print("TRACE-Net context retrieval helper v1")
    print(" Status: BUILT")
    summary = bundle["summary"]
    for key in [
        "helper_count",
        "page_count",
        "records_with_summary_count",
        "records_with_retrieval_cues_count",
        "records_with_query_tunnel_terms_count",
        "required_page_missing_count",
        "unsafe_helper_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" helpers_path: {paths['helpers_path']}")
    print(f" jsonl_path: {paths['jsonl_path']}")
    print(f" summary_path: {paths['summary_path']}")
    print(f" manifest_path: {paths['manifest_path']}")

    if args.quality:
        quality = evaluate_helper_quality(
            bundle["records"],
            baseline_checkpoint=baseline,
            baseline_checkpoint_path=args.baseline_checkpoint,
            min_helper_records=args.min_helper_records,
            min_pages_with_helpers=args.min_pages_with_helpers,
            min_records_with_summary=args.min_records_with_summary,
            min_records_with_retrieval_cues=args.min_records_with_retrieval_cues,
            min_records_with_query_tunnel_terms=args.min_records_with_query_tunnel_terms,
            require_pages=required_pages,
            require_baseline_quality_pass=args.require_baseline_quality_pass,
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
    parser = argparse.ArgumentParser(description="Quality-check TRACE-Net Context Retrieval Helper v1 artifacts.")
    parser.add_argument("--helpers-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_HELPERS_FILE)
    parser.add_argument("--baseline-checkpoint", type=Path, default=DEFAULT_BASELINE_CHECKPOINT)
    parser.add_argument("--require-baseline-quality-pass", action="store_true")
    parser.add_argument("--require-first-pages", default="1-50")
    parser.add_argument("--min-helper-records", type=int, default=50)
    parser.add_argument("--min-pages-with-helpers", type=int, default=50)
    parser.add_argument("--min-records-with-summary", type=int, default=40)
    parser.add_argument("--min-records-with-retrieval-cues", type=int, default=40)
    parser.add_argument("--min-records-with-query-tunnel-terms", type=int, default=40)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--quality-path", type=Path, default=None)
    args = parser.parse_args(argv)

    records, _payload_obj = load_helper_records_from_path(args.helpers_path)
    required_pages = parse_page_range(args.require_first_pages)
    baseline = load_baseline_checkpoint(args.baseline_checkpoint)
    quality = evaluate_helper_quality(
        records,
        baseline_checkpoint=baseline,
        baseline_checkpoint_path=args.baseline_checkpoint,
        min_helper_records=args.min_helper_records,
        min_pages_with_helpers=args.min_pages_with_helpers,
        min_records_with_summary=args.min_records_with_summary,
        min_records_with_retrieval_cues=args.min_records_with_retrieval_cues,
        min_records_with_query_tunnel_terms=args.min_records_with_query_tunnel_terms,
        require_pages=required_pages,
        require_baseline_quality_pass=args.require_baseline_quality_pass,
    )
    _print_quality(quality)
    if args.write_json:
        quality_path = args.quality_path or (args.helpers_path.parent / DEFAULT_QUALITY_FILE)
        write_quality_result(quality, quality_path)
        print(f" quality_path: {quality_path}")
    return 0 if quality.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
