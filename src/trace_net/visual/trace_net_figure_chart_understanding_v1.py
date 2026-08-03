"""TRACE-Net Figure / Chart / Diagram Understanding v1.

Read-only front-start TRACE-Net layer that turns existing page registry,
image-recognition, visual-text, table, and candidate artifacts into conservative
visual element records. It classifies figure/chart/diagram/callout candidates,
plans graph attachment, and keeps all visual evidence retrieval-only until it is
verified by OCR/catalog/graph/citation gates.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_figure_chart_understanding_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/figure_chart_understanding")

FIGURE_TERMS = {
    "figure",
    "fig",
    "diagram",
    "illustration",
    "drawing",
    "visual",
    "image",
    "callout",
    "leader",
    "sheet",
}
CHART_TERMS = {"chart", "plot", "graph", "axis", "trend", "curve", "bar chart", "line chart"}
PART_TERMS = {"part", "parts list", "ipl", "item", "nomenclature", "assy", "assembly", "seat structure"}
TABLE_TERMS = {"table", "grid", "row", "cell", "parts list", "list of effective pages"}

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
FIGURE_RE = re.compile(r"\b(?:fig(?:ure)?\.?\s*)\d+[A-Z]?(?:\s*(?:sheet|sht)\s*\d+)?\b", re.IGNORECASE)
SHEET_RE = re.compile(r"\b(?:sheet|sht)\s*\d+\b", re.IGNORECASE)
ITEM_RE = re.compile(r"\b(?:item|callout|ref(?:erence)?)\s*[:#-]?\s*\d{1,3}[A-Z]?\b", re.IGNORECASE)
SMALL_CALLOUT_RE = re.compile(r"\b\d{1,3}[A-Z]?\b")

FORBIDDEN_USER_VISIBLE_MARKERS = [
    "local_data",
    "rescarta_exports",
    "c:\\users",
    "tiff path:",
    "ocr path:",
    "source url:",
    "can_answer_directly: true",
    "can_mutate_source_truth: true",
]

RETRIEVAL_ONLY_BUCKETS = {
    "figure_retrieval_helper",
    "diagram_retrieval_helper",
    "chart_retrieval_helper",
    "visual_context_retrieval_helper",
    "figure_part_catalog_retrieval_helper",
    "visual_needs_review",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: Any, length: int = 12) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return default


def read_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            # Recover simple concatenated JSONL fragments if needed.
            for part in re.split(r"(?<=\})\s+(?=\{)", line):
                try:
                    obj = json.loads(part)
                    if isinstance(obj, dict):
                        records.append(obj)
                except json.JSONDecodeError:
                    continue
            continue
        if isinstance(value, dict):
            records.append(value)
        elif isinstance(value, list):
            records.extend(x for x in value if isinstance(x, dict))
    return records


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


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


def norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict):
        return " ".join(norm_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(norm_text(v) for v in value)
    return str(value).lower()


def has_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def extract_records(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in keys:
            value = summary.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def load_page_registry(path: str | Path) -> list[dict[str, Any]]:
    payload = read_json(path, default={})
    return extract_records(payload, ("records", "page_records", "registry_records"))


def load_embedding_candidates(path: str | Path | None) -> list[dict[str, Any]]:
    payload = read_json(path, default={})
    return extract_records(payload, ("records", "embedding_candidates", "candidates"))


def load_table_normalizer(path: str | Path | None) -> list[dict[str, Any]]:
    payload = read_json(path, default={})
    return extract_records(payload, ("records", "table_records", "normalized_records"))


def load_image_audit_records(path: str | Path | None) -> list[dict[str, Any]]:
    payload = read_json(path, default={})
    records = extract_records(payload, ("records", "page_records", "audit_records", "pages", "sample_records"))
    if records:
        return records
    # Historic artifact stores sample records under summary.sample_records.
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        sample = payload["summary"].get("sample_records")
        if isinstance(sample, list):
            return [x for x in sample if isinstance(x, dict)]
    return []


def page_num_from_id(page_id: str | None) -> int | None:
    if not page_id:
        return None
    m = re.search(r"p0*([0-9]+)$", page_id)
    return int(m.group(1)) if m else None


def index_by_page(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        page_id = str(record.get("page_id") or record.get("page") or "").strip()
        if page_id:
            out[page_id].append(record)
    return dict(out)


def dedupe(values: Iterable[str], *, max_items: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if max_items is not None and len(out) >= max_items:
            break
    return out


def page_registry_has_visual_signal(record: dict[str, Any]) -> bool:
    blob = norm_text(
        [
            record.get("page_traits"),
            record.get("detected_elements"),
            record.get("recommended_extraction_routes"),
            record.get("fishnet_retry_plan"),
            record.get("graph_attachment_plan"),
        ]
    )
    return has_any(blob, FIGURE_TERMS) or has_any(blob, CHART_TERMS)


def image_record_has_visual_signal(record: dict[str, Any]) -> bool:
    return bool(
        record.get("likely_figure_or_diagram")
        or record.get("likely_visual")
        or record.get("likely_table_grid")
        or str(record.get("role") or "").lower() in {"figure", "parts_list", "table"}
        or "figure" in str(record.get("classification") or "").lower()
        or "diagram" in str(record.get("classification") or "").lower()
    )


def classify_visual_type(text_blob: str, image_record: dict[str, Any] | None = None) -> str:
    image_record = image_record or {}
    role = str(image_record.get("role") or "").lower()
    classification = str(image_record.get("classification") or "").lower()
    # The registry uses a combined marker like "figure_chart_or_diagram_signal".
    # Do not let that synthetic marker turn every visual page into a chart.
    chart_text = text_blob.replace("figure_chart_or_diagram", "figure diagram")
    if "parts_list" in role or (has_any(text_blob, PART_TERMS) and has_any(text_blob, FIGURE_TERMS)):
        return "parts_diagram_or_illustrated_parts_list"
    if "table" in role and has_any(text_blob, FIGURE_TERMS):
        return "table_with_figure_or_diagram"
    if has_any(chart_text, CHART_TERMS):
        return "chart_or_plot_candidate"
    if "figure" in role or "figure" in classification or "diagram" in classification:
        return "figure_or_diagram_candidate"
    if "callout" in text_blob or "leader" in text_blob:
        return "callout_diagram_candidate"
    if "drawing" in text_blob or "illustration" in text_blob:
        return "technical_illustration_candidate"
    return "visual_page_candidate"


def visual_bucket_for_type(visual_type: str, part_numbers: list[str]) -> str:
    if "chart" in visual_type:
        return "chart_retrieval_helper"
    if "parts" in visual_type or part_numbers:
        return "figure_part_catalog_retrieval_helper"
    if "diagram" in visual_type:
        return "diagram_retrieval_helper"
    return "figure_retrieval_helper"


def extract_visual_refs(text: str, *, max_items: int = 20) -> dict[str, list[str]]:
    figure_refs = dedupe((m.group(0) for m in FIGURE_RE.finditer(text)), max_items=max_items)
    sheet_refs = dedupe((m.group(0) for m in SHEET_RE.finditer(text)), max_items=max_items)
    item_refs = dedupe((m.group(0) for m in ITEM_RE.finditer(text)), max_items=max_items)
    part_numbers = dedupe((m.group(0) for m in PART_RE.finditer(text)), max_items=max_items)

    # Conservative fallback for callout labels: only keep small numeric labels if
    # the surrounding text already signals figure/diagram/callout context.
    callout_labels: list[str] = []
    if has_any(text.lower(), FIGURE_TERMS):
        callout_labels = dedupe((m.group(0) for m in SMALL_CALLOUT_RE.finditer(text)), max_items=max_items)

    return {
        "figure_refs": figure_refs,
        "sheet_refs": sheet_refs,
        "item_refs": item_refs,
        "callout_labels": callout_labels,
        "part_numbers": part_numbers,
    }


def safe_visual_text(record: dict[str, Any]) -> str:
    for key in (
        "clean_text",
        "text_clean",
        "visual_text_clean",
        "extracted_text_clean",
        "text",
        "visual_text",
        "extracted_text",
        "ocr_text",
        "summary",
        "context_summary",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return re.sub(r"\s+", " ", value).strip()
    return ""


def user_visible_has_forbidden_marker(value: Any) -> bool:
    text = norm_text(value)
    return any(marker in text for marker in FORBIDDEN_USER_VISIBLE_MARKERS)


def make_visual_region(page_id: str, visual_type: str, text_snippet: str, refs: dict[str, list[str]]) -> dict[str, Any]:
    region_kind = "page_level_visual_region"
    if "chart" in visual_type:
        region_kind = "chart_or_plot_region"
    elif "parts" in visual_type:
        region_kind = "illustrated_parts_region"
    elif "diagram" in visual_type:
        region_kind = "diagram_region"
    return {
        "region_id": f"vis_region__{page_id}__{stable_hash([visual_type, refs], 8)}",
        "region_type": region_kind,
        "region_scope": "page_level_candidate",
        "detected_figure_refs": refs["figure_refs"],
        "detected_sheet_refs": refs["sheet_refs"],
        "detected_item_refs": refs["item_refs"],
        "detected_callout_labels": refs["callout_labels"][:20],
        "linked_part_candidates": refs["part_numbers"][:20],
        "source_snippet": text_snippet[:700],
        "authority": "visual_retrieval_helper_only",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "requires_catalog_compare": bool(refs["part_numbers"] or refs["item_refs"] or refs["callout_labels"]),
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
    }


def build_graph_attachment_plan(page_id: str, visual_type: str, regions: list[dict[str, Any]], citation_ids: list[str]) -> dict[str, Any]:
    planned_edges = [
        {"from": page_id, "edge_type": "HAS_VISUAL_ELEMENT", "to": visual_type},
    ]
    for region in regions:
        planned_edges.append({"from": page_id, "edge_type": "HAS_VISUAL_REGION", "to": region["region_id"]})
        for part in region.get("linked_part_candidates", []):
            planned_edges.append({"from": region["region_id"], "edge_type": "MAY_REFER_TO_PART", "to": part})
    for citation_id in citation_ids:
        planned_edges.append({"from": page_id, "edge_type": "HAS_CITATION", "to": citation_id})
    return {
        "plan_id": f"visual_graph_attach__{page_id}__{stable_hash([visual_type, citation_ids], 8)}",
        "mode": "plan_only_no_postgres_mutation",
        "target_page_id": page_id,
        "node_types": ["Page", "VisualElement", "VisualRegion", "SourceCitation"],
        "planned_edges": planned_edges,
        "can_mutate_source_truth": False,
        "requires_authority_gate_before_answer": True,
    }


def candidate_citations(candidates: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for candidate in candidates:
        for key in ("citation_id", "source_citation_id"):
            value = candidate.get(key)
            if value:
                ids.append(str(value))
        for value in as_list(candidate.get("citation_ids")):
            if value:
                ids.append(str(value))
    return dedupe(ids)


def build_record(
    *,
    page_record: dict[str, Any],
    image_records: list[dict[str, Any]],
    visual_text_records: list[dict[str, Any]],
    candidate_records: list[dict[str, Any]],
    table_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    page_id = str(page_record.get("page_id") or "").strip()
    if not page_id:
        return None

    image_record = image_records[0] if image_records else {}
    visual_text = " ".join(safe_visual_text(r) for r in visual_text_records if safe_visual_text(r))
    table_text = norm_text(table_records)
    registry_text = norm_text(page_record)
    candidate_text = norm_text(candidate_records)
    raw_text_blob = " ".join([registry_text, visual_text, table_text, candidate_text])

    if not (page_registry_has_visual_signal(page_record) or any(image_record_has_visual_signal(r) for r in image_records) or visual_text.strip()):
        return None

    visual_type = classify_visual_type(raw_text_blob, image_record)
    refs = extract_visual_refs(" ".join([visual_text, registry_text, table_text, candidate_text]))
    rag_bucket = visual_bucket_for_type(visual_type, refs["part_numbers"])
    text_snippet = visual_text or str(image_record.get("context_summary") or "") or "visual/page registry candidate"
    text_snippet = re.sub(r"\s+", " ", text_snippet).strip()
    regions = [make_visual_region(page_id, visual_type, text_snippet, refs)]
    citation_ids = candidate_citations(candidate_records)

    has_source_trace = "source_trace_present" in as_list(page_record.get("page_traits")) or bool(candidate_records) or bool(citation_ids)
    visual_text_present = bool(visual_text.strip())
    has_part_candidates = bool(refs["part_numbers"])
    has_callout_candidates = bool(refs["callout_labels"] or refs["item_refs"])
    requires_catalog_compare = has_part_candidates or has_callout_candidates or "parts" in visual_type
    trust_tier = "B" if visual_text_present and has_source_trace else "C"
    if not has_source_trace:
        trust_tier = "needs_review"

    review_reasons: list[str] = []
    if requires_catalog_compare:
        review_reasons.append("visual_part_or_callout_requires_catalog_graph_compare")
    if not visual_text_present:
        review_reasons.append("no_visual_text_record_present")
    if not citation_ids:
        review_reasons.append("no_citation_on_visual_record_itself")

    comparison_targets = ["image_recognition", "page_element_registry", "source_trace", "citation", "trust_authority"]
    if visual_text_present:
        comparison_targets.append("visual_text")
    if requires_catalog_compare:
        comparison_targets.append("catalog_or_part_graph")
    if table_records:
        comparison_targets.append("table_context")

    graph_attachment_plan = build_graph_attachment_plan(page_id, visual_type, regions, citation_ids)
    user_visible_payload = {
        "visual_type": visual_type,
        "regions": regions,
    }
    unsafe_user_visible = user_visible_has_forbidden_marker(user_visible_payload)

    return {
        "schema_version": SCHEMA_VERSION,
        "visual_record_id": f"visual_understanding__{page_id}__{stable_hash([visual_type, refs], 10)}",
        "record_type": "figure_chart_diagram_understanding",
        "page_id": page_id,
        "page_number": page_record.get("page_number") or page_num_from_id(page_id),
        "document_id": page_record.get("document_id") or "",
        "ata_code": page_record.get("ata_code") or "",
        "visual_type": visual_type,
        "rag_bucket": rag_bucket,
        "authority": "visual_retrieval_helper_only",
        "trust_tier": trust_tier,
        "answer_use_policy": "retrieval_only_until_visual_text_callouts_parts_are_verified_against_catalog_graph_and_citations",
        "image_recognition_present": bool(image_records),
        "image_role": image_record.get("role") or "",
        "image_classification": image_record.get("classification") or "",
        "likely_figure_or_diagram": bool(image_record.get("likely_figure_or_diagram") or "figure" in visual_type or "diagram" in visual_type),
        "likely_table_grid": bool(image_record.get("likely_table_grid")),
        "visual_text_present": visual_text_present,
        "visual_text_record_count": len(visual_text_records),
        "table_context_record_count": len(table_records),
        "candidate_record_count": len(candidate_records),
        "citation_ids": citation_ids,
        "citation_count": len(citation_ids),
        "figure_refs": refs["figure_refs"],
        "sheet_refs": refs["sheet_refs"],
        "item_refs": refs["item_refs"],
        "callout_labels": refs["callout_labels"][:20],
        "linked_part_candidates": refs["part_numbers"][:20],
        "linked_part_candidate_count": len(refs["part_numbers"]),
        "callout_candidate_count": len(refs["callout_labels"]) + len(refs["item_refs"]),
        "visual_regions": regions,
        "visual_region_count": len(regions),
        "comparison_targets": sorted(set(comparison_targets)),
        "requires_catalog_compare": requires_catalog_compare,
        "requires_ocr_compare": True,
        "requires_graph_compare": True,
        "graph_attachment_plan": graph_attachment_plan,
        "needs_human_review": trust_tier == "needs_review" or requires_catalog_compare,
        "review_reasons": review_reasons,
        "leiden_community_id": None,
        "community_detection_status": "pending_graph_community_pass",
        "can_embed": True,
        "can_retrieve": True,
        "answer_support_candidate": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_answer_authority_allowed": False,
        "final_answer_allowed": False,
        "source_truth_mutations_performed": 0,
        "unsafe_user_visible_payload": unsafe_user_visible,
    }


def summarize(records: list[dict[str, Any]], *, page_count: int, quality_inputs: dict[str, Any]) -> dict[str, Any]:
    visual_type_counts = Counter(str(r.get("visual_type") or "unknown") for r in records)
    bucket_counts = Counter(str(r.get("rag_bucket") or "unknown") for r in records)
    trust_counts = Counter(str(r.get("trust_tier") or "unknown") for r in records)
    page_ids = {r.get("page_id") for r in records if r.get("page_id")}
    visual_answer_allowed = sum(1 for r in records if r.get("can_answer_directly") or r.get("can_prove_claims") or r.get("answer_support_candidate") or r.get("final_answer_allowed"))
    source_truth_mutation_allowed = sum(1 for r in records if r.get("can_mutate_source_truth") or r.get("source_truth_mutations_performed"))
    unsafe_count = sum(1 for r in records if r.get("unsafe_user_visible_payload"))
    missing_page_id = sum(1 for r in records if not r.get("page_id"))
    graph_plan_count = sum(1 for r in records if r.get("graph_attachment_plan"))
    retrieval_only_count = len(records) - visual_answer_allowed
    unverified_claim_count = visual_answer_allowed
    callouts = sum(int(r.get("callout_candidate_count") or 0) for r in records)
    parts = sum(int(r.get("linked_part_candidate_count") or 0) for r in records)
    visual_text_count = sum(1 for r in records if r.get("visual_text_present"))
    catalog_compare_count = sum(1 for r in records if r.get("requires_catalog_compare"))
    human_review_count = sum(1 for r in records if r.get("needs_human_review"))

    image_quality_summary = {}
    image_quality_status = ""
    iq = quality_inputs.get("image_quality")
    if isinstance(iq, dict):
        image_quality_status = str(iq.get("status") or iq.get("quality_status") or "")
        image_quality_summary = iq.get("summary") if isinstance(iq.get("summary"), dict) else {}

    return {
        "schema_version": SCHEMA_VERSION,
        "source_page_registry_count": page_count,
        "visual_understanding_record_count": len(records),
        "visual_candidate_page_count": len(page_ids),
        "figure_diagram_record_count": sum(1 for r in records if any(tok in str(r.get("visual_type") or "") for tok in ("figure", "diagram", "illustration", "parts"))),
        "chart_record_count": sum(1 for r in records if "chart" in str(r.get("visual_type") or "")),
        "parts_diagram_record_count": sum(1 for r in records if "parts" in str(r.get("visual_type") or "")),
        "visual_text_record_backed_count": visual_text_count,
        "visual_region_count": sum(int(r.get("visual_region_count") or 0) for r in records),
        "callout_candidate_count": callouts,
        "linked_part_candidate_count": parts,
        "records_requiring_catalog_compare_count": catalog_compare_count,
        "records_needing_human_review_count": human_review_count,
        "records_with_graph_attachment_plan_count": graph_plan_count,
        "visual_retrieval_only_count": retrieval_only_count,
        "visual_answer_allowed_count": visual_answer_allowed,
        "unverified_visual_claim_count": unverified_claim_count,
        "unsafe_visual_evidence_count": unsafe_count,
        "missing_page_id_count": missing_page_id,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "visual_type_counts": dict(sorted(visual_type_counts.items())),
        "rag_bucket_counts": dict(sorted(bucket_counts.items())),
        "trust_tier_counts": dict(sorted(trust_counts.items())),
        "image_recognition_quality_status": image_quality_status,
        "image_recognition_summary": image_quality_summary,
        "answer_status": "VISUAL_UNDERSTANDING_ONLY",
        "final_answer_allowed": False,
    }


def evaluate_quality(summary: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, observed: Any, expected: Any, severity: str = "error") -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected, "severity": severity})

    thresholds = {
        "min_visual_records": config.get("min_visual_records", 1),
        "min_visual_candidate_pages": config.get("min_visual_candidate_pages", 1),
        "min_figure_diagram_records": config.get("min_figure_diagram_records", 1),
        "min_visual_regions": config.get("min_visual_regions", 1),
        "min_retrieval_only_records": config.get("min_retrieval_only_records", 1),
        "min_graph_attachment_plans": config.get("min_graph_attachment_plans", 1),
        "max_visual_answer_allowed": config.get("max_visual_answer_allowed", 0),
        "max_unverified_visual_claims": config.get("max_unverified_visual_claims", 0),
        "max_unsafe_visual_evidence": config.get("max_unsafe_visual_evidence", 0),
        "max_source_truth_mutation_allowed": config.get("max_source_truth_mutation_allowed", 0),
        "max_missing_page_id": config.get("max_missing_page_id", 0),
    }

    check("min_visual_records", summary["visual_understanding_record_count"] >= thresholds["min_visual_records"], summary["visual_understanding_record_count"], f">= {thresholds['min_visual_records']}")
    check("min_visual_candidate_pages", summary["visual_candidate_page_count"] >= thresholds["min_visual_candidate_pages"], summary["visual_candidate_page_count"], f">= {thresholds['min_visual_candidate_pages']}")
    check("min_figure_diagram_records", summary["figure_diagram_record_count"] >= thresholds["min_figure_diagram_records"], summary["figure_diagram_record_count"], f">= {thresholds['min_figure_diagram_records']}")
    check("min_visual_regions", summary["visual_region_count"] >= thresholds["min_visual_regions"], summary["visual_region_count"], f">= {thresholds['min_visual_regions']}")
    check("min_retrieval_only_records", summary["visual_retrieval_only_count"] >= thresholds["min_retrieval_only_records"], summary["visual_retrieval_only_count"], f">= {thresholds['min_retrieval_only_records']}")
    check("min_graph_attachment_plans", summary["records_with_graph_attachment_plan_count"] >= thresholds["min_graph_attachment_plans"], summary["records_with_graph_attachment_plan_count"], f">= {thresholds['min_graph_attachment_plans']}")
    check("visual_answer_allowed_count", summary["visual_answer_allowed_count"] <= thresholds["max_visual_answer_allowed"], summary["visual_answer_allowed_count"], f"<= {thresholds['max_visual_answer_allowed']}")
    check("unverified_visual_claim_count", summary["unverified_visual_claim_count"] <= thresholds["max_unverified_visual_claims"], summary["unverified_visual_claim_count"], f"<= {thresholds['max_unverified_visual_claims']}")
    check("unsafe_visual_evidence_count", summary["unsafe_visual_evidence_count"] <= thresholds["max_unsafe_visual_evidence"], summary["unsafe_visual_evidence_count"], f"<= {thresholds['max_unsafe_visual_evidence']}")
    check("source_truth_mutation_allowed_count", summary["source_truth_mutation_allowed_count"] <= thresholds["max_source_truth_mutation_allowed"], summary["source_truth_mutation_allowed_count"], f"<= {thresholds['max_source_truth_mutation_allowed']}")
    check("missing_page_id_count", summary["missing_page_id_count"] <= thresholds["max_missing_page_id"], summary["missing_page_id_count"], f"<= {thresholds['max_missing_page_id']}")

    if config.get("require_page_registry_count") is not None:
        expected = int(config["require_page_registry_count"])
        check("require_page_registry_count", summary["source_page_registry_count"] == expected, summary["source_page_registry_count"], expected)

    failed = [c for c in checks if not c["passed"] and c.get("severity") == "error"]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not failed else "FAIL",
        "created_at": utc_now(),
        "checks": checks,
        "summary": summary,
    }


def render_markdown(report: dict[str, Any]) -> str:
    s = report.get("summary", {})
    lines = [
        "# TRACE-Net Figure / Chart / Diagram Understanding v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
        f"- Visual understanding records: {s.get('visual_understanding_record_count', 0)}",
        f"- Visual candidate pages: {s.get('visual_candidate_page_count', 0)}",
        f"- Figure/diagram records: {s.get('figure_diagram_record_count', 0)}",
        f"- Chart records: {s.get('chart_record_count', 0)}",
        f"- Visual regions: {s.get('visual_region_count', 0)}",
        f"- Callout candidates: {s.get('callout_candidate_count', 0)}",
        f"- Linked part candidates: {s.get('linked_part_candidate_count', 0)}",
        f"- Retrieval-only records: {s.get('visual_retrieval_only_count', 0)}",
        f"- Visual answer allowed records: {s.get('visual_answer_allowed_count', 0)}",
        f"- Unsafe visual evidence: {s.get('unsafe_visual_evidence_count', 0)}",
        f"- Source-truth mutations allowed: {s.get('source_truth_mutation_allowed_count', 0)}",
        "",
        "## Safety rule",
        "",
        "Figure/chart/diagram records can route retrieval and plan graph attachment. They cannot prove claims or answer directly until their labels/callouts/parts are verified against OCR, catalog, graph, source, citation, and trust authority gates.",
        "",
        "## Top visual types",
        "",
    ]
    for key, value in list((s.get("visual_type_counts") or {}).items())[:20]:
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def render_html(markdown: str) -> str:
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line.strip() else "" for line in markdown.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Figure/Chart Understanding v1</title></head><body>{body}</body></html>"


def build_figure_chart_understanding_report(
    *,
    page_registry_path: str | Path,
    image_recognition_audit_path: str | Path | None = None,
    image_recognition_quality_path: str | Path | None = None,
    visual_text_records_path: str | Path | None = None,
    visual_text_summary_path: str | Path | None = None,
    embedding_candidates_path: str | Path | None = None,
    table_cell_normalizer_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    quality_config: dict[str, Any] | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    page_records = load_page_registry(page_registry_path)
    image_records = load_image_audit_records(image_recognition_audit_path)
    image_quality = read_json(image_recognition_quality_path, default={})
    _visual_summary = read_json(visual_text_summary_path, default={})
    visual_records = read_jsonl(visual_text_records_path)
    candidates = load_embedding_candidates(embedding_candidates_path)
    table_records = load_table_normalizer(table_cell_normalizer_path)

    image_by_page = index_by_page(image_records)
    visual_by_page = index_by_page(visual_records)
    candidates_by_page = index_by_page(candidates)
    tables_by_page = index_by_page(table_records)

    records: list[dict[str, Any]] = []
    for page_record in sorted(page_records, key=lambda r: (int(r.get("page_number") or page_num_from_id(str(r.get("page_id") or "")) or 999999), str(r.get("page_id") or ""))):
        page_id = str(page_record.get("page_id") or "").strip()
        if not page_id:
            continue
        record = build_record(
            page_record=page_record,
            image_records=image_by_page.get(page_id, []),
            visual_text_records=visual_by_page.get(page_id, []),
            candidate_records=candidates_by_page.get(page_id, []),
            table_records=tables_by_page.get(page_id, []),
        )
        if record:
            records.append(record)

    summary = summarize(records, page_count=len(page_records), quality_inputs={"image_quality": image_quality})
    quality = evaluate_quality(summary, quality_config or {})

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_figure_chart_understanding_v1.json"
    records_path = output_dir / "trace_net_figure_chart_understanding_v1_records.jsonl"
    regions_path = output_dir / "trace_net_figure_chart_understanding_v1_regions.jsonl"
    callouts_path = output_dir / "trace_net_figure_chart_understanding_v1_callouts.jsonl"
    graph_plan_path = output_dir / "trace_net_figure_chart_understanding_v1_graph_attachment_plan.jsonl"
    summary_path = output_dir / "trace_net_figure_chart_understanding_v1_summary.json"
    manifest_path = output_dir / "trace_net_figure_chart_understanding_v1_manifest.json"
    quality_path = output_dir / "trace_net_figure_chart_understanding_v1_quality.json"
    markdown_path = output_dir / "trace_net_figure_chart_understanding_v1.md"
    html_path = output_dir / "trace_net_figure_chart_understanding_v1.html"

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": "FIGURE_CHART_UNDERSTANDING_BUILT",
        "quality_status": quality["status"],
        "input_paths": {
            "page_registry": str(page_registry_path),
            "image_recognition_audit": str(image_recognition_audit_path or ""),
            "image_recognition_quality": str(image_recognition_quality_path or ""),
            "visual_text_records": str(visual_text_records_path or ""),
            "visual_text_summary": str(visual_text_summary_path or ""),
            "embedding_candidates": str(embedding_candidates_path or ""),
            "table_cell_normalizer": str(table_cell_normalizer_path or ""),
        },
        "output_paths": {
            "report": str(report_path),
            "records": str(records_path),
            "regions": str(regions_path),
            "callouts": str(callouts_path),
            "graph_attachment_plan": str(graph_plan_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
            "markdown": str(markdown_path),
            "html": str(html_path),
        },
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "FIGURE_CHART_UNDERSTANDING_BUILT",
        "quality_status": quality["status"],
        "created_at": manifest["created_at"],
        "record_count": len(records),
        "summary": summary,
        "quality": quality,
        "records": records,
        "manifest": manifest,
    }
    report["report_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    manifest["report_sha256"] = report["report_sha256"]

    regions = []
    callouts = []
    graph_plans = []
    for record in records:
        for region in record.get("visual_regions", []):
            regions.append({"page_id": record["page_id"], **region})
            for label in region.get("detected_callout_labels", []):
                callouts.append({"page_id": record["page_id"], "region_id": region["region_id"], "callout_label": label})
        graph_plans.append({"page_id": record["page_id"], **record["graph_attachment_plan"]})

    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(regions_path, regions)
    write_jsonl(callouts_path, callouts)
    write_jsonl(graph_plan_path, graph_plans)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    markdown = render_markdown(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(render_html(markdown), encoding="utf-8")

    report["report_path"] = str(report_path)
    report["records_path"] = str(records_path)
    report["regions_path"] = str(regions_path)
    report["callouts_path"] = str(callouts_path)
    report["graph_attachment_plan_path"] = str(graph_plan_path)
    report["summary_path"] = str(summary_path)
    report["manifest_path"] = str(manifest_path)
    report["quality_path"] = str(quality_path)
    return report


def quality_report_from_path(report_path: str | Path, quality_config: dict[str, Any] | None = None, *, write_json_file: bool = False) -> dict[str, Any]:
    payload = read_json(report_path, default={})
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid report JSON: {report_path}")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Report is missing summary")
    quality = evaluate_quality(summary, quality_config or {})
    if write_json_file:
        path = Path(report_path).with_name("trace_net_figure_chart_understanding_v1_quality.json")
        write_json(path, quality)
        quality["quality_path"] = str(path)
    return quality


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--require-page-registry-count", type=int, default=None)
    parser.add_argument("--min-visual-records", type=int, default=1)
    parser.add_argument("--min-visual-candidate-pages", type=int, default=1)
    parser.add_argument("--min-figure-diagram-records", type=int, default=1)
    parser.add_argument("--min-visual-regions", type=int, default=1)
    parser.add_argument("--min-retrieval-only-records", type=int, default=1)
    parser.add_argument("--min-graph-attachment-plans", type=int, default=1)


def quality_config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "require_page_registry_count": args.require_page_registry_count,
        "min_visual_records": args.min_visual_records,
        "min_visual_candidate_pages": args.min_visual_candidate_pages,
        "min_figure_diagram_records": args.min_figure_diagram_records,
        "min_visual_regions": args.min_visual_regions,
        "min_retrieval_only_records": args.min_retrieval_only_records,
        "min_graph_attachment_plans": args.min_graph_attachment_plans,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net figure/chart/diagram understanding v1 artifacts.")
    parser.add_argument("--page-registry", required=True)
    parser.add_argument("--image-recognition-audit", default="local_data/organization/image_recognition/page_image_recognition_audit.json")
    parser.add_argument("--image-recognition-quality", default="local_data/organization/image_recognition/page_image_recognition_quality.json")
    parser.add_argument("--visual-text-records", default="local_data/organization/visual_text/visual_text_extraction_clean.jsonl")
    parser.add_argument("--visual-text-summary", default="local_data/organization/visual_text/visual_text_clean_summary.json")
    parser.add_argument("--embedding-candidates", default="local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json")
    parser.add_argument("--table-cell-normalizer", default="local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--quality", action="store_true")
    add_common_quality_args(parser)
    args = parser.parse_args(argv)

    report = build_figure_chart_understanding_report(
        page_registry_path=args.page_registry,
        image_recognition_audit_path=args.image_recognition_audit,
        image_recognition_quality_path=args.image_recognition_quality,
        visual_text_records_path=args.visual_text_records,
        visual_text_summary_path=args.visual_text_summary,
        embedding_candidates_path=args.embedding_candidates,
        table_cell_normalizer_path=args.table_cell_normalizer,
        output_dir=args.output_dir,
        quality_config=quality_config_from_args(args),
        write_quality=args.quality,
    )
    s = report["summary"]
    print("TRACE-Net figure / chart / diagram understanding v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "visual_understanding_record_count",
        "visual_candidate_page_count",
        "figure_diagram_record_count",
        "chart_record_count",
        "parts_diagram_record_count",
        "visual_region_count",
        "callout_candidate_count",
        "linked_part_candidate_count",
        "visual_retrieval_only_count",
        "visual_answer_allowed_count",
        "unverified_visual_claim_count",
        "unsafe_visual_evidence_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


def quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net figure/chart/diagram understanding v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_quality_args(parser)
    args = parser.parse_args(argv)
    quality = quality_report_from_path(args.report_path, quality_config_from_args(args), write_json_file=args.write_json)
    s = quality["summary"]
    print("TRACE-Net figure / chart / diagram understanding v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "visual_understanding_record_count",
        "visual_candidate_page_count",
        "figure_diagram_record_count",
        "chart_record_count",
        "visual_region_count",
        "visual_retrieval_only_count",
        "visual_answer_allowed_count",
        "unverified_visual_claim_count",
        "unsafe_visual_evidence_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    if args.write_json:
        print(f" quality_path: {quality.get('quality_path')}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
