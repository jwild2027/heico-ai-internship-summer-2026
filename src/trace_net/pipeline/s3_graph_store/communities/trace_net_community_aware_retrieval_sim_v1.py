"""TRACE-Net Community-Aware Retrieval Simulation v1.

Step 22 combines three advisory retrieval signals:

* the passed hybrid retrieval simulation (Qdrant page/candidate hits),
* Leiden graph communities (graph neighborhood hints), and
* sanitized feedback memory (thumbs/comments converted to advisory records).

The output is a read-only ranking simulation. Community and feedback signals may
boost, demote, or flag retrieval groups, but they never become source truth and
never prove answer claims. Final answer authority still belongs to citations,
source resolution, trust authority, and the final answer gate.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_community_aware_retrieval_sim_v1"
ALGORITHM = "trace_net_community_feedback_advisory_ranker_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/community_aware_retrieval_sim")
DEFAULT_HYBRID_REPORT = Path("local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json")
DEFAULT_LEIDEN_COMMUNITIES = Path("local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json")
DEFAULT_FEEDBACK_MEMORY = Path("local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json")

COMMUNITY_BOOST_PER_COMMUNITY = 0.045
COMMUNITY_BOOST_MAX = 0.135
FEEDBACK_PAGE_WEIGHT = 0.16
FEEDBACK_CITATION_WEIGHT = 0.12
FEEDBACK_COMMUNITY_WEIGHT = 0.10
FEEDBACK_QUERY_WEIGHT = 0.04
FEEDBACK_MAX_ABS = 0.35

RETRIEVAL_ONLY_BUCKETS = {
    "page_retrieval_profile",
    "context_retrieval_helper",
    "source_evidence",
    "derived_context",
    "figure_part_catalog_retrieval_helper",
    "chart_retrieval_helper",
    "vision_model_retrieval_helper",
    "feedback_memory_advisory",
    "leiden_graph_community_retrieval_helper",
}


class CommunityAwareRetrievalError(RuntimeError):
    """Raised when community-aware retrieval cannot be built safely."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            count += 1
    return count


def stable_hash(*parts: Any, length: int = 16) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{stable_hash(*parts, length=16)}"


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "allowed", "pass"}:
            return True
        if text in {"0", "false", "no", "n", "blocked", "fail"}:
            return False
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def unique_texts(values: Iterable[Any]) -> list[str]:
    return sorted({as_text(v) for v in values if as_text(v)})


def quality_status(payload: Mapping[str, Any]) -> str:
    for key in ("quality_status", "status"):
        value = as_text(payload.get(key)).upper()
        if value in {"PASS", "FAIL"}:
            return value
    q = payload.get("quality")
    if isinstance(q, Mapping):
        value = as_text(q.get("status")).upper()
        if value in {"PASS", "FAIL"}:
            return value
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        for key in (
            "hybrid_quality_status",
            "leiden_quality_status",
            "feedback_memory_quality_status",
            "quality_status",
        ):
            value = as_text(summary.get(key)).upper()
            if value in {"PASS", "FAIL"}:
                return value
    return ""


def normalize_community_id(value: Any) -> str:
    text = as_text(value)
    if not text:
        return ""
    if text.startswith("tracenet_community_"):
        return text
    if text.startswith("community_"):
        suffix = text.split("community_", 1)[1]
        if suffix.isdigit():
            return f"tracenet_community_{int(suffix):05d}"
    if text.isdigit():
        return f"tracenet_community_{int(text):05d}"
    return text


