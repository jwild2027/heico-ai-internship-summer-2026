"""TRACE-Net Dublin Core Page Metadata Crosswalk v1.

Builds a read-only Dublin Core + TRACE-Net metadata crosswalk for every page.

Dublin Core fields provide standard resource description:
- dc:identifier, dc:type, dc:format, dc:source, dc:description
- dcterms:isPartOf, dcterms:hasPart, dcterms:provenance, dcterms:extent

TRACE-Net fields preserve operational/evidence metadata:
- element_count, element_type_count, element_type_counts
- review, trust, retrieval, citation, source-trace and safety flags

Safety contract:
- This module is a metadata/export layer only.
- It cannot answer directly, prove claims, mutate source truth, or promote evidence.
- Dublin Core fields are interoperability metadata, not answer authority.
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

SCHEMA_VERSION = "trace_net_dublin_core_crosswalk_v1"
ALGORITHM = "trace_net_dublin_core_plus_trace_net_page_metadata_crosswalk_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/dublin_core_crosswalk")
DEFAULT_DOCUMENT_ID = "t_p_120_1176"
DEFAULT_FORMAT = "image/tiff"

DC_PREFIXES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "trace_net": "https://heico.example/trace-net/terms/",
}

TOP_LEVEL_ELEMENT_TYPES = {
    "source_trace",
    "source_text",
    "table",
    "visual_region",
    "part_candidate",
    "context_v2",
    "citation",
    "fishnet_plan",
    "review_task",
    "community",
    "blank_source_trace_preservation",
}

PAGE_SCOPED_NODE_TYPES = {
    "Page",
    "PageElementRegistry",
    "TableElement",
    "TableRow",
    "TableCell",
    "TableCellRepair",
    "VisualUnderstanding",
    "VisualRegion",
    "CalloutCandidate",
    "EvidenceCandidate",
    "Citation",
    "FishnetRetryPlan",
    "FishnetRetryAction",
    "BlankSourceTracePreservation",
    "ExtractionRoutePlan",
}

NODE_TYPE_TO_ELEMENT = {
    "Page": "page_node",
    "PageElementRegistry": "page_element_registry",
    "TableElement": "table",
    "TableRow": "table_row",
    "TableCell": "table_cell",
    "TableCellRepair": "table_repair",
    "VisualUnderstanding": "visual_understanding",
    "VisualRegion": "visual_region",
    "CalloutCandidate": "callout_candidate",
    "PartCandidate": "part_candidate",
    "EvidenceCandidate": "evidence_candidate",
    "Citation": "citation",
    "FishnetRetryPlan": "fishnet_plan",
    "FishnetRetryAction": "fishnet_action",
    "BlankSourceTracePreservation": "blank_source_trace_preservation",
    "ExtractionRoutePlan": "extraction_route_plan",
    "TrustAuthority": "trust_authority",
}

DOC_TYPE_TO_ELEMENT = {
    "embedding_candidate": "search_document_embedding_candidate",
    "page_retrieval_profile": "search_document_page_profile",
    "table_cell_normalized": "table_cell_search_document",
    "table_row_normalized": "table_row_search_document",
    "part_candidate_lineage": "part_candidate_search_document",
    "community_summary": "community_search_document",
    "context_retrieval_helper": "context_retrieval_helper_search_document",
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


def read_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


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


def extract_records(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def page_sort_key(page_id: str) -> tuple[str, int, str]:
    match = re.search(r"p0*([0-9]+)$", str(page_id))
    if match:
        return (str(page_id).split("p")[0], int(match.group(1)), str(page_id))
    return (str(page_id), 999999, str(page_id))


def parse_page_number(page_id: str | None) -> int | None:
    if not page_id:
        return None
    match = re.search(r"p0*([0-9]+)$", str(page_id))
    if match:
        return int(match.group(1))
    return None


def infer_document_id(page_id: str | None, fallback: str = DEFAULT_DOCUMENT_ID) -> str:
    if not page_id:
        return fallback
    page_id = str(page_id)
    match = re.match(r"(.+)_p0*[0-9]+$", page_id)
    if match:
        return match.group(1)
    return fallback


def sanitize_text(value: Any, max_chars: int = 1000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = value.replace("\x00", " ").strip()
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]


def add_count(counter: Counter[str], key: str, amount: int = 1) -> None:
    if amount <= 0:
        return
    if key:
        counter[str(key)] += int(amount)


def list_counter(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted((key, int(value)) for key, value in counter.items() if value > 0))


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


def page_ids_from_node(node: dict[str, Any]) -> list[str]:
    page_ids: list[str] = []
    for key in ("page_id", "source_page_ids", "page_ids"):
        for value in as_list(node.get(key)):
            if isinstance(value, str) and value.strip():
                page_ids.append(value.strip())
    props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    for key in ("page_id", "source_page_ids", "page_ids"):
        for value in as_list(props.get(key)):
            if isinstance(value, str) and value.strip():
                page_ids.append(value.strip())
    return unique_strings(page_ids)


def page_id_from_record(record: dict[str, Any]) -> str:
    for key in ("page_id", "page", "source_page_id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("page_ids", "source_page_ids"):
        values = unique_strings(as_list(record.get(key)))
        if len(values) == 1:
            return values[0]
    return ""


def build_page_index(page_registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}
    for record in extract_records(page_registry, ("records", "page_records", "registry_records")):
        page_id = page_id_from_record(record)
        if not page_id:
            continue
        pages[page_id] = record
    return pages


def make_page_context(pages: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}
    for page_id, record in pages.items():
        context[page_id] = {
            "registry_record": record,
            "element_counts": Counter(),
            "subjects": set(),
            "relations": set(),
            "community_ids": set(),
            "citation_ids": set(unique_strings(record.get("citation_ids") or [])),
            "part_numbers": set(),
            "review_task_ids": set(),
            "review_task_count": 0,
            "feedback_memory_ids": set(),
            "opensearch_document_ids": set(),
            "opensearch_document_type_counts": Counter(),
            "graph_node_count": 0,
            "graph_edge_count": 0,
            "source_trace_present": False,
            "ocr_present": False,
            "context_v2_present": truthy(record.get("context_v2_present")),
            "needs_human_review": truthy(record.get("needs_human_review")),
            "layout_class": "",
            "visual_type": "",
            "source_confirmed_blank": False,
        }
        # Registry detected elements are the first page-level element signal.
        for element in as_list(record.get("detected_elements")):
            if isinstance(element, dict):
                element_type = str(element.get("element_type") or element.get("type") or "detected_element")
            else:
                element_type = str(element)
            add_count(context[page_id]["element_counts"], element_type)
            if element_type == "source_trace":
                context[page_id]["source_trace_present"] = True
            if element_type in {"source_text", "ocr_text", "source_text_evidence"}:
                context[page_id]["ocr_present"] = True
        for trait in as_list(record.get("page_traits")):
            trait_text = str(trait)
            if trait_text:
                context[page_id]["subjects"].add(trait_text)
            if "source_trace" in trait_text and "present" in trait_text:
                context[page_id]["source_trace_present"] = True
            if "ocr_text_present" in trait_text or "ocr_present" in trait_text:
                context[page_id]["ocr_present"] = True
        for route in as_list(record.get("recommended_extraction_routes")):
            if route:
                context[page_id]["relations"].add(f"route:{route}")
        bucket_counts = record.get("candidate_bucket_counts") if isinstance(record.get("candidate_bucket_counts"), dict) else {}
        for bucket, count in bucket_counts.items():
            add_count(context[page_id]["element_counts"], f"rag_bucket:{bucket}", int(count or 0))
            context[page_id]["subjects"].add(str(bucket))
        if record.get("context_v2_present"):
            add_count(context[page_id]["element_counts"], "context_v2")
        if record.get("citation_count"):
            add_count(context[page_id]["element_counts"], "citation", int(record.get("citation_count") or 0))
        if record.get("source_candidate_count"):
            add_count(context[page_id]["element_counts"], "source_candidate", int(record.get("source_candidate_count") or 0))
    return context


def update_from_table_normalizer(context: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    for record in extract_records(payload, ("records", "table_records", "normalized_table_records")):
        page_id = page_id_from_record(record)
        if page_id not in context:
            continue
        ctx = context[page_id]
        add_count(ctx["element_counts"], "table")
        table_type = str(record.get("table_type") or "")
        if table_type:
            ctx["subjects"].add(table_type)
        row_count = int(record.get("normalized_row_count") or len(as_list(record.get("rows"))) or 0)
        cell_count = int(record.get("normalized_cell_count") or len(as_list(record.get("cells"))) or 0)
        repair_count = int(record.get("repair_count") or record.get("normalized_repair_count") or len(as_list(record.get("repairs"))) or 0)
        answer_support_rows = int(record.get("answer_support_row_count") or 0)
        add_count(ctx["element_counts"], "table_row", row_count)
        add_count(ctx["element_counts"], "table_cell", cell_count)
        add_count(ctx["element_counts"], "table_repair", repair_count)
        add_count(ctx["element_counts"], "table_answer_support_row_candidate", answer_support_rows)
        if repair_count:
            ctx["needs_human_review"] = True
            ctx["subjects"].add("table_repair")
        for repair in as_list(record.get("repairs")):
            if isinstance(repair, dict):
                part = repair.get("merged_part_number") or repair.get("part_number")
                if part:
                    ctx["part_numbers"].add(str(part))
        for row in as_list(record.get("rows")):
            if isinstance(row, dict):
                for citation_id in unique_strings(row.get("citation_ids") or []):
                    ctx["citation_ids"].add(citation_id)


def update_from_figure(context: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    for record in extract_records(payload, ("records", "visual_records", "figure_records")):
        page_id = page_id_from_record(record)
        if page_id not in context:
            continue
        ctx = context[page_id]
        add_count(ctx["element_counts"], "visual_understanding")
        visual_type = str(record.get("visual_type") or record.get("source_visual_type") or "")
        if visual_type:
            ctx["visual_type"] = visual_type
            ctx["subjects"].add(visual_type)
        visual_region_count = int(record.get("visual_region_count") or len(as_list(record.get("visual_regions"))) or 0)
        callouts = record.get("callout_labels") if record.get("callout_labels") is not None else record.get("callout_candidates")
        callout_count = int(record.get("callout_candidate_count") or len(as_list(callouts)) or 0)
        part_candidates = record.get("linked_part_candidates") if record.get("linked_part_candidates") is not None else record.get("part_candidates")
        part_count = int(record.get("linked_part_candidate_count") or len(as_list(part_candidates)) or 0)
        add_count(ctx["element_counts"], "visual_region", visual_region_count)
        add_count(ctx["element_counts"], "callout_candidate", callout_count)
        add_count(ctx["element_counts"], "linked_part_candidate", part_count)
        for part in as_list(part_candidates):
            if isinstance(part, str):
                ctx["part_numbers"].add(part)
            elif isinstance(part, dict):
                value = part.get("part_number") or part.get("label") or part.get("candidate")
                if value:
                    ctx["part_numbers"].add(str(value))
        if truthy(record.get("needs_human_review")) or truthy(record.get("requires_catalog_compare")):
            ctx["needs_human_review"] = True


def update_from_visual_ink(context: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    for record in extract_records(payload, ("records", "calibrated_records")):
        page_id = page_id_from_record(record)
        if page_id not in context:
            continue
        ctx = context[page_id]
        layout_class = str(record.get("calibrated_layout_class") or record.get("layout_class") or "")
        if layout_class:
            ctx["layout_class"] = layout_class
            ctx["subjects"].add(layout_class)
            add_count(ctx["element_counts"], f"layout:{layout_class}")
        if truthy(record.get("source_confirmed_blank")) or layout_class == "blank":
            ctx["source_confirmed_blank"] = True
            add_count(ctx["element_counts"], "blank_source_trace_preservation")
        if truthy(record.get("needs_human_review")):
            ctx["needs_human_review"] = True


def update_from_graph_attachment(context: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    for node in extract_records(payload, ("node_plans", "nodes")):
        node_type = str(node.get("node_type") or "")
        element_type = NODE_TYPE_TO_ELEMENT.get(node_type, node_type.lower() if node_type else "graph_node")
        for page_id in page_ids_from_node(node):
            if page_id not in context:
                continue
            ctx = context[page_id]
            ctx["graph_node_count"] += 1
            add_count(ctx["element_counts"], element_type)
            if node_type == "Citation":
                citation_id = str(node.get("citation_id") or node.get("node_id") or "")
                if citation_id:
                    ctx["citation_ids"].add(citation_id)
            if node_type == "PartCandidate":
                props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
                part = node.get("part_number") or props.get("part_number") or props.get("canonical_part_candidate") or node.get("label")
                if part:
                    ctx["part_numbers"].add(str(part))
    for edge in extract_records(payload, ("edge_plans", "edges")):
        page_id = page_id_from_record(edge)
        if page_id not in context:
            continue
        context[page_id]["graph_edge_count"] += 1


def update_from_leiden(context: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    for member in extract_records(payload, ("node_membership", "memberships")):
        community_id = str(member.get("community_id") or "")
        if not community_id:
            continue
        node_type = str(member.get("node_type") or "")
        node_id = str(member.get("node_id") or "")
        page_ids: list[str] = []
        if node_type == "Page":
            page_ids.append(node_id.replace("page::", ""))
        if member.get("page_id"):
            page_ids.append(str(member.get("page_id")))
        for page_id in unique_strings(page_ids):
            if page_id in context:
                context[page_id]["community_ids"].add(community_id)
                add_count(context[page_id]["element_counts"], "community")
    for community in extract_records(payload, ("communities", "community_records")):
        community_id = str(community.get("community_id") or "")
        if not community_id:
            continue
        for page_id in unique_strings(community.get("page_ids") or []):
            if page_id in context:
                context[page_id]["community_ids"].add(community_id)
                add_count(context[page_id]["element_counts"], "community")
        for family in as_list(community.get("part_families")):
            if isinstance(family, str) and family.strip():
                for page_id in unique_strings(community.get("page_ids") or []):
                    if page_id in context:
                        context[page_id]["subjects"].add(f"part_family:{family}")


def update_from_opensearch(context: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    for doc in extract_records(payload, ("documents", "opensearch_documents")):
        doc_id = str(doc.get("opensearch_document_id") or doc.get("id") or "")
        doc_type = str(doc.get("document_type") or "opensearch_document")
        element = DOC_TYPE_TO_ELEMENT.get(doc_type, f"search_document:{doc_type}")
        page_ids = unique_strings([doc.get("page_id"), *as_list(doc.get("source_page_ids"))])
        for page_id in page_ids:
            if page_id not in context:
                continue
            ctx = context[page_id]
            ctx["opensearch_document_type_counts"][doc_type] += 1
            if doc_id:
                ctx["opensearch_document_ids"].add(doc_id)
            add_count(ctx["element_counts"], element)
            bucket = str(doc.get("rag_bucket") or "")
            if bucket:
                ctx["subjects"].add(bucket)


def update_from_feedback(context: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    for record in extract_records(payload, ("memory_records", "records", "feedback_memory_records")):
        mem_id = str(record.get("memory_id") or record.get("feedback_id") or "")
        page_ids = unique_strings([record.get("page_id"), *as_list(record.get("page_ids"))])
        for page_id in page_ids:
            if page_id not in context:
                continue
            add_count(context[page_id]["element_counts"], "feedback_memory")
            if mem_id:
                context[page_id]["feedback_memory_ids"].add(mem_id)
            if truthy(record.get("prompt_injection_flagged")):
                context[page_id]["needs_human_review"] = True


def update_from_human_review_triage(context: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    for card in extract_records(payload, ("triage_cards", "cards")):
        card_id = str(card.get("triage_card_id") or card.get("review_task_id") or "")
        page_ids = unique_strings(card.get("page_ids") or ([card.get("page_id")] if card.get("page_id") else []))
        for page_id in page_ids:
            if page_id not in context:
                continue
            add_count(context[page_id]["element_counts"], "review_task")
            context[page_id]["review_task_count"] += int(card.get("task_count") or 1)
            if card_id:
                context[page_id]["review_task_ids"].add(card_id)
            context[page_id]["needs_human_review"] = True
            for community_id in unique_strings(card.get("community_ids") or []):
                context[page_id]["community_ids"].add(community_id)
            for part in unique_strings(card.get("part_numbers") or []):
                context[page_id]["part_numbers"].add(part)


def complexity_class(element_counts: Counter[str], needs_review: bool, source_confirmed_blank: bool) -> str:
    if source_confirmed_blank:
        return "blank"
    detailed_count = sum(element_counts.values())
    type_count = len([v for v in element_counts.values() if v > 0])
    if needs_review and (detailed_count >= 100 or type_count >= 8):
        return "high_review"
    if detailed_count >= 100 or type_count >= 8:
        return "high"
    if detailed_count >= 20 or type_count >= 5:
        return "medium"
    return "low"


def dc_types_from_context(ctx: dict[str, Any]) -> list[str]:
    types = {"technical_manual_page"}
    counts: Counter[str] = ctx["element_counts"]
    if ctx.get("source_confirmed_blank"):
        types.add("blank_page")
    if counts.get("source_text") or counts.get("rag_bucket:source_text_evidence"):
        types.add("text_page")
    if counts.get("table") or counts.get("table_row") or counts.get("table_cell"):
        types.add("table_page")
    if counts.get("visual_region") or counts.get("visual_understanding") or counts.get("callout_candidate"):
        types.add("visual_page")
    if counts.get("part_candidate") or counts.get("linked_part_candidate") or counts.get("rag_bucket:verified_part_evidence"):
        types.add("parts_page")
    if ctx.get("context_v2_present"):
        types.add("context_v2_page")
    return sorted(types)


def description_from_context(page_id: str, registry: dict[str, Any], ctx: dict[str, Any]) -> str:
    traits = unique_strings(registry.get("page_traits") or [])[:8]
    layout = ctx.get("layout_class") or ""
    visual = ctx.get("visual_type") or ""
    counts = ctx["element_counts"]
    pieces: list[str] = []
    if layout:
        pieces.append(f"layout={layout}")
    if visual:
        pieces.append(f"visual={visual}")
    if traits:
        pieces.append("traits=" + ", ".join(traits[:5]))
    if counts.get("table_row") or counts.get("table_cell"):
        pieces.append(f"table_rows={counts.get('table_row', 0)}, table_cells={counts.get('table_cell', 0)}")
    if counts.get("callout_candidate") or counts.get("linked_part_candidate"):
        pieces.append(f"callouts={counts.get('callout_candidate', 0)}, linked_parts={counts.get('linked_part_candidate', 0)}")
    if ctx.get("source_confirmed_blank"):
        pieces.append("source-confirmed blank page")
    if not pieces:
        pieces.append("TRACE-Net page metadata record")
    return sanitize_text(f"{page_id}: " + "; ".join(pieces), max_chars=1500)


def build_page_crosswalk_record(page_id: str, ctx: dict[str, Any]) -> dict[str, Any]:
    registry = ctx["registry_record"]
    document_id = str(registry.get("document_id") or infer_document_id(page_id))
    page_number = registry.get("page_number") or parse_page_number(page_id)
    element_counts = ctx["element_counts"]
    detailed_element_count = int(sum(element_counts.values()))
    element_type_counts = list_counter(element_counts)
    element_type_count = len(element_type_counts)
    top_level_count = sum(1 for key in TOP_LEVEL_ELEMENT_TYPES if element_counts.get(key, 0) > 0)
    if top_level_count == 0 and detailed_element_count > 0:
        top_level_count = min(element_type_count, detailed_element_count)
    dc_type = dc_types_from_context(ctx)
    subjects = set(ctx["subjects"])
    if ctx.get("layout_class"):
        subjects.add(str(ctx["layout_class"]))
    if ctx.get("visual_type"):
        subjects.add(str(ctx["visual_type"]))
    for part in list(ctx["part_numbers"])[:10]:
        subjects.add(f"part:{part}")
    relations = set(ctx["relations"])
    for community_id in ctx["community_ids"]:
        relations.add(f"community:{community_id}")
    for citation_id in list(ctx["citation_ids"])[:25]:
        relations.add(f"citation:{citation_id}")

    review_required = bool(ctx.get("needs_human_review") or ctx.get("review_task_count", 0) > 0)
    comp_class = complexity_class(element_counts, review_required, bool(ctx.get("source_confirmed_blank")))

    dc_record = {
        "dc:identifier": page_id,
        "dc:title": f"TRACE-Net page {page_number or page_id}",
        "dc:type": dc_type,
        "dc:format": DEFAULT_FORMAT,
        "dc:source": f"source_trace:{page_id}",
        "dc:description": description_from_context(page_id, registry, ctx),
        "dc:subject": unique_strings(subjects)[:80],
        "dc:relation": unique_strings(relations)[:100],
        "dcterms:isPartOf": document_id,
        "dcterms:hasPart": [f"trace_net_element_count:{detailed_element_count}", *[f"trace_net_element_type:{k}" for k in sorted(element_type_counts)[:40]]],
        "dcterms:provenance": "TRACE-Net source trace, OCR/extraction artifacts, graph overlays, trust/review metadata",
        "dcterms:extent": f"{detailed_element_count} TRACE-Net detected/planned elements across {element_type_count} element type(s)",
    }

    trace_record = {
        "trace_net:page_id": page_id,
        "trace_net:document_id": document_id,
        "trace_net:page_number": page_number,
        "trace_net:element_count": detailed_element_count,
        "trace_net:top_level_element_count": int(top_level_count),
        "trace_net:detailed_element_count": detailed_element_count,
        "trace_net:element_type_count": element_type_count,
        "trace_net:element_type_counts": element_type_counts,
        "trace_net:graph_node_count": int(ctx.get("graph_node_count", 0)),
        "trace_net:graph_edge_count": int(ctx.get("graph_edge_count", 0)),
        "trace_net:opensearch_document_type_counts": list_counter(ctx["opensearch_document_type_counts"]),
        "trace_net:opensearch_document_count": len(ctx["opensearch_document_ids"]),
        "trace_net:citation_count": len(ctx["citation_ids"]),
        "trace_net:citation_ids": unique_strings(ctx["citation_ids"])[:100],
        "trace_net:part_number_count": len(ctx["part_numbers"]),
        "trace_net:part_numbers": unique_strings(ctx["part_numbers"])[:100],
        "trace_net:community_count": len(ctx["community_ids"]),
        "trace_net:community_ids": unique_strings(ctx["community_ids"]),
        "trace_net:review_required": review_required,
        "trace_net:review_task_count": int(ctx.get("review_task_count", 0)),
        "trace_net:review_task_ids": unique_strings(ctx["review_task_ids"])[:100],
        "trace_net:feedback_memory_count": len(ctx["feedback_memory_ids"]),
        "trace_net:feedback_memory_ids": unique_strings(ctx["feedback_memory_ids"])[:100],
        "trace_net:complexity_class": comp_class,
        "trace_net:source_trace_present": bool(ctx.get("source_trace_present") or dc_record["dc:source"]),
        "trace_net:ocr_present": bool(ctx.get("ocr_present")),
        "trace_net:context_v2_present": bool(ctx.get("context_v2_present")),
        "trace_net:source_confirmed_blank": bool(ctx.get("source_confirmed_blank")),
        "trace_net:layout_class": ctx.get("layout_class") or "",
        "trace_net:visual_type": ctx.get("visual_type") or "",
        "trace_net:trust_assignment_policy": registry.get("trust_assignment_policy") or "evidence_consensus_then_trust_authority_gate",
        "trace_net:can_answer_directly": False,
        "trace_net:can_prove_claims": False,
        "trace_net:can_mutate_source_truth": False,
        "trace_net:source_truth_mutation_allowed": False,
        "trace_net:requires_citation": True,
        "trace_net:requires_source_resolution": True,
        "trace_net:requires_authority_gate": True,
        "trace_net:metadata_only": True,
    }

    record = {
        "schema_version": SCHEMA_VERSION,
        "record_id": f"dc_page::{page_id}::{stable_hash([page_id, element_type_counts], 8)}",
        "record_type": "dublin_core_page_crosswalk",
        "page_id": page_id,
        "document_id": document_id,
        "page_number": page_number,
        "metadata_profile": "dublin_core_plus_trace_net",
        "dc": dc_record,
        "trace_net": trace_record,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }
    return record


def build_document_record(page_records: list[dict[str, Any]], *, document_id: str = DEFAULT_DOCUMENT_ID) -> dict[str, Any]:
    page_count = len(page_records)
    type_counts = Counter()
    total_elements = 0
    for rec in page_records:
        total_elements += int(rec["trace_net"].get("trace_net:element_count") or 0)
        for dtype in as_list(rec["dc"].get("dc:type")):
            type_counts[str(dtype)] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": f"dc_document::{document_id}",
        "record_type": "dublin_core_document_crosswalk",
        "document_id": document_id,
        "dc": {
            "dc:identifier": document_id,
            "dc:title": f"TRACE-Net document {document_id}",
            "dc:type": ["technical_manual", "document_collection"],
            "dc:format": "compound_resource",
            "dc:description": f"TRACE-Net Dublin Core crosswalk for {page_count} page(s).",
            "dcterms:hasPart": [rec["page_id"] for rec in page_records],
            "dcterms:extent": f"{page_count} pages; {total_elements} TRACE-Net detected/planned elements",
            "dcterms:provenance": "TRACE-Net local artifact pipeline",
        },
        "trace_net": {
            "trace_net:document_id": document_id,
            "trace_net:page_count": page_count,
            "trace_net:total_element_count": total_elements,
            "trace_net:page_type_counts": dict(sorted(type_counts.items())),
            "trace_net:can_answer_directly": False,
            "trace_net:can_prove_claims": False,
            "trace_net:can_mutate_source_truth": False,
            "trace_net:source_truth_mutation_allowed": False,
        },
    }


def summarize(page_records: list[dict[str, Any]], document_records: list[dict[str, Any]], source_summaries: dict[str, Any]) -> dict[str, Any]:
    element_type_presence = Counter()
    dc_type_counts = Counter()
    complexity_counts = Counter()
    page_records_with_element_counts = 0
    page_records_with_review_required = 0
    source_truth_mutation_allowed_count = 0
    direct_answer_allowed_count = 0
    claim_proof_allowed_count = 0
    missing_dc_identifier_count = 0
    missing_dc_source_count = 0
    missing_dc_format_count = 0
    missing_trace_net_element_count = 0
    missing_trace_net_element_type_count = 0
    for rec in page_records:
        dc = rec.get("dc", {})
        tn = rec.get("trace_net", {})
        if not dc.get("dc:identifier"):
            missing_dc_identifier_count += 1
        if not dc.get("dc:source"):
            missing_dc_source_count += 1
        if not dc.get("dc:format"):
            missing_dc_format_count += 1
        element_count = int(tn.get("trace_net:element_count") or 0)
        element_type_count = int(tn.get("trace_net:element_type_count") or 0)
        if element_count > 0:
            page_records_with_element_counts += 1
        else:
            missing_trace_net_element_count += 1
        if element_type_count > 0:
            for key, value in (tn.get("trace_net:element_type_counts") or {}).items():
                if value:
                    element_type_presence[key] += 1
        else:
            missing_trace_net_element_type_count += 1
        for dtype in as_list(dc.get("dc:type")):
            dc_type_counts[str(dtype)] += 1
        if tn.get("trace_net:review_required"):
            page_records_with_review_required += 1
        complexity_counts[str(tn.get("trace_net:complexity_class") or "unknown")] += 1
        if rec.get("can_answer_directly") or tn.get("trace_net:can_answer_directly"):
            direct_answer_allowed_count += 1
        if rec.get("can_prove_claims") or tn.get("trace_net:can_prove_claims"):
            claim_proof_allowed_count += 1
        if rec.get("source_truth_mutation_allowed") or tn.get("trace_net:source_truth_mutation_allowed"):
            source_truth_mutation_allowed_count += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "page_dc_record_count": len(page_records),
        "document_dc_record_count": len(document_records),
        "page_records_with_element_counts": page_records_with_element_counts,
        "page_records_with_review_required": page_records_with_review_required,
        "dc_type_counts": dict(sorted(dc_type_counts.items())),
        "element_type_page_presence_counts": dict(sorted(element_type_presence.items())),
        "complexity_class_counts": dict(sorted(complexity_counts.items())),
        "missing_dc_identifier_count": missing_dc_identifier_count,
        "missing_dc_source_count": missing_dc_source_count,
        "missing_dc_format_count": missing_dc_format_count,
        "missing_trace_net_element_count": missing_trace_net_element_count,
        "missing_trace_net_element_type_count": missing_trace_net_element_type_count,
        "direct_answer_allowed_count": direct_answer_allowed_count,
        "claim_proof_allowed_count": claim_proof_allowed_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "source_truth_mutations_performed": 0,
        "source_summaries": source_summaries,
    }


def evaluate_quality(summary: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, value: Any, expected: Any, severity: str = "critical") -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})

    page_count = int(summary.get("page_dc_record_count") or 0)
    required_page_count = int(config.get("require_page_count") or 0)
    if required_page_count:
        check("page_count_matches_required", page_count == required_page_count, page_count, required_page_count)
    min_page_records = int(config.get("min_page_records") or 0)
    if min_page_records:
        check("min_page_records", page_count >= min_page_records, page_count, f">={min_page_records}")
    min_document_records = int(config.get("min_document_records") or 0)
    if min_document_records:
        check("min_document_records", int(summary.get("document_dc_record_count") or 0) >= min_document_records, summary.get("document_dc_record_count"), f">={min_document_records}")
    min_pages_with_element_counts = int(config.get("min_pages_with_element_counts") or 0)
    if min_pages_with_element_counts:
        check(
            "min_pages_with_element_counts",
            int(summary.get("page_records_with_element_counts") or 0) >= min_pages_with_element_counts,
            summary.get("page_records_with_element_counts"),
            f">={min_pages_with_element_counts}",
        )
    check("dc_identifier_present", int(summary.get("missing_dc_identifier_count") or 0) == 0, summary.get("missing_dc_identifier_count"), 0)
    check("dc_source_present", int(summary.get("missing_dc_source_count") or 0) == 0, summary.get("missing_dc_source_count"), 0)
    check("dc_format_present", int(summary.get("missing_dc_format_count") or 0) == 0, summary.get("missing_dc_format_count"), 0)
    check("trace_net_element_count_present", int(summary.get("missing_trace_net_element_count") or 0) == 0, summary.get("missing_trace_net_element_count"), 0)
    check("trace_net_element_type_count_present", int(summary.get("missing_trace_net_element_type_count") or 0) == 0, summary.get("missing_trace_net_element_type_count"), 0)
    check("direct_answer_allowed_zero", int(summary.get("direct_answer_allowed_count") or 0) == 0, summary.get("direct_answer_allowed_count"), 0)
    check("claim_proof_allowed_zero", int(summary.get("claim_proof_allowed_count") or 0) == 0, summary.get("claim_proof_allowed_count"), 0)
    check("source_truth_mutation_allowed_zero", int(summary.get("source_truth_mutation_allowed_count") or 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)

    failed = [c for c in checks if not c["passed"] and c.get("severity") == "critical"]
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_check_count": len(failed),
        **{key: summary.get(key) for key in [
            "page_dc_record_count",
            "document_dc_record_count",
            "page_records_with_element_counts",
            "missing_dc_identifier_count",
            "missing_dc_source_count",
            "missing_dc_format_count",
            "missing_trace_net_element_count",
            "missing_trace_net_element_type_count",
            "direct_answer_allowed_count",
            "claim_proof_allowed_count",
            "source_truth_mutation_allowed_count",
        ]},
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Dublin Core Crosswalk v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Generated:** {report.get('created_at')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "page_dc_record_count",
        "document_dc_record_count",
        "page_records_with_element_counts",
        "page_records_with_review_required",
        "missing_dc_identifier_count",
        "missing_dc_source_count",
        "missing_dc_format_count",
        "missing_trace_net_element_count",
        "missing_trace_net_element_type_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Dublin Core Type Counts", "", "| Type | Pages |", "|---|---:|"])
    for key, value in (summary.get("dc_type_counts") or {}).items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Top Element Type Presence", "", "| Element type | Pages |", "|---|---:|"])
    for key, value in list((summary.get("element_type_page_presence_counts") or {}).items())[:40]:
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Notes", "", "Dublin Core fields are standard descriptive metadata. TRACE-Net fields preserve element counts, safety, review, and retrieval metadata. This export cannot answer directly, prove claims, or mutate source truth."])
    return "\n".join(lines) + "\n"


def render_html(markdown: str) -> str:
    escaped = html.escape(markdown)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Dublin Core Crosswalk v1</title><style>body{{font-family:Arial,sans-serif;margin:2rem;line-height:1.45}}pre{{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:8px}}</style></head><body><pre>{escaped}</pre></body></html>"


def build_crosswalk_report(
    *,
    page_registry_path: str | Path,
    table_cell_normalizer_path: str | Path | None = None,
    figure_chart_understanding_path: str | Path | None = None,
    visual_ink_layout_calibrator_path: str | Path | None = None,
    element_graph_attachment_path: str | Path | None = None,
    leiden_communities_path: str | Path | None = None,
    opensearch_adapter_path: str | Path | None = None,
    feedback_memory_path: str | Path | None = None,
    human_review_triage_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    quality_config: dict[str, Any] | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    page_registry = read_json(page_registry_path)
    pages = build_page_index(page_registry)
    context = make_page_context(pages)

    sources = {
        "page_registry": str(page_registry_path),
        "table_cell_normalizer": str(table_cell_normalizer_path or ""),
        "figure_chart_understanding": str(figure_chart_understanding_path or ""),
        "visual_ink_layout_calibrator": str(visual_ink_layout_calibrator_path or ""),
        "element_graph_attachment": str(element_graph_attachment_path or ""),
        "leiden_communities": str(leiden_communities_path or ""),
        "opensearch_adapter": str(opensearch_adapter_path or ""),
        "feedback_memory": str(feedback_memory_path or ""),
        "human_review_triage": str(human_review_triage_path or ""),
    }

    update_from_table_normalizer(context, read_json(table_cell_normalizer_path))
    update_from_figure(context, read_json(figure_chart_understanding_path))
    update_from_visual_ink(context, read_json(visual_ink_layout_calibrator_path))
    update_from_graph_attachment(context, read_json(element_graph_attachment_path))
    update_from_leiden(context, read_json(leiden_communities_path))
    update_from_opensearch(context, read_json(opensearch_adapter_path))
    update_from_feedback(context, read_json(feedback_memory_path))
    update_from_human_review_triage(context, read_json(human_review_triage_path))

    page_records = [build_page_crosswalk_record(page_id, context[page_id]) for page_id in sorted(context, key=page_sort_key)]
    document_ids = unique_strings(rec["document_id"] for rec in page_records) or [DEFAULT_DOCUMENT_ID]
    document_records = [
        build_document_record([rec for rec in page_records if rec["document_id"] == document_id], document_id=document_id)
        for document_id in document_ids
    ]
    source_summaries = {
        "page_registry_quality_status": page_registry.get("quality_status") or (page_registry.get("quality") or {}).get("status"),
        "source_artifacts": {k: v for k, v in sources.items() if v},
    }
    summary = summarize(page_records, document_records, source_summaries)
    quality = evaluate_quality(summary, quality_config or {})
    created_at = now_iso()

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_dublin_core_crosswalk_v1.json"
    pages_path = output_dir / "trace_net_dublin_core_pages_v1.jsonl"
    docs_path = output_dir / "trace_net_dublin_core_documents_v1.jsonl"
    summary_path = output_dir / "trace_net_dublin_core_crosswalk_v1_summary.json"
    quality_path = output_dir / "trace_net_dublin_core_crosswalk_v1_quality.json"
    manifest_path = output_dir / "trace_net_dublin_core_crosswalk_v1_manifest.json"
    md_path = output_dir / "trace_net_dublin_core_crosswalk_v1.md"
    html_path = output_dir / "trace_net_dublin_core_crosswalk_v1.html"
    crosswalk_md_path = output_dir / "trace_net_dublin_core_crosswalk_field_map_v1.md"

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "status": "DUBLIN_CORE_CROSSWALK_BUILT",
        "quality_status": quality["status"],
        "input_paths": sources,
        "output_paths": {
            "report": str(report_path),
            "pages": str(pages_path),
            "documents": str(docs_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
            "markdown": str(md_path),
            "html": str(html_path),
            "field_map": str(crosswalk_md_path),
        },
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "DUBLIN_CORE_CROSSWALK_BUILT",
        "quality_status": quality["status"],
        "created_at": created_at,
        "dc_prefixes": DC_PREFIXES,
        "summary": summary,
        "quality": quality,
        "document_records": document_records,
        "page_records": page_records,
        "manifest": manifest,
    }
    report["report_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    manifest["report_sha256"] = report["report_sha256"]

    md = render_markdown(report)
    field_map = """# TRACE-Net Dublin Core Crosswalk Field Map v1

