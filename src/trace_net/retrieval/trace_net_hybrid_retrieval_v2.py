"""TRACE-Net Hybrid Retrieval v2.

This module is a live-ready, read-only hybrid retrieval planner.  It combines:

* semantic retrieval groups from the existing Hybrid Retrieval Simulation v1,
* exact/keyword matches from the safe OpenSearch Adapter v1 document set,
* category/community hints from Category-Aware Leiden Overlay v1,
* sanitized feedback memory as an advisory signal.

It does not require a running OpenSearch server yet.  It performs a local exact
search over the safe OpenSearch document artifact, which lets the project test
hybrid ranking before the OpenSearch Loader Smoke module is available.

Safety contract:
- Retrieval may rank and group possible evidence.
- Retrieval cannot answer directly.
- Retrieval cannot prove claims.
- Feedback and community/category signals are advisory only.
- No Postgres, Qdrant, OpenSearch, source, citation, or graph writes occur.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_hybrid_retrieval_v2"
ALGORITHM = "trace_net_semantic_exact_category_feedback_hybrid_ranker_v2"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/hybrid_retrieval_v2")
DEFAULT_HYBRID_REPORT = Path("local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json")
DEFAULT_OPENSEARCH_ADAPTER = Path("local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json")
DEFAULT_COMMUNITY_AWARE_RETRIEVAL = Path("local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1.json")
DEFAULT_CATEGORY_AWARE_LEIDEN = Path("local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1.json")
DEFAULT_FEEDBACK_MEMORY = Path("local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json")
DEFAULT_OUTPUT_FILE = "trace_net_hybrid_retrieval_v2.json"
DEFAULT_RESULTS_FILE = "trace_net_hybrid_retrieval_v2_results.jsonl"
DEFAULT_GROUPS_FILE = "trace_net_hybrid_retrieval_v2_groups.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_hybrid_retrieval_v2_summary.json"
DEFAULT_QUALITY_FILE = "trace_net_hybrid_retrieval_v2_quality.json"
DEFAULT_MANIFEST_FILE = "trace_net_hybrid_retrieval_v2_manifest.json"

DEFAULT_QUERIES = [
    {
        "query_id": "manual_revision_history",
        "query": "Which pages discuss manual revision history?",
        "intent": "revision_history_page_lookup",
    },
    {
        "query_id": "part_120_46137_001",
        "query": "120-46137-001",
        "intent": "exact_part_number_lookup",
    },
    {
        "query_id": "ata_25_21_00",
        "query": "ATA 25-21-00",
        "intent": "exact_ata_code_lookup",
    },
    {
        "query_id": "revision_4",
        "query": "Revision 4",
        "intent": "exact_revision_lookup",
    },
    {
        "query_id": "record_of_revisions",
        "query": "record of revisions",
        "intent": "exact_phrase_revision_lookup",
    },
]

ANSWER_SUPPORT_BUCKETS = {
    "source_text_evidence",
    "verified_part_evidence",
    "table_structured_evidence",
    "table_part_catalog_evidence",
    "clean_evidence_snippet",
}
RETRIEVAL_ONLY_BUCKETS = {
    "source_evidence",
    "derived_context",
    "context_retrieval_helper",
    "page_retrieval_profile",
    "community_retrieval_helper",
    "part_candidate_lineage",
    "table_cell_normalized",
    "table_row_normalized",
    "feedback_memory_advisory",
}
BANNED_BUCKET_TOKENS = {
    "raw_ocr",
    "raw_visual",
    "raw_table",
    "raw_feedback",
    "prompt",
    "debug",
    "unsafe",
    "excluded",
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it", "of", "on", "or", "the", "this", "to", "what", "where", "which", "who", "with",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]*")
PART_RE = re.compile(r"\b\d{2,4}-\d{2,6}-\d{2,4}\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")


class HybridRetrievalV2Error(RuntimeError):
    """Raised when Hybrid Retrieval v2 cannot be built safely."""


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
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        for key in ("quality_status", "status", "source_taxonomy_quality_status", "source_leiden_quality_status"):
            value = as_text(summary.get(key)).upper()
            if value in {"PASS", "FAIL"}:
                return value
    return ""


def tokenize(text: Any) -> list[str]:
    tokens = [m.group(0).lower() for m in TOKEN_RE.finditer(as_text(text))]
    return [t for t in tokens if len(t) > 1 and t not in STOPWORDS]


def keyword_terms(query: str) -> list[str]:
    terms = tokenize(query)
    # Preserve exact identifiers even when tokenization already includes them.
    for pattern in (PART_RE, ATA_RE):
        for match in pattern.findall(query):
            terms.append(match.lower())
    return unique_texts(terms)


def load_queries(query_file: str | Path | None = None) -> list[dict[str, str]]:
    if query_file:
        payload = read_json(query_file)
        rows = payload.get("queries") if isinstance(payload.get("queries"), list) else []
        out = []
        for idx, row in enumerate(rows):
            if isinstance(row, Mapping) and as_text(row.get("query")):
                out.append({
                    "query_id": as_text(row.get("query_id") or f"query_{idx + 1:03d}"),
                    "query": as_text(row.get("query")),
                    "intent": as_text(row.get("intent") or "custom_query"),
                })
        if out:
            return out
    return [dict(q) for q in DEFAULT_QUERIES]


def opensearch_documents(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    docs = payload.get("documents")
    if isinstance(docs, list):
        return [dict(d) for d in docs if isinstance(d, Mapping)]
    return []


def doc_text(doc: Mapping[str, Any]) -> str:
    pieces = [
        doc.get("title"),
        doc.get("text"),
        doc.get("page_id"),
        " ".join(as_text(v) for v in as_list(doc.get("source_page_ids"))),
        " ".join(as_text(v) for v in as_list(doc.get("part_numbers"))),
        " ".join(as_text(v) for v in as_list(doc.get("citation_ids"))),
        " ".join(as_text(v) for v in as_list(doc.get("community_ids"))),
        doc.get("rag_bucket"),
        doc.get("document_type"),
    ]
    return "\n".join(as_text(p) for p in pieces if as_text(p))


def is_safe_opensearch_doc(doc: Mapping[str, Any]) -> bool:
    if as_bool(doc.get("can_answer_directly")):
        return False
    if as_bool(doc.get("can_prove_claims")):
        return False
    if as_bool(doc.get("can_mutate_source_truth")) or as_bool(doc.get("source_truth_mutation_allowed")):
        return False
    if as_bool(doc.get("raw_feedback_indexed")) or as_bool(doc.get("raw_visual_output")) or as_bool(doc.get("raw_ocr_unfiltered")):
        return False
    bucket = as_text(doc.get("rag_bucket")).lower()
    if any(token in bucket for token in BANNED_BUCKET_TOKENS):
        return False
    if not doc.get("page_id") and not doc.get("source_page_ids"):
        return False
    return as_bool(doc.get("safe_for_opensearch"), True)


def score_exact_doc(query: str, doc: Mapping[str, Any]) -> dict[str, Any]:
    terms = keyword_terms(query)
    if not terms:
        return {"score": 0.0, "matched_terms": [], "matched_part_numbers": [], "matched_ata_codes": []}
    hay = doc_text(doc).lower()
    title = as_text(doc.get("title")).lower()
    text = as_text(doc.get("text")).lower()
    score = 0.0
    matched_terms: list[str] = []
    for term in terms:
        if term in hay:
            matched_terms.append(term)
            score += 1.0
            if term in title:
                score += 0.5
            if term in text:
                score += 0.25
    query_lower = as_text(query).lower()
    if query_lower and len(query_lower) > 3 and query_lower in hay:
        score += 2.0
    part_numbers = [p.lower() for p in unique_texts(doc.get("part_numbers") or [])]
    matched_parts = [p for p in PART_RE.findall(query_lower) if p.lower() in part_numbers or p.lower() in hay]
    if matched_parts:
        score += 4.0 * len(matched_parts)
    matched_ata = [a for a in ATA_RE.findall(query_lower) if a.lower() in hay]
    if matched_ata:
        score += 3.0 * len(matched_ata)
    # Answer-support docs are still not proof here, but they are better retrieval candidates.
    if as_bool(doc.get("answer_support_candidate")):
        score += 0.3
    if doc.get("citation_ids"):
        score += 0.2
    if doc.get("page_id"):
        score += 0.1
    return {
        "score": round(score, 6),
        "matched_terms": unique_texts(matched_terms),
        "matched_part_numbers": unique_texts(matched_parts),
        "matched_ata_codes": unique_texts(matched_ata),
    }


def exact_search(query: str, docs: list[dict[str, Any]], *, top_k: int = 12) -> list[dict[str, Any]]:
    hits = []
    for doc in docs:
        if not is_safe_opensearch_doc(doc):
            continue
        scored = score_exact_doc(query, doc)
        if scored["score"] <= 0:
            continue
        hits.append({
            "hit_type": "opensearch_exact_local",
            "score": scored["score"],
            "matched_terms": scored["matched_terms"],
            "matched_part_numbers": scored["matched_part_numbers"],
            "matched_ata_codes": scored["matched_ata_codes"],
            "opensearch_document_id": as_text(doc.get("opensearch_document_id")),
            "document_type": as_text(doc.get("document_type")),
            "title": as_text(doc.get("title")),
            "page_id": as_text(doc.get("page_id")) or None,
            "source_page_ids": unique_texts(doc.get("source_page_ids") or []),
            "citation_ids": unique_texts(doc.get("citation_ids") or []),
            "community_ids": unique_texts(doc.get("community_ids") or []),
            "part_numbers": unique_texts(doc.get("part_numbers") or []),
            "rag_bucket": as_text(doc.get("rag_bucket")),
            "authority": as_text(doc.get("authority")),
            "retrieval_only": as_bool(doc.get("retrieval_only"), True),
            "answer_support_candidate": as_bool(doc.get("answer_support_candidate")),
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
            "text_preview": as_text(doc.get("text"))[:500],
        })
    hits.sort(key=lambda h: (-as_float(h.get("score")), as_text(h.get("page_id") or ""), as_text(h.get("opensearch_document_id"))))
    for rank, hit in enumerate(hits[:top_k], start=1):
        hit["rank"] = rank
    return hits[:top_k]


def query_results_from_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("query_results") or report.get("results") or []
    if isinstance(rows, list):
        return [dict(r) for r in rows if isinstance(r, Mapping)]
    return []


def groups_from_result(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = result.get("ranked_groups") or result.get("groups") or []
    return [dict(g) for g in groups if isinstance(g, Mapping)] if isinstance(groups, list) else []


def result_query_id(row: Mapping[str, Any]) -> str:
    return as_text(row.get("query_id") or row.get("id"))


def find_semantic_groups(query: Mapping[str, str], hybrid_report: Mapping[str, Any], community_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    qid = as_text(query.get("query_id"))
    qtext = as_text(query.get("query")).lower()
    candidates = []
    for report_name, report in (("community_aware", community_report), ("hybrid_v1", hybrid_report)):
        for row in query_results_from_report(report):
            row_id = result_query_id(row)
            row_q = as_text(row.get("query")).lower()
            if row_id == qid or (row_q and (row_q == qtext or qtext in row_q or row_q in qtext)):
                for group in groups_from_result(row):
                    g = dict(group)
                    g["semantic_source_report"] = report_name
                    candidates.append(g)
                if candidates:
                    return candidates
    # If query id does not match old report, do a conservative lexical match over group text.
    terms = set(keyword_terms(as_text(query.get("query"))))
    if not terms:
        return []
    scored = []
    for report_name, report in (("community_aware", community_report), ("hybrid_v1", hybrid_report)):
        for row in query_results_from_report(report):
            for group in groups_from_result(row):
                hay = stable_json(group).lower()
                overlap = sum(1 for t in terms if t in hay)
                if overlap:
                    g = dict(group)
                    g["semantic_source_report"] = report_name
                    g["semantic_lexical_overlap"] = overlap
                    scored.append(g)
    scored.sort(key=lambda g: (-int(g.get("semantic_lexical_overlap") or 0), -semantic_group_score(g)))
    return scored[:12]


def semantic_group_score(group: Mapping[str, Any]) -> float:
    for key in ("community_aware_score", "hybrid_score", "combined_score", "score", "group_score", "base_hybrid_score"):
        value = group.get(key)
        try:
            f = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            return f
    # Conservative fallback using rank.
    rank = int(as_float(group.get("rank") or group.get("community_aware_rank") or 99, 99))
    return max(0.0, 1.0 - (rank - 1) * 0.05)


def page_ids_from_exact_hit(hit: Mapping[str, Any]) -> list[str]:
    values = []
    if hit.get("page_id"):
        values.append(hit.get("page_id"))
    values.extend(as_list(hit.get("source_page_ids")))
    return unique_texts(values)


def group_page_id(group: Mapping[str, Any]) -> str:
    return as_text(group.get("page_id"))


def group_citation_ids(group: Mapping[str, Any]) -> list[str]:
    values = []
    values.extend(as_list(group.get("citation_ids")))
    for key in ("candidate_hits", "page_profile_hits", "hits", "exact_hits"):
        for item in as_list(group.get(key)):
            if isinstance(item, Mapping):
                values.extend(as_list(item.get("citation_ids")))
                if item.get("citation_id"):
                    values.append(item.get("citation_id"))
    return unique_texts(values)


def group_community_ids(group: Mapping[str, Any]) -> list[str]:
    values = []
    values.extend(as_list(group.get("community_ids")))
    for key in ("candidate_hits", "page_profile_hits", "hits", "exact_hits"):
        for item in as_list(group.get(key)):
            if isinstance(item, Mapping):
                values.extend(as_list(item.get("community_ids")))
    return unique_texts(values)


def group_part_numbers(group: Mapping[str, Any]) -> list[str]:
    values = []
    values.extend(as_list(group.get("part_numbers")))
    for key in ("candidate_hits", "page_profile_hits", "hits", "exact_hits"):
        for item in as_list(group.get(key)):
            if isinstance(item, Mapping):
                values.extend(as_list(item.get("part_numbers")))
    return unique_texts(values)


def category_page_profiles(category_overlay: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = category_overlay.get("page_category_membership") or category_overlay.get("page_category_profiles") or []
    out: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping) and as_text(row.get("page_id")):
                out[as_text(row.get("page_id"))] = dict(row)
    return out


def community_profiles(category_overlay: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = category_overlay.get("community_category_profiles") or category_overlay.get("category_aware_community_cards") or []
    out: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                props = row.get("properties") if isinstance(row.get("properties"), Mapping) else row
                cid = as_text(props.get("community_id"))
                if cid:
                    out[cid] = dict(props)
    return out


def feedback_records(feedback_memory: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = feedback_memory.get("memory_records") or feedback_memory.get("records") or []
    return [dict(r) for r in rows if isinstance(r, Mapping)] if isinstance(rows, list) else []


def feedback_delta_for_group(group: Mapping[str, Any], query: Mapping[str, str], feedback_rows: list[dict[str, Any]]) -> tuple[float, list[str]]:
    page_ids = set(page_ids_from_group(group))
    citation_ids = set(group_citation_ids(group))
    community_ids = set(group_community_ids(group))
    query_text = as_text(query.get("query")).lower()
    delta = 0.0
    applied: list[str] = []
    for rec in feedback_rows:
        if as_bool(rec.get("raw_feedback_direct_to_llm")):
            continue
        target_type = as_text(rec.get("target_type")).lower()
        target_id = as_text(rec.get("target_id"))
        score = as_float(rec.get("rating_score") or rec.get("feedback_score") or rec.get("rating") or 0.0)
        if score == 0.0:
            signal = as_text(rec.get("feedback_signal") or rec.get("rating_label")).lower()
            if signal in {"positive", "up", "helpful"}:
                score = 1.0
            elif signal in {"negative", "down", "unhelpful"}:
                score = -1.0
        weight = 0.0
        if target_type == "page" and target_id in page_ids:
            weight = 0.08
        elif target_type == "citation" and target_id in citation_ids:
            weight = 0.06
        elif target_type == "community" and target_id in community_ids:
            weight = 0.05
        elif target_type in {"answer", "query", "retrieval_group"}:
            summary = as_text(rec.get("feedback_summary") or rec.get("sanitized_comment")).lower()
            if query_text and any(term in summary for term in keyword_terms(query_text)):
                weight = 0.02
        if weight:
            delta += max(-1.0, min(1.0, score)) * weight
            applied.append(as_text(rec.get("memory_id") or rec.get("feedback_id") or stable_hash(rec)))
    return round(max(-0.25, min(0.25, delta)), 6), unique_texts(applied)


def page_ids_from_group(group: Mapping[str, Any]) -> list[str]:
    page_ids = []
    if group.get("page_id"):
        page_ids.append(group.get("page_id"))
    page_ids.extend(as_list(group.get("source_page_ids")))
    for key in ("candidate_hits", "page_profile_hits", "hits", "exact_hits"):
        for item in as_list(group.get(key)):
            if isinstance(item, Mapping):
                page_ids.extend(page_ids_from_exact_hit(item))
    return unique_texts(page_ids)


def make_group_seed(page_id: str | None) -> dict[str, Any]:
    return {
        "page_id": page_id,
        "source_page_ids": [] if not page_id else [page_id],
        "exact_hits": [],
        "semantic_groups": [],
        "citation_ids": [],
        "community_ids": [],
        "part_numbers": [],
        "buckets": [],
        "authorities": [],
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
    }


def merge_exact_hit(group: dict[str, Any], hit: Mapping[str, Any]) -> None:
    group["exact_hits"].append(dict(hit))
    group["source_page_ids"] = unique_texts(list(group.get("source_page_ids") or []) + page_ids_from_exact_hit(hit))
    group["citation_ids"] = unique_texts(list(group.get("citation_ids") or []) + as_list(hit.get("citation_ids")))
    group["community_ids"] = unique_texts(list(group.get("community_ids") or []) + as_list(hit.get("community_ids")))
    group["part_numbers"] = unique_texts(list(group.get("part_numbers") or []) + as_list(hit.get("part_numbers")))
    group["buckets"] = unique_texts(list(group.get("buckets") or []) + [hit.get("rag_bucket")])
    group["authorities"] = unique_texts(list(group.get("authorities") or []) + [hit.get("authority")])


def merge_semantic_group(group: dict[str, Any], semantic: Mapping[str, Any]) -> None:
    group["semantic_groups"].append(dict(semantic))
    group["source_page_ids"] = unique_texts(list(group.get("source_page_ids") or []) + page_ids_from_group(semantic))
    group["citation_ids"] = unique_texts(list(group.get("citation_ids") or []) + group_citation_ids(semantic))
    group["community_ids"] = unique_texts(list(group.get("community_ids") or []) + group_community_ids(semantic))
    group["part_numbers"] = unique_texts(list(group.get("part_numbers") or []) + group_part_numbers(semantic))
    buckets = []
    buckets.extend(as_list(semantic.get("rag_buckets") or semantic.get("buckets")))
    bc = semantic.get("bucket_counts")
    if isinstance(bc, Mapping):
        buckets.extend(bc.keys())
    group["buckets"] = unique_texts(list(group.get("buckets") or []) + buckets)


def category_boost(group: Mapping[str, Any], page_profiles: dict[str, dict[str, Any]], community_profile_map: dict[str, dict[str, Any]]) -> tuple[float, list[str], list[str]]:
    labels: list[str] = []
    hints: list[str] = []
    for pid in page_ids_from_group(group):
        profile = page_profiles.get(pid)
        if profile:
            labels.append(as_text(profile.get("page_category_label")))
            hints.extend(as_list(profile.get("leiden_hint_element_families")))
    for cid in group_community_ids(group):
        profile = community_profile_map.get(cid)
        if profile:
            labels.append(as_text(profile.get("category_aware_label")))
            hints.extend(as_list(profile.get("dominant_leiden_hint_families")))
    labels = unique_texts(labels)
    hints = unique_texts(hints)
    boost = 0.0
    # Keep the boost small; categories help explain/route, not prove.
    if labels:
        boost += 0.03
    if any(h in {"table", "part", "diagram", "visual", "source", "text"} for h in hints):
        boost += 0.02
    if any("review" in label for label in labels):
        boost -= 0.015
    return round(boost, 6), labels, hints


def build_query_result(
    query: Mapping[str, str],
    *,
    docs: list[dict[str, Any]],
    hybrid_report: Mapping[str, Any],
    community_report: Mapping[str, Any],
    category_overlay: Mapping[str, Any],
    feedback_memory: Mapping[str, Any],
    top_k_exact: int,
    max_groups: int,
) -> dict[str, Any]:
    exact_hits = exact_search(as_text(query.get("query")), docs, top_k=top_k_exact)
    semantic_groups = find_semantic_groups(query, hybrid_report, community_report)
    grouped: dict[str, dict[str, Any]] = {}

    for hit in exact_hits:
        page_ids = page_ids_from_exact_hit(hit) or ["__cross_page__"]
        for page_id in page_ids:
            group = grouped.setdefault(page_id, make_group_seed(None if page_id == "__cross_page__" else page_id))
            merge_exact_hit(group, hit)

    for semantic in semantic_groups:
        page_id = group_page_id(semantic) or (page_ids_from_group(semantic)[:1] or ["__cross_page__"])[0]
        group = grouped.setdefault(page_id, make_group_seed(None if page_id == "__cross_page__" else page_id))
        merge_semantic_group(group, semantic)

    page_profiles = category_page_profiles(category_overlay)
    community_profiles_map = community_profiles(category_overlay)
    feedback_rows = feedback_records(feedback_memory)

    ranked_groups: list[dict[str, Any]] = []
    for page_key, group in grouped.items():
        exact_score = sum(as_float(h.get("score")) for h in group.get("exact_hits", []))
        exact_score_norm = min(1.0, exact_score / 12.0)
        semantic_score = max([semantic_group_score(g) for g in group.get("semantic_groups", [])] or [0.0])
        cat_boost, cat_labels, hint_families = category_boost(group, page_profiles, community_profiles_map)
        feedback_delta, feedback_ids = feedback_delta_for_group(group, query, feedback_rows)
        citation_boost = min(0.08, 0.015 * len(group.get("citation_ids", [])))
        part_boost = min(0.06, 0.01 * len(group.get("part_numbers", [])))
        combined = (0.58 * semantic_score) + (0.34 * exact_score_norm) + cat_boost + feedback_delta + citation_boost + part_boost
        unsafe_reasons = []
        for hit in group.get("exact_hits", []):
            if as_bool(hit.get("can_answer_directly")):
                unsafe_reasons.append("exact_hit_can_answer_directly")
            if as_bool(hit.get("can_prove_claims")):
                unsafe_reasons.append("exact_hit_can_prove_claims")
            if as_bool(hit.get("source_truth_mutation_allowed")):
                unsafe_reasons.append("exact_hit_source_truth_mutation_allowed")
        record = {
            "hybrid_v2_group_id": f"hv2grp__{stable_hash([query.get('query_id'), page_key, group.get('citation_ids'), group.get('part_numbers')])}",
            "query_id": as_text(query.get("query_id")),
            "query": as_text(query.get("query")),
            "page_id": group.get("page_id"),
            "source_page_ids": unique_texts(group.get("source_page_ids") or []),
            "exact_hit_count": len(group.get("exact_hits", [])),
            "semantic_group_count": len(group.get("semantic_groups", [])),
            "exact_score": round(exact_score, 6),
            "exact_score_normalized": round(exact_score_norm, 6),
            "semantic_score": round(semantic_score, 6),
            "category_boost": cat_boost,
            "feedback_advisory_delta": feedback_delta,
            "citation_boost": round(citation_boost, 6),
            "part_number_boost": round(part_boost, 6),
            "hybrid_v2_score": round(combined, 6),
            "citation_ids": unique_texts(group.get("citation_ids") or []),
            "community_ids": unique_texts(group.get("community_ids") or []),
            "part_numbers": unique_texts(group.get("part_numbers") or []),
            "rag_buckets": unique_texts(group.get("buckets") or []),
            "authorities": unique_texts(group.get("authorities") or []),
            "category_labels": cat_labels,
            "category_hint_families": hint_families,
            "feedback_memory_ids_applied": feedback_ids,
            "exact_hits": sorted(group.get("exact_hits", []), key=lambda h: int(h.get("rank") or 999))[:8],
            "semantic_groups": sorted(group.get("semantic_groups", []), key=lambda g: -semantic_group_score(g))[:4],
            "retrieval_only": True,
            "answer_support_candidate_count": sum(1 for h in group.get("exact_hits", []) if as_bool(h.get("answer_support_candidate"))),
            "answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
            "feedback_as_proof": False,
            "community_as_proof": False,
            "category_as_proof": False,
            "unsafe_reasons": unique_texts(unsafe_reasons),
            "safety_status": "unsafe" if unsafe_reasons else "retrieval_safe",
        }
        ranked_groups.append(record)

    ranked_groups.sort(key=lambda g: (-as_float(g.get("hybrid_v2_score")), as_text(g.get("page_id") or "")))
    for rank, group in enumerate(ranked_groups[:max_groups], start=1):
        group["hybrid_v2_rank"] = rank
    ranked_groups = ranked_groups[:max_groups]
    return {
        "query_id": as_text(query.get("query_id")),
        "query": as_text(query.get("query")),
        "intent": as_text(query.get("intent")),
        "exact_hit_count": len(exact_hits),
        "semantic_group_count": len(semantic_groups),
        "ranked_group_count": len(ranked_groups),
        "ranked_groups": ranked_groups,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def summarize(report: Mapping[str, Any]) -> dict[str, Any]:
    query_results = report.get("query_results") or []
    groups = [g for qr in query_results if isinstance(qr, Mapping) for g in as_list(qr.get("ranked_groups")) if isinstance(g, Mapping)]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "hybrid_v2_query_count": len(query_results),
        "queries_with_results_count": sum(1 for qr in query_results if int(qr.get("ranked_group_count") or 0) > 0),
        "hybrid_v2_group_count": len(groups),
        "exact_hit_group_count": sum(1 for g in groups if int(g.get("exact_hit_count") or 0) > 0),
        "semantic_group_count": sum(1 for g in groups if int(g.get("semantic_group_count") or 0) > 0),
        "combined_exact_semantic_group_count": sum(1 for g in groups if int(g.get("exact_hit_count") or 0) > 0 and int(g.get("semantic_group_count") or 0) > 0),
        "feedback_adjusted_group_count": sum(1 for g in groups if abs(as_float(g.get("feedback_advisory_delta"))) > 0),
        "category_boosted_group_count": sum(1 for g in groups if abs(as_float(g.get("category_boost"))) > 0),
        "unsafe_group_count": sum(1 for g in groups if g.get("unsafe_reasons")),
        "retrieval_only_answer_allowed_count": sum(1 for g in groups if as_bool(g.get("retrieval_only")) and as_bool(g.get("answer_allowed"))),
        "direct_answer_allowed_count": sum(1 for g in groups if as_bool(g.get("can_answer_directly"))),
        "claim_proof_allowed_count": sum(1 for g in groups if as_bool(g.get("can_prove_claims"))),
        "feedback_as_proof_count": sum(1 for g in groups if as_bool(g.get("feedback_as_proof"))),
        "community_as_proof_count": sum(1 for g in groups if as_bool(g.get("community_as_proof"))),
        "category_as_proof_count": sum(1 for g in groups if as_bool(g.get("category_as_proof"))),
        "source_truth_mutation_allowed_count": sum(1 for g in groups if as_bool(g.get("source_truth_mutation_allowed"))),
        "postgres_write_attempt_count": int(report.get("postgres_write_attempt_count") or 0),
        "qdrant_write_attempt_count": int(report.get("qdrant_write_attempt_count") or 0),
        "opensearch_write_attempt_count": int(report.get("opensearch_write_attempt_count") or 0),
        "source_quality_statuses": report.get("source_quality_statuses") or {},
    }
    summary["query_ids"] = [as_text(qr.get("query_id")) for qr in query_results if isinstance(qr, Mapping)]
    summary["page_ids"] = unique_texts(g.get("page_id") for g in groups)
    summary["rag_bucket_counts"] = dict(Counter(bucket for g in groups for bucket in as_list(g.get("rag_buckets"))))
    summary["document_type_counts"] = dict(Counter(hit.get("document_type") for g in groups for hit in as_list(g.get("exact_hits")) if isinstance(hit, Mapping)))
    return summary


def quality_report(
    report: Mapping[str, Any],
    *,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_groups: int = 1,
    min_exact_hit_groups: int = 1,
    min_semantic_groups: int = 1,
    require_opensearch_quality_pass: bool = False,
    require_hybrid_quality_pass: bool = False,
) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else summarize(report)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: Any, severity: str = "critical") -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})

    add("hybrid_v2_query_count_min", int(summary.get("hybrid_v2_query_count", 0)) >= min_queries, summary.get("hybrid_v2_query_count"), f">= {min_queries}")
    add("queries_with_results_count_min", int(summary.get("queries_with_results_count", 0)) >= min_queries_with_results, summary.get("queries_with_results_count"), f">= {min_queries_with_results}")
    add("hybrid_v2_group_count_min", int(summary.get("hybrid_v2_group_count", 0)) >= min_groups, summary.get("hybrid_v2_group_count"), f">= {min_groups}")
    add("exact_hit_group_count_min", int(summary.get("exact_hit_group_count", 0)) >= min_exact_hit_groups, summary.get("exact_hit_group_count"), f">= {min_exact_hit_groups}")
    add("semantic_group_count_min", int(summary.get("semantic_group_count", 0)) >= min_semantic_groups, summary.get("semantic_group_count"), f">= {min_semantic_groups}")
    add("unsafe_group_count_zero", int(summary.get("unsafe_group_count", 0)) == 0, summary.get("unsafe_group_count"), 0)
    add("retrieval_only_answer_allowed_count_zero", int(summary.get("retrieval_only_answer_allowed_count", 0)) == 0, summary.get("retrieval_only_answer_allowed_count"), 0)
    add("direct_answer_allowed_count_zero", int(summary.get("direct_answer_allowed_count", 0)) == 0, summary.get("direct_answer_allowed_count"), 0)
    add("claim_proof_allowed_count_zero", int(summary.get("claim_proof_allowed_count", 0)) == 0, summary.get("claim_proof_allowed_count"), 0)
    add("feedback_as_proof_count_zero", int(summary.get("feedback_as_proof_count", 0)) == 0, summary.get("feedback_as_proof_count"), 0)
    add("community_as_proof_count_zero", int(summary.get("community_as_proof_count", 0)) == 0, summary.get("community_as_proof_count"), 0)
    add("category_as_proof_count_zero", int(summary.get("category_as_proof_count", 0)) == 0, summary.get("category_as_proof_count"), 0)
    add("source_truth_mutation_allowed_count_zero", int(summary.get("source_truth_mutation_allowed_count", 0)) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("postgres_write_attempt_count_zero", int(summary.get("postgres_write_attempt_count", 0)) == 0, summary.get("postgres_write_attempt_count"), 0)
    add("qdrant_write_attempt_count_zero", int(summary.get("qdrant_write_attempt_count", 0)) == 0, summary.get("qdrant_write_attempt_count"), 0)
    add("opensearch_write_attempt_count_zero", int(summary.get("opensearch_write_attempt_count", 0)) == 0, summary.get("opensearch_write_attempt_count"), 0)
    source_statuses = summary.get("source_quality_statuses") if isinstance(summary.get("source_quality_statuses"), Mapping) else {}
    if require_opensearch_quality_pass:
        add("opensearch_adapter_quality_pass", as_text(source_statuses.get("opensearch_adapter")).upper() == "PASS", source_statuses.get("opensearch_adapter"), "PASS")
    if require_hybrid_quality_pass:
        add("hybrid_report_quality_pass", as_text(source_statuses.get("hybrid_report")).upper() == "PASS", source_statuses.get("hybrid_report"), "PASS")
    status = "PASS" if all(c["passed"] or c["severity"] != "critical" for c in checks) else "FAIL"
    return {"status": status, "checks": checks, "summary": dict(summary)}


def build_hybrid_retrieval_v2(
    *,
    hybrid_report_path: str | Path = DEFAULT_HYBRID_REPORT,
    opensearch_adapter_path: str | Path = DEFAULT_OPENSEARCH_ADAPTER,
    community_aware_retrieval_path: str | Path | None = DEFAULT_COMMUNITY_AWARE_RETRIEVAL,
    category_aware_leiden_overlay_path: str | Path | None = DEFAULT_CATEGORY_AWARE_LEIDEN,
    feedback_memory_path: str | Path | None = DEFAULT_FEEDBACK_MEMORY,
    query_file: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    top_k_exact: int = 12,
    max_groups: int = 8,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_groups: int = 1,
    min_exact_hit_groups: int = 1,
    min_semantic_groups: int = 1,
    require_opensearch_quality_pass: bool = False,
    require_hybrid_quality_pass: bool = False,
) -> dict[str, Any]:
    hybrid_report = read_json(hybrid_report_path)
    opensearch_report = read_json(opensearch_adapter_path)
    community_report = read_json(community_aware_retrieval_path) if community_aware_retrieval_path else {}
    category_overlay = read_json(category_aware_leiden_overlay_path) if category_aware_leiden_overlay_path else {}
    feedback_memory = read_json(feedback_memory_path) if feedback_memory_path else {}
    docs = opensearch_documents(opensearch_report)
    queries = load_queries(query_file)

    query_results = [
        build_query_result(
            query,
            docs=docs,
            hybrid_report=hybrid_report,
            community_report=community_report,
            category_overlay=category_overlay,
            feedback_memory=feedback_memory,
            top_k_exact=top_k_exact,
            max_groups=max_groups,
        )
        for query in queries
    ]
    source_quality_statuses = {
        "hybrid_report": quality_status(hybrid_report),
        "opensearch_adapter": quality_status(opensearch_report),
        "community_aware_retrieval": quality_status(community_report),
        "category_aware_leiden_overlay": quality_status(category_overlay),
        "feedback_memory": quality_status(feedback_memory),
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "HYBRID_RETRIEVAL_V2_BUILT",
        "generated_at": now_iso(),
        "query_count": len(queries),
        "queries": queries,
        "query_results": query_results,
        "source_artifacts": {
            "hybrid_report": str(hybrid_report_path),
            "opensearch_adapter": str(opensearch_adapter_path),
            "community_aware_retrieval": str(community_aware_retrieval_path or ""),
            "category_aware_leiden_overlay": str(category_aware_leiden_overlay_path or ""),
            "feedback_memory": str(feedback_memory_path or ""),
        },
        "source_quality_statuses": source_quality_statuses,
        "retrieval_mode": "local_artifact_hybrid_v2",
        "exact_search_mode": "local_opensearch_document_scan",
        "semantic_search_mode": "hybrid_report_reuse",
        "read_only": True,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
    }
    report["summary"] = summarize(report)
    q = quality_report(
        report,
        min_queries=min_queries,
        min_queries_with_results=min_queries_with_results,
        min_groups=min_groups,
        min_exact_hit_groups=min_exact_hit_groups,
        min_semantic_groups=min_semantic_groups,
        require_opensearch_quality_pass=require_opensearch_quality_pass,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
    )
    report["quality_status"] = q["status"]
    report["quality_checks"] = q["checks"]
    report["summary"]["status"] = q["status"]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / DEFAULT_OUTPUT_FILE
    results_path = out_dir / DEFAULT_RESULTS_FILE
    groups_path = out_dir / DEFAULT_GROUPS_FILE
    summary_path = out_dir / DEFAULT_SUMMARY_FILE
    quality_path = out_dir / DEFAULT_QUALITY_FILE
    manifest_path = out_dir / DEFAULT_MANIFEST_FILE
    write_json(report_path, report)
    write_jsonl(results_path, query_results)
    write_jsonl(groups_path, [g for qr in query_results for g in as_list(qr.get("ranked_groups")) if isinstance(g, Mapping)])
    write_json(summary_path, report["summary"])
    write_json(quality_path, q)
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "report_path": str(report_path),
        "results_path": str(results_path),
        "groups_path": str(groups_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_artifacts": report["source_artifacts"],
    })
    md = render_markdown(report)
    (out_dir / "trace_net_hybrid_retrieval_v2.md").write_text(md, encoding="utf-8")
    report["report_path"] = str(report_path)
    report["quality_path"] = str(quality_path)
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Hybrid Retrieval v2",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "hybrid_v2_query_count",
        "queries_with_results_count",
        "hybrid_v2_group_count",
        "exact_hit_group_count",
        "semantic_group_count",
        "combined_exact_semantic_group_count",
        "feedback_adjusted_group_count",
        "category_boosted_group_count",
        "unsafe_group_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Top Results", ""])
    for qr in as_list(report.get("query_results")):
        if not isinstance(qr, Mapping):
            continue
        lines.append(f"### {qr.get('query_id')}: {qr.get('query')}")
        lines.append("")
        for group in as_list(qr.get("ranked_groups"))[:5]:
            if not isinstance(group, Mapping):
                continue
            lines.append(
                f"- rank {group.get('hybrid_v2_rank')}: page {group.get('page_id')} "
                f"score={group.get('hybrid_v2_score')} exact={group.get('exact_hit_count')} semantic={group.get('semantic_group_count')} "
                f"categories={', '.join(as_list(group.get('category_labels'))[:3])}"
            )
        lines.append("")
    lines.append("Safety: retrieval groups are advisory only and cannot answer or prove claims.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Hybrid Retrieval v2 local-artifact report.")
    parser.add_argument("--hybrid-report", default=str(DEFAULT_HYBRID_REPORT))
    parser.add_argument("--opensearch-adapter", default=str(DEFAULT_OPENSEARCH_ADAPTER))
    parser.add_argument("--community-aware-retrieval", default=str(DEFAULT_COMMUNITY_AWARE_RETRIEVAL))
    parser.add_argument("--category-aware-leiden-overlay", default=str(DEFAULT_CATEGORY_AWARE_LEIDEN))
    parser.add_argument("--feedback-memory", default=str(DEFAULT_FEEDBACK_MEMORY))
    parser.add_argument("--query-file", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--top-k-exact", type=int, default=12)
    parser.add_argument("--max-groups", type=int, default=8)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-queries-with-results", type=int, default=1)
    parser.add_argument("--min-groups", type=int, default=1)
    parser.add_argument("--min-exact-hit-groups", type=int, default=1)
    parser.add_argument("--min-semantic-groups", type=int, default=1)
    parser.add_argument("--require-opensearch-quality-pass", action="store_true")
    parser.add_argument("--require-hybrid-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    report = build_hybrid_retrieval_v2(
        hybrid_report_path=args.hybrid_report,
        opensearch_adapter_path=args.opensearch_adapter,
        community_aware_retrieval_path=args.community_aware_retrieval,
        category_aware_leiden_overlay_path=args.category_aware_leiden_overlay,
        feedback_memory_path=args.feedback_memory,
        query_file=args.query_file,
        output_dir=args.output_dir,
        top_k_exact=args.top_k_exact,
        max_groups=args.max_groups,
        min_queries=args.min_queries,
        min_queries_with_results=args.min_queries_with_results,
        min_groups=args.min_groups,
        min_exact_hit_groups=args.min_exact_hit_groups,
        min_semantic_groups=args.min_semantic_groups,
        require_opensearch_quality_pass=args.require_opensearch_quality_pass,
        require_hybrid_quality_pass=args.require_hybrid_quality_pass,
    )
    s = report["summary"]
    print("TRACE-Net Hybrid Retrieval v2")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" hybrid_v2_query_count: {s.get('hybrid_v2_query_count')}")
    print(f" queries_with_results_count: {s.get('queries_with_results_count')}")
    print(f" hybrid_v2_group_count: {s.get('hybrid_v2_group_count')}")
    print(f" exact_hit_group_count: {s.get('exact_hit_group_count')}")
    print(f" semantic_group_count: {s.get('semantic_group_count')}")
    print(f" combined_exact_semantic_group_count: {s.get('combined_exact_semantic_group_count')}")
    print(f" feedback_adjusted_group_count: {s.get('feedback_adjusted_group_count')}")
    print(f" category_boosted_group_count: {s.get('category_boosted_group_count')}")
    print(f" unsafe_group_count: {s.get('unsafe_group_count')}")
    print(f" retrieval_only_answer_allowed_count: {s.get('retrieval_only_answer_allowed_count')}")
    print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
