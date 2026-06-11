"""TRACE-Net Callout Cleaner / Visual Part Verifier v1.

Read-only visual verification layer for technical drawings and illustrated
parts pages.  It consumes conservative visual understanding records, normalized
rows/cells, and part-candidate lineage to separate likely callout labels from
random OCR numbers, link callouts to same-page table rows, compare visual part
candidates against catalog/graph signals, and flag pages that need human review.

All outputs are retrieval/review helpers.  This module does not grant answer
authority, does not mutate source truth, and does not write to Postgres/Qdrant.
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

SCHEMA_VERSION = "trace_net_callout_visual_part_verifier_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/callout_visual_part_verifier")

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
DATE_TOKEN_RE = re.compile(r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|sep\.?|apr\.?)$", re.IGNORECASE)
CALLOUT_LABEL_RE = re.compile(r"^[A-Z]?\d{1,3}[A-Z]?$|^[A-Z]{1,2}$")
NUMERIC_RE = re.compile(r"^\d{1,3}$")

FORBIDDEN_USER_VISIBLE_MARKERS = [
    "local_data",
    "rescarta_exports",
    "c:\\users",
    "tiff path:",
    "ocr path:",
    "source url:",
    "raw bytes",
    "ocr text: [b",
    "can_answer_directly: true",
    "can_mutate_source_truth: true",
]

ANSWER_BLOCKED_AUTHORITY = "visual_callout_part_verification_retrieval_only"
RETRIEVAL_BUCKET = "visual_callout_part_verification_helper"


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
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(value)
        elif isinstance(value, list):
            out.extend(x for x in value if isinstance(x, dict))
    return out


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


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


def dedupe(values: Iterable[Any], *, max_items: int | None = None) -> list[str]:
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


def page_num_from_id(page_id: str) -> int | None:
    m = re.search(r"p(\d{6})$", str(page_id))
    if not m:
        return None
    return int(m.group(1))


def norm_label(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"^(?:ITEM|CALLOUT|REF(?:ERENCE)?)[\s:#-]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^A-Z0-9-]", "", text)
    return text


def collect_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, (int, float)):
        out.append(str(value))
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(collect_strings(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            out.extend(collect_strings(item))
    return out


def visible_text_has_forbidden(value: Any) -> bool:
    text = "\n".join(collect_strings(value)).lower()
    return any(marker.lower() in text for marker in FORBIDDEN_USER_VISIBLE_MARKERS)


def load_records_from_report(path: str | Path | None, *keys: str) -> list[dict[str, Any]]:
    payload = read_json(path, default={})
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def extract_catalog_parts(part_property_payload: dict[str, Any], embedding_payload: dict[str, Any]) -> set[str]:
    parts: set[str] = set()
    for key in ("part_candidate_nodes", "node_plans", "nodes"):
        for node in as_list(part_property_payload.get(key)):
            if not isinstance(node, dict):
                continue
            candidates = [
                node.get("part_number"),
                node.get("canonical_part_candidate"),
                node.get("label"),
                node.get("node_id"),
            ]
            props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            candidates.extend([props.get("part_number"), props.get("canonical_part_candidate")])
            for text in collect_strings(candidates):
                parts.update(PART_RE.findall(text))
    if isinstance(embedding_payload, dict):
        for record in as_list(embedding_payload.get("records")):
            if not isinstance(record, dict):
                continue
            if str(record.get("rag_bucket") or "") == "verified_part_evidence":
                parts.update(PART_RE.findall(" ".join(collect_strings(record))))
    return parts


def table_rows_by_page(table_records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table in table_records:
        page_id = str(table.get("page_id") or "")
        if not page_id:
            continue
        table_id = str(table.get("normalized_table_id") or table.get("table_id") or table.get("source_table_id") or stable_hash(table, 10))
        cells_by_row: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for cell in as_list(table.get("cells")):
            if isinstance(cell, dict):
                row_id = str(cell.get("row_id") or cell.get("normalized_row_id") or "")
                cells_by_row[row_id].append(cell)
        for row in as_list(table.get("rows")):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("source_row_id") or row.get("row_id") or row.get("normalized_row_id") or "")
            row_cells = cells_by_row.get(row_id) or cells_by_row.get(str(row.get("normalized_row_id") or "")) or []
            row_text = str(row.get("row_text") or " ".join(str(c.get("normalized_text") or c.get("text") or "") for c in row_cells))
            part_numbers = dedupe(PART_RE.findall(row_text))
            item_tokens = infer_row_item_tokens(row, row_cells, row_text)
            by_page[page_id].append({
                "table_id": table_id,
                "row_id": row_id or str(row.get("normalized_row_id") or stable_hash(row, 10)),
                "normalized_row_id": row.get("normalized_row_id"),
                "row_index": row.get("row_index"),
                "row_type": row.get("row_type"),
                "row_text": row_text,
                "item_tokens": item_tokens,
                "part_numbers": part_numbers,
                "answer_support_candidate": bool(row.get("answer_support_candidate")),
                "citation_ids": [str(x) for x in as_list(row.get("citation_ids")) if str(x)],
            })
    return by_page


def infer_row_item_tokens(row: dict[str, Any], cells: list[dict[str, Any]], row_text: str) -> list[str]:
    tokens: list[str] = []
    # Prefer the first one or two small numeric cells; item columns usually live there.
    for cell in sorted(cells, key=lambda c: int(c.get("col_index") or c.get("column_index") or 0))[:3]:
        text = norm_label(cell.get("normalized_text") or cell.get("text") or cell.get("original_text"))
        if NUMERIC_RE.match(text) and 1 <= int(text) <= 300:
            tokens.append(text)
    if not tokens:
        # Fallback to leading numeric token in row text.
        m = re.match(r"\s*(\d{1,3}[A-Z]?)\b", row_text.strip())
        if m:
            tokens.append(norm_label(m.group(1)))
    return dedupe(tokens, max_items=8)


def is_probable_random_number(label: str, *, page_number: int | None, table_item_tokens: set[str], visual_type: str) -> tuple[bool, str]:
    if not label:
        return True, "empty_label"
    if PART_RE.match(label):
        return True, "part_number_not_callout_label"
    if YEAR_RE.match(label):
        return True, "year_token"
    if DATE_TOKEN_RE.match(label):
        return True, "date_token"
    if page_number is not None and label == str(page_number):
        return True, "matches_page_number"
    if not CALLOUT_LABEL_RE.match(label):
        return True, "not_callout_shape"
    if NUMERIC_RE.match(label):
        num = int(label)
        if num == 0:
            return True, "zero_not_callout"
        if num > 300:
            return True, "large_numeric_token"
        if label in table_item_tokens:
            return False, "supported_by_table_item"
        if "parts" in visual_type or "diagram" in visual_type or "illustrated" in visual_type:
            if 1 <= num <= 99:
                return False, "small_numeric_diagram_label"
            return True, "large_diagram_number_without_table_support"
        # For chart/text visual types, only keep if supported by table item.
        return True, "numeric_label_without_visual_support"
    # Letter labels are plausible only for visual/diagram pages.
    if "parts" in visual_type or "diagram" in visual_type or "illustrated" in visual_type:
        return False, "letter_diagram_label"
    return True, "letter_label_without_visual_support"


def collect_callout_candidates(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    values.extend(as_list(record.get("callout_labels")))
    values.extend(as_list(record.get("item_refs")))
    for region in as_list(record.get("visual_regions")):
        if isinstance(region, dict):
            values.extend(as_list(region.get("detected_callout_labels")))
            values.extend(as_list(region.get("detected_item_refs")))
    out: list[str] = []
    for value in values:
        text = norm_label(value)
        if text:
            out.append(text)
    return dedupe(out, max_items=200)


def collect_linked_part_candidates(record: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    parts.extend(str(x) for x in as_list(record.get("linked_part_candidates")) if str(x))
    for region in as_list(record.get("visual_regions")):
        if isinstance(region, dict):
            parts.extend(str(x) for x in as_list(region.get("linked_part_candidates")) if str(x))
    found: list[str] = []
    for text in parts + collect_strings(record.get("visual_regions")):
        found.extend(PART_RE.findall(text))
    return dedupe(found, max_items=200)


def verify_visual_record(record: dict[str, Any], *, table_rows: list[dict[str, Any]], catalog_parts: set[str]) -> dict[str, Any]:
    page_id = str(record.get("page_id") or "")
    page_number = record.get("page_number") or page_num_from_id(page_id)
    visual_type = str(record.get("visual_type") or "visual_page_candidate")
    raw_callouts = collect_callout_candidates(record)
    linked_parts = collect_linked_part_candidates(record)
    table_item_tokens = {tok for row in table_rows for tok in row.get("item_tokens", [])}
    table_parts = {part for row in table_rows for part in row.get("part_numbers", [])}

    clean_callouts: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for label in raw_callouts:
        is_random, reason = is_probable_random_number(label, page_number=page_number, table_item_tokens=table_item_tokens, visual_type=visual_type)
        entry = {"label": label, "reason": reason}
        if is_random:
            suppressed.append(entry)
        else:
            clean_callouts.append({
                "callout_id": f"callout_clean__{page_id}__{stable_hash([page_id, label], 10)}",
                "label": label,
                "cleaning_reason": reason,
                "authority": "visual_callout_candidate_retrieval_only",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "requires_catalog_compare": True,
                "requires_source_resolution": True,
                "requires_citation": True,
                "requires_authority_gate": True,
            })

    row_links: list[dict[str, Any]] = []
    for callout in clean_callouts:
        label = callout["label"]
        for row in table_rows:
            if label in set(row.get("item_tokens", [])):
                row_links.append({
                    "link_id": f"callout_row_link__{stable_hash([page_id, label, row.get('row_id')], 12)}",
                    "page_id": page_id,
                    "callout_label": label,
                    "table_id": row.get("table_id"),
                    "row_id": row.get("row_id"),
                    "normalized_row_id": row.get("normalized_row_id"),
                    "row_type": row.get("row_type"),
                    "row_part_numbers": row.get("part_numbers", []),
                    "citation_ids": row.get("citation_ids", []),
                    "link_status": "candidate_supported_by_table_item",
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "can_mutate_source_truth": False,
                })

    visual_part_links: list[dict[str, Any]] = []
    candidate_parts = dedupe(list(linked_parts) + list(table_parts), max_items=300)
    for part in candidate_parts:
        in_catalog = part in catalog_parts
        in_table = part in table_parts
        in_visual = part in linked_parts
        if not (in_catalog or in_table or in_visual):
            continue
        status = "catalog_and_table_supported" if in_catalog and in_table else "catalog_supported" if in_catalog else "table_supported_unverified_catalog" if in_table else "visual_candidate_unverified"
        visual_part_links.append({
            "visual_part_link_id": f"visual_part_link__{stable_hash([page_id, part, status], 12)}",
            "page_id": page_id,
            "part_number": part,
            "catalog_supported": in_catalog,
            "same_page_table_supported": in_table,
            "visual_candidate_present": in_visual,
            "verification_status": status,
            "authority": "visual_part_candidate_catalog_compare_retrieval_only",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "requires_source_resolution": True,
            "requires_citation": True,
            "requires_authority_gate": True,
        })

    catalog_verified_count = sum(1 for x in visual_part_links if x.get("catalog_supported"))
    linked_row_count = len(row_links)
    needs_review = bool(
        ("parts" in visual_type or "diagram" in visual_type or linked_parts or clean_callouts)
        and (catalog_verified_count == 0 or linked_row_count == 0 or bool(suppressed))
    )
    review_reasons: list[str] = []
    if clean_callouts and linked_row_count == 0:
        review_reasons.append("clean_callouts_without_table_row_link")
    if linked_parts and catalog_verified_count == 0:
        review_reasons.append("visual_part_candidates_without_catalog_support")
    if suppressed:
        review_reasons.append("random_number_callout_candidates_suppressed")
    if record.get("needs_human_review"):
        review_reasons.append("source_visual_understanding_required_review")

    unsafe_visible = visible_text_has_forbidden({
        "clean_callouts": clean_callouts,
        "suppressed_callouts": suppressed,
        "visual_part_links": visual_part_links,
    })

    graph_plan = {
        "status": "planned_not_written",
        "page_id": page_id,
        "node_types": ["Page", "CleanCalloutCandidate", "VisualPartCandidate", "TableRow", "PartCandidate"],
        "planned_edges": [],
        "can_mutate_source_truth": False,
    }
    for callout in clean_callouts:
        graph_plan["planned_edges"].append({"from": page_id, "edge_type": "HAS_CLEAN_CALLOUT_CANDIDATE", "to": callout["callout_id"]})
    for link in row_links:
        graph_plan["planned_edges"].append({"from": f"clean_callout::{page_id}::{link['callout_label']}", "edge_type": "MAY_MATCH_TABLE_ROW", "to": link.get("row_id")})
    for part_link in visual_part_links:
        graph_plan["planned_edges"].append({"from": page_id, "edge_type": "HAS_VISUAL_PART_CANDIDATE", "to": part_link["part_number"]})

    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "callout_visual_part_verification",
        "verifier_record_id": f"callout_visual_verifier__{page_id}__{stable_hash([raw_callouts, linked_parts], 10)}",
        "page_id": page_id,
        "page_number": page_number,
        "source_visual_record_id": record.get("visual_record_id"),
        "source_visual_type": visual_type,
        "authority": ANSWER_BLOCKED_AUTHORITY,
        "rag_bucket": RETRIEVAL_BUCKET,
        "trust_tier": "C" if needs_review else "B",
        "answer_use_policy": "retrieval_and_review_only_until_callouts_parts_are_verified_by_catalog_graph_table_citation_and_authority_gate",
        "raw_callout_candidate_count": len(raw_callouts),
        "clean_callout_count": len(clean_callouts),
        "suppressed_random_number_count": len(suppressed),
        "clean_callouts": clean_callouts,
        "suppressed_callout_candidates": suppressed,
        "callout_to_table_row_link_count": len(row_links),
        "callout_to_table_row_links": row_links,
        "linked_visual_part_candidate_count": len(candidate_parts),
        "catalog_verified_visual_part_count": catalog_verified_count,
        "table_supported_visual_part_count": sum(1 for x in visual_part_links if x.get("same_page_table_supported")),
        "visual_part_links": visual_part_links,
        "table_row_context_count": len(table_rows),
        "requires_catalog_compare": True if clean_callouts or candidate_parts else bool(record.get("requires_catalog_compare")),
        "requires_graph_compare": True,
        "requires_ocr_compare": True,
        "needs_human_review": needs_review,
        "review_reasons": dedupe(review_reasons),
        "graph_attachment_plan": graph_plan,
        "safety_status": "unsafe_user_visible_marker_detected" if unsafe_visible else "callout_visual_part_verification_safe",
        "unsafe_visual_evidence": unsafe_visible,
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
    }


def compute_summary(records: list[dict[str, Any]], *, source_visual_record_count: int, catalog_part_count: int) -> dict[str, Any]:
    clean_callouts = [c for r in records for c in r.get("clean_callouts", []) if isinstance(c, dict)]
    suppressed = [c for r in records for c in r.get("suppressed_callout_candidates", []) if isinstance(c, dict)]
    row_links = [l for r in records for l in r.get("callout_to_table_row_links", []) if isinstance(l, dict)]
    part_links = [l for r in records for l in r.get("visual_part_links", []) if isinstance(l, dict)]
    review_records = [r for r in records if r.get("needs_human_review")]
    unsafe = [r for r in records if r.get("unsafe_visual_evidence")]
    answer_allowed = [r for r in records if r.get("can_answer_directly") or r.get("can_prove_claims") or r.get("answer_support_candidate") or r.get("final_answer_allowed")]
    source_truth_mutation = [r for r in records if r.get("can_mutate_source_truth") or r.get("source_truth_mutations_performed")]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_visual_record_count": source_visual_record_count,
        "callout_verifier_record_count": len(records),
        "page_count": len({r.get("page_id") for r in records if r.get("page_id")}),
        "raw_callout_candidate_count": sum(int(r.get("raw_callout_candidate_count") or 0) for r in records),
        "clean_callout_count": len(clean_callouts),
        "random_number_suppressed_count": len(suppressed),
        "callout_to_table_row_link_count": len(row_links),
        "linked_visual_part_candidate_count": sum(int(r.get("linked_visual_part_candidate_count") or 0) for r in records),
        "visual_part_link_count": len(part_links),
        "catalog_verified_visual_part_count": sum(1 for l in part_links if l.get("catalog_supported")),
        "table_supported_visual_part_count": sum(1 for l in part_links if l.get("same_page_table_supported")),
        "diagrams_needing_human_review_count": len(review_records),
        "records_with_graph_attachment_plan_count": sum(1 for r in records if r.get("graph_attachment_plan")),
        "unsafe_visual_evidence_count": len(unsafe),
        "visual_answer_allowed_count": len(answer_allowed),
        "unverified_visual_claim_count": len(answer_allowed),
        "source_truth_mutation_allowed_count": len(source_truth_mutation),
        "retrieval_only_record_count": len(records) - len(answer_allowed),
        "catalog_part_count": catalog_part_count,
        "authority_counts": dict(Counter(str(r.get("authority") or "unknown") for r in records)),
        "rag_bucket_counts": dict(Counter(str(r.get("rag_bucket") or "unknown") for r in records)),
        "trust_tier_counts": dict(Counter(str(r.get("trust_tier") or "unknown") for r in records)),
        "answer_status": "CALLOUT_VISUAL_PART_VERIFICATION_ONLY",
        "final_answer_allowed": False,
    }


def evaluate_quality(summary: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    thresholds = {
        "min_verifier_records": config.get("min_verifier_records", 1),
        "min_clean_callouts": config.get("min_clean_callouts", 1),
        "min_random_numbers_suppressed": config.get("min_random_numbers_suppressed", 0),
        "min_callout_to_table_row_links": config.get("min_callout_to_table_row_links", 0),
        "min_catalog_verified_visual_parts": config.get("min_catalog_verified_visual_parts", 0),
        "min_records_with_graph_attachment_plans": config.get("min_records_with_graph_attachment_plans", 1),
        "max_unsafe_visual_evidence": config.get("max_unsafe_visual_evidence", 0),
        "max_visual_answer_allowed": config.get("max_visual_answer_allowed", 0),
        "max_unverified_visual_claims": config.get("max_unverified_visual_claims", 0),
        "max_source_truth_mutation_allowed": config.get("max_source_truth_mutation_allowed", 0),
    }
    check("min_verifier_records", summary["callout_verifier_record_count"] >= thresholds["min_verifier_records"], summary["callout_verifier_record_count"], f">= {thresholds['min_verifier_records']}")
    check("min_clean_callouts", summary["clean_callout_count"] >= thresholds["min_clean_callouts"], summary["clean_callout_count"], f">= {thresholds['min_clean_callouts']}")
    check("min_random_numbers_suppressed", summary["random_number_suppressed_count"] >= thresholds["min_random_numbers_suppressed"], summary["random_number_suppressed_count"], f">= {thresholds['min_random_numbers_suppressed']}")
    check("min_callout_to_table_row_links", summary["callout_to_table_row_link_count"] >= thresholds["min_callout_to_table_row_links"], summary["callout_to_table_row_link_count"], f">= {thresholds['min_callout_to_table_row_links']}")
    check("min_catalog_verified_visual_parts", summary["catalog_verified_visual_part_count"] >= thresholds["min_catalog_verified_visual_parts"], summary["catalog_verified_visual_part_count"], f">= {thresholds['min_catalog_verified_visual_parts']}")
    check("min_records_with_graph_attachment_plans", summary["records_with_graph_attachment_plan_count"] >= thresholds["min_records_with_graph_attachment_plans"], summary["records_with_graph_attachment_plan_count"], f">= {thresholds['min_records_with_graph_attachment_plans']}")
    check("unsafe_visual_evidence_count", summary["unsafe_visual_evidence_count"] <= thresholds["max_unsafe_visual_evidence"], summary["unsafe_visual_evidence_count"], f"<= {thresholds['max_unsafe_visual_evidence']}")
    check("visual_answer_allowed_count", summary["visual_answer_allowed_count"] <= thresholds["max_visual_answer_allowed"], summary["visual_answer_allowed_count"], f"<= {thresholds['max_visual_answer_allowed']}")
    check("unverified_visual_claim_count", summary["unverified_visual_claim_count"] <= thresholds["max_unverified_visual_claims"], summary["unverified_visual_claim_count"], f"<= {thresholds['max_unverified_visual_claims']}")
    check("source_truth_mutation_allowed_count", summary["source_truth_mutation_allowed_count"] <= thresholds["max_source_truth_mutation_allowed"], summary["source_truth_mutation_allowed_count"], f"<= {thresholds['max_source_truth_mutation_allowed']}")
    failed = [c for c in checks if not c["passed"]]
    return {"schema_version": SCHEMA_VERSION, "status": "PASS" if not failed else "FAIL", "created_at": utc_now(), "checks": checks, "summary": summary}


def render_markdown(report: dict[str, Any]) -> str:
    s = report.get("summary", {})
    lines = [
        "# TRACE-Net Callout Cleaner / Visual Part Verifier v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
        f"- Verification records: {s.get('callout_verifier_record_count', 0)}",
        f"- Raw callout candidates: {s.get('raw_callout_candidate_count', 0)}",
        f"- Clean callouts: {s.get('clean_callout_count', 0)}",
        f"- Random numbers suppressed: {s.get('random_number_suppressed_count', 0)}",
        f"- Callout-to-table row links: {s.get('callout_to_table_row_link_count', 0)}",
        f"- Visual part links: {s.get('visual_part_link_count', 0)}",
        f"- Catalog-verified visual parts: {s.get('catalog_verified_visual_part_count', 0)}",
        f"- Records needing human review: {s.get('diagrams_needing_human_review_count', 0)}",
        f"- Unsafe visual evidence: {s.get('unsafe_visual_evidence_count', 0)}",
        f"- Source truth mutations allowed: {s.get('source_truth_mutation_allowed_count', 0)}",
        "",
        "## Safety rule",
        "",
        "Clean callouts and visual part links are retrieval/review helpers only. They cannot prove claims or answer directly until catalog, graph, OCR/source, citation, trust authority, and final answer gates approve them.",
    ]
    return "\n".join(lines) + "\n"


def render_html(markdown: str) -> str:
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line.strip() else "" for line in markdown.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Callout Visual Part Verifier v1</title></head><body>{body}</body></html>"


def build_callout_visual_part_verifier_report(
    *,
    figure_chart_understanding_path: str | Path,
    table_cell_normalizer_path: str | Path | None = None,
    graph_overlay_part_normalizer_path: str | Path | None = None,
    embedding_candidates_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    quality_config: dict[str, Any] | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    visual_records = load_records_from_report(figure_chart_understanding_path, "records", "visual_records")
    table_records = load_records_from_report(table_cell_normalizer_path, "records", "table_records")
    part_payload = read_json(graph_overlay_part_normalizer_path, default={})
    embedding_payload = read_json(embedding_candidates_path, default={})
    catalog_parts = extract_catalog_parts(part_payload if isinstance(part_payload, dict) else {}, embedding_payload if isinstance(embedding_payload, dict) else {})
    rows_by_page = table_rows_by_page(table_records)

    records: list[dict[str, Any]] = []
    for visual in visual_records:
        if not isinstance(visual, dict):
            continue
        page_id = str(visual.get("page_id") or "")
        if not page_id:
            continue
        # Only build verifier records for visual route records that have callout,
        # part, diagram, chart, or catalog-compare signals.
        has_signal = bool(
            visual.get("callout_candidate_count")
            or visual.get("linked_part_candidate_count")
            or visual.get("requires_catalog_compare")
            or "diagram" in str(visual.get("visual_type") or "")
            or "parts" in str(visual.get("visual_type") or "")
            or "chart" in str(visual.get("visual_type") or "")
        )
        if not has_signal:
            continue
        records.append(verify_visual_record(visual, table_rows=rows_by_page.get(page_id, []), catalog_parts=catalog_parts))

    summary = compute_summary(records, source_visual_record_count=len(visual_records), catalog_part_count=len(catalog_parts))
    quality = evaluate_quality(summary, quality_config)
    status = "CALLOUT_VISUAL_PART_VERIFIER_BUILT"
    quality_status = quality["status"]

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "quality_status": quality_status,
        "created_at": utc_now(),
        "algorithm": "trace_net_callout_cleaner_visual_part_catalog_compare_v1",
        "writeback_mode": "read_only_verification_plan",
        "answer_status": "CALLOUT_VISUAL_PART_VERIFICATION_ONLY",
        "final_answer_allowed": False,
        "records": records,
        "summary": summary,
        "quality": quality,
        "source_paths": {
            "figure_chart_understanding": str(figure_chart_understanding_path),
            "table_cell_normalizer": str(table_cell_normalizer_path or ""),
            "graph_overlay_part_normalizer": str(graph_overlay_part_normalizer_path or ""),
            "embedding_candidates": str(embedding_candidates_path or ""),
        },
    }

    report_path = output_dir / "trace_net_callout_visual_part_verifier_v1.json"
    records_path = output_dir / "trace_net_callout_visual_part_verifier_v1_records.jsonl"
    callouts_path = output_dir / "trace_net_callout_visual_part_verifier_v1_callouts.jsonl"
    links_path = output_dir / "trace_net_callout_visual_part_verifier_v1_links.jsonl"
    summary_path = output_dir / "trace_net_callout_visual_part_verifier_v1_summary.json"
    manifest_path = output_dir / "trace_net_callout_visual_part_verifier_v1_manifest.json"
    quality_path = output_dir / "trace_net_callout_visual_part_verifier_v1_quality.json"
    md_path = output_dir / "trace_net_callout_visual_part_verifier_v1.md"
    html_path = output_dir / "trace_net_callout_visual_part_verifier_v1.html"

    all_callouts = [c | {"page_id": r.get("page_id")} for r in records for c in r.get("clean_callouts", []) if isinstance(c, dict)]
    all_links = []
    for r in records:
        for link in r.get("callout_to_table_row_links", []):
            if isinstance(link, dict):
                all_links.append(link)
        for link in r.get("visual_part_links", []):
            if isinstance(link, dict):
                all_links.append(link)

    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(callouts_path, all_callouts)
    write_jsonl(links_path, all_links)
    write_json(summary_path, summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "callouts_path": str(callouts_path),
        "links_path": str(links_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "writeback_mode": "read_only_verification_plan",
    }
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    markdown = render_markdown(report)
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(render_html(markdown), encoding="utf-8")

    report.update({
        "report_path": str(report_path),
        "records_path": str(records_path),
        "callouts_path": str(callouts_path),
        "links_path": str(links_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
    })
    return report


def check_callout_visual_part_verifier_quality(*, report_path: str | Path, quality_config: dict[str, Any] | None = None, write_json_report: bool = False) -> dict[str, Any]:
    report = read_json(report_path, default={})
    summary = report.get("summary") if isinstance(report, dict) else None
    if not isinstance(summary, dict):
        summary = {}
    quality = evaluate_quality(summary, quality_config)
    if write_json_report:
        out = Path(report_path).with_name("trace_net_callout_visual_part_verifier_v1_quality.json")
        write_json(out, quality)
    return quality


# Compatibility names for tests/scripts.
run_callout_visual_part_verifier = build_callout_visual_part_verifier_report
quality_report = check_callout_visual_part_verifier_quality


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net callout cleaner / visual part verifier v1")
    parser.add_argument("--figure-chart-understanding", required=True)
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--graph-overlay-part-normalizer")
    parser.add_argument("--embedding-candidates")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-verifier-records", type=int, default=1)
    parser.add_argument("--min-clean-callouts", type=int, default=1)
    parser.add_argument("--min-random-numbers-suppressed", type=int, default=0)
    parser.add_argument("--min-callout-to-table-row-links", type=int, default=0)
    parser.add_argument("--min-catalog-verified-visual-parts", type=int, default=0)
    parser.add_argument("--min-records-with-graph-attachment-plans", type=int, default=1)
    parser.add_argument("--quality", action="store_true")
    return parser


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net callout cleaner / visual part verifier quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-verifier-records", type=int, default=1)
    parser.add_argument("--min-clean-callouts", type=int, default=1)
    parser.add_argument("--min-random-numbers-suppressed", type=int, default=0)
    parser.add_argument("--min-callout-to-table-row-links", type=int, default=0)
    parser.add_argument("--min-catalog-verified-visual-parts", type=int, default=0)
    parser.add_argument("--min-records-with-graph-attachment-plans", type=int, default=1)
    parser.add_argument("--write-json", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "min_verifier_records": args.min_verifier_records,
        "min_clean_callouts": args.min_clean_callouts,
        "min_random_numbers_suppressed": args.min_random_numbers_suppressed,
        "min_callout_to_table_row_links": args.min_callout_to_table_row_links,
        "min_catalog_verified_visual_parts": args.min_catalog_verified_visual_parts,
        "min_records_with_graph_attachment_plans": args.min_records_with_graph_attachment_plans,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_callout_visual_part_verifier_report(
        figure_chart_understanding_path=args.figure_chart_understanding,
        table_cell_normalizer_path=args.table_cell_normalizer,
        graph_overlay_part_normalizer_path=args.graph_overlay_part_normalizer,
        embedding_candidates_path=args.embedding_candidates,
        output_dir=args.output_dir,
        quality_config=config_from_args(args),
        write_quality=args.quality,
    )
    s = report["summary"]
    print("TRACE-Net callout cleaner / visual part verifier v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "callout_verifier_record_count",
        "raw_callout_candidate_count",
        "clean_callout_count",
        "random_number_suppressed_count",
        "callout_to_table_row_link_count",
        "visual_part_link_count",
        "catalog_verified_visual_part_count",
        "diagrams_needing_human_review_count",
        "unsafe_visual_evidence_count",
        "visual_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key, 0)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


def quality_main(argv: list[str] | None = None) -> int:
    args = quality_arg_parser().parse_args(argv)
    quality = check_callout_visual_part_verifier_quality(report_path=args.report_path, quality_config=config_from_args(args), write_json_report=args.write_json)
    s = quality.get("summary", {})
    print("TRACE-Net callout cleaner / visual part verifier v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "callout_verifier_record_count",
        "clean_callout_count",
        "random_number_suppressed_count",
        "callout_to_table_row_link_count",
        "catalog_verified_visual_part_count",
        "unsafe_visual_evidence_count",
        "visual_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key, 0)}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
