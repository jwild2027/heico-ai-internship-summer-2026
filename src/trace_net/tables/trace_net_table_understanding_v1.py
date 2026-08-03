"""TRACE-Net Table Understanding v1.

Read-only front-start TRACE-Net layer that turns existing table-candidate,
table-tile, and refined table text artifacts into conservative structured table
records. It does not mutate Postgres, Qdrant, source files, trust, or source
truth.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_table_understanding_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_understanding")

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
IPL_RE = re.compile(r"\b\d{1,2}\s*-?\s*IPL\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}/\d{2,4}\b", re.IGNORECASE)
PAGE_REF_RE = re.compile(r"\b(?:Page|FIG|IPL|Parts List|Vendor)\s+[A-Za-z0-9./*-]+\b", re.IGNORECASE)
INDEX_LABEL_RE = re.compile(r"\b(?:APPLICABILITY|CONTENTS|LIST OF EFFECTIVE PAGES|RECORD OF REVISION|REVISION|VENDOR|PARTS LIST)\b", re.IGNORECASE)
FORBIDDEN_MARKERS = [
    "can_answer_directly: true",
    "can_mutate_source_truth: true",
]

ANSWER_SUPPORT_BUCKETS = {"table_structured_evidence", "table_part_catalog_evidence"}
RETRIEVAL_ONLY_BUCKETS = {"table_retrieval_helper", "table_needs_review"}


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
        return json.loads(p.read_text(encoding="utf-8"))
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
            obj = json.loads(line)
            if isinstance(obj, dict):
                records.append(obj)
            elif isinstance(obj, list):
                records.extend(x for x in obj if isinstance(x, dict))
        except json.JSONDecodeError:
            # Some historic JSONL artifacts can be copied/pasted with several JSON
            # objects on one long line. Try to recover by splitting on "} {".
            parts = re.split(r"(?<=\})\s+(?=\{)", line)
            for part in parts:
                try:
                    obj = json.loads(part)
                    if isinstance(obj, dict):
                        records.append(obj)
                except json.JSONDecodeError:
                    continue
    return records


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


def norm_page_number(page_id: str) -> int | None:
    m = re.search(r"p(\d{6})$", page_id or "")
    if not m:
        return None
    return int(m.group(1))


def load_page_registry(path: str | Path) -> list[dict[str, Any]]:
    payload = read_json(path, default={})
    if isinstance(payload, dict):
        records = payload.get("records") or payload.get("page_records") or []
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def load_embedding_candidates(path: str | Path | None) -> list[dict[str, Any]]:
    payload = read_json(path, default={})
    if isinstance(payload, dict):
        records = payload.get("records") or []
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
    return []


def page_has_table_signal(page_record: dict[str, Any]) -> bool:
    haystack: list[str] = []
    for key in ("page_traits", "detected_elements", "recommended_extraction_routes", "fishnet_retry_plan"):
        value = page_record.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    haystack.extend(str(v) for v in item.values())
                else:
                    haystack.append(str(item))
        elif value is not None:
            haystack.append(str(value))
    text = " ".join(haystack).lower()
    return any(token in text for token in ("table", "grid", "tile", "parts_list", "list_of_effective", "row", "cell"))


def clean_line(line: str) -> str:
    line = re.sub(r"\[[^\]]+\]", " ", line or "")
    line = line.replace("|", " | ")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def token_type(text: str) -> str:
    if PART_RE.fullmatch(text):
        return "part_number"
    if ATA_RE.fullmatch(text):
        return "ata_code"
    if DATE_RE.fullmatch(text):
        return "date"
    if IPL_RE.fullmatch(text):
        return "ipl_reference"
    if INDEX_LABEL_RE.search(text):
        return "index_label"
    if PAGE_REF_RE.fullmatch(text):
        return "page_reference"
    if re.fullmatch(r"\d+", text):
        return "number"
    return "text"


def recognized_spans(line: str) -> list[tuple[int, int, str, str]]:
    matches: list[tuple[int, int, str, str]] = []
    patterns = [
        ("part_number", PART_RE),
        ("ata_code", ATA_RE),
        ("date", DATE_RE),
        ("ipl_reference", IPL_RE),
        ("index_label", INDEX_LABEL_RE),
        ("page_reference", PAGE_REF_RE),
    ]
    for kind, pattern in patterns:
        for m in pattern.finditer(line):
            matches.append((m.start(), m.end(), m.group(0).strip(), kind))
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    selected: list[tuple[int, int, str, str]] = []
    last_end = -1
    for start, end, text, kind in matches:
        if start < last_end:
            continue
        selected.append((start, end, text, kind))
        last_end = end
    return selected


def split_whitespace_cells(line: str) -> list[tuple[str, str]]:
    if "|" in line:
        parts = [part.strip() for part in line.split("|") if part.strip()]
    else:
        parts = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
    if len(parts) <= 1:
        parts = [part.strip() for part in line.split() if part.strip()]
    return [(part, token_type(part)) for part in parts]


def grab_table_cells_from_text(text: str, *, max_rows: int = 80) -> dict[str, Any]:
    """Conservative OCR-table cell grabber.

    It uses token spans first (part numbers, ATA codes, dates, page refs), then
    whitespace/grid splitting. It intentionally returns confidence metadata so
    weak rows can stay retrieval-only or review-only.
    """
    raw_lines = (text or "").splitlines()
    rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    for raw_idx, raw_line in enumerate(raw_lines[:max_rows]):
        line = clean_line(raw_line)
        if not line:
            continue
        spans = recognized_spans(line)
        cell_items: list[tuple[str, str, int, int | None]] = []
        if spans:
            for start, end, value, kind in spans:
                cell_items.append((value, kind, start, end))
            method = "token_span_cell_grabber_v1"
        else:
            cell_items = [(value, kind, idx, None) for idx, (value, kind) in enumerate(split_whitespace_cells(line))]
            method = "whitespace_grid_cell_grabber_v1"
        if not cell_items:
            continue
        recognized = sum(1 for _, kind, *_ in cell_items if kind != "text")
        confidence = round((recognized / max(len(cell_items), 1)) if cell_items else 0.0, 4)
        row_id = f"row_{len(rows)+1:04d}"
        row_cells: list[str] = []
        for col_index, (value, kind, start, end) in enumerate(cell_items, 1):
            cell_id = f"cell_{len(cells)+1:06d}"
            row_cells.append(cell_id)
            cells.append(
                {
                    "cell_id": cell_id,
                    "row_id": row_id,
                    "source_line_index": raw_idx,
                    "col_index": col_index,
                    "text": value,
                    "normalized_text": re.sub(r"\s+", " ", value).strip(),
                    "token_type": kind,
                    "span_start": start,
                    "span_end": end,
                    "cell_grabber_method": method,
                    "cell_confidence": 1.0 if kind != "text" else 0.35,
                }
            )
        rows.append(
            {
                "row_id": row_id,
                "source_line_index": raw_idx,
                "raw_text": raw_line,
                "clean_text": line,
                "cell_ids": row_cells,
                "cell_count": len(row_cells),
                "recognized_cell_count": recognized,
                "row_confidence": confidence,
                "row_grabber_method": method,
            }
        )
    token_counts = Counter(cell["token_type"] for cell in cells)
    recognized_cells = sum(1 for cell in cells if cell["token_type"] != "text")
    confidence = round(recognized_cells / max(len(cells), 1), 4) if cells else 0.0
    return {
        "rows": rows,
        "cells": cells,
        "row_count": len(rows),
        "cell_count": len(cells),
        "token_type_counts": dict(token_counts),
        "recognized_cell_count": recognized_cells,
        "cell_grabber_confidence": confidence,
        "cell_grabber_algorithm": "trace_net_token_span_plus_whitespace_grid_v1",
    }


def infer_table_type(record: dict[str, Any], cell_result: dict[str, Any]) -> str:
    text = " ".join(
        str(record.get(k, ""))
        for k in ("text", "index_labels", "ata_codes", "canonical_part_numbers", "catalog_supported_part_numbers")
    ).lower()
    token_counts = cell_result.get("token_type_counts", {}) if isinstance(cell_result, dict) else {}
    part_count = len(as_list(record.get("canonical_part_numbers"))) or token_counts.get("part_number", 0)
    date_count = token_counts.get("date", 0)
    ata_count = len(as_list(record.get("ata_codes"))) or token_counts.get("ata_code", 0)
    if "record of revision" in text or ("revision" in text and date_count):
        return "revision_table"
    if "effective" in text or "ipl" in text or date_count >= 3:
        return "list_of_effective_pages"
    if part_count >= 2:
        return "parts_list_table"
    if "vendor" in text:
        return "vendor_table"
    if ata_count:
        return "ata_index_table"
    if token_counts.get("index_label", 0):
        return "index_table"
    return "unknown_table"


def record_source(record: dict[str, Any]) -> dict[str, Any]:
    source_record = record.get("source_record") if isinstance(record.get("source_record"), dict) else {}
    return {
        "source_url": record.get("source_url") or source_record.get("source_url"),
        "ocr_path": record.get("ocr_path") or source_record.get("ocr_path"),
        "tiff_path": record.get("tiff_path") or source_record.get("tiff_path"),
        "tile_path": record.get("tile_path") or source_record.get("tile_path"),
        "tile_id": record.get("tile_id") or source_record.get("tile_id"),
    }


def make_table_citation_id(page_id: str, source: dict[str, Any], table_id: str) -> str:
    seed = {"page_id": page_id, "source_url": source.get("source_url"), "tile_id": source.get("tile_id"), "table_id": table_id}
    return f"cite:table_structured:{page_id}:{stable_hash(seed, 10)}"


def group_refined_records(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        page_id = record.get("page_id")
        if page_id:
            grouped[str(page_id)].append(record)
    return grouped


def aggregate_page_table_text(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records:
        text = record.get("text") or ""
        if text:
            lines.append(str(text))
    return "\n".join(lines)


def candidate_counts_by_page(candidates: list[dict[str, Any]]) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for cand in candidates:
        page_id = cand.get("page_id")
        bucket = cand.get("rag_bucket") or cand.get("safety_bucket") or cand.get("record_type") or "unknown"
        if page_id:
            out[str(page_id)][str(bucket)] += 1
    return out


def make_table_record(
    page_record: dict[str, Any],
    refined_records: list[dict[str, Any]],
    candidate_bucket_counts: Counter,
) -> dict[str, Any]:
    page_id = str(page_record.get("page_id") or "")
    page_number = page_record.get("page_number") or norm_page_number(page_id)
    text = aggregate_page_table_text(refined_records)
    source = record_source(refined_records[0]) if refined_records else {}
    cell_result = grab_table_cells_from_text(text)
    table_type = infer_table_type(refined_records[0] if refined_records else page_record, cell_result)
    trust_tiers = [r.get("classification_trust_tier") or r.get("trust_tier") for r in refined_records]
    trust_tiers = [str(t) for t in trust_tiers if t]
    if "B" in trust_tiers:
        trust_tier = "B"
    elif "A" in trust_tiers:
        trust_tier = "A"
    elif "C" in trust_tiers:
        trust_tier = "C"
    else:
        trust_tier = "route_only"
    table_id = f"table__{page_id}__{stable_hash({'page_id': page_id, 'type': table_type}, 10)}"
    citation_id = make_table_citation_id(page_id, source, table_id) if source.get("source_url") else None
    has_structured_cells = cell_result["cell_count"] > 0
    has_catalog_parts = any(as_list(r.get("catalog_supported_part_numbers")) for r in refined_records)
    rag_bucket = "table_structured_evidence" if has_structured_cells else "table_retrieval_helper"
    if has_catalog_parts:
        rag_bucket = "table_part_catalog_evidence"
    answer_support_candidate = bool(rag_bucket in ANSWER_SUPPORT_BUCKETS and citation_id and trust_tier in {"A", "B"})

    rows = []
    cells = []
    for row in cell_result["rows"]:
        rows.append({**row, "page_id": page_id, "table_id": table_id})
    for cell in cell_result["cells"]:
        cells.append({**cell, "page_id": page_id, "table_id": table_id})

    detected_elements = []
    value = page_record.get("detected_elements")
    if isinstance(value, list):
        detected_elements = value

    return {
        "schema_version": SCHEMA_VERSION,
        "table_understanding_id": f"tblu__{page_id}__{stable_hash({'page_id': page_id, 'text': text[:200]}, 12)}",
        "page_id": page_id,
        "page_number": page_number,
        "table_id": table_id,
        "record_type": "table_understanding_record",
        "table_type": table_type,
        "rag_bucket": rag_bucket,
        "authority": "table_structured_candidate_requires_gate",
        "trust_tier": trust_tier,
        "source": source,
        "citation_id": citation_id,
        "citation_ids": [citation_id] if citation_id else [],
        "source_trace_present": bool(source.get("source_url")),
        "ocr_path_present": bool(source.get("ocr_path")),
        "tile_path_present": bool(source.get("tile_path")),
        "detected_elements_from_registry": detected_elements,
        "candidate_bucket_counts": dict(candidate_bucket_counts),
        "refined_record_count": len(refined_records),
        "refined_tile_ids": [r.get("tile_id") for r in refined_records if r.get("tile_id")],
        "canonical_part_numbers": sorted({p for r in refined_records for p in as_list(r.get("canonical_part_numbers"))}),
        "catalog_supported_part_numbers": sorted({p for r in refined_records for p in as_list(r.get("catalog_supported_part_numbers"))}),
        "ata_codes": sorted({p for r in refined_records for p in as_list(r.get("ata_codes"))}),
        "index_labels": sorted({p for r in refined_records for p in as_list(r.get("index_labels"))}),
        "cell_grabber_algorithm": cell_result["cell_grabber_algorithm"],
        "cell_grabber_confidence": cell_result["cell_grabber_confidence"],
        "row_count": cell_result["row_count"],
        "cell_count": cell_result["cell_count"],
        "token_type_counts": cell_result["token_type_counts"],
        "has_structured_cells": has_structured_cells,
        "rows": rows,
        "cells": cells,
        "table_evidence_role": "answer_support_candidate_after_final_gate" if answer_support_candidate else "retrieval_or_review_only_until_cited_and_gated",
        "answer_support_candidate": answer_support_candidate,
        "can_embed": True,
        "can_retrieve": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "source_truth_mutations_performed": 0,
        "fishnet_retry_plan": build_table_fishnet_plan(has_structured_cells, trust_tier, table_type),
        "comparison_targets": [
            "ocr_text",
            "table_tile_text_refined",
            "part_catalog" if has_catalog_parts else "part_catalog_optional",
            "page_element_registry",
            "source_trace",
            "citation_gate",
            "trust_authority",
        ],
        "graph_attachment_plan": make_graph_attachment_plan(page_id, table_id, rows, cells, citation_id, trust_tier),
    }


def build_table_fishnet_plan(has_cells: bool, trust_tier: str, table_type: str) -> list[dict[str, Any]]:
    plan = [
        {
            "fishnet_layer": 0,
            "layer_name": "use_existing_table_tile_text_refined",
            "retry_route": "none_if_cells_present_else_table_tile_text_retry",
            "needed": not has_cells,
        },
        {
            "fishnet_layer": 1,
            "layer_name": "token_span_plus_whitespace_grid_cell_grabber",
            "retry_route": "row_cell_reconstruction_retry",
            "needed": table_type == "unknown_table" or not has_cells,
        },
        {
            "fishnet_layer": 2,
            "layer_name": "catalog_graph_compare",
            "retry_route": "part_catalog_or_ocr_graph_validation",
            "needed": trust_tier not in {"A", "B"},
        },
        {
            "fishnet_layer": 3,
            "layer_name": "human_review_if_unverified",
            "retry_route": "human_review",
            "needed": trust_tier not in {"A", "B"} or not has_cells,
        },
    ]
    return plan


def make_graph_attachment_plan(
    page_id: str,
    table_id: str,
    rows: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    citation_id: str | None,
    trust_tier: str,
) -> dict[str, Any]:
    edges = [
        {"from": page_id, "edge_type": "HAS_TABLE_ELEMENT", "to": table_id},
        {"from": table_id, "edge_type": "HAS_TRUST_TIER", "to": f"trust_tier:{trust_tier}"},
    ]
    if citation_id:
        edges.append({"from": table_id, "edge_type": "HAS_TABLE_CITATION", "to": citation_id})
    for row in rows[:100]:
        edges.append({"from": table_id, "edge_type": "HAS_TABLE_ROW", "to": row["row_id"]})
    for cell in cells[:300]:
        edges.append({"from": cell["row_id"], "edge_type": "HAS_TABLE_CELL", "to": cell["cell_id"]})
    return {
        "graph_writeback_status": "plan_only_no_postgres_mutation",
        "nodes_to_attach": 1 + len(rows) + len(cells),
        "edges_to_attach": len(edges),
        "sample_edges": edges[:25],
        "can_mutate_source_truth": False,
    }


def summarize(records: list[dict[str, Any]], *, source_summaries: dict[str, Any] | None = None) -> dict[str, Any]:
    source_summaries = source_summaries or {}
    table_types = Counter(r.get("table_type") for r in records)
    buckets = Counter(r.get("rag_bucket") for r in records)
    trust = Counter(r.get("trust_tier") for r in records)
    pages_with_cells = sum(1 for r in records if r.get("has_structured_cells"))
    total_cells = sum(int(r.get("cell_count") or 0) for r in records)
    total_rows = sum(int(r.get("row_count") or 0) for r in records)
    return {
        "schema_version": SCHEMA_VERSION,
        "table_understanding_record_count": len(records),
        "page_count": len({r.get("page_id") for r in records}),
        "pages_with_structured_cells_count": pages_with_cells,
        "table_type_assigned_count": sum(1 for r in records if r.get("table_type") and r.get("table_type") != "unknown_table"),
        "unknown_table_count": table_types.get("unknown_table", 0),
        "table_type_counts": dict(table_types),
        "bucket_counts": dict(buckets),
        "trust_tier_counts": dict(trust),
        "row_count": total_rows,
        "cell_count": total_cells,
        "answer_support_candidate_count": sum(1 for r in records if r.get("answer_support_candidate")),
        "retrieval_only_table_count": sum(1 for r in records if r.get("rag_bucket") in RETRIEVAL_ONLY_BUCKETS),
        "source_trace_table_count": sum(1 for r in records if r.get("source_trace_present")),
        "missing_page_id_count": sum(1 for r in records if not r.get("page_id")),
        "missing_source_trace_count": sum(1 for r in records if not r.get("source_trace_present")),
        "uncited_answer_capable_table_count": sum(1 for r in records if r.get("answer_support_candidate") and not r.get("citation_ids")),
        "retrieval_only_table_answer_allowed_count": sum(1 for r in records if r.get("rag_bucket") in RETRIEVAL_ONLY_BUCKETS and r.get("can_answer_directly")),
        "unsafe_table_evidence_count": count_unsafe_records(records),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("can_mutate_source_truth")),
        "final_answer_allowed_count": sum(1 for r in records if r.get("final_answer_allowed")),
        "llm_freeform_answer_allowed_count": sum(1 for r in records if r.get("llm_freeform_answer_allowed")),
        "cell_grabber_algorithm": "trace_net_token_span_plus_whitespace_grid_v1",
        "source_summaries": source_summaries,
    }


def count_unsafe_records(records: list[dict[str, Any]]) -> int:
    count = 0
    for r in records:
        if r.get("can_mutate_source_truth") is True:
            count += 1
        if r.get("can_answer_directly") is True:
            count += 1
        if r.get("can_prove_claims") is True:
            count += 1
        if r.get("rag_bucket") in RETRIEVAL_ONLY_BUCKETS and r.get("answer_support_candidate"):
            count += 1
    return count


def quality_checks(summary: dict[str, Any], args: argparse.Namespace | None = None) -> tuple[str, list[dict[str, Any]]]:
    args = args or argparse.Namespace()
    def get_arg(name: str, default: Any) -> Any:
        return getattr(args, name, default)
    checks = []
    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    add("table_understanding_records", summary.get("table_understanding_record_count", 0) >= get_arg("min_table_records", 1), f"records={summary.get('table_understanding_record_count', 0)} minimum={get_arg('min_table_records', 1)}")
    add("pages_with_structured_cells", summary.get("pages_with_structured_cells_count", 0) >= get_arg("min_pages_with_structured_cells", 1), f"pages={summary.get('pages_with_structured_cells_count', 0)} minimum={get_arg('min_pages_with_structured_cells', 1)}")
    add("cell_records", summary.get("cell_count", 0) >= get_arg("min_cell_records", 1), f"cells={summary.get('cell_count', 0)} minimum={get_arg('min_cell_records', 1)}")
    add("table_types_assigned", summary.get("table_type_assigned_count", 0) >= get_arg("min_table_types_assigned", 1), f"assigned={summary.get('table_type_assigned_count', 0)} minimum={get_arg('min_table_types_assigned', 1)}")
    add("source_trace_available", summary.get("source_trace_table_count", 0) >= get_arg("min_source_trace_tables", 1), f"source_trace={summary.get('source_trace_table_count', 0)} minimum={get_arg('min_source_trace_tables', 1)}")
    add("missing_page_ids", summary.get("missing_page_id_count", 0) <= get_arg("max_missing_page_id", 0), f"missing={summary.get('missing_page_id_count', 0)} max={get_arg('max_missing_page_id', 0)}")
    add("uncited_answer_capable_tables", summary.get("uncited_answer_capable_table_count", 0) <= get_arg("max_uncited_answer_capable_tables", 0), f"uncited={summary.get('uncited_answer_capable_table_count', 0)} max={get_arg('max_uncited_answer_capable_tables', 0)}")
    add("retrieval_only_answer_allowed", summary.get("retrieval_only_table_answer_allowed_count", 0) <= 0, f"count={summary.get('retrieval_only_table_answer_allowed_count', 0)}")
    add("unsafe_table_evidence", summary.get("unsafe_table_evidence_count", 0) <= 0, f"count={summary.get('unsafe_table_evidence_count', 0)}")
    add("source_truth_mutation_allowed", summary.get("source_truth_mutation_allowed_count", 0) <= 0, f"count={summary.get('source_truth_mutation_allowed_count', 0)}")
    add("final_answer_not_allowed_here", summary.get("final_answer_allowed_count", 0) <= 0, f"count={summary.get('final_answer_allowed_count', 0)}")
    status = "PASS" if all(check["ok"] for check in checks) else "FAIL"
    return status, checks


def build_table_understanding(
    *,
    page_registry_path: str | Path,
    refined_records_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    embedding_candidates_path: str | Path | None = None,
    table_candidate_summary_path: str | Path | None = None,
    table_tile_summary_path: str | Path | None = None,
    refined_summary_path: str | Path | None = None,
    refined_quality_path: str | Path | None = None,
    max_records: int | None = None,
    write_quality: bool = False,
    quality_args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    page_records = load_page_registry(page_registry_path)
    refined_records = read_jsonl(refined_records_path)
    refined_by_page = group_refined_records(refined_records)
    candidate_counts = candidate_counts_by_page(load_embedding_candidates(embedding_candidates_path))

    records: list[dict[str, Any]] = []
    for page_record in page_records:
        page_id = str(page_record.get("page_id") or "")
        if not page_id:
            continue
        table_signal = page_has_table_signal(page_record)
        page_refined = refined_by_page.get(page_id, [])
        if not table_signal and not page_refined:
            continue
        if not page_refined and not table_signal:
            continue
        # Table understanding is most useful when there is refined text. Keep
        # route-only pages only if a registry table signal exists, but cap them
        # by max_records if requested.
        records.append(make_table_record(page_record, page_refined, candidate_counts.get(page_id, Counter())))
        if max_records and len(records) >= max_records:
            break
    # If the registry is conservative and misses a refined page, still include it.
    known_page_ids = {r["page_id"] for r in records}
    registry_by_page = {str(r.get("page_id")): r for r in page_records if r.get("page_id")}
    for page_id, page_refined in sorted(refined_by_page.items()):
        if page_id in known_page_ids:
            continue
        page_record = registry_by_page.get(page_id, {"page_id": page_id, "page_number": norm_page_number(page_id), "detected_elements": []})
        records.append(make_table_record(page_record, page_refined, candidate_counts.get(page_id, Counter())))
        if max_records and len(records) >= max_records:
            break

    source_summaries = {
        "table_candidate_summary": read_json(table_candidate_summary_path, default={}),
        "table_tile_summary": read_json(table_tile_summary_path, default={}),
        "table_tile_text_refined_summary": read_json(refined_summary_path, default={}),
        "table_tile_text_refined_quality": read_json(refined_quality_path, default={}),
    }
    summary = summarize(records, source_summaries=source_summaries)
    quality_status, checks = quality_checks(summary, quality_args)

    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": "TABLE_UNDERSTANDING_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "quality": {"status": quality_status, "checks": checks},
        "records": records,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "trace_net_table_understanding_v1.json"
    records_path = out_dir / "trace_net_table_understanding_v1_records.jsonl"
    rows_path = out_dir / "trace_net_table_understanding_v1_rows.jsonl"
    cells_path = out_dir / "trace_net_table_understanding_v1_cells.jsonl"
    graph_path = out_dir / "trace_net_table_understanding_v1_graph_attachment_plan.jsonl"
    summary_path = out_dir / "trace_net_table_understanding_v1_summary.json"
    manifest_path = out_dir / "trace_net_table_understanding_v1_manifest.json"
    quality_path = out_dir / "trace_net_table_understanding_v1_quality.json"
    md_path = out_dir / "trace_net_table_understanding_v1.md"
    html_path = out_dir / "trace_net_table_understanding_v1.html"

    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(rows_path, [row for record in records for row in record.get("rows", [])])
    write_jsonl(cells_path, [cell for record in records for cell in record.get("cells", [])])
    write_jsonl(graph_path, [{"page_id": r["page_id"], "table_id": r["table_id"], "graph_attachment_plan": r["graph_attachment_plan"]} for r in records])
    write_json(summary_path, summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "rows_path": str(rows_path),
        "cells_path": str(cells_path),
        "graph_attachment_plan_path": str(graph_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_paths": {
            "page_registry": str(page_registry_path),
            "refined_records": str(refined_records_path),
            "embedding_candidates": str(embedding_candidates_path) if embedding_candidates_path else "",
        },
    }
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality_status, "summary": summary, "checks": checks})
    write_markdown(md_path, report)
    html_path.write_text(markdown_to_html(md_path.read_text(encoding="utf-8")), encoding="utf-8")

    report["report_path"] = str(report_path)
    report["records_path"] = str(records_path)
    report["rows_path"] = str(rows_path)
    report["cells_path"] = str(cells_path)
    report["graph_attachment_plan_path"] = str(graph_path)
    report["quality_path"] = str(quality_path)
    return report


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Table Understanding v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "table_understanding_record_count",
        "page_count",
        "pages_with_structured_cells_count",
        "table_type_assigned_count",
        "row_count",
        "cell_count",
        "answer_support_candidate_count",
        "retrieval_only_table_count",
        "unsafe_table_evidence_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines += ["", "## Table types", ""]
    for key, value in sorted((summary.get("table_type_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines += ["", "## Safety contract", "", "- Tables are structured evidence candidates, not direct answers.", "- Retrieval-only table records cannot prove claims.", "- Final answer use still requires citation, source resolution, and authority gate."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def markdown_to_html(markdown_text: str) -> str:
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line else "" for line in markdown_text.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Table Understanding v1</title></head><body>{body}</body></html>"


def check_table_understanding_quality(
    *,
    report_path: str | Path,
    write_json_flag: bool = False,
    quality_args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    report = read_json(report_path, default={})
    summary = report.get("summary") if isinstance(report, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    status, checks = quality_checks(summary, quality_args)
    payload = {"schema_version": SCHEMA_VERSION, "status": status, "summary": summary, "checks": checks}
    if write_json_flag:
        out = Path(report_path).with_name("trace_net_table_understanding_v1_quality.json")
        write_json(out, payload)
        payload["quality_path"] = str(out)
    return payload


def add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-table-records", type=int, default=1)
    parser.add_argument("--min-pages-with-structured-cells", type=int, default=1)
    parser.add_argument("--min-cell-records", type=int, default=1)
    parser.add_argument("--min-table-types-assigned", type=int, default=1)
    parser.add_argument("--min-source-trace-tables", type=int, default=1)
    parser.add_argument("--max-missing-page-id", type=int, default=0)
    parser.add_argument("--max-uncited-answer-capable-tables", type=int, default=0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table understanding v1 artifacts.")
    parser.add_argument("--page-registry", default="local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json")
    parser.add_argument("--table-tile-text-refined-records", default="local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_records.jsonl")
    parser.add_argument("--embedding-candidates", default="local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json")
    parser.add_argument("--table-candidate-summary", default="local_data/organization/table_extraction/all_page_scan/table_candidate_summary.json")
    parser.add_argument("--table-tile-summary", default="local_data/organization/table_extraction/table_tile_summary.json")
    parser.add_argument("--table-tile-text-refined-summary", default="local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_summary.json")
    parser.add_argument("--table-tile-text-refined-quality", default="local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_quality.json")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-records", type=int, default=0)
    parser.add_argument("--quality", action="store_true")
    add_quality_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_table_understanding(
        page_registry_path=args.page_registry,
        refined_records_path=args.table_tile_text_refined_records,
        output_dir=args.output_dir,
        embedding_candidates_path=args.embedding_candidates,
        table_candidate_summary_path=args.table_candidate_summary,
        table_tile_summary_path=args.table_tile_summary,
        refined_summary_path=args.table_tile_text_refined_summary,
        refined_quality_path=args.table_tile_text_refined_quality,
        max_records=args.max_records or None,
        write_quality=args.quality,
        quality_args=args,
    )
    summary = report["summary"]
    print("TRACE-Net table understanding v1")
    print(" Status:", report["status"])
    print(" Quality status:", report["quality_status"])
    for key in [
        "table_understanding_record_count",
        "page_count",
        "pages_with_structured_cells_count",
        "table_type_assigned_count",
        "row_count",
        "cell_count",
        "answer_support_candidate_count",
        "retrieval_only_table_count",
        "unsafe_table_evidence_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}:", summary.get(key))
    print(" report_path:", report.get("report_path"))
    print(" cells_path:", report.get("cells_path"))
    print(" quality_path:", report.get("quality_path"))
    return 0 if report["quality_status"] == "PASS" else 1


def quality_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table understanding v1 quality.")
    parser.add_argument("--report-path", default="local_data/organization/trace_net/table_understanding/trace_net_table_understanding_v1.json")
    parser.add_argument("--write-json", action="store_true")
    add_quality_args(parser)
    return parser


def quality_main(argv: list[str] | None = None) -> int:
    parser = quality_parser()
    args = parser.parse_args(argv)
    payload = check_table_understanding_quality(report_path=args.report_path, write_json_flag=args.write_json, quality_args=args)
    summary = payload["summary"]
    print("TRACE-Net table understanding v1 quality")
    print(" Status:", payload["status"])
    for key in [
        "table_understanding_record_count",
        "page_count",
        "pages_with_structured_cells_count",
        "table_type_assigned_count",
        "row_count",
        "cell_count",
        "answer_support_candidate_count",
        "retrieval_only_table_count",
        "unsafe_table_evidence_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}:", summary.get(key))
    if payload.get("quality_path"):
        print(" quality_path:", payload["quality_path"])
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
