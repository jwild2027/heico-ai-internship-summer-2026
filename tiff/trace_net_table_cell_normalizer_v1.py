"""TRACE-Net Table Cell Normalizer / Part Row Repair v1.

Read-only Step 15.1 layer that refines the Step 15 table-understanding
artifacts. It normalizes table rows/cells, detects split part-number rows,
repairs only with explicit provenance, and keeps all table evidence behind the
TRACE-Net citation/source/authority gates.

This module does not mutate Postgres, Qdrant, source files, graph truth, trust
truth, or citations.
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

SCHEMA_VERSION = "trace_net_table_cell_normalizer_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_cell_normalizer")

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
PART_FRAGMENT_LEFT_RE = re.compile(r"^\d{3}-\d{1,4}$")
PART_FRAGMENT_RIGHT_RE = re.compile(r"^\d{1,5}-\d{3}$")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2}/\d{2,4}\b", re.IGNORECASE)
IPL_RE = re.compile(r"\b\d{1,2}\s*-?\s*IPL\b", re.IGNORECASE)
REVISION_RE = re.compile(r"\b(?:REV(?:ISION)?|RECORD OF REVISION|EFFECTIVE PAGES|INSERT REVISED PAGES|SUPERSEDES)\b", re.IGNORECASE)
INDEX_RE = re.compile(r"\b(?:PARTS LIST|VENDOR|CONTENTS|FIG|FIGURE|ITEM|NOMENCLATURE|QTY|QUANTITY)\b", re.IGNORECASE)
FORBIDDEN_MARKERS = [
    "local_data\\",
    "local_data/",
    "rescarta_exports",
    "C:\\Users\\",
    "TIFF path:",
    "OCR path:",
    "OCR text: [b",
    "can_answer_directly: true",
    "can_mutate_source_truth: true",
]

ANSWER_SUPPORT_TABLE_BUCKETS = {"table_structured_evidence", "table_part_catalog_evidence"}
RETRIEVAL_ONLY_TABLE_BUCKETS = {"table_retrieval_helper", "table_needs_review", "unknown_table"}
ANSWER_SUPPORT_ROW_TYPES = {"part_number_row", "part_catalog_row", "revision_effectivity_row", "source_text_table_row"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: Any, length: int = 12) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:length]


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
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
            elif isinstance(obj, list):
                rows.extend(x for x in obj if isinstance(x, dict))
        except json.JSONDecodeError:
            continue
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


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


def load_records_from_json(path: str | Path | None, keys: tuple[str, ...] = ("records",)) -> list[dict[str, Any]]:
    payload = read_json(path, default={})
    if isinstance(payload, dict):
        for key in keys:
            records = payload.get(key)
            if isinstance(records, list):
                return [r for r in records if isinstance(r, dict)]
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for sub in value.values():
            yield from flatten_strings(sub)
    elif isinstance(value, list):
        for sub in value:
            yield from flatten_strings(sub)


def extract_catalog_part_numbers(embedding_candidates: list[dict[str, Any]]) -> set[str]:
    parts: set[str] = set()
    for record in embedding_candidates:
        bucket = str(record.get("rag_bucket") or record.get("safety_bucket") or "").lower()
        # Prefer part-related records, but still scan all text because some older
        # artifacts store known parts inside generic metadata fields.
        scan_text = " ".join(flatten_strings(record))
        for match in PART_RE.finditer(scan_text):
            parts.add(match.group(0))
        if "part" in bucket:
            for key in ("part_number", "part_id", "source_candidate_id", "embedding_text"):
                val = record.get(key)
                if isinstance(val, str):
                    for match in PART_RE.finditer(val):
                        parts.add(match.group(0))
    return parts


def clean_cell_text(text: Any) -> str:
    raw = str(text or "")
    raw = re.sub(r"\[[^\]]+\]", " ", raw)
    raw = raw.replace("|", " ")
    raw = re.sub(r"\s+", " ", raw)
    raw = raw.strip(" ,;:\t\r\n")
    return raw


def normalize_cell_value(text: str) -> str:
    text = clean_cell_text(text)
    # Keep hyphens because part numbers and ATA codes depend on them.
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def cell_kind(text: str) -> str:
    value = normalize_cell_value(text)
    if PART_RE.fullmatch(value):
        return "part_number"
    if PART_FRAGMENT_LEFT_RE.fullmatch(value):
        return "part_fragment_left"
    if PART_FRAGMENT_RIGHT_RE.fullmatch(value):
        return "part_fragment_right"
    if ATA_RE.fullmatch(value):
        return "ata_code"
    if DATE_RE.search(value):
        return "date"
    if IPL_RE.search(value):
        return "ipl_reference"
    if INDEX_RE.search(value):
        return "index_label"
    if re.fullmatch(r"\d+", value):
        return "number"
    if not value:
        return "empty"
    return "text"


def candidate_join_part(left: str, right: str) -> str | None:
    a = normalize_cell_value(left)
    b = normalize_cell_value(right)
    if not a or not b:
        return None
    joined = f"{a}{b}"
    if PART_RE.fullmatch(joined):
        return joined
    # Sometimes OCR leaves an extra hyphen at the boundary or whitespace in the
    # right half. Try one conservative repair by removing only boundary clutter.
    joined2 = re.sub(r"--+", "-", f"{a}-{b}")
    if PART_RE.fullmatch(joined2):
        return joined2
    return None


def extract_row_cells(table_record: dict[str, Any], row: dict[str, Any]) -> list[dict[str, Any]]:
    row_id = row.get("row_id")
    table_cells = table_record.get("cells")
    if isinstance(table_cells, list):
        cells = [c for c in table_cells if isinstance(c, dict) and c.get("row_id") == row_id]
        if cells:
            return sorted(cells, key=lambda c: int(c.get("col_index") or c.get("column_index") or 0))
    row_cells = row.get("cells")
    if isinstance(row_cells, list):
        out: list[dict[str, Any]] = []
        for idx, c in enumerate(row_cells):
            if isinstance(c, dict):
                item = dict(c)
                item.setdefault("col_index", idx)
                item.setdefault("row_id", row_id)
                out.append(item)
            else:
                out.append({"row_id": row_id, "col_index": idx, "text": str(c)})
        return out
    raw_text = row.get("text") or row.get("raw_text") or ""
    if raw_text:
        parts = [p for p in re.split(r"\s{2,}|\|", str(raw_text)) if p.strip()]
        if len(parts) <= 1:
            parts = str(raw_text).split()
        return [{"row_id": row_id, "col_index": idx, "text": part} for idx, part in enumerate(parts)]
    return []


def infer_row_type(normalized_cells: list[dict[str, Any]], row_text: str, repairs: list[dict[str, Any]]) -> str:
    kinds = Counter(c.get("normalized_kind") for c in normalized_cells)
    if any(r.get("repair_type") == "split_part_number_merge" for r in repairs) or kinds.get("part_number", 0) > 0:
        if INDEX_RE.search(row_text) or kinds.get("number", 0) > 0:
            return "part_catalog_row"
        return "part_number_row"
    if DATE_RE.search(row_text) and (IPL_RE.search(row_text) or REVISION_RE.search(row_text) or kinds.get("ata_code", 0) > 0):
        return "revision_effectivity_row"
    if INDEX_RE.search(row_text):
        return "index_or_header_row"
    if kinds.get("ata_code", 0) > 0 and DATE_RE.search(row_text):
        return "source_text_table_row"
    if len(normalized_cells) >= 3:
        return "structured_text_row"
    return "unstructured_row"


def row_confidence(normalized_cells: list[dict[str, Any]], repairs: list[dict[str, Any]], catalog_supported: int) -> float:
    if not normalized_cells:
        return 0.0
    recognized = sum(1 for c in normalized_cells if c.get("normalized_kind") not in {"text", "empty"})
    base = 0.45 + min(0.35, recognized / max(1, len(normalized_cells)) * 0.35)
    if repairs:
        base += 0.08
    if catalog_supported:
        base += 0.12
    return round(min(base, 0.98), 4)


def normalize_row(
    table_record: dict[str, Any],
    row: dict[str, Any],
    *,
    catalog_parts: set[str],
    table_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_cells = extract_row_cells(table_record, row)
    normalized_cells: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    row_id = str(row.get("row_id") or f"row_{stable_hash(row, 8)}")
    page_id = str(table_record.get("page_id") or "")

    for idx, cell in enumerate(raw_cells):
        text = normalize_cell_value(cell.get("text") or cell.get("value") or "")
        kind = cell_kind(text)
        normalized_cells.append({
            "normalized_cell_id": f"normcell__{stable_hash([table_id, row_id, idx, text], 14)}",
            "source_cell_id": cell.get("cell_id"),
            "table_id": table_id,
            "row_id": row_id,
            "page_id": page_id,
            "col_index": int(cell.get("col_index") or cell.get("column_index") or idx),
            "original_text": str(cell.get("text") or cell.get("value") or ""),
            "normalized_text": text,
            "normalized_kind": kind,
            "normalization_method": "trace_net_cell_text_normalize_v1",
        })

    # Conservative split part-number repair: adjacent cells only, original cells
    # retained, repaired part inserted as an additional normalized cell.
    for idx in range(len(normalized_cells) - 1):
        left = normalized_cells[idx]
        right = normalized_cells[idx + 1]
        merged = candidate_join_part(left.get("normalized_text", ""), right.get("normalized_text", ""))
        if not merged:
            continue
        supported = merged in catalog_parts
        repair = {
            "repair_id": f"tblrepair__{stable_hash([table_id, row_id, idx, merged], 14)}",
            "repair_type": "split_part_number_merge",
            "page_id": page_id,
            "table_id": table_id,
            "row_id": row_id,
            "source_cell_indices": [left.get("col_index"), right.get("col_index")],
            "source_cell_texts": [left.get("normalized_text"), right.get("normalized_text")],
            "merged_part_number": merged,
            "catalog_supported": supported,
            "repair_confidence": 0.94 if supported else 0.72,
            "repair_status": "catalog_supported" if supported else "candidate_unverified",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "requires_source_resolution": True,
            "requires_citation": True,
            "requires_authority_gate": True,
        }
        repairs.append(repair)
        normalized_cells.append({
            "normalized_cell_id": f"normcell__{stable_hash([table_id, row_id, idx, merged, 'merged'], 14)}",
            "source_cell_id": None,
            "table_id": table_id,
            "row_id": row_id,
            "page_id": page_id,
            "col_index": min(int(left.get("col_index") or 0), int(right.get("col_index") or 0)),
            "original_text": " ".join([str(left.get("normalized_text") or ""), str(right.get("normalized_text") or "")]).strip(),
            "normalized_text": merged,
            "normalized_kind": "part_number",
            "normalization_method": "split_part_number_merge_v1",
            "repair_id": repair["repair_id"],
            "catalog_supported": supported,
        })

    row_text = " ".join(c.get("normalized_text", "") for c in normalized_cells if c.get("normalized_text"))
    catalog_supported_count = sum(1 for r in repairs if r.get("catalog_supported"))
    kind = infer_row_type(normalized_cells, row_text, repairs)
    confidence = row_confidence(normalized_cells, repairs, catalog_supported_count)
    citation_ids = [str(x) for x in as_list(table_record.get("citation_ids")) if str(x)]
    table_bucket = str(table_record.get("rag_bucket") or "")
    table_answer_support = bool(table_record.get("answer_support_candidate")) or table_bucket in ANSWER_SUPPORT_TABLE_BUCKETS
    row_answer_support = (
        table_answer_support
        and kind in ANSWER_SUPPORT_ROW_TYPES
        and bool(citation_ids)
        and confidence >= 0.65
    )

    normalized_row = {
        "normalized_row_id": f"normrow__{stable_hash([table_id, row_id, row_text], 14)}",
        "source_row_id": row.get("row_id"),
        "table_id": table_id,
        "page_id": page_id,
        "row_index": int(row.get("row_index") or row.get("index") or 0),
        "row_type": kind,
        "row_text": row_text,
        "normalized_cell_count": len(normalized_cells),
        "repair_count": len(repairs),
        "part_number_merge_candidate_count": len([r for r in repairs if r.get("repair_type") == "split_part_number_merge"]),
        "catalog_supported_merge_count": catalog_supported_count,
        "row_confidence": confidence,
        "answer_support_candidate": row_answer_support,
        "table_answer_support_candidate": table_answer_support,
        "citation_ids": citation_ids,
        "authority": "table_row_support_with_citation" if row_answer_support else "table_row_retrieval_helper",
        "rag_bucket": "table_normalized_row_evidence" if row_answer_support else "table_row_retrieval_helper",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "final_answer_allowed": False,
        "normalization_algorithm": "trace_net_table_cell_normalizer_part_row_repair_v1",
    }
    return normalized_row, normalized_cells + repairs


USER_VISIBLE_TABLE_TEXT_KEYS = {
    "text",
    "value",
    "raw_text",
    "clean_text",
    "row_text",
    "original_text",
    "normalized_text",
    "source_cell_texts",
    "merged_part_number",
}


def collect_user_visible_table_text(value: Any, *, parent_key: str = "") -> list[str]:
    """Collect only table text fields that could become user-facing evidence.

    Step 15.1 is an internal normalization artifact and may carry provenance in
    parent/source records.  A source URL, TIFF path, or OCR path in provenance is
    not itself unsafe table evidence.  The safety leak check should only inspect
    extracted/normalized table text that could later be shown as evidence.
    """
    fragments: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text in USER_VISIBLE_TABLE_TEXT_KEYS:
                if isinstance(item, (str, int, float, bool)) or item is None:
                    fragments.append(str(item or ""))
                elif isinstance(item, list):
                    fragments.extend(str(x or "") for x in item if isinstance(x, (str, int, float, bool)) or x is None)
                    fragments.extend(collect_user_visible_table_text(x, parent_key=key_text) for x in item if isinstance(x, dict))
                elif isinstance(item, dict):
                    fragments.extend(collect_user_visible_table_text(item, parent_key=key_text))
            elif isinstance(item, (dict, list, tuple)):
                fragments.extend(collect_user_visible_table_text(item, parent_key=key_text))
    elif isinstance(value, (list, tuple)):
        for item in value:
            fragments.extend(collect_user_visible_table_text(item, parent_key=parent_key))
    return [f for f in fragments if f]


def table_has_forbidden_leak(record: dict[str, Any]) -> bool:
    text = "\n".join(collect_user_visible_table_text(record))
    low = text.lower()
    return any(marker.lower() in low for marker in FORBIDDEN_MARKERS)


def normalize_table_record(table_record: dict[str, Any], *, catalog_parts: set[str]) -> dict[str, Any]:
    page_id = str(table_record.get("page_id") or "")
    source_table_id = str(table_record.get("table_id") or table_record.get("table_understanding_id") or table_record.get("record_id") or stable_hash(table_record, 10))
    table_id = f"normtable__{stable_hash([SCHEMA_VERSION, source_table_id, page_id], 14)}"
    rows = table_record.get("rows") if isinstance(table_record.get("rows"), list) else []
    normalized_rows: list[dict[str, Any]] = []
    normalized_cells: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row = dict(row)
        row.setdefault("row_index", idx)
        norm_row, cell_or_repair = normalize_row(table_record, row, catalog_parts=catalog_parts, table_id=table_id)
        normalized_rows.append(norm_row)
        for item in cell_or_repair:
            if "repair_type" in item:
                repairs.append(item)
            else:
                normalized_cells.append(item)

    citation_ids = [str(x) for x in as_list(table_record.get("citation_ids")) if str(x)]
    answer_support_rows = [r for r in normalized_rows if r.get("answer_support_candidate")]
    table_type = str(table_record.get("table_type") or "unknown_table")
    trust_tier = str(table_record.get("trust_tier") or "review")
    unsafe = table_has_forbidden_leak({
        "normalized_rows": normalized_rows,
        "normalized_cells": normalized_cells,
        "repairs": repairs,
    })
    record = {
        "normalized_table_id": table_id,
        "source_table_id": source_table_id,
        "schema_version": SCHEMA_VERSION,
        "record_type": "table_cell_normalization_record",
        "page_id": page_id,
        "page_number": table_record.get("page_number"),
        "table_type": table_type,
        "source_table_trust_tier": trust_tier,
        "source_rag_bucket": table_record.get("rag_bucket"),
        "normalization_status": "normalized_with_repairs" if repairs else "normalized_no_repairs",
        "cell_normalizer_algorithm": "trace_net_table_cell_normalizer_part_row_repair_v1",
        "source_row_count": len(rows),
        "normalized_row_count": len(normalized_rows),
        "normalized_cell_count": len(normalized_cells),
        "repair_count": len(repairs),
        "part_number_merge_candidate_count": len([r for r in repairs if r.get("repair_type") == "split_part_number_merge"]),
        "catalog_supported_merge_count": len([r for r in repairs if r.get("catalog_supported")]),
        "candidate_unverified_merge_count": len([r for r in repairs if r.get("repair_status") == "candidate_unverified"]),
        "answer_support_row_count": len(answer_support_rows),
        "retrieval_only_row_count": len([r for r in normalized_rows if not r.get("answer_support_candidate")]),
        "citation_ids": citation_ids,
        "has_citation": bool(citation_ids),
        "rows": normalized_rows,
        "cells": normalized_cells,
        "repairs": repairs,
        "graph_attachment_plan": {
            "status": "planned_not_written",
            "page_id": page_id,
            "proposed_edges": [
                {"from": page_id, "edge_type": "HAS_NORMALIZED_TABLE", "to": table_id},
                {"from": table_id, "edge_type": "DERIVED_FROM_TABLE_UNDERSTANDING", "to": source_table_id},
            ],
            "row_node_count": len(normalized_rows),
            "cell_node_count": len(normalized_cells),
            "repair_node_count": len(repairs),
            "can_mutate_source_truth": False,
        },
        "safety_status": "unsafe_forbidden_marker_detected" if unsafe else "table_cell_normalization_safe",
        "unsafe_table_evidence": unsafe,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "final_answer_allowed": False,
    }
    return record


def compute_summary(records: list[dict[str, Any]], *, source_table_count: int, catalog_part_count: int) -> dict[str, Any]:
    rows = [row for r in records for row in r.get("rows", []) if isinstance(row, dict)]
    cells = [cell for r in records for cell in r.get("cells", []) if isinstance(cell, dict)]
    repairs = [repair for r in records for repair in r.get("repairs", []) if isinstance(repair, dict)]
    answer_rows = [row for row in rows if row.get("answer_support_candidate")]
    uncited_answer_rows = [row for row in answer_rows if not row.get("citation_ids")]
    retrieval_answer_rows = [row for row in rows if row.get("rag_bucket") == "table_row_retrieval_helper" and row.get("answer_support_candidate")]
    table_type_counts = Counter(str(r.get("table_type") or "unknown_table") for r in records)
    row_type_counts = Counter(str(r.get("row_type") or "unknown") for r in rows)
    source_truth_mutation_allowed_count = sum(
        1
        for obj in list(records) + rows + cells + repairs
        if obj.get("can_mutate_source_truth") is True
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_table_record_count": source_table_count,
        "normalized_table_record_count": len(records),
        "normalized_row_count": len(rows),
        "normalized_cell_count": len(cells),
        "normalized_repair_count": len(repairs),
        "table_type_counts": dict(table_type_counts),
        "row_type_counts": dict(row_type_counts),
        "part_number_merge_candidate_count": len([r for r in repairs if r.get("repair_type") == "split_part_number_merge"]),
        "catalog_supported_merge_count": len([r for r in repairs if r.get("catalog_supported")]),
        "candidate_unverified_merge_count": len([r for r in repairs if r.get("repair_status") == "candidate_unverified"]),
        "table_records_with_repairs_count": len([r for r in records if r.get("repair_count", 0) > 0]),
        "answer_support_row_count": len(answer_rows),
        "uncited_answer_capable_row_count": len(uncited_answer_rows),
        "retrieval_only_answer_allowed_count": len(retrieval_answer_rows),
        "unsafe_table_evidence_count": len([r for r in records if r.get("unsafe_table_evidence")]),
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "catalog_part_count": catalog_part_count,
        "final_answer_allowed_count": sum(1 for r in records if r.get("final_answer_allowed") is True),
    }


def quality_checks(summary: dict[str, Any], args: argparse.Namespace | None = None) -> list[dict[str, Any]]:
    args = args or argparse.Namespace()
    checks = []

    def add(name: str, passed: bool, actual: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    add("min_normalized_table_records", summary.get("normalized_table_record_count", 0) >= getattr(args, "min_normalized_table_records", 1), summary.get("normalized_table_record_count", 0), f">= {getattr(args, 'min_normalized_table_records', 1)}")
    add("min_normalized_rows", summary.get("normalized_row_count", 0) >= getattr(args, "min_normalized_rows", 1), summary.get("normalized_row_count", 0), f">= {getattr(args, 'min_normalized_rows', 1)}")
    add("min_normalized_cells", summary.get("normalized_cell_count", 0) >= getattr(args, "min_normalized_cells", 1), summary.get("normalized_cell_count", 0), f">= {getattr(args, 'min_normalized_cells', 1)}")
    add("min_part_number_merge_candidates", summary.get("part_number_merge_candidate_count", 0) >= getattr(args, "min_part_number_merge_candidates", 0), summary.get("part_number_merge_candidate_count", 0), f">= {getattr(args, 'min_part_number_merge_candidates', 0)}")
    add("min_answer_support_rows", summary.get("answer_support_row_count", 0) >= getattr(args, "min_answer_support_rows", 0), summary.get("answer_support_row_count", 0), f">= {getattr(args, 'min_answer_support_rows', 0)}")
    add("unsafe_table_evidence_zero", summary.get("unsafe_table_evidence_count", 0) == 0, summary.get("unsafe_table_evidence_count", 0), "0")
    add("uncited_answer_capable_rows_zero", summary.get("uncited_answer_capable_row_count", 0) == 0, summary.get("uncited_answer_capable_row_count", 0), "0")
    add("retrieval_only_answer_allowed_zero", summary.get("retrieval_only_answer_allowed_count", 0) == 0, summary.get("retrieval_only_answer_allowed_count", 0), "0")
    add("source_truth_mutation_allowed_zero", summary.get("source_truth_mutation_allowed_count", 0) == 0, summary.get("source_truth_mutation_allowed_count", 0), "0")
    add("final_answer_allowed_zero", summary.get("final_answer_allowed_count", 0) == 0, summary.get("final_answer_allowed_count", 0), "0")
    return checks


def quality_status(checks: list[dict[str, Any]]) -> str:
    return "PASS" if all(c.get("passed") for c in checks) else "FAIL"


def build_trace_net_table_cell_normalizer(
    *,
    table_understanding_path: str | Path,
    embedding_candidates_path: str | Path | None = None,
    page_registry_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source_records = load_records_from_json(table_understanding_path, keys=("records", "table_records"))
    embedding_candidates = load_records_from_json(embedding_candidates_path, keys=("records",)) if embedding_candidates_path else []
    catalog_parts = extract_catalog_part_numbers(embedding_candidates)
    normalized_records = [normalize_table_record(r, catalog_parts=catalog_parts) for r in source_records if isinstance(r, dict)]
    summary = compute_summary(normalized_records, source_table_count=len(source_records), catalog_part_count=len(catalog_parts))
    checks = quality_checks(summary, args)
    status = quality_status(checks)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_CELL_NORMALIZER_BUILT",
        "quality_status": status,
        "created_at": utc_now(),
        "table_understanding_path": str(table_understanding_path),
        "embedding_candidates_path": str(embedding_candidates_path) if embedding_candidates_path else "",
        "page_registry_path": str(page_registry_path) if page_registry_path else "",
        "record_count": len(normalized_records),
        "summary": summary,
        "quality": {"status": status, "checks": checks},
        "records": normalized_records,
    }

    base = output / "trace_net_table_cell_normalizer_v1"
    report_path = base.with_suffix(".json")
    records_path = output / "trace_net_table_cell_normalizer_v1_records.jsonl"
    rows_path = output / "trace_net_table_cell_normalizer_v1_rows.jsonl"
    cells_path = output / "trace_net_table_cell_normalizer_v1_cells.jsonl"
    repairs_path = output / "trace_net_table_cell_normalizer_v1_repairs.jsonl"
    graph_path = output / "trace_net_table_cell_normalizer_v1_graph_attachment_plan.jsonl"
    summary_path = output / "trace_net_table_cell_normalizer_v1_summary.json"
    manifest_path = output / "trace_net_table_cell_normalizer_v1_manifest.json"
    quality_path = output / "trace_net_table_cell_normalizer_v1_quality.json"
    md_path = output / "trace_net_table_cell_normalizer_v1.md"
    html_path = output / "trace_net_table_cell_normalizer_v1.html"

    rows = [row for rec in normalized_records for row in rec.get("rows", [])]
    cells = [cell for rec in normalized_records for cell in rec.get("cells", [])]
    repairs = [repair for rec in normalized_records for repair in rec.get("repairs", [])]
    graph_plans = [rec.get("graph_attachment_plan", {}) for rec in normalized_records]

    write_json(report_path, payload)
    write_jsonl(records_path, normalized_records)
    write_jsonl(rows_path, rows)
    write_jsonl(cells_path, cells)
    write_jsonl(repairs_path, repairs)
    write_jsonl(graph_path, graph_plans)
    write_json(summary_path, summary)
    write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": status, "summary": summary, "checks": checks})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": payload["created_at"],
        "status": payload["status"],
        "quality_status": status,
        "report_path": str(report_path),
        "records_path": str(records_path),
        "rows_path": str(rows_path),
        "cells_path": str(cells_path),
        "repairs_path": str(repairs_path),
        "graph_attachment_plan_path": str(graph_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
    }
    write_json(manifest_path, manifest)

    md = render_markdown(payload)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text("<html><body>" + html.escape(md).replace("\n", "<br>\n") + "</body></html>", encoding="utf-8")
    payload.update({
        "report_path": str(report_path),
        "records_path": str(records_path),
        "rows_path": str(rows_path),
        "cells_path": str(cells_path),
        "repairs_path": str(repairs_path),
        "quality_path": str(quality_path),
    })
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# TRACE-Net Table Cell Normalizer v1",
        "",
        f"**Status:** {payload.get('status')}",
        f"**Quality:** {payload.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "normalized_table_record_count",
        "normalized_row_count",
        "normalized_cell_count",
        "normalized_repair_count",
        "part_number_merge_candidate_count",
        "catalog_supported_merge_count",
        "candidate_unverified_merge_count",
        "answer_support_row_count",
        "unsafe_table_evidence_count",
        "uncited_answer_capable_row_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend([
        "",
        "## Safety rule",
        "",
        "Table rows may be normalized and repaired, but they cannot answer directly. Final answer use still requires source resolution, citation, and authority gates.",
    ])
    return "\n".join(lines) + "\n"


def check_trace_net_table_cell_normalizer_quality(
    *,
    report_path: str | Path,
    args: argparse.Namespace | None = None,
    write_json_flag: bool = False,
) -> dict[str, Any]:
    payload = read_json(report_path, default={})
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    checks = quality_checks(summary, args)
    status = quality_status(checks)
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "summary": summary,
        "checks": checks,
        "report_path": str(report_path),
    }
    if write_json_flag:
        quality_path = Path(report_path).with_name("trace_net_table_cell_normalizer_v1_quality.json")
        write_json(quality_path, result)
        result["quality_path"] = str(quality_path)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Table Cell Normalizer / Part Row Repair v1 artifacts.")
    parser.add_argument("--table-understanding", required=True)
    parser.add_argument("--embedding-candidates", default=None)
    parser.add_argument("--page-registry", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-normalized-table-records", type=int, default=1)
    parser.add_argument("--min-normalized-rows", type=int, default=1)
    parser.add_argument("--min-normalized-cells", type=int, default=1)
    parser.add_argument("--min-part-number-merge-candidates", type=int, default=0)
    parser.add_argument("--min-answer-support-rows", type=int, default=0)
    parser.add_argument("--quality", action="store_true")
    return parser


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Table Cell Normalizer v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-normalized-table-records", type=int, default=1)
    parser.add_argument("--min-normalized-rows", type=int, default=1)
    parser.add_argument("--min-normalized-cells", type=int, default=1)
    parser.add_argument("--min-part-number-merge-candidates", type=int, default=0)
    parser.add_argument("--min-answer-support-rows", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        payload = build_trace_net_table_cell_normalizer(
            table_understanding_path=args.table_understanding,
            embedding_candidates_path=args.embedding_candidates,
            page_registry_path=args.page_registry,
            output_dir=args.output_dir,
            args=args,
        )
        summary = payload["summary"]
        print("TRACE-Net table cell normalizer / part row repair v1")
        print(f" Status: {payload['status']}")
        print(f" Quality status: {payload['quality_status']}")
        for key in [
            "normalized_table_record_count",
            "normalized_row_count",
            "normalized_cell_count",
            "normalized_repair_count",
            "part_number_merge_candidate_count",
            "catalog_supported_merge_count",
            "candidate_unverified_merge_count",
            "answer_support_row_count",
            "unsafe_table_evidence_count",
            "uncited_answer_capable_row_count",
            "retrieval_only_answer_allowed_count",
            "source_truth_mutation_allowed_count",
        ]:
            print(f" {key}: {summary.get(key)}")
        print(f" report_path: {payload['report_path']}")
        print(f" rows_path: {payload['rows_path']}")
        print(f" cells_path: {payload['cells_path']}")
        print(f" repairs_path: {payload['repairs_path']}")
        print(f" quality_path: {payload['quality_path']}")
        return 0 if payload["quality_status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net table cell normalizer failed: {exc}")
        return 2


def quality_main(argv: list[str] | None = None) -> int:
    parser = build_quality_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = check_trace_net_table_cell_normalizer_quality(report_path=args.report_path, args=args, write_json_flag=args.write_json)
        summary = result["summary"]
        print("TRACE-Net table cell normalizer v1 quality")
        print(f" Status: {result['status']}")
        for key in [
            "normalized_table_record_count",
            "normalized_row_count",
            "normalized_cell_count",
            "part_number_merge_candidate_count",
            "catalog_supported_merge_count",
            "answer_support_row_count",
            "unsafe_table_evidence_count",
            "uncited_answer_capable_row_count",
            "retrieval_only_answer_allowed_count",
            "source_truth_mutation_allowed_count",
        ]:
            print(f" {key}: {summary.get(key)}")
        if result.get("quality_path"):
            print(f" quality_path: {result['quality_path']}")
        return 0 if result["status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net table cell normalizer quality check failed: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
