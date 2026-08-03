"""TRACE-Net Table BBox Scoped Cell Extraction v1.

Read-only downstream table consumer that joins existing table row/cell/value
records with the preferred table OCR crop produced by
trace_net_table_ocr_bbox_enrichment_v1. This module does not re-OCR source
images and does not mutate source truth. It creates a downstream-safe bridge
artifact proving that rows/cells/values are scoped to the selected
``table_extraction_bbox`` crop before later extraction/normalization stages use
that evidence.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no direct answer permission
- no claim-proof authority
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_table_bbox_scoped_cell_extraction_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_bbox_scoped_cell_extraction_v1_quality"
STATUS_BUILT = "TABLE_BBOX_SCOPED_CELL_EXTRACTION_BUILT"
STATUS_NOT_READY = "TABLE_BBOX_SCOPED_CELL_EXTRACTION_NOT_READY"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_bbox_scoped_cell_extraction")


BBOX_KEYS = (
    "inferred_table_region_bbox",
    "table_extraction_bbox",
    "selected_table_extraction_bbox",
    "table_extraction_bbox_candidate",
    "table_region_bbox",
    "bbox",
)

SAFETY_FALSE_KEYS = (
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "final_answer_allowed",
    "llm_freeform_answer_allowed",
    "source_truth_mutation_allowed",
    "can_mutate_source_truth",
    "postgres_write_attempted",
    "qdrant_write_attempted",
    "opensearch_write_attempted",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, *parts: Any, length: int = 14) -> str:
    data = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}__{digest}"


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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def first_present(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def normalize_bbox(value: Any) -> dict[str, Any] | None:
    """Return a small normalized bbox mapping or None for invalid inputs."""
    if isinstance(value, Mapping):
        if all(k in value for k in ("x0", "y0", "x1", "y1")):
            x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("x0", "y0", "x1", "y1"))
        elif all(k in value for k in ("left", "top", "right", "bottom")):
            x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("left", "top", "right", "bottom"))
        elif all(k in value for k in ("x", "y", "width", "height")):
            x = as_float(value.get("x"))
            y = as_float(value.get("y"))
            w = as_float(value.get("width"))
            h = as_float(value.get("height"))
            if x is None or y is None or w is None or h is None:
                return None
            x0, y0, x1, y1 = x, y, x + w, y + h
        else:
            return None
    elif isinstance(value, (list, tuple)) and len(value) >= 4:
        x0, y0, x1, y1 = (as_float(v) for v in value[:4])
    else:
        return None
    if None in (x0, y0, x1, y1):
        return None
    assert x0 is not None and y0 is not None and x1 is not None and y1 is not None
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    width = x1 - x0
    height = y1 - y0
    if width <= 1 or height <= 1:
        return None
    return {
        "x0": round(x0, 3),
        "y0": round(y0, 3),
        "x1": round(x1, 3),
        "y1": round(y1, 3),
        "width": round(width, 3),
        "height": round(height, 3),
        "coordinate_system": str(value.get("coordinate_system") or "pixels") if isinstance(value, Mapping) else "pixels",
    }


def load_table_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("records", "table_understanding_records", "tables", "table_records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def load_enrichment_cards(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("table_ocr_bbox_enrichment_cards", "cards", "records", "bbox_enrichment_cards"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def payload_quality_status(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    quality = payload.get("quality")
    if isinstance(quality, Mapping) and quality.get("status"):
        return str(quality.get("status"))
    if payload.get("quality_status"):
        return str(payload.get("quality_status"))
    if payload.get("status") in {"PASS", "FAIL"}:
        return str(payload.get("status"))
    return None


def choose_enrichment_bbox(card: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None, dict[str, Any]]:
    diagnostics = {
        "enrichment_card_id": card.get("ocr_bbox_enrichment_card_id") or card.get("card_id") or card.get("id"),
        "enrichment_bbox_source": card.get("bbox_source"),
        "enrichment_crop_candidate_ready": bool(card.get("crop_candidate_ready")),
        "table_extraction_bbox_preferred": bool(card.get("table_extraction_bbox_preferred")),
        "table_extraction_bbox_source": card.get("table_extraction_bbox_source"),
        "table_extraction_bbox_source_key": card.get("table_extraction_bbox_source_key"),
        "table_extraction_bbox_coverage_ratio": card.get("table_extraction_bbox_coverage_ratio"),
        "ocr_bbox_source": card.get("ocr_bbox_source"),
    }
    if not card.get("crop_candidate_ready"):
        diagnostics["bbox_consume_rejection_reason"] = "enrichment_crop_candidate_not_ready"
        return None, None, diagnostics
    preferred = card.get("table_extraction_bbox_preferred") or card.get("bbox_source") == "table_extraction_bbox_preferred"
    if not preferred:
        diagnostics["bbox_consume_rejection_reason"] = "preferred_table_extraction_bbox_not_selected"
        return None, None, diagnostics
    for key in BBOX_KEYS:
        box = normalize_bbox(card.get(key))
        if box:
            diagnostics["bbox_consume_rejection_reason"] = None
            diagnostics["consumed_bbox_key"] = key
            return box, key, diagnostics
    diagnostics["bbox_consume_rejection_reason"] = "preferred_bbox_missing_or_invalid"
    return None, None, diagnostics


def build_enrichment_indexes(cards: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_table: dict[str, dict[str, Any]] = {}
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        page_id = str(card.get("page_id") or "")
        table_id = str(card.get("table_id") or "")
        if table_id:
            by_table[table_id] = card
        if page_id:
            by_page[page_id].append(card)
    return by_table, by_page


def match_enrichment_card(table_record: Mapping[str, Any], by_table: Mapping[str, dict[str, Any]], by_page: Mapping[str, list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, str]:
    table_id = str(table_record.get("table_id") or "")
    page_id = str(table_record.get("page_id") or "")
    if table_id and table_id in by_table:
        return by_table[table_id], "table_id"
    page_cards = list(by_page.get(page_id, []))
    if len(page_cards) == 1:
        return page_cards[0], "page_id_single_card"
    preferred_cards = [c for c in page_cards if c.get("table_extraction_bbox_preferred") or c.get("bbox_source") == "table_extraction_bbox_preferred"]
    if len(preferred_cards) == 1:
        return preferred_cards[0], "page_id_single_preferred_card"
    if preferred_cards:
        return preferred_cards[0], "page_id_first_preferred_card"
    if page_cards:
        return page_cards[0], "page_id_first_card"
    return None, "no_match"


def make_scoped_value_records(record: Mapping[str, Any], scope_id: str, box: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    page_id = str(record.get("page_id") or "")
    table_id = str(record.get("table_id") or "")
    out: list[dict[str, Any]] = []
    for cell in as_list(record.get("cells")):
        if not isinstance(cell, Mapping):
            continue
        cell_id = str(cell.get("cell_id") or stable_id("cell", page_id, table_id, len(out)))
        value = cell.get("normalized_text") if cell.get("normalized_text") not in (None, "") else cell.get("text")
        out.append({
            "schema_version": SCHEMA_VERSION,
            "value_record_id": stable_id("bbox_scoped_value", page_id, table_id, cell_id, value),
            "page_id": page_id,
            "table_id": table_id,
            "row_id": cell.get("row_id"),
            "cell_id": cell_id,
            "col_index": cell.get("col_index"),
            "text": cell.get("text"),
            "normalized_text": value,
            "token_type": cell.get("token_type"),
            "source_line_index": cell.get("source_line_index"),
            "cell_confidence": cell.get("cell_confidence"),
            "table_bbox_scope_id": scope_id,
            "table_extraction_bbox": dict(box) if box else None,
            "bbox_scoped_extraction_ready": bool(box),
            "record_role": "bbox_scoped_table_cell_value_candidate",
            "retrieval_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "can_mutate_source_truth": False,
        })
    return out


def make_scoped_record(table_record: Mapping[str, Any], enrichment_card: Mapping[str, Any] | None, match_method: str) -> dict[str, Any]:
    page_id = str(table_record.get("page_id") or "")
    table_id = str(table_record.get("table_id") or "")
    table_type = table_record.get("table_type")
    box = None
    consumed_key = None
    diagnostics: dict[str, Any] = {"bbox_consume_rejection_reason": "no_enrichment_card"}
    if enrichment_card:
        box, consumed_key, diagnostics = choose_enrichment_bbox(enrichment_card)
    bbox_consumed = box is not None
    scope_id = stable_id("table_bbox_scope", page_id, table_id, consumed_key, box)
    rows = []
    for row in as_list(table_record.get("rows")):
        if not isinstance(row, Mapping):
            continue
        rows.append({
            **dict(row),
            "table_bbox_scope_id": scope_id,
            "table_extraction_bbox": dict(box) if box else None,
            "bbox_scoped_extraction_ready": bbox_consumed,
            "row_cell_extraction_scope": "table_extraction_bbox_crop" if bbox_consumed else "unscoped_page_or_legacy_crop",
        })
    cells = []
    for cell in as_list(table_record.get("cells")):
        if not isinstance(cell, Mapping):
            continue
        cells.append({
            **dict(cell),
            "table_bbox_scope_id": scope_id,
            "table_extraction_bbox": dict(box) if box else None,
            "bbox_scoped_extraction_ready": bbox_consumed,
            "row_cell_extraction_scope": "table_extraction_bbox_crop" if bbox_consumed else "unscoped_page_or_legacy_crop",
        })
    value_records = make_scoped_value_records({**dict(table_record), "cells": cells}, scope_id, box)
    review_flags = []
    if not enrichment_card:
        review_flags.append("missing_table_ocr_bbox_enrichment_card")
    if enrichment_card and not bbox_consumed:
        review_flags.append("preferred_table_extraction_bbox_not_consumed")
    if not rows:
        review_flags.append("source_table_record_has_no_rows")
    if not cells:
        review_flags.append("source_table_record_has_no_cells")
    return {
        "schema_version": SCHEMA_VERSION,
        "scoped_table_record_id": stable_id("bbox_scoped_table", page_id, table_id, scope_id),
        "page_id": page_id,
        "table_id": table_id,
        "source_table_understanding_id": table_record.get("table_understanding_id") or table_record.get("id"),
        "source_table_type": table_type,
        "source_rag_bucket": table_record.get("rag_bucket"),
        "source_trust_tier": table_record.get("trust_tier"),
        "source_citation_ids": table_record.get("citation_ids") or [],
        "bbox_match_method": match_method,
        "bbox_consumed_by_row_cell_extraction": bbox_consumed,
        "bbox_scoped_extraction_ready": bbox_consumed,
        "row_cell_extraction_scope": "table_extraction_bbox_crop" if bbox_consumed else "unscoped_page_or_legacy_crop",
        "table_bbox_scope_id": scope_id,
        "table_extraction_bbox": dict(box) if box else None,
        "table_extraction_bbox_source": diagnostics.get("table_extraction_bbox_source"),
        "table_extraction_bbox_source_key": diagnostics.get("table_extraction_bbox_source_key"),
        "consumed_bbox_key": consumed_key,
        "bbox_source": "table_ocr_bbox_enrichment_preferred_table_extraction_bbox" if bbox_consumed else "unresolved",
        "enrichment_card_id": diagnostics.get("enrichment_card_id"),
        "enrichment_bbox_source": diagnostics.get("enrichment_bbox_source"),
        "ocr_bbox_source": diagnostics.get("ocr_bbox_source"),
        "table_extraction_bbox_coverage_ratio": diagnostics.get("table_extraction_bbox_coverage_ratio"),
        "bbox_consume_rejection_reason": diagnostics.get("bbox_consume_rejection_reason"),
        "source_row_count": len(as_list(table_record.get("rows"))),
        "source_cell_count": len(as_list(table_record.get("cells"))),
        "scoped_row_count": len(rows),
        "scoped_cell_count": len(cells),
        "scoped_value_record_count": len(value_records),
        "rows": rows,
        "cells": cells,
        "value_records": value_records,
        "review_required": bool(review_flags),
        "review_flags": review_flags,
        "recommended_next_actions": [
            "feed_bbox_scoped_cells_to_table_cell_normalization_or_row_reconstruction" if bbox_consumed else "inspect_missing_or_invalid_table_extraction_bbox_before_normalization"
        ],
        "record_role": "downstream_table_row_cell_value_bbox_scope_bridge",
        "retrieval_only": True,
        "routing_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "can_mutate_source_truth": False,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
    }


def unsafe_record_count(records: list[Mapping[str, Any]]) -> int:
    count = 0
    for record in records:
        for key in SAFETY_FALSE_KEYS:
            if record.get(key) is True:
                count += 1
                break
    return count


def summarize(
    scoped_records: list[dict[str, Any]],
    *,
    all_records: list[dict[str, Any]] | None = None,
    table_payload: Any = None,
    enrichment_payload: Any = None,
    source_table_record_count: int | None = None,
) -> dict[str, Any]:
    """Summarize only bbox-scoped records while preserving source coverage counts.

    ``table_understanding`` can contain legacy/non-route table-like records beyond
    the 20 table-route geometry cards that have ``table_extraction_bbox`` evidence.
    The strict bbox-scoped PASS gate should apply to the bbox target set only, not
    to every historical table-understanding record. This keeps the bridge honest:
    it proves 20 routed tables are crop-scoped and reports the remaining records as
    legacy pass-through candidates instead of pretending they consumed a bbox.
    """
    all_records = all_records or scoped_records
    source_count = int(source_table_record_count if source_table_record_count is not None else len(all_records))
    source_rows = sum(int(r.get("source_row_count") or 0) for r in all_records)
    source_cells = sum(int(r.get("source_cell_count") or 0) for r in all_records)
    scoped_rows = sum(int(r.get("scoped_row_count") or 0) for r in scoped_records)
    scoped_cells = sum(int(r.get("scoped_cell_count") or 0) for r in scoped_records)
    value_records = sum(int(r.get("scoped_value_record_count") or 0) for r in scoped_records)
    consumed = sum(1 for r in scoped_records if r.get("bbox_consumed_by_row_cell_extraction"))
    target_records = [r for r in all_records if r.get("enrichment_card_id")]
    target_count = len(target_records)
    target_missing_or_invalid = sum(1 for r in target_records if not r.get("bbox_consumed_by_row_cell_extraction"))
    legacy_unscoped = sum(1 for r in all_records if not r.get("enrichment_card_id"))
    return {
        "schema_version": SCHEMA_VERSION,
        "source_table_understanding_quality_status": payload_quality_status(table_payload),
        "source_table_ocr_bbox_enrichment_quality_status": payload_quality_status(enrichment_payload),
        "source_table_record_count": source_count,
        "source_page_count": len({r.get("page_id") for r in all_records if r.get("page_id")}),
        "bbox_scope_target_record_count": target_count,
        "legacy_unscoped_table_record_count": legacy_unscoped,
        "scoped_table_record_count": len(scoped_records),
        "page_count": len({r.get("page_id") for r in scoped_records if r.get("page_id")}),
        "scoped_page_count": len({r.get("page_id") for r in scoped_records if r.get("page_id")}),
        "source_row_count": source_rows,
        "source_cell_count": source_cells,
        "scoped_row_count": scoped_rows,
        "scoped_cell_count": scoped_cells,
        "scoped_value_record_count": value_records,
        "table_extraction_bbox_available_record_count": target_count,
        "table_extraction_bbox_consumed_record_count": consumed,
        "table_extraction_bbox_missing_or_invalid_record_count": target_missing_or_invalid,
        "bbox_scoped_extraction_ready_record_count": sum(1 for r in scoped_records if r.get("bbox_scoped_extraction_ready")),
        "bbox_match_method_counts": dict(Counter(r.get("bbox_match_method") for r in scoped_records)),
        "bbox_source_counts": dict(Counter(r.get("bbox_source") for r in scoped_records)),
        "row_cell_extraction_scope_counts": dict(Counter(r.get("row_cell_extraction_scope") for r in scoped_records)),
        "legacy_unscoped_match_method_counts": dict(Counter(r.get("bbox_match_method") for r in all_records if not r.get("bbox_consumed_by_row_cell_extraction"))),
        "review_required_record_count": sum(1 for r in scoped_records if r.get("review_required")),
        "unsafe_scoped_table_record_count": unsafe_record_count(scoped_records),
        "answer_permission_count": sum(1 for r in scoped_records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in scoped_records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in scoped_records if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in scoped_records if r.get("source_truth_mutation_allowed") or r.get("can_mutate_source_truth")),
        "postgres_write_attempt_count": sum(1 for r in scoped_records if r.get("postgres_write_attempted")),
        "qdrant_write_attempt_count": sum(1 for r in scoped_records if r.get("qdrant_write_attempted")),
        "opensearch_write_attempt_count": sum(1 for r in scoped_records if r.get("opensearch_write_attempted")),
    }


def quality_checks(summary: Mapping[str, Any], thresholds: Mapping[str, Any] | argparse.Namespace | None = None) -> tuple[str, list[dict[str, Any]]]:
    thresholds = thresholds or {}

    def get(name: str, default: Any) -> Any:
        if isinstance(thresholds, Mapping):
            return thresholds.get(name, default)
        return getattr(thresholds, name, default)

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("source_table_records", summary.get("source_table_record_count", 0) >= get("min_source_table_records", 1), f"records={summary.get('source_table_record_count', 0)} minimum={get('min_source_table_records', 1)}")
    add("scoped_table_records", summary.get("scoped_table_record_count", 0) >= get("min_scoped_table_records", 1), f"records={summary.get('scoped_table_record_count', 0)} minimum={get('min_scoped_table_records', 1)}")
    add("bbox_consumed_records", summary.get("table_extraction_bbox_consumed_record_count", 0) >= get("min_bbox_consumed_records", 1), f"consumed={summary.get('table_extraction_bbox_consumed_record_count', 0)} minimum={get('min_bbox_consumed_records', 1)}")
    add("scoped_cell_records", summary.get("scoped_cell_count", 0) >= get("min_scoped_cells", 1), f"cells={summary.get('scoped_cell_count', 0)} minimum={get('min_scoped_cells', 1)}")
    add("scoped_value_records", summary.get("scoped_value_record_count", 0) >= get("min_scoped_value_records", 1), f"values={summary.get('scoped_value_record_count', 0)} minimum={get('min_scoped_value_records', 1)}")
    add("unsafe_scoped_table_records", summary.get("unsafe_scoped_table_record_count", 0) <= get("max_unsafe_scoped_table_records", 0), f"unsafe={summary.get('unsafe_scoped_table_record_count', 0)} max={get('max_unsafe_scoped_table_records', 0)}")
    add("answer_permission", summary.get("answer_permission_count", 0) <= get("max_answer_permission_count", 0), f"count={summary.get('answer_permission_count', 0)} max={get('max_answer_permission_count', 0)}")
    add("source_truth_mutation_allowed", summary.get("source_truth_mutation_allowed_count", 0) <= get("max_source_truth_mutation_allowed", 0), f"count={summary.get('source_truth_mutation_allowed_count', 0)} max={get('max_source_truth_mutation_allowed', 0)}")
    add("postgres_writes", summary.get("postgres_write_attempt_count", 0) == 0, f"count={summary.get('postgres_write_attempt_count', 0)}")
    add("qdrant_writes", summary.get("qdrant_write_attempt_count", 0) == 0, f"count={summary.get('qdrant_write_attempt_count', 0)}")
    add("opensearch_writes", summary.get("opensearch_write_attempt_count", 0) == 0, f"count={summary.get('opensearch_write_attempt_count', 0)}")
    if get("require_table_understanding_quality_pass", False):
        add("source_table_understanding_quality_pass", summary.get("source_table_understanding_quality_status") == "PASS", f"status={summary.get('source_table_understanding_quality_status')}")
    if get("require_table_ocr_bbox_enrichment_quality_pass", False):
        add("source_table_ocr_bbox_enrichment_quality_pass", summary.get("source_table_ocr_bbox_enrichment_quality_status") == "PASS", f"status={summary.get('source_table_ocr_bbox_enrichment_quality_status')}")
    if get("require_all_records_bbox_scoped", False):
        add("all_bbox_target_records_scoped", summary.get("table_extraction_bbox_missing_or_invalid_record_count", 0) == 0, f"target_missing_or_invalid={summary.get('table_extraction_bbox_missing_or_invalid_record_count', 0)} target_records={summary.get('bbox_scope_target_record_count', 0)} legacy_unscoped={summary.get('legacy_unscoped_table_record_count', 0)}")
    status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    return status, checks


def build_report(
    *,
    table_understanding_path: str | Path,
    table_ocr_bbox_enrichment_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    thresholds: Mapping[str, Any] | argparse.Namespace | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    table_payload = read_json(table_understanding_path, default={})
    enrichment_payload = read_json(table_ocr_bbox_enrichment_path, default={})
    table_records = load_table_records(table_payload)
    enrichment_cards = load_enrichment_cards(enrichment_payload)
    by_table, by_page = build_enrichment_indexes(enrichment_cards)
    all_records = []
    scoped_records = []
    legacy_unscoped_records = []
    for record in table_records:
        card, match_method = match_enrichment_card(record, by_table, by_page)
        scoped_record = make_scoped_record(record, card, match_method)
        all_records.append(scoped_record)
        if scoped_record.get("bbox_consumed_by_row_cell_extraction"):
            scoped_records.append(scoped_record)
        else:
            legacy_unscoped_records.append(scoped_record)
    summary = summarize(
        scoped_records,
        all_records=all_records,
        table_payload=table_payload,
        enrichment_payload=enrichment_payload,
        source_table_record_count=len(table_records),
    )
    quality_status, checks = quality_checks(summary, thresholds)
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "quality": {"schema_version": QUALITY_SCHEMA_VERSION, "status": quality_status, "checks": checks},
        "scoped_table_records": scoped_records,
        "legacy_unscoped_table_record_count": len(legacy_unscoped_records),
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_table_bbox_scoped_cell_extraction_v1.json"
    records_path = out / "trace_net_table_bbox_scoped_cell_extraction_v1_records.jsonl"
    values_path = out / "trace_net_table_bbox_scoped_cell_extraction_v1_values.jsonl"
    legacy_path = out / "trace_net_table_bbox_scoped_cell_extraction_v1_legacy_unscoped_records.jsonl"
    summary_path = out / "trace_net_table_bbox_scoped_cell_extraction_v1_summary.json"
    quality_path = out / "trace_net_table_bbox_scoped_cell_extraction_v1_quality.json"
    manifest_path = out / "trace_net_table_bbox_scoped_cell_extraction_v1_manifest.json"
    write_json(report_path, report)
    write_jsonl(records_path, scoped_records)
    write_jsonl(values_path, [value for record in scoped_records for value in record.get("value_records", [])])
    write_jsonl(legacy_path, legacy_unscoped_records)
    write_json(summary_path, summary)
    if write_quality:
        write_json(quality_path, {"schema_version": QUALITY_SCHEMA_VERSION, "status": quality_status, "summary": summary, "checks": checks})
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "values_path": str(values_path),
        "legacy_unscoped_records_path": str(legacy_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_paths": {
            "table_understanding": str(table_understanding_path),
            "table_ocr_bbox_enrichment": str(table_ocr_bbox_enrichment_path),
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
        },
    })
    report["report_path"] = str(report_path)
    report["records_path"] = str(records_path)
    report["values_path"] = str(values_path)
    report["legacy_unscoped_records_path"] = str(legacy_path)
    report["quality_path"] = str(quality_path)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net table bbox scoped cell extraction v1 artifacts.")
    p.add_argument("--table-understanding", required=True)
    p.add_argument("--table-ocr-bbox-enrichment", required=True)
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--min-source-table-records", type=int, default=1)
    p.add_argument("--min-scoped-table-records", type=int, default=1)
    p.add_argument("--min-bbox-consumed-records", type=int, default=1)
    p.add_argument("--min-scoped-cells", type=int, default=1)
    p.add_argument("--min-scoped-value-records", type=int, default=1)
    p.add_argument("--max-unsafe-scoped-table-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-table-understanding-quality-pass", action="store_true")
    p.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    p.add_argument("--require-all-records-bbox-scoped", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_report(
        table_understanding_path=args.table_understanding,
        table_ocr_bbox_enrichment_path=args.table_ocr_bbox_enrichment,
        output_dir=args.output_dir,
        thresholds=args,
        write_quality=args.quality,
    )
    summary = report.get("summary", {})
    print("TRACE-Net Table BBox Scoped Cell Extraction v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "source_table_record_count",
        "source_page_count",
        "bbox_scope_target_record_count",
        "legacy_unscoped_table_record_count",
        "scoped_table_record_count",
        "page_count",
        "scoped_row_count",
        "scoped_cell_count",
        "scoped_value_record_count",
        "table_extraction_bbox_consumed_record_count",
        "table_extraction_bbox_missing_or_invalid_record_count",
        "bbox_scoped_extraction_ready_record_count",
        "unsafe_scoped_table_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
