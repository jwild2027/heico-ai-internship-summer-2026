"""TRACE-Net Element Category Taxonomy v1.

Normalizes TRACE-Net page/graph/search/review element signals into a stable
category taxonomy that can feed UI filtering, review triage and later
category-aware Leiden/community overlays.

Safety contract:
- Read-only taxonomy/profile build only.
- No Postgres/Qdrant/OpenSearch writes.
- Categories are navigation/retrieval/review metadata only.
- Categories cannot answer directly, prove claims, or mutate source truth.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_element_category_taxonomy_v1"
ALGORITHM = "trace_net_element_category_normalizer_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/element_category_taxonomy")

FAMILY_ORDER = [
    "source",
    "text",
    "table",
    "visual",
    "diagram",
    "chart",
    "part",
    "citation",
    "evidence",
    "trust",
    "context",
    "search",
    "community",
    "feedback",
    "review",
    "incident",
    "operation",
    "page_trait",
    "blank",
    "other",
]

ANSWER_OR_PROOF_KEYS = {
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
}

CATEGORY_LIBRARY: dict[str, tuple[str, str, str]] = {
    # Source/text/evidence.
    "source_trace": ("source", "source_trace", "source_locator"),
    "source_candidate": ("source", "source_candidate", "source_locator"),
    "source_evidence": ("source", "source_evidence", "source_locator"),
    "source_text": ("text", "source_text", "answer_support_candidate"),
    "source_text_evidence": ("text", "source_text_evidence", "answer_support_candidate"),
    "ocr_text": ("text", "ocr_text", "working_or_source_text"),
    "evidence_candidate": ("evidence", "evidence_candidate", "requires_authority_gate"),
    "verified_part_evidence": ("part", "verified_part_evidence", "answer_support_candidate"),
    "derived_context": ("context", "derived_context", "retrieval_helper"),
    "context_retrieval_helper": ("context", "context_retrieval_helper", "retrieval_helper"),
    "context_v2": ("context", "page_context_v2", "retrieval_helper"),
    # Tables.
    "table": ("table", "table", "retrieval_review"),
    "table_element": ("table", "table", "retrieval_review"),
    "table_row": ("table", "table_row", "retrieval_review"),
    "tablerow": ("table", "table_row", "retrieval_review"),
    "table_cell": ("table", "table_cell", "retrieval_helper"),
    "tablecell": ("table", "table_cell", "retrieval_helper"),
    "table_repair": ("table", "table_repair", "review_or_promotion_candidate"),
    "tablecellrepair": ("table", "table_repair", "review_or_promotion_candidate"),
    "table_answer_support_row_candidate": ("table", "table_answer_support_row_candidate", "answer_support_candidate"),
    "table_row_normalized": ("table", "table_row_normalized", "retrieval_helper"),
    "table_cell_normalized": ("table", "table_cell_normalized", "retrieval_helper"),
    # Visual/diagram/chart.
    "visual_understanding": ("visual", "visual_understanding", "retrieval_review"),
    "visual_region": ("visual", "visual_region", "retrieval_review"),
    "visualregion": ("visual", "visual_region", "retrieval_review"),
    "callout_candidate": ("diagram", "diagram_callout_candidate", "review_only"),
    "calloutcandidate": ("diagram", "diagram_callout_candidate", "review_only"),
    "linked_part_candidate": ("part", "visual_linked_part_candidate", "review_only"),
    "chart_candidate": ("chart", "chart_or_plot_candidate", "retrieval_review"),
    "chart_or_plot_candidate": ("chart", "chart_or_plot_candidate", "retrieval_review"),
    "figure_part_catalog_retrieval_helper": ("diagram", "figure_part_catalog_retrieval_helper", "retrieval_helper"),
    # Parts.
    "part_candidate": ("part", "part_candidate", "navigation_review"),
    "partcandidate": ("part", "part_candidate", "navigation_review"),
    "part_candidate_search_document": ("part", "part_candidate_lineage", "navigation_helper"),
    "part_candidate_lineage": ("part", "part_candidate_lineage", "navigation_helper"),
    # Citation/trust.
    "citation": ("citation", "citation", "source_support"),
    "trust_authority": ("trust", "trust_authority", "authority_gate"),
    "trustauthority": ("trust", "trust_authority", "authority_gate"),
    # Operations/review/feedback/community/search.
    "fishnet_plan": ("operation", "fishnet_plan", "retry_review_plan"),
    "fishnetretryplan": ("operation", "fishnet_plan", "retry_review_plan"),
    "fishnet_action": ("operation", "fishnet_action", "retry_review_action"),
    "fishnetretryaction": ("operation", "fishnet_action", "retry_review_action"),
    "extraction_route_plan": ("operation", "extraction_route_plan", "routing_helper"),
    "extractionrouteplan": ("operation", "extraction_route_plan", "routing_helper"),
    "review_task": ("review", "human_review_task", "human_workflow"),
    "feedback_memory": ("feedback", "feedback_memory", "advisory_memory"),
    "community": ("community", "leiden_community", "navigation_helper"),
    "community_summary": ("community", "community_summary", "navigation_helper"),
    "community_retrieval_helper": ("community", "community_retrieval_helper", "navigation_helper"),
    "search_document_embedding_candidate": ("search", "opensearch_embedding_candidate_document", "search_only"),
    "search_document_page_profile": ("search", "opensearch_page_profile_document", "search_only"),
    "opensearch_document": ("search", "opensearch_document", "search_only"),
    "page_retrieval_profile": ("search", "page_retrieval_profile", "route_only"),
    "context_retrieval_helper_search_document": ("search", "context_helper_search_document", "search_only"),
    "table_cell_search_document": ("search", "table_cell_search_document", "search_only"),
    "table_row_search_document": ("search", "table_row_search_document", "search_only"),
    "community_search_document": ("search", "community_search_document", "search_only"),
    "blank_source_trace_preservation": ("blank", "blank_source_trace_preservation", "source_locator"),
    "page_element_registry": ("operation", "page_element_registry", "routing_helper"),
    "page_node": ("source", "page_node", "source_container"),
    "page": ("source", "page_node", "source_container"),
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


def unique_strings(values: Iterable[Any] | Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, int, float, bool)):
        values = [values]
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


def normalize_type(raw_type: Any) -> str:
    text = str(raw_type or "").strip()
    if not text:
        return "unknown"
    # Preserve useful prefix values but normalize separators.
    text = text.replace("/", "_").replace("-", "_").replace(" ", "_")
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def categorize_element(raw_type: Any) -> dict[str, str]:
    raw = str(raw_type or "unknown").strip() or "unknown"
    key = normalize_type(raw)

    # Prefix-based signals from older/refined page metadata.
    if key.startswith("review:") or raw.startswith("review:"):
        review_type = raw.split(":", 1)[1] if ":" in raw else raw
        return {
            "raw_element_type": raw,
            "element_family": "review",
            "element_category": normalize_type(review_type),
            "element_role": "human_workflow",
        }
    if key.startswith("secondary_signal:") or raw.startswith("secondary_signal:"):
        signal = raw.split(":", 1)[1] if ":" in raw else raw
        sig = normalize_type(signal)
        if "review" in sig:
            family, category, role = "review", sig, "human_workflow"
        elif "diagram" in sig or "visual" in sig:
            family, category, role = "diagram", sig, "routing_signal"
        elif "table" in sig:
            family, category, role = "table", sig, "routing_signal"
        elif "context" in sig:
            family, category, role = "context", sig, "routing_signal"
        else:
            family, category, role = "page_trait", sig, "routing_signal"
        return {
            "raw_element_type": raw,
            "element_family": family,
            "element_category": category,
            "element_role": role,
        }
    if key.startswith("dc_type:") or raw.startswith("dc_type:"):
        dc_type = raw.split(":", 1)[1] if ":" in raw else raw
        return {
            "raw_element_type": raw,
            "element_family": "page_trait",
            "element_category": f"dc_type_{normalize_type(dc_type)}",
            "element_role": "catalog_metadata",
        }
    if key.startswith("route:") or raw.startswith("route:"):
        return {
            "raw_element_type": raw,
            "element_family": "operation",
            "element_category": "extraction_route",
            "element_role": "routing_helper",
        }
    if key.startswith("rag_bucket:") or raw.startswith("rag_bucket:"):
        bucket = raw.split(":", 1)[1] if ":" in raw else key.split(":", 1)[-1]
        mapped = categorize_element(bucket)
        mapped["raw_element_type"] = raw
        if mapped["element_family"] == "other":
            mapped.update({
                "element_family": "evidence",
                "element_category": f"rag_bucket_{normalize_type(bucket)}",
                "element_role": "requires_authority_gate",
            })
        return mapped
    if key.startswith("layout:") or raw.startswith("layout:"):
        layout = raw.split(":", 1)[1] if ":" in raw else raw
        return {
            "raw_element_type": raw,
            "element_family": "page_trait",
            "element_category": f"layout_{normalize_type(layout)}",
            "element_role": "routing_signal",
        }
    if key.startswith("visual_type:") or raw.startswith("visual_type:"):
        visual_type = raw.split(":", 1)[1] if ":" in raw else raw
        vt = normalize_type(visual_type)
        family = "chart" if "chart" in vt or "plot" in vt else "diagram" if "diagram" in vt or "parts" in vt else "visual"
        return {
            "raw_element_type": raw,
            "element_family": family,
            "element_category": vt,
            "element_role": "routing_signal",
        }

    if key in CATEGORY_LIBRARY:
        family, category, role = CATEGORY_LIBRARY[key]
        return {
            "raw_element_type": raw,
            "element_family": family,
            "element_category": category,
            "element_role": role,
        }

    # Heuristic fallback makes uncategorized count zero while still surfacing raw type.
    if "callout" in key:
        family, category, role = "diagram", "diagram_callout_candidate", "review_only"
    elif "chart" in key or "plot" in key:
        family, category, role = "chart", "chart_or_plot_candidate", "retrieval_review"
    elif "diagram" in key or "figure" in key:
        family, category, role = "diagram", "diagram_or_figure", "retrieval_review"
    elif "visual" in key or "image" in key:
        family, category, role = "visual", "visual_signal", "retrieval_review"
    elif "table" in key or "cell" in key or "row" in key:
        family, category, role = "table", key, "retrieval_review"
    elif "part" in key or "nomenclature" in key:
        family, category, role = "part", key, "navigation_review"
    elif "citation" in key or "cite" in key:
        family, category, role = "citation", "citation", "source_support"
    elif "source" in key or "ocr" in key or "page" in key:
        family, category, role = "source", key, "source_locator"
    elif "trust" in key or "authority" in key:
        family, category, role = "trust", key, "authority_gate"
    elif "context" in key:
        family, category, role = "context", key, "retrieval_helper"
    elif "feedback" in key:
        family, category, role = "feedback", key, "advisory_memory"
    elif "review" in key:
        family, category, role = "review", key, "human_workflow"
    elif "incident" in key or "alert" in key:
        family, category, role = "incident", key, "operation_alert"
    elif "community" in key or "leiden" in key:
        family, category, role = "community", key, "navigation_helper"
    elif "search" in key or "qdrant" in key or "opensearch" in key or "embedding" in key or "vector" in key:
        family, category, role = "search", key, "search_only"
    elif "fishnet" in key or "route" in key or "operation" in key:
        family, category, role = "operation", key, "routing_or_retry_helper"
    elif "blank" in key:
        family, category, role = "blank", key, "source_locator"
    else:
        family, category, role = "other", f"other_{key}", "metadata_only"

    return {
        "raw_element_type": raw,
        "element_family": family,
        "element_category": category,
        "element_role": role,
    }


def family_rank(family: str) -> int:
    try:
        return FAMILY_ORDER.index(family)
    except ValueError:
        return len(FAMILY_ORDER)


def get_trace(record: dict[str, Any]) -> dict[str, Any]:
    trace = record.get("trace_net")
    return trace if isinstance(trace, dict) else {}


def get_dc(record: dict[str, Any]) -> dict[str, Any]:
    dc = record.get("dc")
    return dc if isinstance(dc, dict) else {}


def build_page_base(crosswalk: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}
    for record in as_list(crosswalk.get("page_records")):
        if not isinstance(record, dict):
            continue
        page_id = str(record.get("page_id") or record.get("dc", {}).get("dc:identifier") or "").strip()
        if not page_id:
            continue
        pages[page_id] = record
    return pages


def add_category_record(
    records: list[dict[str, Any]],
    *,
    page_id: str | None,
    source_layer: str,
    raw_element_type: str,
    element_count: int = 1,
    node_ids: Iterable[str] | None = None,
    source_ids: Iterable[str] | None = None,
) -> None:
    if element_count <= 0:
        return
    cat = categorize_element(raw_element_type)
    node_ids_list = unique_strings(node_ids or [])
    source_ids_list = unique_strings(source_ids or [])
    seed = {
        "page_id": page_id or "",
        "source_layer": source_layer,
        "raw_element_type": raw_element_type,
        "element_count": element_count,
        "node_ids": node_ids_list[:20],
        "source_ids": source_ids_list[:20],
    }
    records.append({
        "category_record_id": f"elcat_{stable_hash(seed)}",
        "page_id": page_id or "",
        "source_layer": source_layer,
        "raw_element_type": cat["raw_element_type"],
        "element_family": cat["element_family"],
        "element_category": cat["element_category"],
        "element_role": cat["element_role"],
        "element_count": int(element_count),
        "node_ids": node_ids_list[:50],
        "source_ids": source_ids_list[:50],
        "supports_leiden_grouping": True,
        "recommended_leiden_edge_policy": "page_local_category_or_low_weight_edge",
        "avoid_global_category_hub": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
    })


def collect_from_dublin_core_refined(crosswalk: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    pages = build_page_base(crosswalk)
    records: list[dict[str, Any]] = []
    for page_id, record in pages.items():
        trace = get_trace(record)
        physical = clean_count_map(trace.get("trace_net:physical_element_type_counts"))
        operational = clean_count_map(trace.get("trace_net:operational_element_type_counts"))
        for raw_type, count in physical.items():
            add_category_record(records, page_id=page_id, source_layer="dublin_core_refined_physical", raw_element_type=raw_type, element_count=count)
        for raw_type, count in operational.items():
            add_category_record(records, page_id=page_id, source_layer="dublin_core_refined_operational", raw_element_type=raw_type, element_count=count)
        for dc_type in as_list(get_dc(record).get("dc:type")):
            add_category_record(records, page_id=page_id, source_layer="dublin_core_refined_dc_type", raw_element_type=f"dc_type:{dc_type}", element_count=1)
        for signal in as_list(trace.get("trace_net:secondary_type_signals")):
            add_category_record(records, page_id=page_id, source_layer="dublin_core_refined_secondary_signal", raw_element_type=f"secondary_signal:{signal}", element_count=1)
    return pages, records


def collect_from_element_graph(graph: dict[str, Any], known_pages: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for node in as_list(graph.get("node_plans")):
        if not isinstance(node, dict):
            continue
        page_id = str(node.get("page_id") or "").strip()
        if page_id and page_id not in known_pages:
            # Keep page scoped records only for known pages to avoid bad lineage.
            continue
        node_type = str(node.get("node_type") or "unknown")
        node_id = str(node.get("node_id") or "")
        if page_id:
            grouped[(page_id, node_type)].append(node_id)
    for (page_id, node_type), node_ids in grouped.items():
        add_category_record(records, page_id=page_id, source_layer="element_graph_attachment_node_type", raw_element_type=node_type, element_count=len(node_ids), node_ids=node_ids)
    return records


def collect_from_opensearch(adapter: dict[str, Any], known_pages: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    grouped: Counter[tuple[str, str]] = Counter()
    doc_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for doc in as_list(adapter.get("documents")):
        if not isinstance(doc, dict):
            continue
        page_ids = unique_strings([doc.get("page_id"), *as_list(doc.get("source_page_ids"))])
        if not page_ids:
            continue
        raw_types = unique_strings([doc.get("document_type"), doc.get("rag_bucket")])
        doc_id = str(doc.get("opensearch_document_id") or doc.get("id") or "")
        for page_id in page_ids:
            if page_id not in known_pages:
                continue
            for raw_type in raw_types:
                key = (page_id, f"opensearch:{raw_type}")
                grouped[key] += 1
                if doc_id:
                    doc_ids[key].append(doc_id)
    for (page_id, raw_type), count in grouped.items():
        add_category_record(records, page_id=page_id, source_layer="opensearch_adapter_document", raw_element_type=raw_type, element_count=count, source_ids=doc_ids[(page_id, raw_type)])
    return records


def collect_from_table_normalizer(table: dict[str, Any], known_pages: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rec in as_list(table.get("records")):
        if not isinstance(rec, dict):
            continue
        page_id = str(rec.get("page_id") or "").strip()
        if not page_id or page_id not in known_pages:
            continue
        add_category_record(records, page_id=page_id, source_layer="table_cell_normalizer", raw_element_type="table", element_count=1)
        for raw_key, raw_type in [
            ("normalized_row_count", "table_row"),
            ("normalized_cell_count", "table_cell"),
            ("repair_count", "table_repair"),
            ("answer_support_row_count", "table_answer_support_row_candidate"),
            ("part_number_merge_candidate_count", "part_number_merge_candidate"),
        ]:
            try:
                count = int(rec.get(raw_key) or 0)
            except (TypeError, ValueError):
                count = 0
            add_category_record(records, page_id=page_id, source_layer="table_cell_normalizer", raw_element_type=raw_type, element_count=count)
    return records


def collect_from_figure_chart(fig: dict[str, Any], known_pages: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rec in as_list(fig.get("records")):
        if not isinstance(rec, dict):
            continue
        page_id = str(rec.get("page_id") or "").strip()
        if not page_id or page_id not in known_pages:
            continue
        visual_type = str(rec.get("visual_type") or "visual_signal")
        add_category_record(records, page_id=page_id, source_layer="figure_chart_understanding", raw_element_type=f"visual_type:{visual_type}", element_count=1)
        for raw_key, raw_type in [
            ("visual_region_count", "visual_region"),
            ("callout_candidate_count", "callout_candidate"),
            ("linked_part_candidate_count", "linked_part_candidate"),
        ]:
            try:
                count = int(rec.get(raw_key) or 0)
            except (TypeError, ValueError):
                count = 0
            add_category_record(records, page_id=page_id, source_layer="figure_chart_understanding", raw_element_type=raw_type, element_count=count)
    return records


def collect_from_callout_verifier(callouts: dict[str, Any], known_pages: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rec in as_list(callouts.get("records")):
        if not isinstance(rec, dict):
            continue
        page_id = str(rec.get("page_id") or "").strip()
        if not page_id or page_id not in known_pages:
            continue
        for raw_key, raw_type in [
            ("clean_callout_count", "clean_diagram_callout"),
            ("suppressed_random_number_count", "suppressed_random_number"),
            ("callout_to_table_row_link_count", "callout_to_table_row_link"),
            ("catalog_verified_visual_part_count", "catalog_verified_visual_part"),
            ("linked_visual_part_candidate_count", "linked_part_candidate"),
        ]:
            try:
                count = int(rec.get(raw_key) or 0)
            except (TypeError, ValueError):
                count = 0
            add_category_record(records, page_id=page_id, source_layer="callout_visual_part_verifier", raw_element_type=raw_type, element_count=count)
    return records


def collect_from_human_review_triage(triage: dict[str, Any], known_pages: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    grouped: Counter[tuple[str, str]] = Counter()
    card_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for card in as_list(triage.get("triage_cards")):
        if not isinstance(card, dict):
            continue
        pages = unique_strings(card.get("page_ids") or [])
        if not pages and card.get("page_id"):
            pages = [str(card.get("page_id"))]
        card_type = str(card.get("card_type") or "review_task")
        card_id = str(card.get("triage_card_id") or "")
        for page_id in pages:
            if page_id not in known_pages:
                continue
            key = (page_id, f"review:{card_type}")
            grouped[key] += 1
            if card_id:
                card_ids[key].append(card_id)
    for (page_id, raw_type), count in grouped.items():
        add_category_record(records, page_id=page_id, source_layer="human_review_triage", raw_element_type=raw_type, element_count=count, source_ids=card_ids[(page_id, raw_type)])
    return records


def collect_from_leiden(leiden: dict[str, Any], known_pages: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    grouped: Counter[tuple[str, str]] = Counter()
    comm_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for community in as_list(leiden.get("communities")):
        if not isinstance(community, dict):
            continue
        community_id = str(community.get("community_id") or "")
        pages = unique_strings(community.get("page_ids") or [])
        for page_id in pages:
            if page_id not in known_pages:
                continue
            key = (page_id, "community")
            grouped[key] += 1
            if community_id:
                comm_ids[key].append(community_id)
    for (page_id, raw_type), count in grouped.items():
        add_category_record(records, page_id=page_id, source_layer="leiden_graph_communities", raw_element_type=raw_type, element_count=count, source_ids=comm_ids[(page_id, raw_type)])
    return records


LEIDEN_SIGNAL_FAMILIES = {
    "source",
    "text",
    "table",
    "visual",
    "diagram",
    "chart",
    "part",
    "citation",
    "evidence",
    "trust",
    "context",
    "review",
    "blank",
}

INFRASTRUCTURE_FAMILIES = {"operation", "community", "search", "feedback", "page_trait", "other"}



CONTENT_LEIDEN_HINT_FAMILIES = {
    "source",
    "text",
    "table",
    "visual",
    "diagram",
    "chart",
    "part",
    "citation",
    "evidence",
    "context",
    "review",
    "blank",
}

BASE_TEXT_HINT_FAMILIES = {"source", "text", "citation", "evidence", "context", "review"}
BASE_TABLE_HINT_FAMILIES = {"source", "text", "table", "citation", "evidence", "part", "context", "review"}
BASE_VISUAL_HINT_FAMILIES = {"source", "text", "visual", "diagram", "chart", "citation", "evidence", "part", "context", "review"}
BASE_PARTS_HINT_FAMILIES = {"source", "text", "part", "citation", "evidence", "context", "review"}
BASE_BLANK_HINT_FAMILIES = {"blank", "source", "citation", "review"}

def dominant_items(counter: Counter[str], limit: int = 8) -> list[str]:
    return [name for name, _ in sorted(counter.items(), key=lambda kv: (-kv[1], family_rank(kv[0]) if kv[0] in FAMILY_ORDER else 999, kv[0]))[:limit]]


def filtered_counter(counter: Counter[str], allowed: set[str]) -> Counter[str]:
    return Counter({key: value for key, value in counter.items() if key in allowed and value > 0})


def ordered_present_families(families: set[str], family_counts: Counter[str]) -> list[str]:
    return [family for family in FAMILY_ORDER if family in families and family_counts.get(family, 0) > 0]


def build_leiden_hint_family_selection(
    *,
    dc_types: list[str],
    family_counts: Counter[str],
    semantic_dominant_families: list[str],
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Choose safe category families for later Leiden grouping hints.

    The public/refined dc:type is treated as the strongest signal. Weak table or
    visual route signals remain visible in counts and secondary_type_signals, but
    they should not create page-local Leiden category nodes for text/front-matter
    pages. This prevents category-aware Leiden from pulling text pages into
    table/diagram communities only because every page has broad visual/table
    routing artifacts.
    """
    dc_set = set(dc_types)
    allowed: set[str] = set()

    if "blank_page" in dc_set:
        allowed |= BASE_BLANK_HINT_FAMILIES
    if "text_page" in dc_set:
        allowed |= BASE_TEXT_HINT_FAMILIES
    if "table_page" in dc_set:
        allowed |= BASE_TABLE_HINT_FAMILIES
    if "visual_page" in dc_set or "diagram_page" in dc_set:
        allowed |= BASE_VISUAL_HINT_FAMILIES
    if "chart_page" in dc_set:
        allowed |= {"source", "text", "visual", "chart", "citation", "evidence", "context", "review"}
    if "parts_page" in dc_set:
        allowed |= BASE_PARTS_HINT_FAMILIES

    # If the refined type only says technical_manual_page, use conservative
    # source/text/context hints, not table/visual fallbacks.
    if not allowed:
        allowed |= {"source", "text", "citation", "evidence", "context", "review"}

    # Keep review as a hint when review tasks are present.
    if family_counts.get("review", 0) > 0:
        allowed.add("review")

    hint_families = ordered_present_families(allowed & CONTENT_LEIDEN_HINT_FAMILIES, family_counts)[:8]

    # Fallback for legacy inputs with sparse dc:type, but still use only
    # content-bearing families and avoid infrastructure.
    if not hint_families:
        hint_families = [family for family in semantic_dominant_families if family in CONTENT_LEIDEN_HINT_FAMILIES][:8]

    suppressed = [family for family in semantic_dominant_families if family not in set(hint_families)]
    policy = {
        "policy_name": "refined_dc_type_first_no_weak_table_visual_hints_v1",
        "dc_type_first": True,
        "weak_table_visual_signals_kept_as_secondary_only": True,
        "infrastructure_families_excluded_from_hints": sorted(INFRASTRUCTURE_FAMILIES),
        "allowed_hint_families_from_dc_type": sorted(allowed),
    }
    return hint_families, suppressed, policy