def extract_query_results(hybrid_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = hybrid_report.get("query_results") or hybrid_report.get("results") or []
    out: list[dict[str, Any]] = []
    if isinstance(values, list):
        for item in values:
            if isinstance(item, Mapping):
                row = dict(item)
                groups = row.get("ranked_groups") or row.get("groups") or []
                row["ranked_groups"] = [dict(g) for g in groups if isinstance(g, Mapping)]
                out.append(row)
    if out:
        return out
    groups = hybrid_report.get("ranked_groups") or hybrid_report.get("top_groups") or []
    if isinstance(groups, list):
        return [{
            "query_id": as_text(hybrid_report.get("query_id") or "single_query"),
            "query": as_text(hybrid_report.get("query")),
            "ranked_groups": [dict(g) for g in groups if isinstance(g, Mapping)],
        }]
    return []


def group_page_id(group: Mapping[str, Any]) -> str:
    return as_text(group.get("page_id"))


def group_citation_ids(group: Mapping[str, Any]) -> list[str]:
    ids = list(as_list(group.get("citation_ids")))
    for key in ("candidate_hits", "page_profile_hits", "hits"):
        for hit in as_list(group.get(key)):
            if isinstance(hit, Mapping):
                ids.extend(as_list(hit.get("citation_ids")))
                if hit.get("citation_id"):
                    ids.append(hit.get("citation_id"))
    return unique_texts(ids)


def group_buckets(group: Mapping[str, Any]) -> list[str]:
    buckets: list[Any] = []
    bc = group.get("bucket_counts")
    if isinstance(bc, Mapping):
        buckets.extend(bc.keys())
    for key in ("candidate_hits", "page_profile_hits", "hits"):
        for hit in as_list(group.get(key)):
            if isinstance(hit, Mapping) and hit.get("rag_bucket"):
                buckets.append(hit.get("rag_bucket"))
    return unique_texts(buckets)


def build_community_indexes(community_report: Mapping[str, Any]) -> dict[str, Any]:
    communities = [dict(c) for c in as_list(community_report.get("communities")) if isinstance(c, Mapping)]
    node_membership = [dict(m) for m in as_list(community_report.get("node_membership")) if isinstance(m, Mapping)]
    by_id: dict[str, dict[str, Any]] = {}
    page_to_communities: dict[str, set[str]] = defaultdict(set)
    citation_to_communities: dict[str, set[str]] = defaultdict(set)
    part_to_communities: dict[str, set[str]] = defaultdict(set)

    for community in communities:
        cid = normalize_community_id(community.get("community_id"))
        if not cid:
            continue
        community["community_id"] = cid
        by_id[cid] = community
        for page_id in as_list(community.get("page_ids")):
            if as_text(page_id):
                page_to_communities[as_text(page_id)].add(cid)
        for citation_id in as_list(community.get("citation_ids")):
            if as_text(citation_id):
                citation_to_communities[as_text(citation_id)].add(cid)
        for part in as_list(community.get("part_numbers")):
            if as_text(part):
                part_to_communities[as_text(part)].add(cid)

    for member in node_membership:
        cid = normalize_community_id(member.get("community_id"))
        if not cid:
            continue
        if as_text(member.get("page_id")):
            page_to_communities[as_text(member.get("page_id"))].add(cid)
        for page_id in as_list(member.get("source_page_ids")):
            if as_text(page_id):
                page_to_communities[as_text(page_id)].add(cid)
        if member.get("node_type") == "Citation":
            label = as_text(member.get("label"))
            node_id = as_text(member.get("node_id"))
            for candidate in (label, node_id.replace("citation::", "")):
                if candidate:
                    citation_to_communities[candidate].add(cid)

    return {
        "communities": communities,
        "by_id": by_id,
        "page_to_communities": {k: sorted(v) for k, v in page_to_communities.items()},
        "citation_to_communities": {k: sorted(v) for k, v in citation_to_communities.items()},
        "part_to_communities": {k: sorted(v) for k, v in part_to_communities.items()},
        "community_count": len(by_id),
    }


def safe_feedback_records(feedback_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = feedback_report.get("memory_records") or feedback_report.get("records") or []
    out: list[dict[str, Any]] = []
    for record in as_list(records):
        if not isinstance(record, Mapping):
            continue
        row = dict(record)
        # Raw/prompt-injection records can be stored, but they should not influence ranking.
        if as_bool(row.get("can_answer_directly"), default=False):
            continue
        if as_bool(row.get("can_prove_claims"), default=False):
            continue
        if as_bool(row.get("can_mutate_source_truth"), default=False):
            continue
        out.append(row)
    return out


def rating_score(record: Mapping[str, Any]) -> float:
    return max(-1.0, min(1.0, as_float(record.get("rating_score"), 0.0)))


def feedback_record_is_usable_for_ranking(record: Mapping[str, Any]) -> bool:
    if not as_bool(record.get("retrieval_advisory_allowed"), default=True):
        return False
    if as_bool(record.get("prompt_injection_flagged"), default=False):
        return False
    return True


def feedback_applies_to_group(
    record: Mapping[str, Any],
    group: Mapping[str, Any],
    *,
    page_id: str,
    citation_ids: set[str],
    community_ids: set[str],
    query_text: str,
) -> tuple[float, list[str]]:
    if not feedback_record_is_usable_for_ranking(record):
        return 0.0, []
    score = rating_score(record)
    if score == 0:
        return 0.0, []
    reasons: list[str] = []
    delta = 0.0
    target_type = as_text(record.get("target_type"))
    target_id = as_text(record.get("target_id"))
    record_pages = {as_text(v) for v in as_list(record.get("page_ids")) if as_text(v)}
    record_citations = {as_text(v) for v in as_list(record.get("citation_ids")) if as_text(v)}
    record_communities = {normalize_community_id(v) for v in as_list(record.get("community_ids")) if normalize_community_id(v)}
    if target_type == "page" and target_id:
        record_pages.add(target_id)
    if target_type == "citation" and target_id:
        record_citations.add(target_id)
    if target_type == "community" and target_id:
        record_communities.add(normalize_community_id(target_id))

    if page_id and page_id in record_pages:
        delta += score * FEEDBACK_PAGE_WEIGHT
        reasons.append("feedback_page_target_match")
    if citation_ids and citation_ids.intersection(record_citations):
        delta += score * FEEDBACK_CITATION_WEIGHT
        reasons.append("feedback_citation_target_match")
    if community_ids and community_ids.intersection(record_communities):
        delta += score * FEEDBACK_COMMUNITY_WEIGHT
        reasons.append("feedback_community_target_match")

    # A very small query-level advisory effect only when the sanitized feedback came from the same query.
    record_query = as_text(record.get("query_text_redacted") or record.get("query_text"))
    if record_query and query_text and record_query.lower() == query_text.lower() and not reasons:
        delta += score * FEEDBACK_QUERY_WEIGHT
        reasons.append("feedback_same_query_advisory")

    if delta > FEEDBACK_MAX_ABS:
        delta = FEEDBACK_MAX_ABS
    if delta < -FEEDBACK_MAX_ABS:
        delta = -FEEDBACK_MAX_ABS
    return round(delta, 6), reasons


def community_boost_for_group(community_ids: Sequence[str]) -> float:
    if not community_ids:
        return 0.0
    return round(min(len(set(community_ids)) * COMMUNITY_BOOST_PER_COMMUNITY, COMMUNITY_BOOST_MAX), 6)


def enrich_group(
    group: Mapping[str, Any],
    *,
    query_id: str,
    query_text: str,
    community_indexes: Mapping[str, Any],
    feedback_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    page_id = group_page_id(group)
    citation_ids = set(group_citation_ids(group))
    page_communities = set(community_indexes.get("page_to_communities", {}).get(page_id, []))
    for citation_id in citation_ids:
        page_communities.update(community_indexes.get("citation_to_communities", {}).get(citation_id, []))
    community_ids = sorted(page_communities)
    community_boost = community_boost_for_group(community_ids)
    feedback_delta = 0.0
    feedback_reasons: list[str] = []
    feedback_record_ids: list[str] = []
    positive_feedback_count = 0
    negative_feedback_count = 0

    for record in feedback_records:
        delta, reasons = feedback_applies_to_group(
            record,
            group,
            page_id=page_id,
            citation_ids=citation_ids,
            community_ids=set(community_ids),
            query_text=query_text,
        )
        if delta:
            feedback_delta += delta
            feedback_reasons.extend(reasons)
            feedback_record_ids.append(as_text(record.get("memory_id") or record.get("feedback_id") or record.get("target_id")))
            if delta > 0:
                positive_feedback_count += 1
            elif delta < 0:
                negative_feedback_count += 1

    feedback_delta = round(max(-FEEDBACK_MAX_ABS, min(FEEDBACK_MAX_ABS, feedback_delta)), 6)
    base_score = as_float(group.get("hybrid_score"), 0.0)
    final_score = round(base_score + community_boost + feedback_delta, 6)
    buckets = group_buckets(group)
    unsafe_reasons = [as_text(v) for v in as_list(group.get("unsafe_reasons")) if as_text(v)]
    retrieval_only_answer_allowed = False
    if as_bool(group.get("answer_allowed"), default=False) or as_bool(group.get("can_answer_directly"), default=False):
        if any(bucket in RETRIEVAL_ONLY_BUCKETS for bucket in buckets):
            retrieval_only_answer_allowed = True
    out = dict(group)
    out.update({
        "query_id": query_id,
        "query": query_text,
        "base_hybrid_score": round(base_score, 6),
        "community_aware_score": final_score,
        "community_boost": community_boost,
        "feedback_advisory_delta": feedback_delta,
        "community_ids": community_ids,
        "community_count": len(community_ids),
        "feedback_memory_ids_applied": unique_texts(feedback_record_ids),
        "feedback_reason_counts": dict(Counter(feedback_reasons)),
        "positive_feedback_applied_count": positive_feedback_count,
        "negative_feedback_applied_count": negative_feedback_count,
        "community_can_answer_directly": False,
        "community_can_prove_claims": False,
        "feedback_can_answer_directly": False,
        "feedback_can_prove_claims": False,
        "community_feedback_use_policy": "advisory_ranking_only_requires_source_citation_trust_gate_for_answer",
        "community_or_feedback_as_proof": False,
        "community_as_proof": False,
        "feedback_as_proof": False,
        "retrieval_only_answer_allowed": retrieval_only_answer_allowed,
        "source_truth_mutation_allowed": as_bool(group.get("can_mutate_source_truth"), default=False),
        "unsafe_reasons": unsafe_reasons,
        "safety_status": "retrieval_safe" if not unsafe_reasons and not retrieval_only_answer_allowed else "unsafe",
        "answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
    })
    return out


def build_community_aware_query_result(
    query_result: Mapping[str, Any],
    *,
    community_indexes: Mapping[str, Any],
    feedback_records: Sequence[Mapping[str, Any]],
    max_groups: int,
) -> dict[str, Any]:
    query_id = as_text(query_result.get("query_id") or stable_id("query", query_result.get("query")))
    query_text = as_text(query_result.get("query"))
    groups = [dict(g) for g in as_list(query_result.get("ranked_groups")) if isinstance(g, Mapping)]
    enriched = [
        enrich_group(
            group,
            query_id=query_id,
            query_text=query_text,
            community_indexes=community_indexes,
            feedback_records=feedback_records,
        )
        for group in groups
    ]
    enriched.sort(key=lambda g: as_float(g.get("community_aware_score"), 0.0), reverse=True)
    for idx, group in enumerate(enriched, start=1):
        group["community_aware_rank"] = idx
        group["rank_delta_from_hybrid"] = int(group.get("rank") or idx) - idx
    limited = enriched[:max_groups]
    return {
        "query_id": query_id,
        "query": query_text,
        "ranked_groups": limited,
        "ranked_group_count": len(limited),
        "community_boosted_result_count": sum(1 for g in limited if as_float(g.get("community_boost")) > 0),
        "feedback_adjusted_result_count": sum(1 for g in limited if as_float(g.get("feedback_advisory_delta")) != 0),
        "feedback_boosted_result_count": sum(1 for g in limited if as_float(g.get("feedback_advisory_delta")) > 0),
        "feedback_penalized_result_count": sum(1 for g in limited if as_float(g.get("feedback_advisory_delta")) < 0),
    }


def summarize_report(
    query_results: Sequence[Mapping[str, Any]],
    *,
    hybrid_report: Mapping[str, Any],
    community_report: Mapping[str, Any],
    feedback_report: Mapping[str, Any],
    feedback_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups = [g for qr in query_results for g in as_list(qr.get("ranked_groups")) if isinstance(g, Mapping)]
    community_count = int((community_report.get("summary") or {}).get("community_count") or len(as_list(community_report.get("communities"))))
    page_count = int((community_report.get("summary") or {}).get("page_count") or (hybrid_report.get("summary") or {}).get("page_count") or 0)
    feedback_summary = feedback_report.get("summary") if isinstance(feedback_report.get("summary"), Mapping) else {}
    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "community_aware_query_count": len(query_results),
        "queries_with_results_count": sum(1 for qr in query_results if int(qr.get("ranked_group_count") or 0) > 0),
        "grouped_result_count": len(groups),
        "community_boosted_result_count": sum(1 for g in groups if as_float(g.get("community_boost")) > 0),
        "feedback_adjusted_result_count": sum(1 for g in groups if as_float(g.get("feedback_advisory_delta")) != 0),
        "feedback_boosted_result_count": sum(1 for g in groups if as_float(g.get("feedback_advisory_delta")) > 0),
        "feedback_penalized_result_count": sum(1 for g in groups if as_float(g.get("feedback_advisory_delta")) < 0),
        "community_count": community_count,
        "page_count": page_count,
        "hybrid_quality_status": quality_status(hybrid_report),
        "leiden_quality_status": quality_status(community_report),
        "feedback_memory_quality_status": quality_status(feedback_report),
        "feedback_memory_record_count": len(feedback_records),
        "feedback_event_count": int(feedback_summary.get("feedback_event_count") or 0),
        "prompt_injection_flagged_count": int(feedback_summary.get("prompt_injection_flagged_count") or 0),
        "raw_feedback_direct_to_llm_count": int(feedback_summary.get("raw_feedback_direct_to_llm_count") or 0),
        "feedback_can_answer_directly_count": int(feedback_summary.get("feedback_can_answer_directly_count") or 0),
        "feedback_can_prove_claims_count": int(feedback_summary.get("feedback_can_prove_claims_count") or 0),
        "feedback_can_mutate_source_truth_count": int(feedback_summary.get("feedback_can_mutate_source_truth_count") or 0),
        "unsafe_result_count": sum(1 for g in groups if as_text(g.get("safety_status")) == "unsafe" or as_list(g.get("unsafe_reasons"))),
        "community_as_proof_count": sum(1 for g in groups if as_bool(g.get("community_can_prove_claims"), default=False)),
        "feedback_as_proof_count": sum(1 for g in groups if as_bool(g.get("feedback_can_prove_claims"), default=False)),
        "direct_answer_allowed_result_count": sum(1 for g in groups if as_bool(g.get("can_answer_directly"), default=False) or as_bool(g.get("answer_allowed"), default=False)),
        "retrieval_only_answer_allowed_count": sum(1 for g in groups if as_bool(g.get("retrieval_only_answer_allowed"), default=False)),
        "source_truth_mutation_allowed_count": sum(1 for g in groups if as_bool(g.get("can_mutate_source_truth"), default=False) or as_bool(g.get("source_truth_mutation_allowed"), default=False)),
        "missing_page_id_count": sum(1 for g in groups if not as_text(g.get("page_id"))),
        "community_feedback_answer_policy": "advisory_only_no_proof_no_source_truth_mutation",
    }
    return summary


def quality_checks(
    summary: Mapping[str, Any],
    *,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_grouped_results: int = 1,
    min_community_boosted_results: int = 1,
    min_feedback_memory_records: int = 0,
    min_feedback_adjusted_results: int = 0,
    require_hybrid_quality_pass: bool = True,
    require_leiden_quality_pass: bool = True,
    require_feedback_quality_pass: bool = True,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    add("min_queries", int(summary.get("community_aware_query_count") or 0) >= min_queries, summary.get("community_aware_query_count"), f">= {min_queries}")
    add("min_queries_with_results", int(summary.get("queries_with_results_count") or 0) >= min_queries_with_results, summary.get("queries_with_results_count"), f">= {min_queries_with_results}")
    add("min_grouped_results", int(summary.get("grouped_result_count") or 0) >= min_grouped_results, summary.get("grouped_result_count"), f">= {min_grouped_results}")
    add("min_community_boosted_results", int(summary.get("community_boosted_result_count") or 0) >= min_community_boosted_results, summary.get("community_boosted_result_count"), f">= {min_community_boosted_results}")
    add("min_feedback_memory_records", int(summary.get("feedback_memory_record_count") or 0) >= min_feedback_memory_records, summary.get("feedback_memory_record_count"), f">= {min_feedback_memory_records}")
    add("min_feedback_adjusted_results", int(summary.get("feedback_adjusted_result_count") or 0) >= min_feedback_adjusted_results, summary.get("feedback_adjusted_result_count"), f">= {min_feedback_adjusted_results}")
    if require_hybrid_quality_pass:
        add("hybrid_quality_pass", summary.get("hybrid_quality_status") == "PASS", summary.get("hybrid_quality_status"), "PASS")
    if require_leiden_quality_pass:
        add("leiden_quality_pass", summary.get("leiden_quality_status") == "PASS", summary.get("leiden_quality_status"), "PASS")
    if require_feedback_quality_pass:
        add("feedback_quality_pass", summary.get("feedback_memory_quality_status") == "PASS", summary.get("feedback_memory_quality_status"), "PASS")
    add("unsafe_result_count_zero", int(summary.get("unsafe_result_count") or 0) == 0, summary.get("unsafe_result_count"), 0)
    add("community_as_proof_zero", int(summary.get("community_as_proof_count") or 0) == 0, summary.get("community_as_proof_count"), 0)
    add("feedback_as_proof_zero", int(summary.get("feedback_as_proof_count") or 0) == 0, summary.get("feedback_as_proof_count"), 0)
    add("direct_answer_allowed_zero", int(summary.get("direct_answer_allowed_result_count") or 0) == 0, summary.get("direct_answer_allowed_result_count"), 0)
    add("retrieval_only_answer_allowed_zero", int(summary.get("retrieval_only_answer_allowed_count") or 0) == 0, summary.get("retrieval_only_answer_allowed_count"), 0)
    add("source_truth_mutation_allowed_zero", int(summary.get("source_truth_mutation_allowed_count") or 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("raw_feedback_direct_to_llm_zero", int(summary.get("raw_feedback_direct_to_llm_count") or 0) == 0, summary.get("raw_feedback_direct_to_llm_count"), 0)
    add("feedback_can_answer_directly_zero", int(summary.get("feedback_can_answer_directly_count") or 0) == 0, summary.get("feedback_can_answer_directly_count"), 0)
    add("feedback_can_prove_claims_zero", int(summary.get("feedback_can_prove_claims_count") or 0) == 0, summary.get("feedback_can_prove_claims_count"), 0)
    add("feedback_can_mutate_source_truth_zero", int(summary.get("feedback_can_mutate_source_truth_count") or 0) == 0, summary.get("feedback_can_mutate_source_truth_count"), 0)
    return checks


def quality_status_from_checks(checks: Sequence[Mapping[str, Any]]) -> str:
    return "PASS" if all(as_bool(check.get("passed"), default=False) for check in checks) else "FAIL"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Community-Aware Retrieval Simulation v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "community_aware_query_count",
        "grouped_result_count",
        "community_boosted_result_count",
        "feedback_adjusted_result_count",
        "feedback_memory_record_count",
        "unsafe_result_count",
        "community_as_proof_count",
        "feedback_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Top results")
    for query_result in as_list(report.get("query_results")):
        if not isinstance(query_result, Mapping):
            continue
        lines.append("")
        lines.append(f"### {query_result.get('query_id')}")
        for group in as_list(query_result.get("ranked_groups"))[:5]:
            if not isinstance(group, Mapping):
                continue
            lines.append(
                f"- rank {group.get('community_aware_rank')}: {group.get('page_id')} "
                f"score={group.get('community_aware_score')} "
                f"community_boost={group.get('community_boost')} "
                f"feedback_delta={group.get('feedback_advisory_delta')}"
            )
    lines.append("")
    lines.append("Community and feedback signals are advisory only and cannot prove claims.")
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Community-Aware Retrieval Simulation v1</title></head><body><pre>" + escaped + "</pre></body></html>\n"


def build_community_aware_retrieval_sim(
    *,
    hybrid_report_path: str | Path = DEFAULT_HYBRID_REPORT,
    leiden_communities_path: str | Path = DEFAULT_LEIDEN_COMMUNITIES,
    feedback_memory_path: str | Path = DEFAULT_FEEDBACK_MEMORY,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    max_groups: int = 8,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_grouped_results: int = 1,
    min_community_boosted_results: int = 1,
    min_feedback_memory_records: int = 0,
    min_feedback_adjusted_results: int = 0,
    require_hybrid_quality_pass: bool = True,
    require_leiden_quality_pass: bool = True,
    require_feedback_quality_pass: bool = True,
    write_quality: bool = True,
) -> dict[str, Any]:
    hybrid_report = read_json(hybrid_report_path)
    community_report = read_json(leiden_communities_path)
    feedback_report = read_json(feedback_memory_path)
    community_indexes = build_community_indexes(community_report)
    feedback_records = safe_feedback_records(feedback_report)
    source_query_results = extract_query_results(hybrid_report)
    query_results = [
        build_community_aware_query_result(
            query_result,
            community_indexes=community_indexes,
            feedback_records=feedback_records,
            max_groups=max_groups,
        )
        for query_result in source_query_results
    ]
    summary = summarize_report(
        query_results,
        hybrid_report=hybrid_report,
        community_report=community_report,
        feedback_report=feedback_report,
        feedback_records=feedback_records,
    )
    checks = quality_checks(
        summary,
        min_queries=min_queries,
        min_queries_with_results=min_queries_with_results,
        min_grouped_results=min_grouped_results,
        min_community_boosted_results=min_community_boosted_results,
        min_feedback_memory_records=min_feedback_memory_records,
        min_feedback_adjusted_results=min_feedback_adjusted_results,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_leiden_quality_pass=require_leiden_quality_pass,
        require_feedback_quality_pass=require_feedback_quality_pass,
    )
    status = quality_status_from_checks(checks)
    out_dir = Path(output_dir)
    report_path = out_dir / "trace_net_community_aware_retrieval_sim_v1.json"
    results_path = out_dir / "trace_net_community_aware_retrieval_sim_v1_results.jsonl"
    groups_path = out_dir / "trace_net_community_aware_retrieval_sim_v1_groups.jsonl"
    summary_path = out_dir / "trace_net_community_aware_retrieval_sim_v1_summary.json"
    manifest_path = out_dir / "trace_net_community_aware_retrieval_sim_v1_manifest.json"
    quality_path = out_dir / "trace_net_community_aware_retrieval_sim_v1_quality.json"
    markdown_path = out_dir / "trace_net_community_aware_retrieval_sim_v1.md"
    html_path = out_dir / "trace_net_community_aware_retrieval_sim_v1.html"

    all_groups = [g for qr in query_results for g in qr.get("ranked_groups", [])]
    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "COMMUNITY_AWARE_RETRIEVAL_SIM_BUILT",
        "quality_status": status,
        "created_at": now_iso(),
        "source_paths": {
            "hybrid_report": str(hybrid_report_path),
            "leiden_communities": str(leiden_communities_path),
            "feedback_memory": str(feedback_memory_path),
        },
        "query_results": query_results,
        "groups": all_groups,
        "summary": summary,
        "quality": {"status": status, "checks": checks},
        "community_feedback_policy": {
            "community_signals_are_source_truth": False,
            "feedback_signals_are_source_truth": False,
            "community_can_answer_directly": False,
            "feedback_can_answer_directly": False,
            "community_can_prove_claims": False,
            "feedback_can_prove_claims": False,
            "requires_source_resolution": True,
            "requires_citation": True,
            "requires_authority_gate": True,
        },
        "report_path": str(report_path),
        "results_path": str(results_path),
        "groups_path": str(groups_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
    }
    write_json(report_path, report)
    write_jsonl(results_path, query_results)
    write_jsonl(groups_path, all_groups)
    write_json(summary_path, summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": report["created_at"],
        "report_path": str(report_path),
        "results_path": str(results_path),
        "groups_path": str(groups_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_paths": report["source_paths"],
    }
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, {"status": status, "summary": summary, "checks": checks, "report_path": str(report_path)})
    md = render_markdown(report)
    markdown_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    return report


def check_community_aware_retrieval_quality(
    *,
    report_path: str | Path,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_grouped_results: int = 1,
    min_community_boosted_results: int = 1,
    min_feedback_memory_records: int = 0,
    min_feedback_adjusted_results: int = 0,
    require_hybrid_quality_pass: bool = True,
    require_leiden_quality_pass: bool = True,
    require_feedback_quality_pass: bool = True,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path)
    summary = dict(report.get("summary") or {})
    checks = quality_checks(
        summary,
        min_queries=min_queries,
        min_queries_with_results=min_queries_with_results,
        min_grouped_results=min_grouped_results,
        min_community_boosted_results=min_community_boosted_results,
        min_feedback_memory_records=min_feedback_memory_records,
        min_feedback_adjusted_results=min_feedback_adjusted_results,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_leiden_quality_pass=require_leiden_quality_pass,
        require_feedback_quality_pass=require_feedback_quality_pass,
    )
    status = quality_status_from_checks(checks)
    quality = {"status": status, "summary": summary, "checks": checks, "report_path": str(report_path)}
    if write_json_report:
        qpath = Path(report_path).with_name("trace_net_community_aware_retrieval_sim_v1_quality.json")
        write_json(qpath, quality)
        quality["quality_path"] = str(qpath)
    return quality



def run_community_aware_retrieval_sim(
    *,
    hybrid_report_path: str | Path = DEFAULT_HYBRID_REPORT,
    leiden_communities_path: str | Path = DEFAULT_LEIDEN_COMMUNITIES,
    feedback_memory_path: str | Path = DEFAULT_FEEDBACK_MEMORY,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    max_groups: int | None = None,
    max_groups_per_query: int | None = None,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_grouped_results: int = 1,
    min_community_boosted_results: int = 1,
    min_feedback_memory_records: int = 0,
    min_feedback_adjusted_results: int | None = None,
    min_feedback_boosted_results: int | None = None,
    require_hybrid_quality_pass: bool = True,
    require_leiden_quality_pass: bool = True,
    require_feedback_quality_pass: bool = True,
    write_quality: bool = True,
) -> dict[str, Any]:
    """Backward-compatible public entrypoint used by scripts/tests.

    Earlier drafts called this function ``run_community_aware_retrieval_sim`` and used
    ``max_groups_per_query`` / ``min_feedback_boosted_results`` argument names. The
    implementation function is ``build_community_aware_retrieval_sim``. This wrapper
    keeps those names stable for users who already installed the first Step 22 patch.
    """
    resolved_max_groups = max_groups if max_groups is not None else max_groups_per_query
    if resolved_max_groups is None:
        resolved_max_groups = 8
    resolved_feedback_min = (
        min_feedback_adjusted_results
        if min_feedback_adjusted_results is not None
        else (min_feedback_boosted_results if min_feedback_boosted_results is not None else 0)
    )
    return build_community_aware_retrieval_sim(
        hybrid_report_path=hybrid_report_path,
        leiden_communities_path=leiden_communities_path,
        feedback_memory_path=feedback_memory_path,
        output_dir=output_dir,
        max_groups=resolved_max_groups,
        min_queries=min_queries,
        min_queries_with_results=min_queries_with_results,
        min_grouped_results=min_grouped_results,
        min_community_boosted_results=min_community_boosted_results,
        min_feedback_memory_records=min_feedback_memory_records,
        min_feedback_adjusted_results=resolved_feedback_min,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_leiden_quality_pass=require_leiden_quality_pass,
        require_feedback_quality_pass=require_feedback_quality_pass,
        write_quality=write_quality,
    )


def quality_report(
    report_path: str | Path,
    *,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_grouped_results: int = 1,
    min_community_boosted_results: int = 1,
    min_feedback_memory_records: int = 0,
    min_feedback_adjusted_results: int | None = None,
    min_feedback_boosted_results: int | None = None,
    require_hybrid_quality_pass: bool = True,
    require_leiden_quality_pass: bool = True,
    require_feedback_quality_pass: bool = True,
    write_json_flag: bool = False,
    write_json_report: bool | None = None,
) -> dict[str, Any]:
    """Backward-compatible public quality entrypoint.

    Supports both ``write_json_flag`` and ``write_json_report``, plus the older
    ``min_feedback_boosted_results`` name.
    """
    resolved_feedback_min = (
        min_feedback_adjusted_results
        if min_feedback_adjusted_results is not None
        else (min_feedback_boosted_results if min_feedback_boosted_results is not None else 0)
    )
    resolved_write = write_json_flag if write_json_report is None else write_json_report
    return check_community_aware_retrieval_quality(
        report_path=report_path,
        min_queries=min_queries,
        min_queries_with_results=min_queries_with_results,
        min_grouped_results=min_grouped_results,
        min_community_boosted_results=min_community_boosted_results,
        min_feedback_memory_records=min_feedback_memory_records,
        min_feedback_adjusted_results=resolved_feedback_min,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_leiden_quality_pass=require_leiden_quality_pass,
        require_feedback_quality_pass=require_feedback_quality_pass,
        write_json_report=resolved_write,
    )

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net community-aware retrieval simulation v1.")
    parser.add_argument("--hybrid-report", default=str(DEFAULT_HYBRID_REPORT))
    parser.add_argument("--leiden-communities", default=str(DEFAULT_LEIDEN_COMMUNITIES))
    parser.add_argument("--feedback-memory", default=str(DEFAULT_FEEDBACK_MEMORY))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-groups", type=int, default=8)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-queries-with-results", type=int, default=1)
    parser.add_argument("--min-grouped-results", type=int, default=1)
    parser.add_argument("--min-community-boosted-results", type=int, default=1)
    parser.add_argument("--min-feedback-memory-records", type=int, default=0)
    parser.add_argument("--min-feedback-adjusted-results", type=int, default=0)
    parser.add_argument("--no-require-hybrid-quality-pass", action="store_true")
    parser.add_argument("--no-require-leiden-quality-pass", action="store_true")
    parser.add_argument("--no-require-feedback-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net community-aware retrieval simulation quality v1.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-queries-with-results", type=int, default=1)
    parser.add_argument("--min-grouped-results", type=int, default=1)
    parser.add_argument("--min-community-boosted-results", type=int, default=1)
    parser.add_argument("--min-feedback-memory-records", type=int, default=0)
    parser.add_argument("--min-feedback-adjusted-results", type=int, default=0)
    parser.add_argument("--no-require-hybrid-quality-pass", action="store_true")
    parser.add_argument("--no-require-leiden-quality-pass", action="store_true")
    parser.add_argument("--no-require-feedback-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_community_aware_retrieval_sim(
        hybrid_report_path=args.hybrid_report,
        leiden_communities_path=args.leiden_communities,
        feedback_memory_path=args.feedback_memory,
        output_dir=args.output_dir,
        max_groups=args.max_groups,
        min_queries=args.min_queries,
        min_queries_with_results=args.min_queries_with_results,
        min_grouped_results=args.min_grouped_results,
        min_community_boosted_results=args.min_community_boosted_results,
        min_feedback_memory_records=args.min_feedback_memory_records,
        min_feedback_adjusted_results=args.min_feedback_adjusted_results,
        require_hybrid_quality_pass=not args.no_require_hybrid_quality_pass,
        require_leiden_quality_pass=not args.no_require_leiden_quality_pass,
        require_feedback_quality_pass=not args.no_require_feedback_quality_pass,
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net community-aware retrieval simulation v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "community_aware_query_count",
        "queries_with_results_count",
        "grouped_result_count",
        "community_boosted_result_count",
        "feedback_adjusted_result_count",
        "feedback_boosted_result_count",
        "feedback_penalized_result_count",
        "community_count",
        "feedback_memory_record_count",
        "unsafe_result_count",
        "community_as_proof_count",
        "feedback_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


def quality_main(argv: Sequence[str] | None = None) -> int:
    args = build_quality_arg_parser().parse_args(argv)
    quality = check_community_aware_retrieval_quality(
        report_path=args.report_path,
        min_queries=args.min_queries,
        min_queries_with_results=args.min_queries_with_results,
        min_grouped_results=args.min_grouped_results,
        min_community_boosted_results=args.min_community_boosted_results,
        min_feedback_memory_records=args.min_feedback_memory_records,
        min_feedback_adjusted_results=args.min_feedback_adjusted_results,
        require_hybrid_quality_pass=not args.no_require_hybrid_quality_pass,
        require_leiden_quality_pass=not args.no_require_leiden_quality_pass,
        require_feedback_quality_pass=not args.no_require_feedback_quality_pass,
        write_json_report=args.write_json,
    )
    summary = quality["summary"]
    print("TRACE-Net community-aware retrieval simulation v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "community_aware_query_count",
        "queries_with_results_count",
        "grouped_result_count",
        "community_boosted_result_count",
        "feedback_adjusted_result_count",
        "feedback_memory_record_count",
        "unsafe_result_count",
        "community_as_proof_count",
        "feedback_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality['quality_path']}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