| Field | Meaning |
|---|---|
| dc:identifier | Standard page/document identifier. |
| dc:type | Standard broad resource/page type. |
| dc:format | Media format, usually image/tiff for source pages. |
| dc:source | Source trace pointer for the page. |
| dc:description | Human-readable page metadata description. |
| dc:subject | Topic/type/candidate metadata useful for catalog/search. |
| dc:relation | Related citations, routes, and community IDs. |
| dcterms:isPartOf | Parent document ID. |
| dcterms:hasPart | Human-readable element-type pointers. |
| dcterms:extent | Human-readable element count summary. |
| trace_net:element_count | Machine-readable detailed element count. |
| trace_net:element_type_count | Number of detected/planned element types. |
| trace_net:element_type_counts | Per-type element counts. |
| trace_net:review_required | Whether TRACE-Net has review signals for the page. |
| trace_net:complexity_class | low, medium, high, high_review, or blank. |
| trace_net:can_answer_directly | Always false for this metadata export. |
| trace_net:can_prove_claims | Always false for this metadata export. |
| trace_net:source_truth_mutation_allowed | Always false for this metadata export. |
"""

    write_json(report_path, report)
    write_jsonl(pages_path, page_records)
    write_jsonl(docs_path, document_records)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    crosswalk_md_path.write_text(field_map, encoding="utf-8")
    if write_quality:
        write_json(quality_path, quality)

    report["report_path"] = str(report_path)
    report["pages_path"] = str(pages_path)
    report["documents_path"] = str(docs_path)
    report["quality_path"] = str(quality_path)
    return report


def quality_report(*, report_path: str | Path, quality_config: dict[str, Any] | None = None, write_json_report: bool = False) -> dict[str, Any]:
    report = read_json(report_path)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    quality = evaluate_quality(summary, quality_config or {})
    if write_json_report:
        output_path = Path(report_path).with_name("trace_net_dublin_core_crosswalk_v1_quality.json")
        write_json(output_path, quality)
        quality["quality_path"] = str(output_path)
    return quality


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Dublin Core + TRACE-Net page metadata crosswalk v1")
    parser.add_argument("--page-registry", required=True)
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--figure-chart-understanding")
    parser.add_argument("--visual-ink-layout-calibrator")
    parser.add_argument("--element-graph-attachment")
    parser.add_argument("--leiden-communities")
    parser.add_argument("--opensearch-adapter")
    parser.add_argument("--feedback-memory")
    parser.add_argument("--human-review-triage")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--require-page-count", type=int, default=0)
    parser.add_argument("--min-page-records", type=int, default=0)
    parser.add_argument("--min-document-records", type=int, default=1)
    parser.add_argument("--min-pages-with-element-counts", type=int, default=0)
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config = {
        "require_page_count": args.require_page_count,
        "min_page_records": args.min_page_records,
        "min_document_records": args.min_document_records,
        "min_pages_with_element_counts": args.min_pages_with_element_counts,
    }
    report = build_crosswalk_report(
        page_registry_path=args.page_registry,
        table_cell_normalizer_path=args.table_cell_normalizer,
        figure_chart_understanding_path=args.figure_chart_understanding,
        visual_ink_layout_calibrator_path=args.visual_ink_layout_calibrator,
        element_graph_attachment_path=args.element_graph_attachment,
        leiden_communities_path=args.leiden_communities,
        opensearch_adapter_path=args.opensearch_adapter,
        feedback_memory_path=args.feedback_memory,
        human_review_triage_path=args.human_review_triage,
        output_dir=args.output_dir,
        quality_config=config,
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net Dublin Core Crosswalk v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" page_dc_record_count: {summary.get('page_dc_record_count')}")
    print(f" document_dc_record_count: {summary.get('document_dc_record_count')}")
    print(f" page_records_with_element_counts: {summary.get('page_records_with_element_counts')}")
    print(f" missing_dc_identifier_count: {summary.get('missing_dc_identifier_count')}")
    print(f" missing_dc_source_count: {summary.get('missing_dc_source_count')}")
    print(f" missing_trace_net_element_count: {summary.get('missing_trace_net_element_count')}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count')}")
    print(f" report_path: {report['report_path']}")
    if args.quality:
        print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