def label_page_profile(family_counts: Counter[str], category_counts: Counter[str], dc_types: list[str]) -> str:
    """Return a human/UI-facing page category label.

    Use the refined public Dublin Core page types as the strongest signal.
    Raw category counts are still retained in the profile, but they should not make
    a text/front-matter page look like a table/diagram page just because routing
    helpers or weak visual/table signals exist.
    """
    dc_set = set(dc_types)
    has_review = family_counts.get("review", 0) > 0

    if "blank_page" in dc_set:
        return "blank_source_trace_page"

    has_table = "table_page" in dc_set
    has_diagram = "visual_page" in dc_set
    has_chart = "chart_page" in dc_set
    has_part = "parts_page" in dc_set
    has_text = "text_page" in dc_set

    # Fallback only for older inputs that may not have refined dc:type.
    if not any([has_table, has_diagram, has_chart, has_part, has_text]):
        signal_counts = filtered_counter(family_counts, LEIDEN_SIGNAL_FAMILIES)
        has_table = signal_counts.get("table", 0) >= 10 or category_counts.get("table_cell", 0) > 0 or category_counts.get("table_row", 0) > 0
        has_diagram = signal_counts.get("diagram", 0) >= 5 or category_counts.get("diagram_callout_candidate", 0) > 0
        has_chart = signal_counts.get("chart", 0) >= 1
        has_part = signal_counts.get("part", 0) >= 3
        has_text = signal_counts.get("text", 0) > 0

    if has_table and has_diagram and has_part:
        return "table_parts_diagram_page_review" if has_review else "table_parts_diagram_page"
    if has_table and has_part:
        return "parts_list_table_page_review" if has_review else "parts_list_table_page"
    if has_diagram and has_part:
        return "visual_part_candidate_page_review" if has_review else "visual_part_candidate_page"
    if has_table:
        return "table_page_review" if has_review else "table_page"
    if has_chart:
        return "chart_page_review" if has_review else "chart_page"
    if has_diagram:
        return "visual_diagram_page_review" if has_review else "visual_diagram_page"
    if has_text:
        return "text_source_page_review" if has_review else "text_source_page"
    return "trace_net_metadata_page_review" if has_review else "trace_net_metadata_page"


