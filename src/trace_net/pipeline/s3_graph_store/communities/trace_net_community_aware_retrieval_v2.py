"""TRACE-Net Community-Aware Retrieval v2.

This module converts tightened Leiden navigation metadata into retrieval-time
navigation hints. It is intentionally read-only and advisory: communities can
help route or rank evidence, but they cannot answer directly or prove claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_community_aware_retrieval_v2"
STATUS_BUILT = "COMMUNITY_AWARE_RETRIEVAL_V2_BUILT"
STATUS_FAIL = "COMMUNITY_AWARE_RETRIEVAL_V2_QUALITY_FAIL"

PART_RE = re.compile(r"\b\d{3}-\d{5}(?:-\d{3})?\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
TOKEN_RE = re.compile(r"[a-z0-9]+")

SAFE_ZERO_COUNTERS = [
    "community_as_proof_count",
    "category_as_proof_count",
    "retrieval_only_answer_allowed_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
]


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected top-level JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def stable_id(*parts: Any, prefix: str = "carv2") -> str:
    raw = "|".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def get_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def quality_status(payload: dict[str, Any]) -> str | None:
    summary = get_summary(payload)
    return payload.get("quality_status") or summary.get("quality_status") or summary.get("status")


def is_pass(value: Any) -> bool:
    return str(value).upper() == "PASS"


def tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall((value or "").lower()))


def extract_part_numbers(value: str) -> list[str]:
    return sorted(set(PART_RE.findall(value or "")))


def extract_ata_codes(value: str) -> list[str]:
    return sorted(set(ATA_RE.findall(value or "")))


def part_family(part_number: str) -> str | None:
    m = re.match(r"^(\d{3}-\d{5})", part_number or "")
    return m.group(1) if m else None


def normalize_confidence(value: Any) -> str:
    raw = str(value or "").upper()
    if "HIGH" in raw:
        return "HIGH_NAVIGATION_CONFIDENCE"
    if "MODERATE" in raw:
        return "MODERATE_NAVIGATION_CONFIDENCE"
    if "LOW" in raw:
        return "LOW_NAVIGATION_CONFIDENCE"
    if "REVIEW" in raw:
        return "REVIEW_ONLY"
    return "UNKNOWN_NAVIGATION_CONFIDENCE"


def confidence_weight(confidence: str) -> float:
    if confidence == "HIGH_NAVIGATION_CONFIDENCE":
        return 0.55
    if confidence == "MODERATE_NAVIGATION_CONFIDENCE":
        return 0.40
    if confidence == "LOW_NAVIGATION_CONFIDENCE":
        return 0.10
    return 0.0


def should_use_as_retrieval_hint(hint: dict[str, Any]) -> bool:
    confidence = normalize_confidence(hint.get("navigation_confidence"))
    if confidence in {"LOW_NAVIGATION_CONFIDENCE", "REVIEW_ONLY"}:
        return False
    if hint.get("review_only") is True:
        return False
    return True


def extract_hybrid_queries(hybrid_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not hybrid_payload:
        return []
    query_results = hybrid_payload.get("query_results") or hybrid_payload.get("queries") or []
    results: list[dict[str, Any]] = []
    for i, query_record in enumerate(query_results):
        if not isinstance(query_record, dict):
            continue
        query = query_record.get("query") or query_record.get("query_text") or query_record.get("user_query") or ""
        query_id = query_record.get("query_id") or query_record.get("id") or stable_id(i, query, prefix="query")
        ranked_groups = query_record.get("ranked_groups") or query_record.get("groups") or []
        page_ids: list[str] = []
        group_summaries: list[dict[str, Any]] = []
        for group in ranked_groups:
            if not isinstance(group, dict):
                continue
            page_id = group.get("page_id") or group.get("source_page_id")
            if page_id:
                page_ids.append(str(page_id))
            group_summaries.append(
                {
                    "page_id": page_id,
                    "hybrid_v2_rank": group.get("hybrid_v2_rank") or group.get("rank"),
                    "hybrid_v2_score": group.get("hybrid_v2_score") or group.get("score"),
                    "exact_hit_count": group.get("exact_hit_count", 0),
                    "semantic_group_count": group.get("semantic_group_count", 0),
                    "part_numbers": [str(x) for x in as_list(group.get("part_numbers")) if x],
                }
            )
        results.append(
            {
                "query_id": str(query_id),
                "query": str(query),
                "ranked_group_count": len(group_summaries),
                "ranked_page_ids": sorted(set(page_ids)),
                "ranked_groups": group_summaries,
            }
        )
    return results


def fallback_queries_from_hints(retrieval_hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hint in retrieval_hints:
        part_numbers = [str(x) for x in as_list(hint.get("representative_part_numbers")) if x]
        for part in part_numbers:
            if part not in seen:
                seen.add(part)
                queries.append(
                    {
                        "query_id": stable_id(part, prefix="query"),
                        "query": part,
                        "ranked_group_count": 0,
                        "ranked_page_ids": [str(x) for x in as_list(hint.get("representative_page_ids")) if x],
                        "ranked_groups": [],
                    }
                )
        if len(queries) >= 5:
            break
    return queries


def index_page_hints(
    page_hints: list[dict[str, Any]],
    retrieval_hints: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for hint in page_hints:
        if not isinstance(hint, dict):
            continue
        page_id = hint.get("page_id") or hint.get("source_page_id")
        if page_id:
            index[str(page_id)].append(hint)

    # If the bridge has no page-hint section, synthesize page hints from the
    # representative pages on retrieval hints. The generated hints remain
    # retrieval-only and cannot prove claims.
    if not index:
        for hint in retrieval_hints:
            community_id = hint.get("community_id")
            for page_id in as_list(hint.get("representative_page_ids")):
                if not page_id:
                    continue
                index[str(page_id)].append(
                    {
                        "page_id": str(page_id),
                        "community_id": community_id,
                        "refined_label": hint.get("refined_label"),
                        "navigation_intent": hint.get("navigation_intent"),
                        "navigation_confidence": hint.get("navigation_confidence"),
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    }
                )
    return index


def community_lookup(
    community_records: list[dict[str, Any]],
    retrieval_hints: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for record in community_records + retrieval_hints:
        if not isinstance(record, dict):
            continue
        cid = record.get("community_id")
        if not cid:
            continue
        existing = lookup.get(str(cid), {})
        merged = {**existing, **record}
        lookup[str(cid)] = merged
    return lookup


def match_score_for_hint(query: dict[str, Any], hint: dict[str, Any], matched_page_ids: list[str]) -> tuple[float, list[str]]:
    reason_codes: list[str] = []
    query_text = query.get("query", "")
    query_tokens = tokens(query_text)
    label_tokens = tokens(str(hint.get("refined_label") or hint.get("label") or ""))
    confidence = normalize_confidence(hint.get("navigation_confidence"))

    score = confidence_weight(confidence)
    if matched_page_ids:
        score += min(0.20, 0.03 * len(set(matched_page_ids)))
        reason_codes.append("hybrid_page_overlap")

    query_parts = extract_part_numbers(query_text)
    hint_parts = [str(x) for x in as_list(hint.get("representative_part_numbers")) if x]
    hint_families = {part_family(p) for p in hint_parts if part_family(p)}
    exact_parts = sorted(set(query_parts) & set(hint_parts))
    if exact_parts:
        score += 0.30
        reason_codes.append("exact_part_number_navigation_match")
    elif query_parts:
        query_families = {part_family(p) for p in query_parts if part_family(p)}
        if query_families & hint_families:
            score += 0.15
            reason_codes.append("part_family_navigation_match")

    overlap = query_tokens & label_tokens
    if overlap:
        score += min(0.10, len(overlap) * 0.025)
        reason_codes.append("label_token_overlap")

    intent = str(hint.get("navigation_intent") or "")
    if "table" in query_tokens and "table" in intent:
        score += 0.08
        reason_codes.append("table_intent_match")
    if "visual" in query_tokens and "visual" in intent:
        score += 0.08
        reason_codes.append("visual_intent_match")
    if {"part", "parts"} & query_tokens and "part_family" in intent:
        score += 0.08
        reason_codes.append("part_intent_match")

    return round(min(score, 0.99), 6), reason_codes


def build_query_navigation_record(
    query: dict[str, Any],
    community_by_id: dict[str, dict[str, Any]],
    retrieval_hints: list[dict[str, Any]],
    page_hint_index: dict[str, list[dict[str, Any]]],
    max_results_per_query: int,
) -> dict[str, Any]:
    candidate: dict[str, dict[str, Any]] = {}
    matched_pages_by_community: dict[str, set[str]] = defaultdict(set)
    excluded_hint_records: list[dict[str, Any]] = []

    ranked_page_ids = [str(x) for x in as_list(query.get("ranked_page_ids")) if x]
    query_text = query.get("query", "")
    query_parts = extract_part_numbers(query_text)
    query_part_families = {part_family(p) for p in query_parts if part_family(p)}

    for page_id in ranked_page_ids:
        for page_hint in page_hint_index.get(page_id, []):
            cid = page_hint.get("community_id")
            if not cid:
                continue
            cid = str(cid)
            hint = {**community_by_id.get(cid, {}), **page_hint}
            if not should_use_as_retrieval_hint(hint):
                excluded_hint_records.append(
                    {
                        "community_id": cid,
                        "page_id": page_id,
                        "navigation_confidence": normalize_confidence(hint.get("navigation_confidence")),
                        "reason": "excluded_low_confidence_or_review_only",
                    }
                )
                continue
            candidate[cid] = {**community_by_id.get(cid, {}), **hint}
            matched_pages_by_community[cid].add(page_id)

    # Exact part-number and part-family matches can add community hints even if
    # the current top hybrid page set is narrow. This is still navigation-only.
    for hint in retrieval_hints:
        if not isinstance(hint, dict) or not should_use_as_retrieval_hint(hint):
            continue
        cid = hint.get("community_id")
        if not cid:
            continue
        hint_parts = [str(x) for x in as_list(hint.get("representative_part_numbers")) if x]
        hint_families = {part_family(p) for p in hint_parts if part_family(p)}
        if query_parts and (set(query_parts) & set(hint_parts) or query_part_families & hint_families):
            cid = str(cid)
            candidate[cid] = {**community_by_id.get(cid, {}), **hint}
            for page_id in as_list(hint.get("representative_page_ids")):
                if page_id and (not ranked_page_ids or page_id in ranked_page_ids):
                    matched_pages_by_community[cid].add(str(page_id))

    navigation_results: list[dict[str, Any]] = []
    for cid, hint in candidate.items():
        matched_pages = sorted(matched_pages_by_community.get(cid, set()))
        score, reason_codes = match_score_for_hint(query, hint, matched_pages)
        confidence = normalize_confidence(hint.get("navigation_confidence"))
        result = {
            "navigation_result_id": stable_id(query.get("query_id"), cid, prefix="navres"),
            "query_id": query.get("query_id"),
            "query": query.get("query"),
            "community_id": cid,
            "refined_label": hint.get("refined_label") or hint.get("label"),
            "navigation_intent": hint.get("navigation_intent"),
            "navigation_confidence": confidence,
            "navigation_score": score,
            "matched_page_ids": matched_pages,
            "representative_page_ids": [str(x) for x in as_list(hint.get("representative_page_ids")) if x],
            "representative_part_family": hint.get("representative_part_family"),
            "representative_part_numbers": [str(x) for x in as_list(hint.get("representative_part_numbers")) if x],
            "reason_codes": reason_codes,
            "retrieval_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "community_as_proof": False,
            "category_as_proof": False,
            "source_artifact": "leiden_navigation_metadata_bridge",
        }
        navigation_results.append(result)

    navigation_results.sort(key=lambda r: (-float(r.get("navigation_score") or 0.0), r.get("community_id") or ""))
    navigation_results = navigation_results[:max_results_per_query]

    return {
        "query_navigation_record_id": stable_id(query.get("query_id"), prefix="querynav"),
        "query_id": query.get("query_id"),
        "query": query.get("query"),
        "query_parts": query_parts,
        "query_ata_codes": extract_ata_codes(query_text),
        "ranked_page_ids": ranked_page_ids,
        "ranked_group_count": query.get("ranked_group_count", 0),
        "navigation_results": navigation_results,
        "navigation_result_count": len(navigation_results),
        "excluded_hint_records": excluded_hint_records,
        "excluded_hint_count": len(excluded_hint_records),
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }


def build_page_navigation_boosts(query_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boosts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in query_records:
        query_id = record.get("query_id")
        for result in record.get("navigation_results") or []:
            for page_id in result.get("matched_page_ids") or result.get("representative_page_ids") or []:
                key = (str(query_id), str(page_id), str(result.get("community_id")))
                current = boosts.get(key)
                boost = {
                    "page_navigation_boost_id": stable_id(*key, prefix="pageboost"),
                    "query_id": query_id,
                    "query": record.get("query"),
                    "page_id": str(page_id),
                    "community_id": result.get("community_id"),
                    "refined_label": result.get("refined_label"),
                    "navigation_intent": result.get("navigation_intent"),
                    "navigation_confidence": result.get("navigation_confidence"),
                    "navigation_score": result.get("navigation_score"),
                    "retrieval_only": True,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                }
                if current is None or float(boost.get("navigation_score") or 0.0) > float(current.get("navigation_score") or 0.0):
                    boosts[key] = boost
    return sorted(boosts.values(), key=lambda r: (str(r.get("query_id")), -float(r.get("navigation_score") or 0.0), str(r.get("page_id"))))


def summarize(
    bridge_payload: dict[str, Any],
    hybrid_payload: dict[str, Any] | None,
    community_records: list[dict[str, Any]],
    retrieval_hints: list[dict[str, Any]],
    page_hints: list[dict[str, Any]],
    query_navigation_records: list[dict[str, Any]],
    page_navigation_boosts: list[dict[str, Any]],
) -> dict[str, Any]:
    bridge_summary = get_summary(bridge_payload)
    source_statuses = {
        "leiden_navigation_metadata_bridge": quality_status(bridge_payload),
    }
    if hybrid_payload is not None:
        source_statuses["hybrid_v2"] = quality_status(hybrid_payload)

    all_results = [r for q in query_navigation_records for r in q.get("navigation_results") or []]
    excluded = [r for q in query_navigation_records for r in q.get("excluded_hint_records") or []]

    confidence_counts = Counter(r.get("navigation_confidence") for r in all_results)
    intent_counts = Counter(r.get("navigation_intent") for r in all_results)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "trace_net_tightened_leiden_navigation_hint_retriever_v2",
        "source_navigation_bridge_quality_status": source_statuses.get("leiden_navigation_metadata_bridge"),
        "source_hybrid_v2_quality_status": source_statuses.get("hybrid_v2"),
        "source_quality_statuses": source_statuses,
        "community_navigation_record_count": len(community_records),
        "source_retrieval_navigation_hint_count": len(retrieval_hints),
        "source_page_navigation_hint_count": len(page_hints),
        "query_count": len(query_navigation_records),
        "queries_with_navigation_hints_count": sum(1 for q in query_navigation_records if q.get("navigation_result_count", 0) > 0),
        "navigation_result_count": len(all_results),
        "page_navigation_boost_count": len(page_navigation_boosts),
        "excluded_hint_count": len(excluded),
        "review_only_hints_used_count": sum(1 for r in all_results if r.get("navigation_confidence") == "REVIEW_ONLY"),
        "low_confidence_hints_used_count": sum(1 for r in all_results if r.get("navigation_confidence") == "LOW_NAVIGATION_CONFIDENCE"),
        "high_confidence_navigation_result_count": confidence_counts.get("HIGH_NAVIGATION_CONFIDENCE", 0),
        "moderate_confidence_navigation_result_count": confidence_counts.get("MODERATE_NAVIGATION_CONFIDENCE", 0),
        "part_family_navigation_result_count": intent_counts.get("part_family_navigation", 0),
        "table_navigation_result_count": intent_counts.get("table_evidence_navigation", 0),
        "visual_navigation_result_count": intent_counts.get("visual_evidence_navigation", 0),
        "mixed_navigation_result_count": intent_counts.get("mixed_evidence_navigation", 0),
        "source_bridge_review_only_community_count": bridge_summary.get("review_only_community_count"),
        "source_bridge_low_navigation_confidence_count": bridge_summary.get("low_navigation_confidence_count"),
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "status": "PASS",
    }
    return summary


def evaluate_quality(summary: dict[str, Any], thresholds: dict[str, Any]) -> tuple[str, list[str]]:
    failures: list[str] = []

    def at_least(key: str, threshold_key: str) -> None:
        threshold = thresholds.get(threshold_key)
        if threshold is not None and int(summary.get(key) or 0) < int(threshold):
            failures.append(f"{key} below {threshold}: {summary.get(key)}")

    def at_most(key: str, threshold_key: str) -> None:
        threshold = thresholds.get(threshold_key)
        if threshold is not None and int(summary.get(key) or 0) > int(threshold):
            failures.append(f"{key} above {threshold}: {summary.get(key)}")

    at_least("query_count", "min_queries")
    at_least("queries_with_navigation_hints_count", "min_queries_with_navigation_hints")
    at_least("navigation_result_count", "min_navigation_results")
    at_least("page_navigation_boost_count", "min_page_navigation_boosts")

    at_most("review_only_hints_used_count", "max_review_only_hints_used")
    at_most("low_confidence_hints_used_count", "max_low_confidence_hints_used")
    at_most("community_as_proof_count", "max_community_as_proof")
    at_most("category_as_proof_count", "max_category_as_proof")
    at_most("retrieval_only_answer_allowed_count", "max_retrieval_only_answer_allowed")
    at_most("source_truth_mutation_allowed_count", "max_source_truth_mutation_allowed")

    if thresholds.get("require_navigation_bridge_quality_pass") and not is_pass(summary.get("source_navigation_bridge_quality_status")):
        failures.append("source_navigation_bridge_quality_status is not PASS")
    if thresholds.get("require_hybrid_v2_quality_pass") and not is_pass(summary.get("source_hybrid_v2_quality_status")):
        failures.append("source_hybrid_v2_quality_status is not PASS")
    if thresholds.get("require_no_answer_permission"):
        for key in ["can_answer_directly_count", "can_prove_claims_count", "retrieval_only_answer_allowed_count"]:
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key} must be 0")

    for key in SAFE_ZERO_COUNTERS:
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key} must be 0")

    return ("FAIL" if failures else "PASS"), failures


def build_community_aware_retrieval_v2(
    *,
    leiden_navigation_metadata_bridge_path: str | Path,
    hybrid_v2_report_path: str | Path | None,
    output_dir: str | Path,
    thresholds: dict[str, Any] | None = None,
    max_results_per_query: int = 8,
    write_quality: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds or {}
    bridge_payload = load_json(leiden_navigation_metadata_bridge_path)
    hybrid_payload = load_json(hybrid_v2_report_path) if hybrid_v2_report_path else None

    community_records = [r for r in bridge_payload.get("community_navigation_records", []) if isinstance(r, dict)]
    retrieval_hints = [r for r in bridge_payload.get("retrieval_navigation_hints", []) if isinstance(r, dict)]
    page_hints = [r for r in bridge_payload.get("page_navigation_hints", []) if isinstance(r, dict)]

    page_hint_index = index_page_hints(page_hints, retrieval_hints)
    community_by_id = community_lookup(community_records, retrieval_hints)

    queries = extract_hybrid_queries(hybrid_payload)
    if not queries:
        queries = fallback_queries_from_hints(retrieval_hints)

    query_records = [
        build_query_navigation_record(
            query=q,
            community_by_id=community_by_id,
            retrieval_hints=retrieval_hints,
            page_hint_index=page_hint_index,
            max_results_per_query=max_results_per_query,
        )
        for q in queries
    ]
    page_boosts = build_page_navigation_boosts(query_records)

    summary = summarize(
        bridge_payload=bridge_payload,
        hybrid_payload=hybrid_payload,
        community_records=community_records,
        retrieval_hints=retrieval_hints,
        page_hints=page_hints,
        query_navigation_records=query_records,
        page_navigation_boosts=page_boosts,
    )
    status, failures = evaluate_quality(summary, thresholds)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "trace_net_community_aware_retrieval_v2.json"
    quality_path = out_dir / "trace_net_community_aware_retrieval_v2_quality.json"
    records_path = out_dir / "trace_net_community_aware_retrieval_v2_records.jsonl"
    page_boosts_path = out_dir / "trace_net_community_aware_retrieval_v2_page_boosts.jsonl"
    markdown_path = out_dir / "trace_net_community_aware_retrieval_v2.md"

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT if status == "PASS" else STATUS_FAIL,
        "quality_status": status,
        "quality_failures": failures,
        "summary": {**summary, "status": status},
        "source_paths": {
            "leiden_navigation_metadata_bridge": str(leiden_navigation_metadata_bridge_path),
            "hybrid_v2_report": str(hybrid_v2_report_path) if hybrid_v2_report_path else None,
        },
        "query_navigation_records": query_records,
        "page_navigation_boosts": page_boosts,
        "artifact_paths": {
            "report_path": str(report_path),
            "quality_path": str(quality_path),
            "records_path": str(records_path),
            "page_boosts_path": str(page_boosts_path),
            "markdown_path": str(markdown_path),
        },
    }

    write_json(report_path, report)
    write_jsonl(records_path, query_records)
    write_jsonl(page_boosts_path, page_boosts)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    if write_quality:
        write_json(quality_path, {
            "schema_version": SCHEMA_VERSION,
            "status": report["status"],
            "quality_status": status,
            "quality_failures": failures,
            "summary": report["summary"],
        })

    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Community-Aware Retrieval v2",
        "",
        f"Status: {report.get('status')}",
        f"Quality status: {report.get('quality_status')}",
        "",
        "This artifact converts tightened Leiden navigation profiles into retrieval-only ranking hints.",
        "Communities remain advisory and cannot prove claims or grant answer permission.",
        "",
        "## Key counts",
        "",
    ]
    for key in [
        "query_count",
        "queries_with_navigation_hints_count",
        "navigation_result_count",
        "page_navigation_boost_count",
        "review_only_hints_used_count",
        "low_confidence_hints_used_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    return "\n".join(lines)


def check_community_aware_retrieval_v2_quality(
    *,
    report_path: str | Path,
    thresholds: dict[str, Any] | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or {}
    report = load_json(report_path)
    summary = dict(get_summary(report))
    status, failures = evaluate_quality(summary, thresholds)
    checked = {
        "schema_version": SCHEMA_VERSION,
        "status": report.get("status") if status == "PASS" else STATUS_FAIL,
        "quality_status": status,
        "quality_failures": failures,
        "summary": {**summary, "status": status},
    }
    if write_json_report:
        p = Path(report_path)
        write_json(p.with_name("trace_net_community_aware_retrieval_v2_quality.json"), checked)
    return checked


def print_summary(report: dict[str, Any], *, title: str = "TRACE-Net Community-Aware Retrieval v2") -> None:
    summary = report.get("summary", {})
    print(title)
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "source_navigation_bridge_quality_status",
        "source_hybrid_v2_quality_status",
        "community_navigation_record_count",
        "source_retrieval_navigation_hint_count",
        "source_page_navigation_hint_count",
        "query_count",
        "queries_with_navigation_hints_count",
        "navigation_result_count",
        "page_navigation_boost_count",
        "review_only_hints_used_count",
        "low_confidence_hints_used_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        if key in summary:
            print(f" {key}: {summary.get(key)}")


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "min_queries": args.min_queries,
        "min_queries_with_navigation_hints": args.min_queries_with_navigation_hints,
        "min_navigation_results": args.min_navigation_results,
        "min_page_navigation_boosts": args.min_page_navigation_boosts,
        "max_review_only_hints_used": args.max_review_only_hints_used,
        "max_low_confidence_hints_used": args.max_low_confidence_hints_used,
        "max_community_as_proof": args.max_community_as_proof,
        "max_category_as_proof": args.max_category_as_proof,
        "max_retrieval_only_answer_allowed": args.max_retrieval_only_answer_allowed,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_navigation_bridge_quality_pass": args.require_navigation_bridge_quality_pass,
        "require_hybrid_v2_quality_pass": args.require_hybrid_v2_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-queries", type=int, default=None)
    parser.add_argument("--min-queries-with-navigation-hints", type=int, default=None)
    parser.add_argument("--min-navigation-results", type=int, default=None)
    parser.add_argument("--min-page-navigation-boosts", type=int, default=None)
    parser.add_argument("--max-review-only-hints-used", type=int, default=0)
    parser.add_argument("--max-low-confidence-hints-used", type=int, default=0)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-navigation-bridge-quality-pass", action="store_true")
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Community-Aware Retrieval v2")
    parser.add_argument("--leiden-navigation-metadata-bridge", required=True)
    parser.add_argument("--hybrid-v2-report", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-results-per-query", type=int, default=8)
    parser.add_argument("--quality", action="store_true")
    add_common_quality_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    thresholds = thresholds_from_args(args) if args.quality else {}
    report = build_community_aware_retrieval_v2(
        leiden_navigation_metadata_bridge_path=args.leiden_navigation_metadata_bridge,
        hybrid_v2_report_path=args.hybrid_v2_report,
        output_dir=args.output_dir,
        thresholds=thresholds,
        max_results_per_query=args.max_results_per_query,
        write_quality=True,
    )
    print_summary(report)
    print(f" report_path: {report['artifact_paths']['report_path']}")
    print(f" quality_path: {report['artifact_paths']['quality_path']}")
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
