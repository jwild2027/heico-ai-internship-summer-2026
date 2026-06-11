"""TRACE-Net Dublin Core Crosswalk Refinement v1.

Refines the TRACE-Net Dublin Core Crosswalk into a cleaner UI/export profile.

This module separates document/page-visible elements from TRACE-Net operational
artifacts and produces stricter Dublin Core page types.

Safety contract:
- Read-only metadata refinement only.
- No Postgres/Qdrant/OpenSearch writes.
- No source-truth mutation.
- Refined Dublin Core metadata cannot answer directly or prove claims.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_dublin_core_crosswalk_refinement_v1"
ALGORITHM = "trace_net_dublin_core_crosswalk_physical_operational_refinement_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/dublin_core_crosswalk_refined")

PHYSICAL_ELEMENT_TYPES = {
    "source_text",
    "ocr_text",
    "source_text_evidence",
    "source_trace",
    "table",
    "table_row",
    "table_cell",
    "table_repair",
    "table_answer_support_row_candidate",
    "visual_region",
    "callout_candidate",
    "linked_part_candidate",
    "part_candidate",
    "part_candidate_search_document",
    "citation",
    "source_candidate",
    "evidence_candidate",
}

OPERATIONAL_ELEMENT_PREFIXES = (
    "route:",
    "rag_bucket:",
    "layout:",
    "visual_type:",
)

OPERATIONAL_ELEMENT_TYPES = {
    "page_node",
    "page_element_registry",
    "visual_understanding",
    "fishnet_plan",
    "fishnet_action",
    "extraction_route_plan",
    "review_task",
    "feedback_memory",
    "community",
    "trust_authority",
    "blank_source_trace_preservation",
    "search_document_embedding_candidate",
    "search_document_page_profile",
    "table_cell_search_document",
    "table_row_search_document",
    "part_candidate_search_document",
    "community_search_document",
    "context_retrieval_helper_search_document",
    "context_v2",
}

ANSWER_OR_PROOF_KEYS = {
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def unique_strings(values: Iterable[Any]) -> list[str]:
    return sorted({str(v).strip() for v in values if v is not None and str(v).strip()})


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "pass", "present", "ok"}
    return bool(value)


def clean_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for key, raw_count in value.items():
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError):
            continue
        if count > 0:
            out[str(key)] = count
    return dict(sorted(out.items()))


def count_sum(counter: dict[str, int]) -> int:
    return int(sum(int(v) for v in counter.values() if int(v) > 0))


def is_operational_type(element_type: str) -> bool:
    if element_type in OPERATIONAL_ELEMENT_TYPES:
        return True
    return element_type.startswith(OPERATIONAL_ELEMENT_PREFIXES)


def split_element_counts(element_counts: dict[str, int], *, is_blank_page: bool = False) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """Return physical, operational and uncategorized element count maps."""
    physical: Counter[str] = Counter()
    operational: Counter[str] = Counter()
    other: Counter[str] = Counter()

    for element_type, count in element_counts.items():
        if count <= 0:
            continue
        if is_blank_page:
            # Blank pages should not appear physically complex because of graph/search/review metadata.
            # Preserve source/citation/provenance signals as operational lineage, not physical content.
            if element_type in PHYSICAL_ELEMENT_TYPES or element_type == "blank_source_trace_preservation":
                operational[f"blank_lineage_or_suppressed_physical_signal:{element_type}"] += count
                continue
        if element_type in PHYSICAL_ELEMENT_TYPES:
            physical[element_type] += count
        elif is_operational_type(element_type):
            operational[element_type] += count
        else:
            other[element_type] += count

    return dict(sorted(physical.items())), dict(sorted(operational.items())), dict(sorted(other.items()))


def infer_blank(record: dict[str, Any], element_counts: dict[str, int]) -> bool:
    dc_types = set(unique_strings(record.get("dc", {}).get("dc:type") if isinstance(record.get("dc"), dict) else []))
    trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
    if "blank_page" in dc_types:
        return True
    if truthy(trace.get("trace_net:source_confirmed_blank")):
        return True
    if element_counts.get("blank_source_trace_preservation", 0) > 0:
        return True
    if element_counts.get("layout:blank", 0) > 0:
        return True
    return False


def infer_clean_dc_types(record: dict[str, Any], physical: dict[str, int], operational: dict[str, int], other: dict[str, int], *, is_blank_page: bool) -> tuple[list[str], list[str]]:
    old_dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
    old_types = set(unique_strings(old_dc.get("dc:type")))
    trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
    all_counts = {**physical, **operational, **other}

    clean = {"technical_manual_page"}
    secondary: set[str] = set()

    if is_blank_page:
        clean.add("blank_page")
    else:
        source_text_signal = physical.get("source_text", 0) + physical.get("source_text_evidence", 0)
        if source_text_signal > 0 or truthy(trace.get("trace_net:ocr_present")) or "text_page" in old_types:
            clean.add("text_page")

        # Keep public Dublin Core page types strict. Broad route/overlay signals such as
        # a generic ``table`` placeholder or one page-level ``visual_region`` are useful
        # TRACE-Net signals, but they should not make every page look like a table or
        # visual page in catalog metadata. Those weak signals are preserved below as
        # ``secondary_type_signals`` instead.
        strong_table_signal = (
            physical.get("table_row", 0)
            + physical.get("table_cell", 0)
            + physical.get("table_repair", 0)
            + physical.get("table_answer_support_row_candidate", 0)
        )
        weak_table_signal = physical.get("table", 0)
        if strong_table_signal > 0:
            clean.add("table_page")
        elif weak_table_signal > 0:
            secondary.add("weak_table_signal")

        if physical.get("table_repair", 0) > 0 or "parts_list_table" in old_types:
            secondary.add("parts_list_signal")

        part_signal = (
            physical.get("part_candidate", 0)
            + physical.get("linked_part_candidate", 0)
            + physical.get("part_candidate_search_document", 0)
            + physical.get("verified_part_evidence", 0)
        )
        if part_signal > 0:
            clean.add("parts_page")

        strong_visual_signal = physical.get("callout_candidate", 0) + physical.get("linked_part_candidate", 0)
        weak_visual_signal = physical.get("visual_region", 0)
        if strong_visual_signal > 0:
            clean.add("visual_page")
            secondary.add("diagram_signal")
        elif weak_visual_signal > 0:
            secondary.add("weak_visual_region_signal")

    if trace.get("trace_net:context_v2_present") or operational.get("context_v2", 0) > 0 or "context_v2_page" in old_types:
        secondary.add("context_v2_present")
    if trace.get("trace_net:review_required"):
        secondary.add("review_required")
    if operational.get("community", 0) > 0 or "community" in str(trace.get("trace_net:community_ids", [])).lower():
        secondary.add("community_member")
    if operational.get("fishnet_action", 0) > 0 or operational.get("fishnet_plan", 0) > 0:
        secondary.add("fishnet_signal")
    for old in old_types:
        if old not in clean:
            secondary.add(f"old_type:{old}")

    return sorted(clean), sorted(secondary)


def compute_complexity_score(physical: dict[str, int], operational: dict[str, int], other: dict[str, int], record: dict[str, Any], *, is_blank_page: bool) -> float:
    if is_blank_page:
        return 0.0
    review_required = truthy((record.get("trace_net") or {}).get("trace_net:review_required"))
    score = 0.0
    score += min(0.20, 0.02 * physical.get("source_text", 0))
    score += min(0.30, 0.004 * physical.get("table_cell", 0) + 0.006 * physical.get("table_row", 0))
    score += min(0.20, 0.05 * physical.get("table", 0) + 0.05 * physical.get("table_repair", 0))
    score += min(0.25, 0.015 * physical.get("callout_candidate", 0) + 0.03 * physical.get("linked_part_candidate", 0) + 0.04 * physical.get("visual_region", 0))
    score += min(0.15, 0.005 * physical.get("part_candidate", 0) + 0.004 * physical.get("part_candidate_search_document", 0))
    score += min(0.12, 0.002 * count_sum(operational))
    score += min(0.08, 0.001 * count_sum(other))
    if review_required:
        score += 0.25
    return round(min(1.0, score), 4)


def complexity_class(score: float, *, is_blank_page: bool, review_required: bool) -> str:
    if is_blank_page:
        return "blank"
    if review_required and score >= 0.35:
        return "high_review"
    if score >= 0.70:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def build_review_summary(record: dict[str, Any], clean_types: list[str]) -> dict[str, Any]:
    trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
    review_required = truthy(trace.get("trace_net:review_required"))
    review_task_ids = unique_strings(trace.get("trace_net:review_task_ids") or trace.get("trace_net:review_card_ids") or [])
    reasons: list[str] = []
    if review_required:
        reasons.append("review_required")
    if "visual_page" in clean_types or "diagram_page" in clean_types:
        reasons.append("visual_or_diagram_signal")
    if "table_page" in clean_types and "parts_page" in clean_types:
        reasons.append("table_or_part_signal")
    for key in ("trace_net:review_reasons", "trace_net:review_reason_counts"):
        value = trace.get(key)
        if isinstance(value, dict):
            reasons.extend(value.keys())
        else:
            reasons.extend(str(v) for v in as_list(value))
    priority = "none"
    raw_priority = trace.get("trace_net:highest_review_priority") or trace.get("trace_net:review_priority")
    if raw_priority:
        priority = str(raw_priority)
    elif review_required:
        priority = "high" if ("visual_page" in clean_types or "table_page" in clean_types) else "medium"
    return {
        "review_required": review_required,
        "review_task_count": int(trace.get("trace_net:review_task_count") or len(review_task_ids) or 0),
        "highest_review_priority": priority,
        "review_task_ids": review_task_ids,
        "review_reasons": unique_strings(reasons),
    }


def build_search_summary(record: dict[str, Any], physical: dict[str, int], operational: dict[str, int]) -> dict[str, Any]:
    trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
    search_doc_type_counts = trace.get("trace_net:opensearch_document_type_counts") or trace.get("trace_net:search_document_type_counts") or {}
    if not isinstance(search_doc_type_counts, dict):
        search_doc_type_counts = {}
    return {
        "opensearch_document_count": int(trace.get("trace_net:opensearch_document_count") or count_sum({k: v for k, v in operational.items() if "search_document" in k}) or 0),
        "opensearch_document_type_counts": clean_count_map(search_doc_type_counts),
        "qdrant_candidate_count": int(trace.get("trace_net:qdrant_candidate_count") or trace.get("trace_net:embedding_candidate_count") or 0),
        "answer_support_candidate_count": int(trace.get("trace_net:answer_support_candidate_count") or physical.get("table_answer_support_row_candidate", 0) or 0),
        "retrieval_only_candidate_count": int(trace.get("trace_net:retrieval_only_candidate_count") or 0),
    }


def build_graph_summary(record: dict[str, Any], physical: dict[str, int], operational: dict[str, int]) -> dict[str, Any]:
    trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
    return {
        "graph_node_count": int(trace.get("trace_net:graph_node_count") or trace.get("trace_net:node_count") or 0),
        "graph_edge_count": int(trace.get("trace_net:graph_edge_count") or trace.get("trace_net:edge_count") or 0),
        "community_ids": unique_strings(trace.get("trace_net:community_ids") or []),
        "part_candidate_count": int(trace.get("trace_net:part_candidate_count") or physical.get("part_candidate", 0) or physical.get("linked_part_candidate", 0) or 0),
        "citation_count": int(trace.get("trace_net:citation_count") or physical.get("citation", 0) or 0),
    }


def sanitize_dc(record: dict[str, Any], clean_types: list[str], secondary: list[str], physical_total: int, operational_total: int) -> dict[str, Any]:
    old_dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
    dc = dict(old_dc)
    dc["dc:type"] = clean_types
    dc["trace_net:secondary_type_signals"] = secondary
    dc["dcterms:extent"] = f"physical elements: {physical_total}; operational elements: {operational_total}"
    return dc


def refine_page_record(record: dict[str, Any]) -> dict[str, Any]:
    trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
    raw_counts = clean_count_map(trace.get("trace_net:element_type_counts"))
    is_blank_page = infer_blank(record, raw_counts)
    physical, operational, other = split_element_counts(raw_counts, is_blank_page=is_blank_page)
    physical_total = count_sum(physical)
    operational_total = count_sum(operational) + count_sum(other)
    clean_types, secondary = infer_clean_dc_types(record, physical, operational, other, is_blank_page=is_blank_page)
    score = compute_complexity_score(physical, operational, other, record, is_blank_page=is_blank_page)
    review_summary = build_review_summary(record, clean_types)
    refined_class = complexity_class(score, is_blank_page=is_blank_page, review_required=review_summary["review_required"])

    dc = sanitize_dc(record, clean_types, secondary, physical_total, operational_total)
    refined_trace = dict(trace)
    refined_trace.update(
        {
            "trace_net:clean_dc_type": clean_types,
            "trace_net:secondary_type_signals": secondary,
            "trace_net:physical_element_count": physical_total,
            "trace_net:physical_element_type_count": len(physical),
            "trace_net:physical_element_type_counts": physical,
            "trace_net:operational_element_count": operational_total,
            "trace_net:operational_element_type_count": len(operational) + len(other),
            "trace_net:operational_element_type_counts": {**operational, **{f"uncategorized:{k}": v for k, v in other.items()}},
            "trace_net:page_complexity_score": score,
            "trace_net:complexity_class_refined": refined_class,
            "trace_net:review": review_summary,
            "trace_net:search": build_search_summary(record, physical, operational),
            "trace_net:graph": build_graph_summary(record, physical, operational),
            "trace_net:can_answer_directly": False,
            "trace_net:can_prove_claims": False,
            "trace_net:source_truth_mutation_allowed": False,
        }
    )

    refined = dict(record)
    refined["dc"] = dc
    refined["trace_net"] = refined_trace
    refined["can_answer_directly"] = False
    refined["can_prove_claims"] = False
    refined["source_truth_mutation_allowed"] = False
    refined["refinement_id"] = f"dcxref::{stable_hash([record.get('page_id'), clean_types, physical, operational])}"
    return refined


def refine_document_record(document: dict[str, Any], page_records: list[dict[str, Any]]) -> dict[str, Any]:
    physical_total = sum(int(r["trace_net"].get("trace_net:physical_element_count") or 0) for r in page_records)
    operational_total = sum(int(r["trace_net"].get("trace_net:operational_element_count") or 0) for r in page_records)
    clean_type_counts = Counter()
    for record in page_records:
        for dc_type in record.get("dc", {}).get("dc:type", []):
            clean_type_counts[dc_type] += 1
    refined = dict(document)
    trace = dict(refined.get("trace_net") if isinstance(refined.get("trace_net"), dict) else {})
    trace.update(
        {
            "trace_net:physical_element_count": physical_total,
            "trace_net:operational_element_count": operational_total,
            "trace_net:clean_dc_type_counts": dict(sorted(clean_type_counts.items())),
            "trace_net:can_answer_directly": False,
            "trace_net:can_prove_claims": False,
            "trace_net:source_truth_mutation_allowed": False,
        }
    )
    refined["trace_net"] = trace
    refined["can_answer_directly"] = False
    refined["can_prove_claims"] = False
    refined["source_truth_mutation_allowed"] = False
    return refined


def build_summary(page_records: list[dict[str, Any]], document_records: list[dict[str, Any]], source_payload: dict[str, Any]) -> dict[str, Any]:
    clean_type_counts = Counter()
    complexity_counts = Counter()
    secondary_counts = Counter()
    missing_clean_dc_type = 0
    physical_present = 0
    operational_present = 0
    records_with_review_summary = 0
    direct_answer_allowed = 0
    claim_proof_allowed = 0
    mutation_allowed = 0
    blank_count = 0
    blank_with_blank_type = 0
    blank_low_physical = 0
    overbroad_clean_type = 0
    old_overbroad = 0
    physical_total = 0
    operational_total = 0

    for record in page_records:
        dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
        trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
        clean_types = unique_strings(dc.get("dc:type"))
        old_types = unique_strings(record.get("source_dc_type") or [])
        if not clean_types:
            missing_clean_dc_type += 1
        if len(clean_types) > 5:
            overbroad_clean_type += 1
        if len(old_types) > 4:
            old_overbroad += 1
        for value in clean_types:
            clean_type_counts[value] += 1
        for value in unique_strings(trace.get("trace_net:secondary_type_signals") or []):
            secondary_counts[value] += 1
        physical = int(trace.get("trace_net:physical_element_count") or 0)
        operational = int(trace.get("trace_net:operational_element_count") or 0)
        physical_total += physical
        operational_total += operational
        if "trace_net:physical_element_count" in trace:
            physical_present += 1
        if "trace_net:operational_element_count" in trace:
            operational_present += 1
        if isinstance(trace.get("trace_net:review"), dict):
            records_with_review_summary += 1
        if str(trace.get("trace_net:complexity_class_refined") or ""):
            complexity_counts[str(trace.get("trace_net:complexity_class_refined"))] += 1
        if "blank_page" in clean_types:
            blank_count += 1
            if "blank_page" in clean_types:
                blank_with_blank_type += 1
            if physical <= 1:
                blank_low_physical += 1
        if truthy(record.get("can_answer_directly")) or truthy(trace.get("trace_net:can_answer_directly")):
            direct_answer_allowed += 1
        if truthy(record.get("can_prove_claims")) or truthy(trace.get("trace_net:can_prove_claims")):
            claim_proof_allowed += 1
        if truthy(record.get("source_truth_mutation_allowed")) or truthy(trace.get("trace_net:source_truth_mutation_allowed")):
            mutation_allowed += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "source_crosswalk_quality_status": source_payload.get("quality_status") or source_payload.get("summary", {}).get("quality_status"),
        "source_crosswalk_status": source_payload.get("status"),
        "page_record_count": len(page_records),
        "document_record_count": len(document_records),
        "records_with_physical_element_counts": physical_present,
        "records_with_operational_element_counts": operational_present,
        "records_with_review_summary": records_with_review_summary,
        "missing_clean_dc_type_count": missing_clean_dc_type,
        "clean_dc_type_counts": dict(sorted(clean_type_counts.items())),
        "secondary_type_signal_counts": dict(sorted(secondary_counts.items())),
        "complexity_class_refined_counts": dict(sorted(complexity_counts.items())),
        "blank_page_count": blank_count,
        "blank_pages_with_blank_type_count": blank_with_blank_type,
        "blank_pages_with_low_physical_count": blank_low_physical,
        "physical_element_total_count": physical_total,
        "operational_element_total_count": operational_total,
        "old_overbroad_dc_type_count": old_overbroad,
        "clean_overbroad_dc_type_count": overbroad_clean_type,
        "dc_type_overbroad_reduction_count": max(0, old_overbroad - overbroad_clean_type),
        "direct_answer_allowed_count": direct_answer_allowed,
        "claim_proof_allowed_count": claim_proof_allowed,
        "source_truth_mutation_allowed_count": mutation_allowed,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def check_quality_summary(summary: dict[str, Any], quality_config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = quality_config or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    required_page_count = cfg.get("require_page_count")
    if required_page_count is not None:
        add("page_record_count_matches_required", int(summary.get("page_record_count") or 0) == int(required_page_count), summary.get("page_record_count"), required_page_count)
    min_page_records = int(cfg.get("min_page_records") or 0)
    if min_page_records:
        add("min_page_records", int(summary.get("page_record_count") or 0) >= min_page_records, summary.get("page_record_count"), min_page_records)
    min_physical = int(cfg.get("min_records_with_physical_counts") or 0)
    if min_physical:
        add("min_records_with_physical_element_counts", int(summary.get("records_with_physical_element_counts") or 0) >= min_physical, summary.get("records_with_physical_element_counts"), min_physical)
    min_operational = int(cfg.get("min_records_with_operational_counts") or 0)
    if min_operational:
        add("min_records_with_operational_element_counts", int(summary.get("records_with_operational_element_counts") or 0) >= min_operational, summary.get("records_with_operational_element_counts"), min_operational)
    min_review = int(cfg.get("min_records_with_review_summary") or 0)
    if min_review:
        add("min_records_with_review_summary", int(summary.get("records_with_review_summary") or 0) >= min_review, summary.get("records_with_review_summary"), min_review)
    min_blank = int(cfg.get("min_blank_pages_with_low_physical") or 0)
    if min_blank:
        add("min_blank_pages_with_low_physical", int(summary.get("blank_pages_with_low_physical_count") or 0) >= min_blank, summary.get("blank_pages_with_low_physical_count"), min_blank)
    max_overbroad = cfg.get("max_clean_overbroad_dc_type")
    if max_overbroad is not None:
        add("max_clean_overbroad_dc_type", int(summary.get("clean_overbroad_dc_type_count") or 0) <= int(max_overbroad), summary.get("clean_overbroad_dc_type_count"), max_overbroad)

    add("missing_clean_dc_type_count_zero", int(summary.get("missing_clean_dc_type_count") or 0) == 0, summary.get("missing_clean_dc_type_count"), 0)
    add("direct_answer_allowed_count_zero", int(summary.get("direct_answer_allowed_count") or 0) == 0, summary.get("direct_answer_allowed_count"), 0)
    add("claim_proof_allowed_count_zero", int(summary.get("claim_proof_allowed_count") or 0) == 0, summary.get("claim_proof_allowed_count"), 0)
    add("source_truth_mutation_allowed_count_zero", int(summary.get("source_truth_mutation_allowed_count") or 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("no_write_attempts", int(summary.get("postgres_write_attempt_count") or 0) == 0 and int(summary.get("qdrant_write_attempt_count") or 0) == 0 and int(summary.get("opensearch_write_attempt_count") or 0) == 0, {"postgres": summary.get("postgres_write_attempt_count"), "qdrant": summary.get("qdrant_write_attempt_count"), "opensearch": summary.get("opensearch_write_attempt_count")}, 0)

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {"status": status, "checks": checks}


def build_refinement_report(
    *,
    crosswalk_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    quality_config: dict[str, Any] | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    source = read_json(crosswalk_path)
    page_records = [r for r in source.get("page_records", []) if isinstance(r, dict)]
    document_records = [r for r in source.get("document_records", []) if isinstance(r, dict)]

    refined_pages: list[dict[str, Any]] = []
    for record in page_records:
        refined = refine_page_record(record)
        old_dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
        refined["source_dc_type"] = unique_strings(old_dc.get("dc:type"))
        refined_pages.append(refined)

    refined_docs = [refine_document_record(doc, refined_pages) for doc in document_records]
    if not refined_docs and refined_pages:
        refined_docs = [
            refine_document_record(
                {
                    "document_id": "unknown_document",
                    "dc": {"dc:identifier": "unknown_document", "dc:type": ["technical_manual"]},
                    "trace_net": {},
                },
                refined_pages,
            )
        ]

    summary = build_summary(refined_pages, refined_docs, source)
    quality = check_quality_summary(summary, quality_config)
    summary["status"] = quality["status"]

    out = Path(output_dir)
    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "DUBLIN_CORE_CROSSWALK_REFINEMENT_BUILT",
        "quality_status": quality["status"],
        "generated_at": now_iso(),
        "source_crosswalk_path": str(crosswalk_path),
        "summary": summary,
        "quality": quality,
        "page_records": refined_pages,
        "document_records": refined_docs,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }

    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_dublin_core_crosswalk_refinement_v1.json"
    pages_path = out / "trace_net_dublin_core_refined_pages_v1.jsonl"
    documents_path = out / "trace_net_dublin_core_refined_documents_v1.jsonl"
    summary_path = out / "trace_net_dublin_core_crosswalk_refinement_v1_summary.json"
    quality_path = out / "trace_net_dublin_core_crosswalk_refinement_v1_quality.json"
    manifest_path = out / "trace_net_dublin_core_crosswalk_refinement_v1_manifest.json"
    md_path = out / "trace_net_dublin_core_crosswalk_refinement_v1.md"
    html_path = out / "trace_net_dublin_core_crosswalk_refinement_v1.html"

    write_json(report_path, report)
    write_jsonl(pages_path, refined_pages)
    write_jsonl(documents_path, refined_docs)
    write_json(summary_path, summary)
    write_json(quality_path, {"status": quality["status"], **summary, "checks": quality["checks"]})
    write_json(manifest_path, {"schema_version": SCHEMA_VERSION, "report_path": str(report_path), "pages_path": str(pages_path), "documents_path": str(documents_path), "quality_path": str(quality_path), "generated_at": report["generated_at"]})
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")

    report.update({"report_path": str(report_path), "pages_path": str(pages_path), "documents_path": str(documents_path), "summary_path": str(summary_path), "quality_path": str(quality_path), "manifest_path": str(manifest_path), "markdown_path": str(md_path), "html_path": str(html_path)})
    if write_quality:
        write_json(quality_path, {"status": quality["status"], **summary, "checks": quality["checks"]})
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Dublin Core Crosswalk Refinement v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    keys = [
        "page_record_count",
        "document_record_count",
        "records_with_physical_element_counts",
        "records_with_operational_element_counts",
        "records_with_review_summary",
        "blank_page_count",
        "blank_pages_with_low_physical_count",
        "old_overbroad_dc_type_count",
        "clean_overbroad_dc_type_count",
        "dc_type_overbroad_reduction_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
    ]
    for key in keys:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Clean Dublin Core type counts", ""])
    for key, value in (summary.get("clean_dc_type_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"


def render_html(report: dict[str, Any]) -> str:
    body = html.escape(render_markdown(report)).replace("\n", "<br>\n")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Dublin Core Crosswalk Refinement v1</title></head><body><pre>{body}</pre></body></html>"


def quality_report(*, report_path: str | Path, quality_config: dict[str, Any] | None = None, write_json_report: bool = False) -> dict[str, Any]:
    payload = read_json(report_path)
    summary = payload.get("summary", payload if isinstance(payload, dict) else {})
    quality = check_quality_summary(summary, quality_config)
    out = {"status": quality["status"], **summary, "checks": quality["checks"]}
    if write_json_report:
        path = Path(report_path).with_name("trace_net_dublin_core_crosswalk_refinement_v1_quality.json")
        write_json(path, out)
        out["quality_path"] = str(path)
    return out


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Dublin Core Crosswalk Refinement v1")
    parser.add_argument("--crosswalk", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-page-records", type=int, default=0)
    parser.add_argument("--min-records-with-physical-counts", type=int, default=0)
    parser.add_argument("--min-records-with-operational-counts", type=int, default=0)
    parser.add_argument("--min-records-with-review-summary", type=int, default=0)
    parser.add_argument("--min-blank-pages-with-low-physical", type=int, default=0)
    parser.add_argument("--max-clean-overbroad-dc-type", type=int, default=None)
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    quality_config = {
        "require_page_count": args.require_page_count,
        "min_page_records": args.min_page_records,
        "min_records_with_physical_counts": args.min_records_with_physical_counts,
        "min_records_with_operational_counts": args.min_records_with_operational_counts,
        "min_records_with_review_summary": args.min_records_with_review_summary,
        "min_blank_pages_with_low_physical": args.min_blank_pages_with_low_physical,
        "max_clean_overbroad_dc_type": args.max_clean_overbroad_dc_type,
    }
    report = build_refinement_report(crosswalk_path=args.crosswalk, output_dir=args.output_dir, quality_config=quality_config, write_quality=args.quality)
    summary = report["summary"]
    print("TRACE-Net Dublin Core Crosswalk Refinement v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "page_record_count",
        "document_record_count",
        "records_with_physical_element_counts",
        "records_with_operational_element_counts",
        "records_with_review_summary",
        "blank_page_count",
        "blank_pages_with_low_physical_count",
        "old_overbroad_dc_type_count",
        "clean_overbroad_dc_type_count",
        "dc_type_overbroad_reduction_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