def build_page_profiles(pages: dict[str, dict[str, Any]], category_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in category_records:
        page_id = str(rec.get("page_id") or "")
        if page_id:
            by_page[page_id].append(rec)

    profiles: list[dict[str, Any]] = []
    for page_id in sorted(pages):
        page_rec = pages[page_id]
        trace = get_trace(page_rec)
        dc = get_dc(page_rec)
        family_counts: Counter[str] = Counter()
        category_counts: Counter[str] = Counter()
        role_counts: Counter[str] = Counter()
        source_layer_counts: Counter[str] = Counter()
        category_node_hints: list[dict[str, Any]] = []

        for rec in by_page.get(page_id, []):
            count = int(rec.get("element_count") or 0)
            family = str(rec.get("element_family") or "other")
            category = str(rec.get("element_category") or "other")
            role = str(rec.get("element_role") or "metadata_only")
            family_counts[family] += count
            category_counts[category] += count
            role_counts[role] += count
            source_layer_counts[str(rec.get("source_layer") or "unknown")] += 1

        dc_types = unique_strings(dc.get("dc:type"))
        page_category_label = label_page_profile(family_counts, category_counts, dc_types)
        dominant_families = dominant_items(family_counts, 8)
        semantic_family_counts = filtered_counter(family_counts, LEIDEN_SIGNAL_FAMILIES)
        infrastructure_family_counts = filtered_counter(family_counts, INFRASTRUCTURE_FAMILIES)
        semantic_dominant_families = dominant_items(semantic_family_counts, 8)
        infrastructure_dominant_families = dominant_items(infrastructure_family_counts, 8)
        dominant_categories = [name for name, _ in category_counts.most_common(12)]

        # Use refined dc:type as the strongest signal for future Leiden hints.
        # Weak table/visual route signals stay in counts and secondary signals,
        # but do not create category nodes for text/front-matter pages.
        hint_families, suppressed_leiden_hint_families, leiden_hint_policy = build_leiden_hint_family_selection(
            dc_types=dc_types,
            family_counts=family_counts,
            semantic_dominant_families=semantic_dominant_families,
        )

        for family in hint_families:
            category_node_hints.append({
                "page_category_node_id": f"page_category::{page_id}::{family}",
                "page_id": page_id,
                "element_family": family,
                "edge_policy": "page_local_category_node",
                "recommended_weight": 0.25 if family in {"operation", "community", "search"} else 0.75,
                "avoid_global_category_hub": True,
            })

        profiles.append({
            "page_category_profile_id": f"pgcat_{stable_hash(page_id)}",
            "page_id": page_id,
            "document_id": trace.get("trace_net:document_id") or dc.get("dcterms:isPartOf") or "t_p_120_1176",
            "dc_type": dc_types,
            "page_category_label": page_category_label,
            "element_family_counts": dict(sorted(family_counts.items(), key=lambda kv: (family_rank(kv[0]), kv[0]))),
            "element_category_counts": dict(sorted(category_counts.items())),
            "element_role_counts": dict(sorted(role_counts.items())),
            "dominant_element_families": dominant_families,
            "semantic_dominant_element_families": semantic_dominant_families,
            "infrastructure_dominant_element_families": infrastructure_dominant_families,
            "leiden_hint_element_families": hint_families,
            "suppressed_leiden_hint_families": suppressed_leiden_hint_families,
            "leiden_hint_policy": leiden_hint_policy,
            "dominant_element_categories": dominant_categories,
            "category_source_layer_counts": dict(sorted(source_layer_counts.items())),
            "category_record_count": len(by_page.get(page_id, [])),
            "total_categorized_element_count": int(sum(family_counts.values())),
            "review_required": truthy(trace.get("trace_net:review_required")) or family_counts.get("review", 0) > 0,
            "complexity_class": trace.get("trace_net:complexity_class_refined") or trace.get("trace_net:complexity_class") or "unknown",
            "community_ids": unique_strings(trace.get("trace_net:community_ids"))[:50],
            "part_numbers": unique_strings(trace.get("trace_net:part_numbers"))[:50],
            "leiden_grouping_hints": {
                "use_page_local_category_nodes": True,
                "use_low_weight_global_category_edges": False,
                "avoid_global_category_hub_edges": True,
                "suggested_page_category_nodes": category_node_hints,
                "hint_element_families": hint_families,
                "suppressed_hint_families": suppressed_leiden_hint_families,
                "hint_policy": leiden_hint_policy,
                "page_to_page_category_similarity_candidate": True,
            },
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
        })
    return profiles


def quality_report(
    report: dict[str, Any],
    *,
    require_page_count: int | None = None,
    min_page_profiles: int = 0,
    min_categorized_elements: int = 1,
    min_diagram_categories: int = 0,
    min_table_categories: int = 0,
    min_part_categories: int = 0,
    min_review_categories: int = 0,
    write_json: bool = False,
) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    issues: list[str] = []

    if require_page_count is not None and int(summary.get("page_count", 0)) != int(require_page_count):
        issues.append(f"page_count {summary.get('page_count')} != required {require_page_count}")
    if int(summary.get("page_category_profile_count", 0)) < int(min_page_profiles):
        issues.append("page_category_profile_count below minimum")
    if int(summary.get("categorized_element_count", 0)) < int(min_categorized_elements):
        issues.append("categorized_element_count below minimum")
    if int(summary.get("diagram_category_count", 0)) < int(min_diagram_categories):
        issues.append("diagram_category_count below minimum")
    if int(summary.get("table_category_count", 0)) < int(min_table_categories):
        issues.append("table_category_count below minimum")
    if int(summary.get("part_category_count", 0)) < int(min_part_categories):
        issues.append("part_category_count below minimum")
    if int(summary.get("review_category_count", 0)) < int(min_review_categories):
        issues.append("review_category_count below minimum")

    for key in [
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "unsafe_category_record_count",
    ]:
        if int(summary.get(key, 0)) != 0:
            issues.append(f"{key} must be zero")

    status = "PASS" if not issues else "FAIL"
    quality = {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "quality_status": status,
        "issues": issues,
        **{key: summary.get(key) for key in [
            "page_count",
            "page_category_profile_count",
            "category_record_count",
            "categorized_element_count",
            "uncategorized_element_count",
            "family_count",
            "category_count",
            "diagram_category_count",
            "chart_category_count",
            "table_category_count",
            "part_category_count",
            "review_category_count",
            "can_answer_directly_count",
            "can_prove_claims_count",
            "source_truth_mutation_allowed_count",
        ]},
    }
    if write_json:
        report_path = Path(str(report.get("report_path") or ""))
        if report_path:
            quality_path = report_path.with_name("trace_net_element_category_taxonomy_v1_quality.json")
            write_json(quality_path, quality)
    return quality


def build_element_category_taxonomy(
    *,
    dublin_core_refined_path: str | Path,
    element_graph_attachment_path: str | Path | None = None,
    table_cell_normalizer_path: str | Path | None = None,
    figure_chart_understanding_path: str | Path | None = None,
    callout_visual_part_verifier_path: str | Path | None = None,
    human_review_triage_path: str | Path | None = None,
    opensearch_adapter_path: str | Path | None = None,
    leiden_communities_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    require_page_count: int | None = None,
    min_page_profiles: int = 0,
    min_categorized_elements: int = 1,
    min_diagram_categories: int = 0,
    min_table_categories: int = 0,
    min_part_categories: int = 0,
    min_review_categories: int = 0,
    write_quality: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    crosswalk = read_json(dublin_core_refined_path)
    pages, category_records = collect_from_dublin_core_refined(crosswalk)
    known_pages = set(pages)

    source_artifacts = {
        "dublin_core_refined": str(dublin_core_refined_path),
    }

    optional_sources = [
        ("element_graph_attachment", element_graph_attachment_path, lambda payload: collect_from_element_graph(payload, known_pages)),
        ("table_cell_normalizer", table_cell_normalizer_path, lambda payload: collect_from_table_normalizer(payload, known_pages)),
        ("figure_chart_understanding", figure_chart_understanding_path, lambda payload: collect_from_figure_chart(payload, known_pages)),
        ("callout_visual_part_verifier", callout_visual_part_verifier_path, lambda payload: collect_from_callout_verifier(payload, known_pages)),
        ("human_review_triage", human_review_triage_path, lambda payload: collect_from_human_review_triage(payload, known_pages)),
        ("opensearch_adapter", opensearch_adapter_path, lambda payload: collect_from_opensearch(payload, known_pages)),
        ("leiden_communities", leiden_communities_path, lambda payload: collect_from_leiden(payload, known_pages)),
    ]

    for name, path, collector in optional_sources:
        payload = read_json(path)
        if payload:
            source_artifacts[name] = str(path)
            category_records.extend(collector(payload))

    page_profiles = build_page_profiles(pages, category_records)

    family_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    source_layer_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    suppressed_leiden_hint_counts: Counter[str] = Counter()
    pages_with_suppressed_leiden_hints = 0
    table_hint_without_table_type_count = 0
    visual_hint_without_visual_type_count = 0
    unsafe_count = 0
    can_answer_count = 0
    can_prove_count = 0
    source_truth_mutation_count = 0

    for rec in category_records:
        count = int(rec.get("element_count") or 0)
        family_counts[str(rec.get("element_family") or "other")] += count
        category_counts[str(rec.get("element_category") or "other")] += count
        role_counts[str(rec.get("element_role") or "metadata_only")] += count
        source_layer_counts[str(rec.get("source_layer") or "unknown")] += 1
        if truthy(rec.get("can_answer_directly")):
            can_answer_count += 1
        if truthy(rec.get("can_prove_claims")):
            can_prove_count += 1
        if truthy(rec.get("source_truth_mutation_allowed")) or truthy(rec.get("can_mutate_source_truth")):
            source_truth_mutation_count += 1
        if truthy(rec.get("unsafe")):
            unsafe_count += 1

    for profile in page_profiles:
        label_counts[str(profile.get("page_category_label") or "unknown")] += 1
        suppressed = unique_strings(profile.get("suppressed_leiden_hint_families") or [])
        if suppressed:
            pages_with_suppressed_leiden_hints += 1
            suppressed_leiden_hint_counts.update(suppressed)
        hints = set(unique_strings(profile.get("leiden_hint_element_families") or []))
        dc_type_set = set(unique_strings(profile.get("dc_type") or []))
        if "table" in hints and "table_page" not in dc_type_set:
            table_hint_without_table_type_count += 1
        if {"visual", "diagram", "chart"}.intersection(hints) and not {"visual_page", "diagram_page", "chart_page"}.intersection(dc_type_set):
            visual_hint_without_visual_type_count += 1

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "page_count": len(pages),
        "page_category_profile_count": len(page_profiles),
        "category_record_count": len(category_records),
        "categorized_element_count": int(sum(family_counts.values())),
        "uncategorized_element_count": 0,
        "family_count": len(family_counts),
        "category_count": len(category_counts),
        "role_count": len(role_counts),
        "family_counts": dict(sorted(family_counts.items(), key=lambda kv: (family_rank(kv[0]), kv[0]))),
        "category_counts": dict(sorted(category_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "source_layer_record_counts": dict(sorted(source_layer_counts.items())),
        "page_category_label_counts": dict(sorted(label_counts.items())),
        "leiden_hint_suppressed_family_counts": dict(sorted(suppressed_leiden_hint_counts.items())),
        "pages_with_suppressed_leiden_hints": pages_with_suppressed_leiden_hints,
        "table_hint_without_table_type_count": table_hint_without_table_type_count,
        "visual_hint_without_visual_type_count": visual_hint_without_visual_type_count,
        "leiden_hint_tightening_policy": "refined_dc_type_first_no_weak_table_visual_hints_v1",
        "diagram_category_count": int(family_counts.get("diagram", 0)),
        "chart_category_count": int(family_counts.get("chart", 0)),
        "table_category_count": int(family_counts.get("table", 0)),
        "part_category_count": int(family_counts.get("part", 0)),
        "review_category_count": int(family_counts.get("review", 0)),
        "visual_category_count": int(family_counts.get("visual", 0)),
        "source_category_count": int(family_counts.get("source", 0)),
        "search_category_count": int(family_counts.get("search", 0)),
        "community_category_count": int(family_counts.get("community", 0)),
        "pages_with_category_profiles": len([p for p in page_profiles if p.get("total_categorized_element_count", 0) > 0]),
        "pages_with_diagram_family": len([p for p in page_profiles if p.get("element_family_counts", {}).get("diagram", 0) > 0]),
        "pages_with_table_family": len([p for p in page_profiles if p.get("element_family_counts", {}).get("table", 0) > 0]),
        "pages_with_part_family": len([p for p in page_profiles if p.get("element_family_counts", {}).get("part", 0) > 0]),
        "pages_with_review_family": len([p for p in page_profiles if p.get("element_family_counts", {}).get("review", 0) > 0]),
        "unsafe_category_record_count": unsafe_count,
        "can_answer_directly_count": can_answer_count,
        "can_prove_claims_count": can_prove_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_count,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "taxonomy_role": "navigation_retrieval_review_grouping_only",
        "category_as_proof_count": 0,
    }

    report_path = output / "trace_net_element_category_taxonomy_v1.json"
    records_path = output / "trace_net_element_category_records_v1.jsonl"
    profiles_path = output / "trace_net_page_category_profiles_v1.jsonl"
    summary_path = output / "trace_net_element_category_taxonomy_v1_summary.json"
    quality_path = output / "trace_net_element_category_taxonomy_v1_quality.json"
    manifest_path = output / "trace_net_element_category_taxonomy_v1_manifest.json"
    md_path = output / "trace_net_element_category_taxonomy_v1.md"
    html_path = output / "trace_net_element_category_taxonomy_v1.html"

    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "ELEMENT_CATEGORY_TAXONOMY_BUILT",
        "quality_status": "PASS",
        "generated_at": now_iso(),
        "summary": summary,
        "source_artifacts": source_artifacts,
        "category_library": [
            {
                "raw_key": key,
                "element_family": family,
                "element_category": category,
                "element_role": role,
            }
            for key, (family, category, role) in sorted(CATEGORY_LIBRARY.items())
        ],
        "page_category_profiles": page_profiles,
        "element_category_records": category_records,
        "report_path": str(report_path),
        "records_path": str(records_path),
        "profiles_path": str(profiles_path),
        "quality_path": str(quality_path),
    }

    quality = quality_report(
        report,
        require_page_count=require_page_count,
        min_page_profiles=min_page_profiles,
        min_categorized_elements=min_categorized_elements,
        min_diagram_categories=min_diagram_categories,
        min_table_categories=min_table_categories,
        min_part_categories=min_part_categories,
        min_review_categories=min_review_categories,
    )
    report["quality_status"] = quality["status"]
    report["summary"]["status"] = quality["status"]

    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report["generated_at"],
        "report_path": str(report_path),
        "records_path": str(records_path),
        "profiles_path": str(profiles_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_artifacts": source_artifacts,
        "write_mode": "local_artifact_build_only",
        "safety": {
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
        },
    }

    write_json(report_path, report)
    write_jsonl(records_path, category_records)
    write_jsonl(profiles_path, page_profiles)
    write_json(summary_path, report["summary"])
    write_json(quality_path, quality)
    write_json(manifest_path, manifest)
    write_markdown(md_path, report)
    write_html(html_path, md_path.read_text(encoding="utf-8"))

    return report


def write_markdown(path: str | Path, report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Element Category Taxonomy v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Generated:** {report.get('generated_at')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "page_count",
        "page_category_profile_count",
        "category_record_count",
        "categorized_element_count",
        "family_count",
        "category_count",
        "diagram_category_count",
        "chart_category_count",
        "table_category_count",
        "part_category_count",
        "review_category_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Family Counts", "", "| Family | Count |", "|---|---:|"])
    for family, count in (summary.get("family_counts") or {}).items():
        lines.append(f"| {family} | {count} |")
    lines.extend(["", "## Page Category Labels", "", "| Label | Pages |", "|---|---:|"])
    for label, count in (summary.get("page_category_label_counts") or {}).items():
        lines.append(f"| {label} | {count} |")
    lines.extend([
        "",
        "## Safety",
        "",
        "Element categories are navigation, retrieval, review and UI metadata only.",
        "They cannot answer directly, prove claims, or mutate source truth.",
    ])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(path: str | Path, markdown_text: str) -> None:
    body = "<br>".join(html.escape(line) for line in markdown_text.splitlines())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Element Category Taxonomy v1</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;line-height:1.45;}"
        "table{border-collapse:collapse;}td,th{border:1px solid #ccc;padding:4px 8px;}</style></head>"
        f"<body><pre style='white-space:pre-wrap'>{html.escape(markdown_text)}</pre></body></html>",
        encoding="utf-8",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Element Category Taxonomy v1")
    parser.add_argument("--dublin-core-refined", required=True)
    parser.add_argument("--element-graph-attachment")
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--figure-chart-understanding")
    parser.add_argument("--callout-visual-part-verifier")
    parser.add_argument("--human-review-triage")
    parser.add_argument("--opensearch-adapter")
    parser.add_argument("--leiden-communities")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-page-profiles", type=int, default=0)
    parser.add_argument("--min-categorized-elements", type=int, default=1)
    parser.add_argument("--min-diagram-categories", type=int, default=0)
    parser.add_argument("--min-table-categories", type=int, default=0)
    parser.add_argument("--min-part-categories", type=int, default=0)
    parser.add_argument("--min-review-categories", type=int, default=0)
    parser.add_argument("--quality", action="store_true")
    return parser


def print_summary(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("TRACE-Net element category taxonomy v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "page_count",
        "page_category_profile_count",
        "category_record_count",
        "categorized_element_count",
        "family_count",
        "category_count",
        "diagram_category_count",
        "chart_category_count",
        "table_category_count",
        "part_category_count",
        "review_category_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_element_category_taxonomy(
        dublin_core_refined_path=args.dublin_core_refined,
        element_graph_attachment_path=args.element_graph_attachment,
        table_cell_normalizer_path=args.table_cell_normalizer,
        figure_chart_understanding_path=args.figure_chart_understanding,
        callout_visual_part_verifier_path=args.callout_visual_part_verifier,
        human_review_triage_path=args.human_review_triage,
        opensearch_adapter_path=args.opensearch_adapter,
        leiden_communities_path=args.leiden_communities,
        output_dir=args.output_dir,
        require_page_count=args.require_page_count,
        min_page_profiles=args.min_page_profiles,
        min_categorized_elements=args.min_categorized_elements,
        min_diagram_categories=args.min_diagram_categories,
        min_table_categories=args.min_table_categories,
        min_part_categories=args.min_part_categories,
        min_review_categories=args.min_review_categories,
        write_quality=args.quality,
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
