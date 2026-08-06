"""TRACE-Net Hybrid Retrieval v3.

Hybrid Retrieval v3 is a read-only retrieval control layer that consumes the
PASS-certified Hybrid Retrieval v2 report and the PASS-certified Corrective
Retrieval Planner v1 report. It can also consume the PASS-certified live
OpenSearch exact-search index as a read-only exact-hit channel. It turns the v2
ranked groups into CRAG-aware retrieval groups by attaching safe corrective
routing metadata, optional live exact-search hits, and small deterministic
re-ranking adjustments.

Safety contract:
- Retrieval may rank and route possible evidence.
- Retrieval cannot answer directly.
- Retrieval cannot prove claims.
- Corrective Retrieval Planner actions are routing instructions only.
- Feedback, community, category, and corrective signals are advisory only.
- No Postgres, Qdrant, OpenSearch, source, citation, graph, or artifact-truth
  writes occur. Live OpenSearch use is read-only search only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_hybrid_retrieval_v3"
ALGORITHM = "trace_net_crag_aware_hybrid_retrieval_v3"

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/hybrid_retrieval_v3")
DEFAULT_HYBRID_V2 = Path(
    "local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json"
)
DEFAULT_CORRECTIVE_PLANNER = Path(
    "local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1.json"
)
DEFAULT_GRAPH_ENRICHMENT = Path(
    "local_data/organization/trace_net/graph_query_evidence_enrichment/trace_net_graph_query_evidence_enrichment_v1.json"
)
DEFAULT_OPENSEARCH_LOADER_SMOKE = Path(
    "local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.json"
)
DEFAULT_OPENSEARCH_LIVE_LOADER = Path(
    "local_data/organization/trace_net/opensearch_live_loader/trace_net_opensearch_live_loader_v1.json"
)
DEFAULT_OPENSEARCH_URL = "http://localhost:9200"
DEFAULT_OPENSEARCH_INDEX_NAME = "trace_net_safe_search_v1"
DEFAULT_QDRANT_PAGE_PROFILE_QUALITY = Path(
    "local_data/organization/trace_net/qdrant_page_retrieval_profiles_ollama_bge_m3/trace_net_page_retrieval_profiles_qdrant_v1_quality.json"
)

DEFAULT_OUTPUT_FILE = "trace_net_hybrid_retrieval_v3.json"
DEFAULT_RESULTS_FILE = "trace_net_hybrid_retrieval_v3_results.jsonl"
DEFAULT_GROUPS_FILE = "trace_net_hybrid_retrieval_v3_groups.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_hybrid_retrieval_v3_summary.json"
DEFAULT_QUALITY_FILE = "trace_net_hybrid_retrieval_v3_quality.json"
DEFAULT_MANIFEST_FILE = "trace_net_hybrid_retrieval_v3_manifest.json"

PAGE_ID_RE = re.compile(r"\bt_p_\d+_\d+_p\d{6}\b")

SAFE_FALSE_FIELDS = (
    "can_answer_directly",
    "can_prove_claims",
    "answer_permission",
    "final_answer_allowed",
    "retrieval_only_answer_allowed",
    "source_truth_mutation_allowed",
    "can_mutate_source_truth",
    "postgres_write_attempted",
    "qdrant_write_attempted",
    "opensearch_write_attempted",
    "community_as_proof",
    "category_as_proof",
    "feedback_as_proof",
    "corrective_action_as_proof",
)

HIGH_RISK_ISSUES = {
    "semantic_page_target_miss",
    "trace_pack_review_recommended",
    "tiff_content_audit_fail",
}
REVIEW_ISSUES = {
    "semantic_page_target_miss",
    "target_page_low_rank",
    "graph_evidence_review_flag",
    "tiff_content_audit_review",
    "trace_pack_review_recommended",
}
CHANNEL_ISSUES = {
    "exact_search_channel_available",
    "semantic_search_channel_available",
    "trace_pack_safe_to_use_final_gate_path",
}


class HybridRetrievalV3Error(RuntimeError):
    """Raised when Hybrid Retrieval v3 cannot be built safely."""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


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


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def stable_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


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
        if text in {"1", "true", "yes", "y", "pass", "allowed"}:
            return True
        if text in {"0", "false", "no", "n", "fail", "blocked"}:
            return False
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
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
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        for key in ("quality_status", "status"):
            value = as_text(summary.get(key)).upper()
            if value in {"PASS", "FAIL"}:
                return value
    return "UNKNOWN" if payload else "MISSING"


def source_quality_statuses(
    *,
    hybrid_v2: Mapping[str, Any],
    corrective_planner: Mapping[str, Any],
    graph_enrichment: Mapping[str, Any],
    opensearch_loader_smoke: Mapping[str, Any],
    qdrant_page_profile_quality: Mapping[str, Any],
    opensearch_live_loader: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    planner_summary = corrective_planner.get("summary") if isinstance(corrective_planner.get("summary"), Mapping) else {}
    nested = planner_summary.get("source_quality_statuses") if isinstance(planner_summary, Mapping) else {}
    qdrant_from_planner = ""
    if isinstance(nested, Mapping):
        qdrant_from_planner = as_text(nested.get("qdrant_page_profile_quality")).upper()
    statuses = {
        "hybrid_retrieval_v2": quality_status(hybrid_v2),
        "corrective_retrieval_planner": quality_status(corrective_planner),
        "graph_query_evidence_enrichment": quality_status(graph_enrichment),
        "opensearch_loader_smoke": quality_status(opensearch_loader_smoke),
        "qdrant_page_profile_quality": qdrant_from_planner if qdrant_from_planner in {"PASS", "FAIL"} else quality_status(qdrant_page_profile_quality),
    }
    if opensearch_live_loader is not None and opensearch_live_loader:
        statuses["opensearch_live_loader"] = quality_status(opensearch_live_loader)
    return statuses


def quality_is_pass(payload: Mapping[str, Any]) -> bool:
    return quality_status(payload) == "PASS"


def source_quality_pass(statuses: Mapping[str, str], *, required: Sequence[str]) -> bool:
    return all(as_text(statuses.get(name)).upper() == "PASS" for name in required)


def query_results(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("query_results") or payload.get("results") or []
    return [dict(r) for r in rows if isinstance(r, Mapping)] if isinstance(rows, list) else []


def groups_from_query_result(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = row.get("ranked_groups") or row.get("groups") or row.get("retrieval_groups") or []
    return [dict(g) for g in rows if isinstance(g, Mapping)] if isinstance(rows, list) else []


def result_query_id(row: Mapping[str, Any], idx: int) -> str:
    return as_text(row.get("query_id") or row.get("id") or f"query_{idx + 1:03d}")


def page_ids_from_record(record: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "page_id",
        "target_page_id",
        "expected_page_id",
        "source_page_id",
        "graph_page_id",
    ):
        if record.get(key):
            values.append(record.get(key))
    for key in ("page_ids", "source_page_ids", "affected_page_ids", "enriched_page_ids"):
        values.extend(as_list(record.get(key)))
    record_id = as_text(record.get("record_id") or record.get("id"))
    values.extend(PAGE_ID_RE.findall(record_id))
    return unique_texts(values)


def page_ids_from_group(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("page_id", "target_page_id", "expected_page_id"):
        if group.get(key):
            values.append(group.get(key))
    for key in ("page_ids", "source_page_ids"):
        values.extend(as_list(group.get(key)))
    for nested_key in ("exact_hits", "semantic_groups", "candidate_hits", "page_profile_hits", "hits"):
        for item in as_list(group.get(nested_key)):
            if isinstance(item, Mapping):
                values.extend(page_ids_from_group(item))
    return unique_texts(values)


def citation_ids_from_group(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("citation_ids")))
    if group.get("citation_id"):
        values.append(group.get("citation_id"))
    for nested_key in ("exact_hits", "semantic_groups", "candidate_hits", "page_profile_hits", "hits"):
        for item in as_list(group.get(nested_key)):
            if isinstance(item, Mapping):
                values.extend(citation_ids_from_group(item))
    return unique_texts(values)


def community_ids_from_group(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("community_ids")))
    if group.get("community_id"):
        values.append(group.get("community_id"))
    for nested_key in ("exact_hits", "semantic_groups", "candidate_hits", "page_profile_hits", "hits"):
        for item in as_list(group.get(nested_key)):
            if isinstance(item, Mapping):
                values.extend(community_ids_from_group(item))
    return unique_texts(values)


def part_numbers_from_group(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("part_numbers")))
    if group.get("part_number"):
        values.append(group.get("part_number"))
    for nested_key in ("exact_hits", "semantic_groups", "candidate_hits", "page_profile_hits", "hits"):
        for item in as_list(group.get(nested_key)):
            if isinstance(item, Mapping):
                values.extend(part_numbers_from_group(item))
    return unique_texts(values)


def base_group_score(group: Mapping[str, Any]) -> float:
    for key in (
        "hybrid_v2_score",
        "hybrid_score",
        "community_aware_score",
        "combined_score",
        "score",
        "group_score",
        "base_hybrid_score",
    ):
        value = group.get(key)
        if value is not None:
            return as_float(value)
    rank = as_int(group.get("hybrid_v2_rank") or group.get("rank") or group.get("community_aware_rank"), 99)
    return max(0.0, 1.0 - max(0, rank - 1) * 0.05)


def group_has_exact_signal(group: Mapping[str, Any]) -> bool:
    if as_bool(group.get("has_exact_hit")) or as_float(group.get("exact_score")) > 0:
        return True
    return bool(group.get("exact_hits"))


def group_has_semantic_signal(group: Mapping[str, Any]) -> bool:
    if as_bool(group.get("has_semantic_hit")) or as_float(group.get("semantic_score")) > 0:
        return True
    return bool(group.get("semantic_groups") or group.get("candidate_hits") or group.get("page_profile_hits"))


def group_has_graph_signal(group: Mapping[str, Any]) -> bool:
    if as_bool(group.get("graph_path_resolved")) or as_bool(group.get("source_identity_resolved")):
        return True
    if group.get("graph_path_card") or group.get("dublin_core_identity"):
        return True
    return False


def live_hit_id(hit: Mapping[str, Any]) -> str:
    return as_text(hit.get("opensearch_document_id") or hit.get("_id") or hit.get("document_id") or stable_hash(hit))


def live_hit_page_ids(hit: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    source = hit.get("_source") if isinstance(hit.get("_source"), Mapping) else hit
    if isinstance(source, Mapping):
        for key in ("page_id", "source_page_id", "target_page_id"):
            if source.get(key):
                values.append(source.get(key))
        for key in ("page_ids", "source_page_ids"):
            values.extend(as_list(source.get(key)))
    values.extend(PAGE_ID_RE.findall(stable_json(hit)))
    return unique_texts(values)


def live_hit_part_numbers(hit: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    source = hit.get("_source") if isinstance(hit.get("_source"), Mapping) else hit
    if isinstance(source, Mapping):
        if source.get("part_number"):
            values.append(source.get("part_number"))
        values.extend(as_list(source.get("part_numbers")))
        for key in ("text", "title", "search_text"):
            text = as_text(source.get(key))
            values.extend(re.findall(r"\b\d{3}-\d{5}-\d{3}\b", text))
    return unique_texts(values)


def compact_live_hit(hit: Mapping[str, Any]) -> dict[str, Any]:
    source = hit.get("_source") if isinstance(hit.get("_source"), Mapping) else hit
    source = source if isinstance(source, Mapping) else {}
    page_ids = live_hit_page_ids(hit)
    text = as_text(source.get("text") or source.get("search_text") or source.get("title"))
    return {
        "opensearch_document_id": live_hit_id(hit),
        "document_type": as_text(source.get("document_type") or hit.get("document_type")),
        "page_id": as_text(source.get("page_id")) or None,
        "source_page_ids": page_ids,
        "part_numbers": live_hit_part_numbers(hit),
        "score": as_float(hit.get("_score") or hit.get("score")),
        "text_preview": text[:260],
        "retrieval_only": True,
        "routing_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "safe_for_opensearch": as_bool(source.get("safe_for_opensearch"), True),
        "source_trace_present": as_bool(source.get("source_trace_present"), bool(page_ids)),
    }


def live_hit_matches_group(hit: Mapping[str, Any], group: Mapping[str, Any]) -> bool:
    hit_pages = set(live_hit_page_ids(hit))
    group_pages = set(as_list(group.get("source_page_ids")) or page_ids_from_group(group))
    if hit_pages and group_pages and hit_pages & group_pages:
        return True
    hit_parts = set(live_hit_part_numbers(hit))
    group_parts = set(part_numbers_from_group(group) or as_list(group.get("part_numbers")))
    return bool(hit_parts and group_parts and hit_parts & group_parts)


def live_query_payload(query_text: str, size: int) -> dict[str, Any]:
    should = []
    for field, boost in (
        ("part_number", 6),
        ("part_numbers", 6),
        ("text", 5),
        ("title", 4),
        ("page_id", 2),
        ("source_page_ids", 2),
        ("opensearch_document_id", 1),
    ):
        should.append({"match_phrase": {field: {"query": query_text, "boost": boost}}})
    return {
        "query": {
            "bool": {
                "should": should,
                "minimum_should_match": 1,
                "filter": [
                    {"term": {"retrieval_only": True}},
                    {"term": {"safe_for_opensearch": True}},
                ],
            }
        },
        "size": max(1, size),
    }


def run_live_opensearch_query(
    *,
    opensearch_url: str,
    index_name: str,
    query_text: str,
    max_hits: int,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    if not query_text or max_hits <= 0:
        return []
    url = opensearch_url.rstrip("/") + f"/{index_name}/_search"
    body = json.dumps(live_query_payload(query_text, max_hits)).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    hits = payload.get("hits", {}).get("hits", []) if isinstance(payload, Mapping) else []
    return [compact_live_hit(hit) for hit in hits if isinstance(hit, Mapping)]


def build_live_hits_by_query_id(
    *,
    hybrid_v2: Mapping[str, Any],
    opensearch_url: str,
    index_name: str,
    max_hits_per_query: int,
) -> dict[str, list[dict[str, Any]]]:
    hits_by_query: dict[str, list[dict[str, Any]]] = {}
    for idx, row in enumerate(query_results(hybrid_v2)):
        query_id = result_query_id(row, idx)
        query_text = as_text(row.get("query") or row.get("user_query") or query_id)
        hits_by_query[query_id] = run_live_opensearch_query(
            opensearch_url=opensearch_url,
            index_name=index_name,
            query_text=query_text,
            max_hits=max_hits_per_query,
        )
    return hits_by_query


def apply_live_opensearch_hits_to_groups(
    *,
    query_id: str,
    query_text: str,
    groups: list[dict[str, Any]],
    live_hits: Sequence[Mapping[str, Any]],
    max_groups_per_query: int,
) -> list[dict[str, Any]]:
    if not live_hits:
        return groups
    attached_hit_ids: set[str] = set()
    out = [dict(g) for g in groups]
    for group in out:
        matches = [compact_live_hit(hit) for hit in live_hits if live_hit_matches_group(hit, group)]
        if not matches:
            group.setdefault("live_opensearch_exact_hit_count", 0)
            group.setdefault("has_live_opensearch_exact_signal", False)
            continue
        for match in matches:
            attached_hit_ids.add(match["opensearch_document_id"])
        live_boost = round(min(0.16, 0.04 * len(matches)), 6)
        group["live_opensearch_exact_hit_count"] = len(matches)
        group["live_opensearch_exact_hits"] = matches[:5]
        group["live_opensearch_hit_document_types"] = unique_texts(m.get("document_type") for m in matches)
        group["has_live_opensearch_exact_signal"] = True
        group["live_opensearch_score_boost"] = live_boost
        group["hybrid_v3_score"] = round(as_float(group.get("hybrid_v3_score")) + live_boost, 6)
        group["ranking_explanation"] = (as_text(group.get("ranking_explanation")) + "; live OpenSearch exact hits attached").strip("; ")
    for idx, hit in enumerate(live_hits, start=1):
        compact = compact_live_hit(hit)
        if compact["opensearch_document_id"] in attached_hit_ids:
            continue
        page_ids = compact.get("source_page_ids") or []
        if not page_ids:
            continue
        synthetic_score = round(0.62 + min(0.18, as_float(compact.get("score")) / 100.0), 6)
        out.append({
            "hybrid_v3_group_id": f"hybrid_v3_live_opensearch::{query_id}::{stable_hash(compact)}",
            "query_id": query_id,
            "query": query_text,
            "page_id": page_ids[0] if page_ids else None,
            "source_page_ids": page_ids,
            "citation_ids": [],
            "community_ids": [],
            "part_numbers": compact.get("part_numbers") or [],
            "base_hybrid_v2_score": 0.0,
            "channel_blend_score": 0.08,
            "corrective_score_adjustment": 0.0,
            "live_opensearch_score_boost": synthetic_score,
            "hybrid_v3_score": synthetic_score,
            "has_exact_signal": True,
            "has_semantic_signal": False,
            "has_graph_source_signal": bool(page_ids),
            "has_live_opensearch_exact_signal": True,
            "live_opensearch_exact_hit_count": 1,
            "live_opensearch_exact_hits": [compact],
            "live_opensearch_hit_document_types": unique_texts([compact.get("document_type")]),
            "corrective_record_count": 0,
            "corrective_issue_types": [],
            "corrective_recommended_actions": [],
            "corrective_max_severity": "INFO",
            "review_required_before_final_answer": False,
            "audit_required_before_final_answer": False,
            "safe_routing_status": "ROUTING_READY",
            "ranking_explanation": "created from live OpenSearch exact-search hit; routing only",
            "source_group_unsafe_flag_count": 0,
            "retrieval_only": True,
            "routing_only": True,
            "answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "answer_permission": False,
            "final_answer_allowed": False,
            "retrieval_only_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "can_mutate_source_truth": False,
            "community_as_proof": False,
            "category_as_proof": False,
            "feedback_as_proof": False,
            "corrective_action_as_proof": False,
            "postgres_write_attempted": False,
            "qdrant_write_attempted": False,
            "opensearch_write_attempted": False,
        })
        if max_groups_per_query > 0 and len(out) >= max_groups_per_query:
            break
    return out


def group_is_unsafe_input(group: Mapping[str, Any]) -> bool:
    return any(as_bool(group.get(field)) for field in SAFE_FALSE_FIELDS)


def corrective_records(planner: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = (
        planner.get("corrective_retrieval_records")
        or planner.get("diagnostic_records")
        or planner.get("correction_records")
        or planner.get("records")
        or []
    )
    return [dict(r) for r in rows if isinstance(r, Mapping)] if isinstance(rows, list) else []


def corrective_index(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    channel_records: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        issue_type = as_text(item.get("issue_type"))
        if issue_type in CHANNEL_ISSUES:
            channel_records.append(item)
        pages = page_ids_from_record(item)
        for page_id in pages:
            by_page[page_id].append(item)
    return by_page, channel_records


def graph_enrichment_pages(graph_enrichment: Mapping[str, Any]) -> set[str]:
    pages: set[str] = set()
    rows = (
        graph_enrichment.get("enriched_page_records")
        or graph_enrichment.get("enriched_pages")
        or graph_enrichment.get("records")
        or []
    )
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                pages.update(page_ids_from_record(row))
    return pages


def channel_summary(channel_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    issue_types = Counter(as_text(r.get("issue_type")) for r in channel_records)
    actions: list[Any] = []
    for record in channel_records:
        actions.extend(as_list(record.get("recommended_actions")))
    return {
        "exact_search_channel_available": issue_types.get("exact_search_channel_available", 0) > 0,
        "semantic_search_channel_available": issue_types.get("semantic_search_channel_available", 0) > 0,
        "final_gate_path_seen": issue_types.get("trace_pack_safe_to_use_final_gate_path", 0) > 0,
        "channel_issue_counts": dict(sorted(issue_types.items())),
        "channel_recommended_actions": unique_texts(actions),
    }


def actions_from_records(records: Sequence[Mapping[str, Any]]) -> list[str]:
    actions: list[Any] = []
    for record in records:
        actions.extend(as_list(record.get("recommended_actions")))
    return unique_texts(actions)


def issue_types_from_records(records: Sequence[Mapping[str, Any]]) -> list[str]:
    return unique_texts(record.get("issue_type") for record in records)


def severity_from_records(records: Sequence[Mapping[str, Any]]) -> str:
    order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0, "": 0}
    best = ""
    best_score = -1
    for record in records:
        severity = as_text(record.get("severity")).upper()
        score = order.get(severity, 0)
        if score > best_score:
            best = severity or "INFO"
            best_score = score
    return best or "INFO"


def corrective_score_adjustment(records: Sequence[Mapping[str, Any]], group: Mapping[str, Any]) -> float:
    if not records:
        return 0.0
    adjustment = 0.0
    issue_types = set(issue_types_from_records(records))
    if "target_page_low_rank" in issue_types:
        adjustment += 0.06
    if "semantic_page_target_miss" in issue_types:
        adjustment -= 0.08
    if "graph_evidence_review_flag" in issue_types:
        adjustment -= 0.04
    if "tiff_content_audit_review" in issue_types:
        adjustment -= 0.05
    if "trace_pack_review_recommended" in issue_types:
        adjustment -= 0.06
    if group_has_exact_signal(group) and "run_opensearch_exact_if_identifier_present" in actions_from_records(records):
        adjustment += 0.05
    if group_has_graph_signal(group) and any(action in actions_from_records(records) for action in ("apply_graph_anchor_rerank", "rerank_with_graph_page_anchor", "rerank_with_graph_source_anchors")):
        adjustment += 0.04
    return round(max(-0.25, min(0.18, adjustment)), 6)


def normalize_group(
    *,
    query_id: str,
    query_text: str,
    source_group: Mapping[str, Any],
    group_index: int,
    page_corrective_index: Mapping[str, Sequence[Mapping[str, Any]]],
    graph_pages: set[str],
) -> dict[str, Any]:
    page_ids = page_ids_from_group(source_group)
    primary_page_id = as_text(source_group.get("page_id")) or (page_ids[0] if page_ids else "")
    related_records: list[dict[str, Any]] = []
    seen = set()
    for page_id in page_ids:
        for record in page_corrective_index.get(page_id, []):
            record_id = as_text(record.get("record_id") or record.get("id") or stable_hash(record))
            if record_id not in seen:
                related_records.append(dict(record))
                seen.add(record_id)
    issue_types = issue_types_from_records(related_records)
    actions = actions_from_records(related_records)
    severity = severity_from_records(related_records) if related_records else "INFO"
    review_required = any(issue in REVIEW_ISSUES for issue in issue_types)
    high_risk = any(issue in HIGH_RISK_ISSUES for issue in issue_types)
    base_score = base_group_score(source_group)
    exact_signal = group_has_exact_signal(source_group)
    semantic_signal = group_has_semantic_signal(source_group)
    graph_signal = group_has_graph_signal(source_group) or bool(set(page_ids) & graph_pages)
    channel_blend = 0.0
    if exact_signal:
        channel_blend += 0.05
    if semantic_signal:
        channel_blend += 0.04
    if graph_signal:
        channel_blend += 0.04
    if citation_ids_from_group(source_group):
        channel_blend += 0.02
    adjustment = corrective_score_adjustment(related_records, source_group)
    v3_score = round(max(0.0, base_score + channel_blend + adjustment), 6)
    explanation_parts = []
    if exact_signal:
        explanation_parts.append("exact-channel signal present")
    if semantic_signal:
        explanation_parts.append("semantic-channel signal present")
    if graph_signal:
        explanation_parts.append("graph/source anchor signal present")
    if related_records:
        explanation_parts.append("corrective planner attached safe routing actions")
    if review_required:
        explanation_parts.append("review route retained before final answer use")
    if not explanation_parts:
        explanation_parts.append("carried forward from Hybrid Retrieval v2")
    unsafe_input = group_is_unsafe_input(source_group)
    out = {
        "hybrid_v3_group_id": f"hybrid_v3::{query_id}::{stable_hash({'query': query_text, 'group': source_group, 'idx': group_index})}",
        "query_id": query_id,
        "query": query_text,
        "page_id": primary_page_id or None,
        "source_page_ids": page_ids,
        "citation_ids": citation_ids_from_group(source_group),
        "community_ids": community_ids_from_group(source_group),
        "part_numbers": part_numbers_from_group(source_group),
        "base_hybrid_v2_score": round(base_score, 6),
        "channel_blend_score": round(channel_blend, 6),
        "corrective_score_adjustment": adjustment,
        "hybrid_v3_score": v3_score,
        "has_exact_signal": exact_signal,
        "has_semantic_signal": semantic_signal,
        "has_graph_source_signal": graph_signal,
        "corrective_record_count": len(related_records),
        "corrective_issue_types": issue_types,
        "corrective_recommended_actions": actions,
        "corrective_max_severity": severity,
        "review_required_before_final_answer": review_required,
        "audit_required_before_final_answer": high_risk,
        "safe_routing_status": "REVIEW_ROUTE_REQUIRED" if review_required else "ROUTING_READY",
        "ranking_explanation": "; ".join(explanation_parts),
        "source_group_unsafe_flag_count": 1 if unsafe_input else 0,
        "retrieval_only": True,
        "routing_only": True,
        "answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "can_mutate_source_truth": False,
        "community_as_proof": False,
        "category_as_proof": False,
        "feedback_as_proof": False,
        "corrective_action_as_proof": False,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
    }
    return out


def build_query_result(
    *,
    row: Mapping[str, Any],
    query_index: int,
    page_corrective_index: Mapping[str, Sequence[Mapping[str, Any]]],
    graph_pages: set[str],
    max_groups_per_query: int,
    live_opensearch_hits: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    query_id = result_query_id(row, query_index)
    query_text = as_text(row.get("query") or row.get("user_query") or query_id)
    source_groups = groups_from_query_result(row)
    normalized = [
        normalize_group(
            query_id=query_id,
            query_text=query_text,
            source_group=group,
            group_index=idx,
            page_corrective_index=page_corrective_index,
            graph_pages=graph_pages,
        )
        for idx, group in enumerate(source_groups, start=1)
    ]
    normalized = apply_live_opensearch_hits_to_groups(
        query_id=query_id,
        query_text=query_text,
        groups=normalized,
        live_hits=live_opensearch_hits or [],
        max_groups_per_query=max_groups_per_query,
    )
    normalized.sort(
        key=lambda g: (
            -as_float(g.get("hybrid_v3_score")),
            as_bool(g.get("review_required_before_final_answer")),
            as_text(g.get("page_id") or ""),
        )
    )
    if max_groups_per_query > 0:
        normalized = normalized[:max_groups_per_query]
    for rank, group in enumerate(normalized, start=1):
        group["hybrid_v3_rank"] = rank
    return {
        "query_id": query_id,
        "query": query_text,
        "intent": as_text(row.get("intent") or row.get("query_intent") or ""),
        "source_hybrid_v2_group_count": len(source_groups),
        "ranked_group_count": len(normalized),
        "groups_with_corrective_actions_count": sum(1 for g in normalized if as_int(g.get("corrective_record_count")) > 0),
        "review_required_group_count": sum(1 for g in normalized if as_bool(g.get("review_required_before_final_answer"))),
        "live_opensearch_exact_hit_group_count": sum(1 for g in normalized if as_int(g.get("live_opensearch_exact_hit_count")) > 0),
        "live_opensearch_exact_hit_count": sum(as_int(g.get("live_opensearch_exact_hit_count")) for g in normalized),
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "ranked_groups": normalized,
    }


def summarize(
    *,
    payload: Mapping[str, Any],
    source_statuses: Mapping[str, str],
    required_source_quality: Sequence[str],
    min_queries: int,
    min_queries_with_results: int,
    min_groups: int,
    min_corrective_groups: int,
    min_review_routed_groups: int,
    min_live_exact_hit_groups: int = 0,
    max_unsafe_groups: int = 0,
    require_no_answer_permission: bool,
) -> dict[str, Any]:
    query_rows = query_results(payload)
    all_groups = [group for row in query_rows for group in groups_from_query_result(row)]
    issue_counter = Counter()
    action_counter = Counter()
    severity_counter = Counter()
    for group in all_groups:
        issue_counter.update(as_list(group.get("corrective_issue_types")))
        action_counter.update(as_list(group.get("corrective_recommended_actions")))
        severity_counter.update([as_text(group.get("corrective_max_severity") or "INFO")])
    query_count = len(query_rows)
    queries_with_results = sum(1 for row in query_rows if groups_from_query_result(row))
    group_count = len(all_groups)
    corrective_group_count = sum(1 for group in all_groups if as_int(group.get("corrective_record_count")) > 0)
    review_group_count = sum(1 for group in all_groups if as_bool(group.get("review_required_before_final_answer")))
    audit_group_count = sum(1 for group in all_groups if as_bool(group.get("audit_required_before_final_answer")))
    live_exact_hit_group_count = sum(1 for group in all_groups if as_int(group.get("live_opensearch_exact_hit_count")) > 0)
    live_exact_hit_count = sum(as_int(group.get("live_opensearch_exact_hit_count")) for group in all_groups)
    unsafe_group_count = sum(as_int(group.get("source_group_unsafe_flag_count")) for group in all_groups)
    answer_permission_count = sum(
        1
        for group in all_groups
        if any(
            as_bool(group.get(field))
            for field in (
                "answer_allowed",
                "answer_permission",
                "final_answer_allowed",
                "retrieval_only_answer_allowed",
                "can_answer_directly",
                "can_prove_claims",
            )
        )
    )
    source_truth_mutation_allowed_count = sum(
        1
        for group in all_groups
        if as_bool(group.get("source_truth_mutation_allowed")) or as_bool(group.get("can_mutate_source_truth"))
    )
    hard_zero_counts = {
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": sum(1 for group in all_groups if as_bool(group.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for group in all_groups if as_bool(group.get("can_prove_claims"))),
        "retrieval_only_answer_allowed_count": sum(1 for group in all_groups if as_bool(group.get("retrieval_only_answer_allowed"))),
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "community_as_proof_count": sum(1 for group in all_groups if as_bool(group.get("community_as_proof"))),
        "category_as_proof_count": sum(1 for group in all_groups if as_bool(group.get("category_as_proof"))),
        "feedback_as_proof_count": sum(1 for group in all_groups if as_bool(group.get("feedback_as_proof"))),
        "corrective_action_as_proof_count": sum(1 for group in all_groups if as_bool(group.get("corrective_action_as_proof"))),
        "postgres_write_attempt_count": sum(1 for group in all_groups if as_bool(group.get("postgres_write_attempted"))),
        "qdrant_write_attempt_count": sum(1 for group in all_groups if as_bool(group.get("qdrant_write_attempted"))),
        "opensearch_write_attempt_count": sum(1 for group in all_groups if as_bool(group.get("opensearch_write_attempted"))),
    }
    quality_fail_reasons: list[str] = []
    if query_count < min_queries:
        quality_fail_reasons.append(f"query_count_below_min:{query_count}<{min_queries}")
    if queries_with_results < min_queries_with_results:
        quality_fail_reasons.append(f"queries_with_results_below_min:{queries_with_results}<{min_queries_with_results}")
    if group_count < min_groups:
        quality_fail_reasons.append(f"group_count_below_min:{group_count}<{min_groups}")
    if corrective_group_count < min_corrective_groups:
        quality_fail_reasons.append(f"corrective_group_count_below_min:{corrective_group_count}<{min_corrective_groups}")
    if review_group_count < min_review_routed_groups:
        quality_fail_reasons.append(f"review_routed_group_count_below_min:{review_group_count}<{min_review_routed_groups}")
    if live_exact_hit_group_count < min_live_exact_hit_groups:
        quality_fail_reasons.append(f"live_exact_hit_group_count_below_min:{live_exact_hit_group_count}<{min_live_exact_hit_groups}")
    if unsafe_group_count > max_unsafe_groups:
        quality_fail_reasons.append(f"unsafe_group_count_above_max:{unsafe_group_count}>{max_unsafe_groups}")
    if require_no_answer_permission and any(hard_zero_counts.values()):
        quality_fail_reasons.append("hard_zero_safety_counter_nonzero")
    missing_sources = [name for name in required_source_quality if as_text(source_statuses.get(name)).upper() != "PASS"]
    if missing_sources:
        quality_fail_reasons.append("source_quality_not_pass:" + ",".join(missing_sources))
    quality = "PASS" if not quality_fail_reasons else "FAIL"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "HYBRID_RETRIEVAL_V3_BUILT",
        "quality_status": quality,
        "query_count": query_count,
        "queries_with_results_count": queries_with_results,
        "hybrid_v3_group_count": group_count,
        "corrective_group_count": corrective_group_count,
        "review_routed_group_count": review_group_count,
        "audit_required_group_count": audit_group_count,
        "live_opensearch_exact_hit_group_count": live_exact_hit_group_count,
        "live_opensearch_exact_hit_count": live_exact_hit_count,
        "unsafe_group_count": unsafe_group_count,
        "source_quality_statuses": dict(source_statuses),
        "required_source_quality": list(required_source_quality),
        "corrective_issue_type_counts": dict(sorted(issue_counter.items())),
        "corrective_recommended_action_counts": dict(sorted(action_counter.items())),
        "severity_counts": dict(sorted(severity_counter.items())),
        "quality_fail_reasons": quality_fail_reasons,
        **hard_zero_counts,
    }
    return summary


def build_hybrid_retrieval_v3(
    *,
    hybrid_v2: Mapping[str, Any],
    corrective_planner: Mapping[str, Any],
    graph_enrichment: Mapping[str, Any],
    opensearch_loader_smoke: Mapping[str, Any],
    qdrant_page_profile_quality: Mapping[str, Any],
    opensearch_live_loader: Mapping[str, Any] | None = None,
    live_opensearch_hits_by_query_id: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    max_groups_per_query: int = 12,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_groups: int = 1,
    min_corrective_groups: int = 1,
    min_review_routed_groups: int = 0,
    min_live_exact_hit_groups: int = 0,
    max_unsafe_groups: int = 0,
    require_hybrid_v2_quality_pass: bool = False,
    require_corrective_planner_quality_pass: bool = False,
    require_graph_enrichment_quality_pass: bool = False,
    require_opensearch_loader_quality_pass: bool = False,
    require_opensearch_live_loader_quality_pass: bool = False,
    require_qdrant_quality_pass: bool = False,
    require_no_answer_permission: bool = True,
) -> dict[str, Any]:
    source_status = source_quality_statuses(
        hybrid_v2=hybrid_v2,
        corrective_planner=corrective_planner,
        graph_enrichment=graph_enrichment,
        opensearch_loader_smoke=opensearch_loader_smoke,
        qdrant_page_profile_quality=qdrant_page_profile_quality,
        opensearch_live_loader=opensearch_live_loader,
    )
    required_sources = []
    if require_hybrid_v2_quality_pass:
        required_sources.append("hybrid_retrieval_v2")
    if require_corrective_planner_quality_pass:
        required_sources.append("corrective_retrieval_planner")
    if require_graph_enrichment_quality_pass:
        required_sources.append("graph_query_evidence_enrichment")
    if require_opensearch_loader_quality_pass:
        required_sources.append("opensearch_loader_smoke")
    if require_opensearch_live_loader_quality_pass:
        required_sources.append("opensearch_live_loader")
    if require_qdrant_quality_pass:
        required_sources.append("qdrant_page_profile_quality")

    planner_records = corrective_records(corrective_planner)
    page_index, channel_records = corrective_index(planner_records)
    graph_pages = graph_enrichment_pages(graph_enrichment)
    channel = channel_summary(channel_records)

    output_query_results = [
        build_query_result(
            row=row,
            query_index=idx,
            page_corrective_index=page_index,
            graph_pages=graph_pages,
            max_groups_per_query=max_groups_per_query,
            live_opensearch_hits=(live_opensearch_hits_by_query_id or {}).get(result_query_id(row, idx), []),
        )
        for idx, row in enumerate(query_results(hybrid_v2))
    ]

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "generated_at": now_iso(),
        "status": "HYBRID_RETRIEVAL_V3_BUILT",
        "source_quality_statuses": source_status,
        "channel_summary": channel,
        "corrective_planner_record_count": len(planner_records),
        "live_opensearch_enabled": bool(live_opensearch_hits_by_query_id),
        "query_results": output_query_results,
        "retrieval_only": True,
        "routing_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    summary = summarize(
        payload=payload,
        source_statuses=source_status,
        required_source_quality=required_sources,
        min_queries=min_queries,
        min_queries_with_results=min_queries_with_results,
        min_groups=min_groups,
        min_corrective_groups=min_corrective_groups,
        min_review_routed_groups=min_review_routed_groups,
        min_live_exact_hit_groups=min_live_exact_hit_groups,
        max_unsafe_groups=max_unsafe_groups,
        require_no_answer_permission=require_no_answer_permission,
    )
    payload["quality_status"] = summary["quality_status"]
    payload["summary"] = summary
    return payload


def build_from_paths(
    *,
    hybrid_v2_path: str | Path,
    corrective_planner_path: str | Path,
    graph_enrichment_path: str | Path,
    opensearch_loader_smoke_path: str | Path,
    qdrant_page_profile_quality_path: str | Path,
    output_dir: str | Path,
    opensearch_live_loader_path: str | Path | None = None,
    enable_live_opensearch: bool = False,
    opensearch_url: str = DEFAULT_OPENSEARCH_URL,
    opensearch_index_name: str = DEFAULT_OPENSEARCH_INDEX_NAME,
    max_live_exact_hits_per_query: int = 10,
    max_groups_per_query: int,
    min_queries: int,
    min_queries_with_results: int,
    min_groups: int,
    min_corrective_groups: int,
    min_review_routed_groups: int,
    min_live_exact_hit_groups: int = 0,
    max_unsafe_groups: int = 0,
    require_hybrid_v2_quality_pass: bool,
    require_corrective_planner_quality_pass: bool,
    require_graph_enrichment_quality_pass: bool,
    require_opensearch_loader_quality_pass: bool,
    require_opensearch_live_loader_quality_pass: bool = False,
    require_qdrant_quality_pass: bool = False,
    require_no_answer_permission: bool,
) -> dict[str, Any]:
    hybrid_v2 = read_json(hybrid_v2_path)
    corrective_planner = read_json(corrective_planner_path)
    graph_enrichment = read_json(graph_enrichment_path)
    opensearch_loader = read_json(opensearch_loader_smoke_path)
    qdrant_quality = read_json(qdrant_page_profile_quality_path)
    opensearch_live_loader = read_json(opensearch_live_loader_path) if opensearch_live_loader_path else {}
    live_hits_by_query = (
        build_live_hits_by_query_id(
            hybrid_v2=hybrid_v2,
            opensearch_url=opensearch_url,
            index_name=opensearch_index_name,
            max_hits_per_query=max_live_exact_hits_per_query,
        )
        if enable_live_opensearch
        else {}
    )
    payload = build_hybrid_retrieval_v3(
        hybrid_v2=hybrid_v2,
        corrective_planner=corrective_planner,
        graph_enrichment=graph_enrichment,
        opensearch_loader_smoke=opensearch_loader,
        qdrant_page_profile_quality=qdrant_quality,
        opensearch_live_loader=opensearch_live_loader,
        live_opensearch_hits_by_query_id=live_hits_by_query,
        max_groups_per_query=max_groups_per_query,
        min_queries=min_queries,
        min_queries_with_results=min_queries_with_results,
        min_groups=min_groups,
        min_corrective_groups=min_corrective_groups,
        min_review_routed_groups=min_review_routed_groups,
        min_live_exact_hit_groups=min_live_exact_hit_groups,
        max_unsafe_groups=max_unsafe_groups,
        require_hybrid_v2_quality_pass=require_hybrid_v2_quality_pass,
        require_corrective_planner_quality_pass=require_corrective_planner_quality_pass,
        require_graph_enrichment_quality_pass=require_graph_enrichment_quality_pass,
        require_opensearch_loader_quality_pass=require_opensearch_loader_quality_pass,
        require_opensearch_live_loader_quality_pass=require_opensearch_live_loader_quality_pass,
        require_qdrant_quality_pass=require_qdrant_quality_pass,
        require_no_answer_permission=require_no_answer_permission,
    )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / DEFAULT_OUTPUT_FILE
    results_path = out_dir / DEFAULT_RESULTS_FILE
    groups_path = out_dir / DEFAULT_GROUPS_FILE
    summary_path = out_dir / DEFAULT_SUMMARY_FILE
    quality_path = out_dir / DEFAULT_QUALITY_FILE
    manifest_path = out_dir / DEFAULT_MANIFEST_FILE
    write_json(report_path, payload)
    write_json(summary_path, payload["summary"])
    write_json(quality_path, {"quality_status": payload["quality_status"], "summary": payload["summary"]})
    write_jsonl(results_path, payload["query_results"])
    all_groups = [group for row in payload["query_results"] for group in row.get("ranked_groups", [])]
    write_jsonl(groups_path, all_groups)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "quality_status": payload["quality_status"],
        "algorithm": ALGORITHM,
        "report_path": str(report_path),
        "results_path": str(results_path),
        "groups_path": str(groups_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_paths": {
            "hybrid_v2": str(hybrid_v2_path),
            "corrective_planner": str(corrective_planner_path),
            "graph_enrichment": str(graph_enrichment_path),
            "opensearch_loader_smoke": str(opensearch_loader_smoke_path),
            "opensearch_live_loader": str(opensearch_live_loader_path) if opensearch_live_loader_path else "",
            "opensearch_url": opensearch_url if enable_live_opensearch else "",
            "opensearch_index_name": opensearch_index_name if enable_live_opensearch else "",
            "qdrant_page_profile_quality": str(qdrant_page_profile_quality_path),
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
            "claim_proof": False,
        },
    }
    write_json(manifest_path, manifest)
    payload["manifest"] = manifest
    return payload


def add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-queries-with-results", type=int, default=1)
    parser.add_argument("--min-groups", type=int, default=1)
    parser.add_argument("--min-corrective-groups", type=int, default=1)
    parser.add_argument("--min-review-routed-groups", type=int, default=0)
    parser.add_argument("--max-unsafe-groups", type=int, default=0)
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-corrective-planner-quality-pass", action="store_true")
    parser.add_argument("--require-graph-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-opensearch-loader-quality-pass", action="store_true")
    parser.add_argument("--require-opensearch-live-loader-quality-pass", action="store_true")
    parser.add_argument("--require-qdrant-quality-pass", action="store_true")
    parser.add_argument("--min-live-exact-hit-groups", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Hybrid Retrieval v3 CRAG-aware retrieval report.")
    parser.add_argument("--hybrid-v2", default=str(DEFAULT_HYBRID_V2))
    parser.add_argument("--corrective-planner", default=str(DEFAULT_CORRECTIVE_PLANNER))
    parser.add_argument("--graph-query-evidence-enrichment", default=str(DEFAULT_GRAPH_ENRICHMENT))
    parser.add_argument("--opensearch-loader-smoke", default=str(DEFAULT_OPENSEARCH_LOADER_SMOKE))
    parser.add_argument("--opensearch-live-loader", default=str(DEFAULT_OPENSEARCH_LIVE_LOADER))
    parser.add_argument("--enable-live-opensearch", action="store_true")
    parser.add_argument("--opensearch-url", default=DEFAULT_OPENSEARCH_URL)
    parser.add_argument("--opensearch-index-name", default=DEFAULT_OPENSEARCH_INDEX_NAME)
    parser.add_argument("--max-live-exact-hits-per-query", type=int, default=10)
    parser.add_argument("--qdrant-page-profile-quality", default=str(DEFAULT_QDRANT_PAGE_PROFILE_QUALITY))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-groups-per-query", type=int, default=12)
    parser.add_argument("--quality", action="store_true", help="Exit non-zero if quality thresholds fail.")
    add_quality_args(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = build_from_paths(
        hybrid_v2_path=args.hybrid_v2,
        corrective_planner_path=args.corrective_planner,
        graph_enrichment_path=args.graph_query_evidence_enrichment,
        opensearch_loader_smoke_path=args.opensearch_loader_smoke,
        qdrant_page_profile_quality_path=args.qdrant_page_profile_quality,
        output_dir=args.output_dir,
        opensearch_live_loader_path=args.opensearch_live_loader,
        enable_live_opensearch=args.enable_live_opensearch,
        opensearch_url=args.opensearch_url,
        opensearch_index_name=args.opensearch_index_name,
        max_live_exact_hits_per_query=args.max_live_exact_hits_per_query,
        max_groups_per_query=args.max_groups_per_query,
        min_queries=args.min_queries,
        min_queries_with_results=args.min_queries_with_results,
        min_groups=args.min_groups,
        min_corrective_groups=args.min_corrective_groups,
        min_review_routed_groups=args.min_review_routed_groups,
        min_live_exact_hit_groups=args.min_live_exact_hit_groups,
        max_unsafe_groups=args.max_unsafe_groups,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_corrective_planner_quality_pass=args.require_corrective_planner_quality_pass,
        require_graph_enrichment_quality_pass=args.require_graph_enrichment_quality_pass,
        require_opensearch_loader_quality_pass=args.require_opensearch_loader_quality_pass,
        require_opensearch_live_loader_quality_pass=args.require_opensearch_live_loader_quality_pass,
        require_qdrant_quality_pass=args.require_qdrant_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    print(json.dumps({"quality_status": payload["quality_status"], "summary": payload["summary"]}, indent=2, sort_keys=True))
    if args.quality and payload["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
