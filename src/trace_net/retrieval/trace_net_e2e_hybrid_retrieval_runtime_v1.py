"""TRACE-Net E2E hybrid retrieval runtime v1.

Local, read-only retrieval runtime for the first end-to-end TRACE-Net path.
It consumes safe E2E query-input records and table hybrid retrieval bridge records,
then produces ranked retrieval groups. It does not answer, prove claims, mutate
source truth, or write to runtime services.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

STATUS_BUILT = "E2E_HYBRID_RETRIEVAL_RUNTIME_BUILT"
READY_STATUS = "E2E_HYBRID_RETRIEVAL_RUNTIME_READY_FOR_CONTEXT_PACK"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

REPORT_FILENAME = "trace_net_e2e_hybrid_retrieval_runtime_v1.json"
QUALITY_FILENAME = "trace_net_e2e_hybrid_retrieval_runtime_v1_quality.json"
GROUPS_JSONL_FILENAME = "trace_net_e2e_hybrid_retrieval_groups_v1.jsonl"
INSPECT_MD_FILENAME = "trace_net_e2e_hybrid_retrieval_runtime_v1_inspect.md"

PART_NUMBER_RE = re.compile(r"\b\d{2,3}-\d{2,5}-\d{2,4}\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


@dataclass(frozen=True)
class QualityThresholds:
    min_source_query_records: int = 1
    min_source_bridge_records: int = 1
    min_retrieval_queries: int = 1
    min_successful_retrieval_queries: int = 1
    min_retrieval_groups: int = 1
    min_total_retrieval_hits: int = 1
    min_pages_with_retrieval_hits: int = 1
    min_field_count: int = 1
    max_unsafe_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_source_query_input_quality_pass: bool = False
    require_source_bridge_quality_pass: bool = False
    require_no_answer_permission: bool = False


def load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _norm_text(value).lower()


def _tokens(value: Any) -> List[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(_norm_text(value))]


def _safe_float(value: Any, default: float = 1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_query_records(query_input: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = _as_list(query_input.get("query_records"))
    return [dict(r) for r in records if isinstance(r, dict)]


def extract_bridge_records(bridge: Mapping[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        bridge.get("bridge_records"),
        bridge.get("table_hybrid_bridge_records"),
        bridge.get("records"),
    ]
    for candidate in candidates:
        rows = _as_list(candidate)
        if rows:
            return [dict(r) for r in rows if isinstance(r, dict)]
    return []


def extract_query_groups(bridge: Mapping[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        bridge.get("query_bridge_groups"),
        bridge.get("query_groups"),
        bridge.get("retrieval_query_groups"),
    ]
    for candidate in candidates:
        rows = _as_list(candidate)
        if rows:
            return [dict(r) for r in rows if isinstance(r, dict)]
    return []


def _query_terms(record: Mapping[str, Any]) -> List[Dict[str, str]]:
    terms: List[Dict[str, str]] = []
    for item in _as_list(record.get("query_terms")):
        if isinstance(item, dict):
            term = _norm_text(item.get("term") or item.get("value") or item.get("text"))
            if term:
                terms.append({"term": term, "term_type": _norm_text(item.get("term_type") or item.get("type") or "query_term")})
        elif item:
            terms.append({"term": _norm_text(item), "term_type": "query_term"})

    user_query = _norm_text(record.get("user_query") or record.get("query"))
    if user_query:
        for match in PART_NUMBER_RE.findall(user_query):
            terms.append({"term": match, "term_type": "part_number"})
        for match in MANUAL_REF_RE.findall(user_query):
            terms.append({"term": match, "term_type": "manual_page_reference"})

    # Add field-intent term so a free-text query such as "covered part numbers" can
    # retrieve table bridge records for that field.
    intent = _norm_text(record.get("query_intent"))
    if intent:
        terms.append({"term": intent, "term_type": "query_intent"})

    # Preserve order while deduplicating.
    seen = set()
    deduped: List[Dict[str, str]] = []
    for item in terms:
        key = (item["term"].lower(), item["term_type"].lower())
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _record_text(record: Mapping[str, Any]) -> str:
    pieces = [
        record.get("normalized_value"),
        record.get("value"),
        record.get("display_value"),
        record.get("field_name"),
        record.get("field_role"),
        record.get("search_text"),
        record.get("page_id"),
        record.get("table_id"),
        record.get("evidence_id"),
    ]
    return " ".join(_norm_text(p) for p in pieces if _norm_text(p))


def _record_value(record: Mapping[str, Any]) -> str:
    for key in ("normalized_value", "value", "display_value", "text_value", "normalized_text"):
        val = _norm_text(record.get(key))
        if val:
            return val
    return ""


def _record_id(record: Mapping[str, Any], fallback_index: int) -> str:
    for key in ("bridge_record_id", "record_id", "evidence_id", "document_id", "id"):
        val = _norm_text(record.get(key))
        if val:
            return val
    page = _norm_text(record.get("page_id")) or "unknown_page"
    field = _norm_text(record.get("field_name") or record.get("field_role")) or "unknown_field"
    value = _record_value(record)[:80]
    return f"bridge::{page}::{field}::{value}::{fallback_index}"


def _score_bridge_record(
    query_record: Mapping[str, Any],
    bridge_record: Mapping[str, Any],
    query_terms: Sequence[Mapping[str, str]],
) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0
    field_name = _lower(bridge_record.get("field_name") or bridge_record.get("field_role"))
    value = _lower(_record_value(bridge_record))
    haystack = _lower(_record_text(bridge_record))
    intent = _lower(query_record.get("query_intent"))
    user_query = _lower(query_record.get("user_query") or query_record.get("query"))
    routing_boost = _safe_float(bridge_record.get("routing_boost"), 1.0)

    for term_obj in query_terms:
        term = _lower(term_obj.get("term"))
        if not term:
            continue
        if term == value:
            score += 300.0 * routing_boost
            reasons.append(f"exact_value:{term}")
        elif term and term in value:
            score += 180.0 * routing_boost
            reasons.append(f"value_contains:{term}")
        elif term and term in haystack:
            score += 120.0 * routing_boost
            reasons.append(f"record_contains:{term}")
        if term == field_name:
            score += 160.0 * routing_boost
            reasons.append(f"field_match:{term}")

    if intent and intent == field_name:
        score += 140.0 * routing_boost
        reasons.append(f"intent_field_match:{intent}")
    elif intent and intent in field_name:
        score += 70.0 * routing_boost
        reasons.append(f"intent_field_contains:{intent}")

    # Mild token overlap for free-text query fallback.
    query_tokens = set(_tokens(user_query))
    record_tokens = set(_tokens(haystack))
    overlap = query_tokens & record_tokens
    if overlap:
        overlap_score = min(len(overlap), 6) * 12.0 * routing_boost
        score += overlap_score
        reasons.append("token_overlap:" + ",".join(sorted(list(overlap))[:6]))

    return score, reasons


def _score_query_group(
    query_record: Mapping[str, Any],
    query_group: Mapping[str, Any],
    query_terms: Sequence[Mapping[str, str]],
) -> Tuple[float, List[str]]:
    group_query = _lower(query_group.get("query") or query_group.get("user_query"))
    user_query = _lower(query_record.get("user_query") or query_record.get("query"))
    reasons: List[str] = []
    score = 0.0
    for term_obj in query_terms:
        term = _lower(term_obj.get("term"))
        if term and term == group_query:
            score += 280.0
            reasons.append(f"query_group_exact:{term}")
        elif term and (term in group_query or group_query in term):
            score += 170.0
            reasons.append(f"query_group_contains:{term}")
    if group_query and group_query in user_query:
        score += 140.0
        reasons.append(f"query_text_contains_group:{group_query}")
    return score, reasons


def _hit_from_bridge_record(record: Mapping[str, Any], score: float, reasons: Sequence[str], index: int) -> Dict[str, Any]:
    return {
        "hit_id": _record_id(record, index),
        "source_channel": "table_hybrid_retrieval_bridge",
        "route": "table",
        "page_id": _norm_text(record.get("page_id")),
        "table_id": _norm_text(record.get("table_id")),
        "field_name": _norm_text(record.get("field_name") or record.get("field_role")),
        "normalized_value": _record_value(record),
        "routing_boost": _safe_float(record.get("routing_boost"), 1.0),
        "retrieval_score": round(score, 4),
        "match_reasons": list(reasons),
        "retrieval_permission": "ranking_only_until_final_gate",
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def _dedupe_hits(hits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for hit in hits:
        key = (
            _norm_text(hit.get("page_id")),
            _norm_text(hit.get("field_name")),
            _norm_text(hit.get("normalized_value")),
        )
        if key not in best or float(hit.get("retrieval_score", 0.0)) > float(best[key].get("retrieval_score", 0.0)):
            best[key] = hit
    return sorted(best.values(), key=lambda h: float(h.get("retrieval_score", 0.0)), reverse=True)


def build_retrieval_group_for_query(
    query_record: Mapping[str, Any],
    bridge_records: Sequence[Mapping[str, Any]],
    query_groups: Sequence[Mapping[str, Any]],
    top_k: int = 10,
) -> Dict[str, Any]:
    terms = _query_terms(query_record)
    hits: List[Dict[str, Any]] = []

    for idx, record in enumerate(bridge_records):
        score, reasons = _score_bridge_record(query_record, record, terms)
        if score > 0:
            hits.append(_hit_from_bridge_record(record, score, reasons, idx))

    # Query group hits act as query-specific shortcuts from prior smoke/demo work.
    for group_idx, group in enumerate(query_groups):
        group_score, group_reasons = _score_query_group(query_record, group, terms)
        if group_score <= 0:
            continue
        for hit_idx, raw_hit in enumerate(_as_list(group.get("hits"))):
            if not isinstance(raw_hit, dict):
                continue
            merged = dict(raw_hit)
            merged.setdefault("routing_boost", raw_hit.get("routing_boost", group.get("routing_boost", 1.0)))
            score = group_score * _safe_float(merged.get("routing_boost"), 1.0)
            reasons = list(group_reasons) + ["query_group_hit"]
            hits.append(_hit_from_bridge_record(merged, score, reasons, group_idx * 100000 + hit_idx))

    ranked_hits = _dedupe_hits(hits)[: max(int(top_k), 1)]
    pages = sorted({_norm_text(hit.get("page_id")) for hit in ranked_hits if _norm_text(hit.get("page_id"))})
    fields = sorted({_norm_text(hit.get("field_name")) for hit in ranked_hits if _norm_text(hit.get("field_name"))})

    return {
        "query_id": _norm_text(query_record.get("query_id")) or "query_unknown",
        "user_query": _norm_text(query_record.get("user_query") or query_record.get("query")),
        "query_intent": _norm_text(query_record.get("query_intent")) or "unknown",
        "requested_routes": list(query_record.get("requested_routes") or []),
        "retrieval_channels": list(query_record.get("retrieval_channels") or []),
        "query_terms": terms,
        "retrieval_status": "RETRIEVAL_MATCHED" if ranked_hits else "RETRIEVAL_NO_MATCH",
        "retrieval_permission": "ranking_only_until_final_gate",
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "hit_count": len(ranked_hits),
        "page_ids": pages,
        "field_names": fields,
        "hits": ranked_hits,
    }


def _field_counts_from_groups(groups: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for group in groups:
        for hit in _as_list(group.get("hits")):
            if not isinstance(hit, dict):
                continue
            field = _norm_text(hit.get("field_name")) or "unknown"
            counts[field] = counts.get(field, 0) + 1
    return dict(sorted(counts.items()))


def _channel_counts_from_groups(groups: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for group in groups:
        for hit in _as_list(group.get("hits")):
            if not isinstance(hit, dict):
                continue
            channel = _norm_text(hit.get("source_channel")) or "unknown"
            counts[channel] = counts.get(channel, 0) + 1
    return dict(sorted(counts.items()))


def _make_quality_check(name: str, observed: Any, expected: str, passed: bool) -> Dict[str, Any]:
    return {"name": name, "observed": observed, "expected": expected, "passed": bool(passed)}


def evaluate_quality(report: Mapping[str, Any], thresholds: QualityThresholds) -> Tuple[str, List[Dict[str, Any]]]:
    summary = _as_dict(report.get("summary"))
    checks: List[Dict[str, Any]] = []

    def ge(name: str, observed: Any, minimum: int) -> None:
        try:
            value = int(observed)
        except (TypeError, ValueError):
            value = -1
        checks.append(_make_quality_check(name, observed, f">= {minimum}", value >= minimum))

    def le(name: str, observed: Any, maximum: int) -> None:
        try:
            value = int(observed)
        except (TypeError, ValueError):
            value = 10**9
        checks.append(_make_quality_check(name, observed, f"<= {maximum}", value <= maximum))

    def eq(name: str, observed: Any, expected: Any) -> None:
        checks.append(_make_quality_check(name, observed, f"== {expected}", observed == expected))

    def true(name: str, observed: Any) -> None:
        checks.append(_make_quality_check(name, observed, "is True", bool(observed) is True))

    ge("source_query_input_record_count", summary.get("source_query_input_record_count"), thresholds.min_source_query_records)
    ge("source_bridge_record_count", summary.get("source_bridge_record_count"), thresholds.min_source_bridge_records)
    ge("hybrid_retrieval_query_count", summary.get("hybrid_retrieval_query_count"), thresholds.min_retrieval_queries)
    ge("successful_retrieval_query_count", summary.get("successful_retrieval_query_count"), thresholds.min_successful_retrieval_queries)
    ge("retrieval_group_count", summary.get("retrieval_group_count"), thresholds.min_retrieval_groups)
    ge("total_retrieval_hit_count", summary.get("total_retrieval_hit_count"), thresholds.min_total_retrieval_hits)
    ge("page_with_retrieval_hit_count", summary.get("page_with_retrieval_hit_count"), thresholds.min_pages_with_retrieval_hits)
    ge("field_count", summary.get("field_count"), thresholds.min_field_count)

    le("unsafe_runtime_record_count", summary.get("unsafe_runtime_record_count"), thresholds.max_unsafe_records)
    le("answer_permission_count", summary.get("answer_permission_count"), thresholds.max_answer_permission_count)
    le("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count"), thresholds.max_source_truth_mutation_allowed)
    eq("can_answer_directly_count", summary.get("can_answer_directly_count"), 0)
    eq("can_prove_claims_count", summary.get("can_prove_claims_count"), 0)
    eq("postgres_write_attempt_count", summary.get("postgres_write_attempt_count"), 0)
    eq("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count"), 0)
    eq("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count"), 0)
    eq("opensearch_upload_attempt_count", summary.get("opensearch_upload_attempt_count"), 0)

    if thresholds.require_source_query_input_quality_pass:
        true("source_query_input_quality_pass", summary.get("source_query_input_quality_pass"))
    if thresholds.require_source_bridge_quality_pass:
        true("source_bridge_quality_pass", summary.get("source_bridge_quality_pass"))
    if thresholds.require_no_answer_permission:
        true("all_results_retrieval_only", summary.get("all_results_retrieval_only"))

    status = QUALITY_PASS if all(check["passed"] for check in checks) else QUALITY_FAIL
    return status, checks


def build_report(
    *,
    e2e_query_input: Mapping[str, Any],
    table_hybrid_retrieval_bridge: Mapping[str, Any],
    e2e_query_input_path: str | Path,
    table_hybrid_retrieval_bridge_path: str | Path,
    top_k: int = 10,
    thresholds: QualityThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or QualityThresholds()
    query_records = extract_query_records(e2e_query_input)
    bridge_records = extract_bridge_records(table_hybrid_retrieval_bridge)
    query_groups = extract_query_groups(table_hybrid_retrieval_bridge)

    retrieval_groups = [
        build_retrieval_group_for_query(record, bridge_records, query_groups, top_k=top_k)
        for record in query_records
    ]

    pages = sorted({page for group in retrieval_groups for page in _as_list(group.get("page_ids")) if page})
    successful = [group for group in retrieval_groups if int(group.get("hit_count") or 0) > 0]
    total_hits = sum(int(group.get("hit_count") or 0) for group in retrieval_groups)
    field_counts = _field_counts_from_groups(retrieval_groups)
    channel_counts = _channel_counts_from_groups(retrieval_groups)

    source_query_input_quality_pass = e2e_query_input.get("quality_status") == QUALITY_PASS
    source_bridge_quality_pass = table_hybrid_retrieval_bridge.get("quality_status") == QUALITY_PASS

    summary: Dict[str, Any] = {
        "e2e_hybrid_retrieval_runtime_status": READY_STATUS,
        "retrieval_permission": "ranking_only_until_final_gate",
        "answer_authority": "blocked",
        "ready_for_context_pack": True,
        "source_query_input_path": str(e2e_query_input_path),
        "source_bridge_path": str(table_hybrid_retrieval_bridge_path),
        "source_query_input_quality_pass": bool(source_query_input_quality_pass),
        "source_bridge_quality_pass": bool(source_bridge_quality_pass),
        "source_query_input_record_count": len(query_records),
        "source_bridge_record_count": len(bridge_records),
        "source_query_bridge_group_count": len(query_groups),
        "hybrid_retrieval_query_count": len(retrieval_groups),
        "successful_retrieval_query_count": len(successful),
        "failed_retrieval_query_count": len(retrieval_groups) - len(successful),
        "retrieval_group_count": len(retrieval_groups),
        "total_retrieval_hit_count": total_hits,
        "page_with_retrieval_hit_count": len(pages),
        "field_count": len(field_counts),
        "field_counts": field_counts,
        "source_channel_counts": channel_counts,
        "unsafe_runtime_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "all_results_retrieval_only": True,
    }

    report: Dict[str, Any] = {
        "artifact_name": "trace_net_e2e_hybrid_retrieval_runtime_v1",
        "status": STATUS_BUILT,
        "quality_status": QUALITY_FAIL,
        "runtime_contract": {
            "purpose": "Merge safe E2E query input records with retrieval/ranking signals into local ranked retrieval groups.",
            "retrieval_permission": "ranking_only_until_final_gate",
            "answer_authority": "blocked",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "ready_for_context_pack": True,
        },
        "summary": summary,
        "retrieval_groups": retrieval_groups,
        "quality_checks": [],
    }

    quality_status, checks = evaluate_quality(report, thresholds)
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    return report


def render_inspect_markdown(report: Mapping[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    contract = _as_dict(report.get("runtime_contract"))
    lines = [
        "# TRACE-Net E2E Hybrid Retrieval Runtime v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status', QUALITY_FAIL)}**",
        "",
        "## Purpose",
        "This artifact consumes safe E2E query-plan records and produces ranked retrieval groups.",
        "It does not answer, prove claims, mutate source truth, or write to runtime services.",
        "",
        "## Runtime contract",
    ]
    for key in [
        "retrieval_permission",
        "answer_authority",
        "ready_for_context_pack",
        "can_answer_directly",
        "can_prove_claims",
        "source_truth_mutation_allowed",
        "writes_to_postgres",
        "writes_to_qdrant",
        "writes_to_opensearch",
        "uploads_to_opensearch",
    ]:
        lines.append(f"- {key}: {contract.get(key)}")

    lines.extend(["", "## Main counters"])
    for key in [
        "source_query_input_record_count",
        "source_bridge_record_count",
        "source_query_bridge_group_count",
        "hybrid_retrieval_query_count",
        "successful_retrieval_query_count",
        "retrieval_group_count",
        "total_retrieval_hit_count",
        "page_with_retrieval_hit_count",
        "field_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")

    lines.extend(["", "## Field counts"])
    field_counts = _as_dict(summary.get("field_counts"))
    if field_counts:
        for field, count in field_counts.items():
            lines.append(f"- {field}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Safety/write counters"])
    for key in [
        "unsafe_runtime_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")

    lines.extend(["", "## Retrieval groups"])
    for group in _as_list(report.get("retrieval_groups")):
        if not isinstance(group, dict):
            continue
        lines.append(
            f"- {group.get('query_id')} | {group.get('query_intent')} | query='{group.get('user_query')}' | "
            f"status={group.get('retrieval_status')} | hits={group.get('hit_count')}"
        )
        for hit in _as_list(group.get("hits"))[:5]:
            if not isinstance(hit, dict):
                continue
            lines.append(
                f"  - {hit.get('page_id')} | {hit.get('field_name')} | {hit.get('normalized_value')} | "
                f"score={hit.get('retrieval_score')} | boost={hit.get('routing_boost')}"
            )

    lines.extend(["", "## Quality checks"])
    for check in _as_list(report.get("quality_checks")):
        if not isinstance(check, dict):
            continue
        marker = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {marker} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"


def write_report_outputs(report: Mapping[str, Any], output_dir: str | Path, write_quality_json: bool = True) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / REPORT_FILENAME
    quality_path = out / QUALITY_FILENAME
    groups_path = out / GROUPS_JSONL_FILENAME
    inspect_path = out / INSPECT_MD_FILENAME

    write_json(report_path, report)
    write_jsonl(groups_path, _as_list(report.get("retrieval_groups")))
    inspect_path.write_text(render_inspect_markdown(report), encoding="utf-8")
    if write_quality_json:
        write_json(
            quality_path,
            {
                "artifact_name": report.get("artifact_name"),
                "quality_status": report.get("quality_status"),
                "summary": report.get("summary", {}),
                "quality_checks": report.get("quality_checks", []),
            },
        )
    return {
        "report_path": str(report_path),
        "quality_path": str(quality_path),
        "retrieval_groups_jsonl_path": str(groups_path),
        "inspect_md_path": str(inspect_path),
    }


def build_from_paths(
    *,
    e2e_query_input_path: str | Path,
    table_hybrid_retrieval_bridge_path: str | Path,
    output_dir: str | Path,
    top_k: int = 10,
    thresholds: QualityThresholds | None = None,
    write_quality_json: bool = True,
) -> Dict[str, Any]:
    query_input = load_json(e2e_query_input_path)
    bridge = load_json(table_hybrid_retrieval_bridge_path)
    report = build_report(
        e2e_query_input=query_input,
        table_hybrid_retrieval_bridge=bridge,
        e2e_query_input_path=e2e_query_input_path,
        table_hybrid_retrieval_bridge_path=table_hybrid_retrieval_bridge_path,
        top_k=top_k,
        thresholds=thresholds,
    )
    paths = write_report_outputs(report, output_dir, write_quality_json=write_quality_json)
    report.update(paths)
    # Re-write with path metadata included.
    write_json(paths["report_path"], report)
    return report
