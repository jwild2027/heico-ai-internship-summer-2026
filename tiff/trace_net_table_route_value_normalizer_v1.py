"""TRACE-Net Table Route Value Normalizer v1.

Converts table-route cell extractor values into fielded, source-traceable
retrieval/evidence records. This module is intentionally read-only and does not
write to Postgres, Qdrant, OpenSearch, or any source-truth artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_table_route_value_normalizer_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_route_value_normalizer_v1_quality"
STATUS_BUILT = "TABLE_ROUTE_VALUE_NORMALIZER_BUILT"
STATUS_SKIPPED = "TABLE_ROUTE_VALUE_NORMALIZATION_SKIPPED"

PART_NUMBER_RE = re.compile(r"\b\d{2,3}-\d{2,5}(?:-\d{2,4})?\b")
PAGE_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}(?:-\d{1,4})?\b")
# LEP rows are often OCR-tokenized into fragments such as ``25-21 -00- 103``.
# This relaxed pattern lets the normalizer rebuild page references at row level.
RELAXED_PAGE_REF_RE = re.compile(r"(?<!\d)(\d{2}\s*-\s*\d{2}\s*-\s*\d{2}(?:\s*-\s*\d{1,4})?)(?!\d)")
NUMERIC_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
LEP_REV_OR_SEQ_RE = re.compile(r"^(?:REV\.?\s*)?[A-Z0-9]{1,4}$", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n")


def stable_id(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8", "ignore"))
        h.update(b"\x1f")
    return f"{prefix}__{h.hexdigest()[:16]}"


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split())


def normalize_part_number(value: str) -> str:
    text = normalize_text(value).upper()
    # Strip common OCR/context prefixes while preserving the true part number.
    m = PART_NUMBER_RE.search(text)
    return m.group(0) if m else text


def normalize_page_reference(value: str) -> str:
    text = normalize_text(value).upper()
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    m = PAGE_REF_RE.search(text)
    return m.group(0) if m else text


def compact_lep_reference_text(text: str) -> str:
    """Return text compacted for fragmented LEP page-reference matching.

    OCR often splits manual page references across adjacent cells or even inside
    one token, for example ``25-2 1-00-92`` or ``25-21 -00- 103``.  The
    normalizer should not treat those fragments as context; it should rebuild
    the page reference from row geometry.
    """
    compact = normalize_text(text).upper()
    compact = re.sub(r"\s+", "", compact)
    compact = compact.replace("–", "-").replace("—", "-").replace("−", "-")
    compact = re.sub(r"-+", "-", compact)
    return compact


def keep_most_specific_page_refs(refs: Sequence[str]) -> list[str]:
    unique: list[str] = []
    for ref in refs:
        if ref not in unique:
            unique.append(ref)
    return [ref for ref in unique if not any(other != ref and other.startswith(ref + "-") for other in unique)]


def extract_lep_page_references_from_text(text: str) -> list[str]:
    refs: list[str] = []
    candidates = [normalize_text(text).upper(), compact_lep_reference_text(text)]
    for candidate in candidates:
        if not candidate:
            continue
        for match in RELAXED_PAGE_REF_RE.finditer(candidate):
            ref = normalize_page_reference(match.group(1))
            if PAGE_REF_RE.fullmatch(ref) and ref not in refs:
                refs.append(ref)
        for match in PAGE_REF_RE.finditer(candidate):
            ref = normalize_page_reference(match.group(0))
            if PAGE_REF_RE.fullmatch(ref) and ref not in refs:
                refs.append(ref)
    return keep_most_specific_page_refs(refs)


def extract_lep_page_references_from_row_values(row_values: Sequence[Mapping[str, Any]]) -> list[str]:
    """Extract LEP page references using token/cell order rather than one cell.

    This is version A of the LEP fix: strengthen parsing from token positions.
    It looks at individual cells, row text, and compact sliding windows of
    adjacent cell texts so split forms like ``25-21`` + ``-00-`` + ``103`` and
    ``25-2`` + ``1-00-92`` become valid page references.
    """
    ordered = sorted(
        row_values,
        key=lambda v: (v.get("column_index") if v.get("column_index") is not None else 9999, str(v.get("cell_id") or "")),
    )
    texts = [normalize_text(v.get("normalized_value") or v.get("value_text")) for v in ordered]
    texts = [t for t in texts if t]
    refs: list[str] = []

    def add_from(text: str) -> None:
        for ref in extract_lep_page_references_from_text(text):
            if ref not in refs:
                refs.append(ref)

    for text in texts:
        add_from(text)
    add_from(" ".join(texts))

    # Sliding compact windows are important when OCR puts the chapter prefix,
    # section/unit, and page number into neighboring cells.
    for start in range(len(texts)):
        combined = ""
        for end in range(start, min(len(texts), start + 6)):
            combined += compact_lep_reference_text(texts[end])
            add_from(combined)

    return keep_most_specific_page_refs(refs)


def is_probably_lep_header_or_title(text: str) -> bool:
    upper = normalize_text(text).upper()
    if not upper:
        return False
    header_terms = (
        "LIST OF EFFECTIVE",
        "PAGE",
        "DATE",
        "REV",
        "REVISION",
        "TEMPORARY REVISION",
        "EFFECTIVE PAGES",
    )
    return any(term in upper for term in header_terms)


def classify_normalized_field(value: Mapping[str, Any]) -> tuple[str | None, str | None, str, float, list[str]]:
    """Return (field_name, normalized_value, evidence_kind, confidence, flags)."""
    template = str(value.get("table_template_type") or "unknown_table_template")
    role = str(value.get("template_value_role") or "unassigned")
    kind = str(value.get("value_kind") or "text")
    raw_text = normalize_text(value.get("normalized_value") or value.get("value_text"))
    part_candidates = [normalize_part_number(p) for p in (value.get("part_number_candidates") or []) if normalize_text(p)]
    part_candidates = [p for p in part_candidates if PART_NUMBER_RE.fullmatch(p)]
    flags: list[str] = []

    if not raw_text:
        return None, None, "empty", 0.0, ["empty_value_skipped"]

    if template == "part_number_coverage_list":
        if role == "covered_part_number" or part_candidates:
            part = part_candidates[0] if part_candidates else normalize_part_number(raw_text)
            if PART_NUMBER_RE.fullmatch(part):
                return "covered_part_number", part, "part_number", 0.96, flags
        if role in {"part_number_list_context", "part_number_list_other", "table_title"}:
            return "part_number_coverage_context", raw_text, "context", 0.55, ["context_record"]
        return None, None, "unmapped_part_number_coverage_value", 0.0, ["unmapped_template_value"]

    if template == "list_of_effective_pages":
        page_refs = extract_lep_page_references_from_text(raw_text)
        if role == "manual_page_reference" or page_refs:
            return "manual_page_reference", page_refs[0] if page_refs else normalize_page_reference(raw_text), "manual_page_reference", 0.88, flags
        if role == "page_rev_or_sequence_value" or (role not in {"lep_other", "header"} and kind in {"numeric", "short_code"}):
            return "page_rev_or_sequence_value", raw_text, "lep_sequence_or_revision", 0.76, flags
        # Keep only genuine LEP title/header context.  Many body fragments arrived
        # from the extractor with role=header, which caused >1k noisy LEP context
        # values.  Body rows are now handled by row-level reconstruction below.
        if role in {"header", "table_title"} or is_probably_lep_header_or_title(raw_text):
            upper = raw_text.upper()
            if "LIST OF EFFECTIVE" in upper or "EFFECTIVE PAGES" in upper or "TEMPORARY REVISION" in upper:
                return "lep_context", raw_text, "context", 0.50, ["context_record"]
            return None, None, "suppressed_lep_header_or_body_context", 0.0, ["lep_body_context_suppressed"]
        if role == "lep_other":
            return None, None, "suppressed_lep_body_context", 0.0, ["lep_body_context_suppressed"]
        return None, None, "unmapped_list_effective_pages_value", 0.0, ["unmapped_template_value"]

    if template == "ipl_split_column_table":
        if role == "part_number" or part_candidates:
            part = part_candidates[0] if part_candidates else normalize_part_number(raw_text)
            if PART_NUMBER_RE.fullmatch(part):
                return "ipl_part_number", part, "part_number", 0.90, flags
        if role == "fig_item_or_quantity":
            if NUMERIC_RE.fullmatch(raw_text):
                return "ipl_figure_item_or_quantity", raw_text, "numeric", 0.72, flags
            return "ipl_figure_item_or_quantity", raw_text, "short_code", 0.62, flags
        if role == "ipl_text":
            return "ipl_text", raw_text, "text", 0.62, flags
        if role in {"ipl_header_or_metadata", "header", "table_title"}:
            return "ipl_context", raw_text, "context", 0.50, ["context_record"]
        return None, None, "unmapped_ipl_value", 0.0, ["unmapped_template_value"]

    if template == "generic_table":
        if part_candidates:
            return "generic_part_number", part_candidates[0], "part_number", 0.70, ["generic_template"]
        return "generic_table_value", raw_text, kind, 0.45, ["generic_template"]

    return None, None, "unknown_template_value", 0.0, ["unknown_template_skipped"]


def build_normalized_records(source_report: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source_records = source_report.get("table_route_cell_extraction_records") or []
    source_values = source_report.get("table_route_value_records") or []
    extraction_by_table = {r.get("table_id"): r for r in source_records if isinstance(r, Mapping)}

    normalizer_records: list[dict[str, Any]] = []
    normalized_values: list[dict[str, Any]] = []
    skipped_review_only = 0
    skipped_unmapped = 0
    skipped_unknown_template = 0
    lep_context_suppressed = 0
    lep_row_derived_manual_refs = 0
    lep_row_derived_sequence_values = 0

    tables_seen: dict[Any, dict[str, Any]] = {}

    for record in source_records:
        if not isinstance(record, Mapping):
            continue
        table_id = record.get("table_id")
        allowed = bool(record.get("table_extraction_allowed")) and not bool(record.get("table_bbox_review_only"))
        if not allowed:
            skipped_review_only += 1 if record.get("table_bbox_review_only") else 0
        tables_seen[table_id] = {
            "table_id": table_id,
            "page_id": record.get("page_id"),
            "table_template_type": record.get("table_template_type") or "unknown_table_template",
            "table_template_confidence": record.get("table_template_confidence"),
            "table_extraction_allowed": allowed,
            "table_bbox_review_only": bool(record.get("table_bbox_review_only")),
            "source_value_count": 0,
            "normalized_value_count": 0,
            "status": STATUS_BUILT if allowed else STATUS_SKIPPED,
            "review_flags": list(record.get("review_flags") or []),
            "retrieval_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempted": False,
            "qdrant_write_attempted": False,
            "opensearch_write_attempted": False,
            "unsafe_table_route_value_normalization": False,
        }

    lep_rows: dict[tuple[Any, Any], list[Mapping[str, Any]]] = {}
    for value in source_values:
        if not isinstance(value, Mapping):
            continue
        if str(value.get("table_template_type") or "") == "list_of_effective_pages":
            lep_rows.setdefault((value.get("table_id"), value.get("row_index")), []).append(value)

    seen_field_keys: set[tuple[Any, str, str, Any, Any]] = set()
    for value in source_values:
        if not isinstance(value, Mapping):
            continue
        table_id = value.get("table_id")
        table_meta = tables_seen.get(table_id) or {}
        if table_id in tables_seen:
            tables_seen[table_id]["source_value_count"] += 1
        source_record = extraction_by_table.get(table_id) or {}
        if source_record.get("table_bbox_review_only") or not source_record.get("table_extraction_allowed", True):
            continue
        field_name, normalized_value, evidence_kind, confidence, flags = classify_normalized_field(value)
        if not field_name or normalized_value is None:
            skipped_unmapped += 1
            if "unknown_template_skipped" in flags:
                skipped_unknown_template += 1
            if "lep_body_context_suppressed" in flags:
                lep_context_suppressed += 1
            continue
        # Deduplicate exact normalized field values within a table/row/column while preserving source trace.
        key = (table_id, field_name, normalized_value, value.get("row_index"), value.get("column_index"))
        if key in seen_field_keys:
            skipped_unmapped += 1
            continue
        seen_field_keys.add(key)
        normalized_id = stable_id("table_route_normalized_value", table_id, value.get("cell_id"), field_name, normalized_value)
        out = {
            "normalized_value_record_id": normalized_id,
            "schema_version": SCHEMA_VERSION,
            "source_value_record_id": value.get("value_record_id"),
            "source_cell_id": value.get("cell_id"),
            "source_row_id": value.get("row_id"),
            "page_id": value.get("page_id"),
            "table_id": table_id,
            "table_template_type": value.get("table_template_type") or table_meta.get("table_template_type"),
            "table_template_confidence": table_meta.get("table_template_confidence"),
            "source_template_value_role": value.get("template_value_role"),
            "source_value_kind": value.get("value_kind"),
            "field_name": field_name,
            "normalized_value": normalized_value,
            "raw_value_text": normalize_text(value.get("value_text") or value.get("normalized_value")),
            "evidence_kind": evidence_kind,
            "normalization_confidence": confidence,
            "row_index": value.get("row_index"),
            "column_index": value.get("column_index"),
            "cell_bbox": value.get("cell_bbox"),
            "part_number_candidates": value.get("part_number_candidates") or [],
            "normalization_flags": flags,
            "source_trace": {
                "source_module": "trace_net_table_route_cell_extractor_v1",
                "source_report_schema_version": source_report.get("schema_version"),
                "source_report_status": source_report.get("status"),
                "source_value_record_id": value.get("value_record_id"),
                "source_cell_id": value.get("cell_id"),
                "page_id": value.get("page_id"),
                "table_id": table_id,
            },
            "retrieval_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempted": False,
            "qdrant_write_attempted": False,
            "opensearch_write_attempted": False,
            "unsafe_table_route_normalized_value": False,
        }
        normalized_values.append(out)
        if table_id in tables_seen:
            tables_seen[table_id]["normalized_value_count"] += 1



    # LIST OF EFFECTIVE PAGES rows often arrive from OCR as multiple small cells
    # with page references split across tokens.  Rebuild useful LEP fields from
    # the whole row instead of preserving every fragment as noisy context.
    for (table_id, row_index), row_values in sorted(lep_rows.items(), key=lambda item: (str(item[0][0]), item[0][1] if item[0][1] is not None else -1)):
        source_record = extraction_by_table.get(table_id) or {}
        if source_record.get("table_bbox_review_only") or not source_record.get("table_extraction_allowed", True):
            continue
        table_meta = tables_seen.get(table_id) or {}
        if table_meta.get("table_template_type") != "list_of_effective_pages":
            continue
        ordered = sorted(row_values, key=lambda v: (v.get("column_index") if v.get("column_index") is not None else 9999, str(v.get("cell_id") or "")))
        row_text = normalize_text(" ".join(normalize_text(v.get("normalized_value") or v.get("value_text")) for v in ordered))
        if not row_text:
            continue
        row_refs = extract_lep_page_references_from_row_values(ordered)
        if not row_refs:
            continue
        row_value_ids = [v.get("value_record_id") for v in ordered if v.get("value_record_id")]
        first_value = ordered[0] if ordered else {}

        def find_existing_row_value(field_name: str, normalized_value: str) -> dict[str, Any] | None:
            for record in normalized_values:
                if (
                    record.get("table_id") == table_id
                    and record.get("row_index") == row_index
                    and record.get("field_name") == field_name
                    and record.get("normalized_value") == normalized_value
                ):
                    return record
            return None

        for ref in row_refs:
            existing = find_existing_row_value("manual_page_reference", ref)
            if existing is not None:
                # The source extractor may already have classified a single cell
                # as a manual page reference.  When row-level parsing verifies
                # the same value, keep only one record but mark it as row-derived
                # so audit/inspect output reflects the stronger LEP method.
                existing["source_template_value_role"] = "lep_row_derived_manual_page_reference"
                existing["source_value_kind"] = "row_derived_verified"
                existing["normalization_confidence"] = max(float(existing.get("normalization_confidence") or 0.0), 0.90)
                flags = list(existing.get("normalization_flags") or [])
                for flag in ("lep_row_reconstructed", "row_level_page_reference", "row_level_existing_value_verified"):
                    if flag not in flags:
                        flags.append(flag)
                existing["normalization_flags"] = flags
                source_trace = dict(existing.get("source_trace") or {})
                source_trace["source_value_record_ids"] = row_value_ids
                existing["source_trace"] = source_trace
                lep_row_derived_manual_refs += 1
                continue
            key = (table_id, "manual_page_reference", ref, row_index, "__row__")
            if key in seen_field_keys:
                continue
            seen_field_keys.add(key)
            out = {
                "normalized_value_record_id": stable_id("table_route_normalized_value", table_id, row_index, "manual_page_reference", ref),
                "schema_version": SCHEMA_VERSION,
                "source_value_record_id": first_value.get("value_record_id"),
                "source_value_record_ids": row_value_ids,
                "source_cell_id": first_value.get("cell_id"),
                "source_row_id": first_value.get("row_id"),
                "page_id": first_value.get("page_id") or table_meta.get("page_id"),
                "table_id": table_id,
                "table_template_type": "list_of_effective_pages",
                "table_template_confidence": table_meta.get("table_template_confidence"),
                "source_template_value_role": "lep_row_derived_manual_page_reference",
                "source_value_kind": "row_derived",
                "field_name": "manual_page_reference",
                "normalized_value": ref,
                "raw_value_text": row_text,
                "evidence_kind": "manual_page_reference",
                "normalization_confidence": 0.90,
                "row_index": row_index,
                "column_index": None,
                "cell_bbox": None,
                "part_number_candidates": [],
                "normalization_flags": ["lep_row_reconstructed", "row_level_page_reference"],
                "source_trace": {
                    "source_module": "trace_net_table_route_cell_extractor_v1",
                    "source_report_schema_version": source_report.get("schema_version"),
                    "source_report_status": source_report.get("status"),
                    "source_value_record_id": first_value.get("value_record_id"),
                    "source_value_record_ids": row_value_ids,
                    "page_id": first_value.get("page_id") or table_meta.get("page_id"),
                    "table_id": table_id,
                },
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "postgres_write_attempted": False,
                "qdrant_write_attempted": False,
                "opensearch_write_attempted": False,
                "unsafe_table_route_normalized_value": False,
            }
            normalized_values.append(out)
            lep_row_derived_manual_refs += 1
            if table_id in tables_seen:
                tables_seen[table_id]["normalized_value_count"] += 1

        # Promote compact revision/sequence cells from the same reconstructed LEP row.
        if not any(r.get("table_id") == table_id and r.get("row_index") == row_index and r.get("field_name") == "page_rev_or_sequence_value" for r in normalized_values):
            for cell in ordered:
                cell_text = normalize_text(cell.get("normalized_value") or cell.get("value_text"))
                if not cell_text or extract_lep_page_references_from_text(cell_text) or is_probably_lep_header_or_title(cell_text):
                    continue
                # Avoid treating fragments used to reconstruct the page reference
                # itself (for example the trailing ``103`` in ``25-21-00-103``)
                # as a separate revision/sequence value.
                ref_fragments = {fragment for ref in row_refs for fragment in ref.split("-")}
                if cell_text.upper() in ref_fragments:
                    continue
                if not LEP_REV_OR_SEQ_RE.fullmatch(cell_text):
                    continue
                key = (table_id, "page_rev_or_sequence_value", cell_text, row_index, cell.get("column_index"))
                if key in seen_field_keys:
                    continue
                seen_field_keys.add(key)
                out = {
                    "normalized_value_record_id": stable_id("table_route_normalized_value", table_id, cell.get("cell_id"), "page_rev_or_sequence_value", cell_text),
                    "schema_version": SCHEMA_VERSION,
                    "source_value_record_id": cell.get("value_record_id"),
                    "source_cell_id": cell.get("cell_id"),
                    "source_row_id": cell.get("row_id"),
                    "page_id": cell.get("page_id") or table_meta.get("page_id"),
                    "table_id": table_id,
                    "table_template_type": "list_of_effective_pages",
                    "table_template_confidence": table_meta.get("table_template_confidence"),
                    "source_template_value_role": "lep_row_derived_page_rev_or_sequence_value",
                    "source_value_kind": "row_derived",
                    "field_name": "page_rev_or_sequence_value",
                    "normalized_value": cell_text,
                    "raw_value_text": cell_text,
                    "evidence_kind": "lep_sequence_or_revision",
                    "normalization_confidence": 0.78,
                    "row_index": row_index,
                    "column_index": cell.get("column_index"),
                    "cell_bbox": cell.get("cell_bbox"),
                    "part_number_candidates": [],
                    "normalization_flags": ["lep_row_reconstructed", "row_level_sequence_or_revision"],
                    "source_trace": {
                        "source_module": "trace_net_table_route_cell_extractor_v1",
                        "source_report_schema_version": source_report.get("schema_version"),
                        "source_report_status": source_report.get("status"),
                        "source_value_record_id": cell.get("value_record_id"),
                        "page_id": cell.get("page_id") or table_meta.get("page_id"),
                        "table_id": table_id,
                    },
                    "retrieval_only": True,
                    "answer_permission": False,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "source_truth_mutation_allowed": False,
                    "postgres_write_attempted": False,
                    "qdrant_write_attempted": False,
                    "opensearch_write_attempted": False,
                    "unsafe_table_route_normalized_value": False,
                }
                normalized_values.append(out)
                lep_row_derived_sequence_values += 1
                if table_id in tables_seen:
                    tables_seen[table_id]["normalized_value_count"] += 1
                break

    # If an extraction-ready LEP table has all body fragments suppressed and no
    # reconstructable row references, keep a single low-confidence table-level
    # context marker. This preserves table coverage without reintroducing the
    # >1k noisy LEP fragment problem.
    for table_id, table in tables_seen.items():
        if (
            table.get("table_extraction_allowed")
            and table.get("table_template_type") == "list_of_effective_pages"
            and table.get("normalized_value_count", 0) == 0
        ):
            fallback_text = "LIST OF EFFECTIVE PAGES table detected; no fielded LEP row values reconstructed"
            normalized_values.append({
                "normalized_value_record_id": stable_id("table_route_normalized_value", table_id, "lep_table_presence_context", fallback_text),
                "schema_version": SCHEMA_VERSION,
                "source_value_record_id": None,
                "source_cell_id": None,
                "source_row_id": None,
                "page_id": table.get("page_id"),
                "table_id": table_id,
                "table_template_type": "list_of_effective_pages",
                "table_template_confidence": table.get("table_template_confidence"),
                "source_template_value_role": "lep_table_presence_context",
                "source_value_kind": "table_level_context",
                "field_name": "lep_context",
                "normalized_value": fallback_text,
                "raw_value_text": fallback_text,
                "evidence_kind": "context",
                "normalization_confidence": 0.35,
                "row_index": None,
                "column_index": None,
                "cell_bbox": None,
                "part_number_candidates": [],
                "normalization_flags": ["context_record", "lep_table_coverage_marker", "no_fielded_lep_rows"],
                "source_trace": {
                    "source_module": "trace_net_table_route_cell_extractor_v1",
                    "source_report_schema_version": source_report.get("schema_version"),
                    "source_report_status": source_report.get("status"),
                    "page_id": table.get("page_id"),
                    "table_id": table_id,
                },
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "postgres_write_attempted": False,
                "qdrant_write_attempted": False,
                "opensearch_write_attempted": False,
                "unsafe_table_route_normalized_value": False,
            })
            table["normalized_value_count"] = 1

    for table in tables_seen.values():
        table["normalizer_record_id"] = stable_id("table_route_value_normalizer", table.get("page_id"), table.get("table_id"))
        table["normalization_status"] = "normalized" if table.get("normalized_value_count", 0) > 0 else "no_fielded_values"
        normalizer_records.append(table)

    diagnostics = {
        "skipped_unmapped_value_count": skipped_unmapped,
        "skipped_unknown_template_value_count": skipped_unknown_template,
        "review_only_source_skipped_count": skipped_review_only,
        "lep_context_suppressed_record_count": lep_context_suppressed,
        "lep_row_derived_manual_page_reference_record_count": lep_row_derived_manual_refs,
        "lep_row_derived_page_rev_or_sequence_value_record_count": lep_row_derived_sequence_values,
    }
    return normalizer_records, normalized_values, diagnostics


def count_where(records: Sequence[Mapping[str, Any]], pred) -> int:
    return sum(1 for r in records if pred(r))


def build_summary(source_report: Mapping[str, Any], normalizer_records: Sequence[Mapping[str, Any]], normalized_values: Sequence[Mapping[str, Any]], diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    source_summary = source_report.get("summary") or {}
    field_count = lambda name: count_where(normalized_values, lambda r: r.get("field_name") == name)
    template_count = lambda name: count_where(normalized_values, lambda r: r.get("table_template_type") == name)
    summary = {
        "source_table_route_cell_extractor_quality_status": source_report.get("quality_status"),
        "source_table_route_cell_extraction_record_count": len(source_report.get("table_route_cell_extraction_records") or []),
        "source_table_value_record_count": len(source_report.get("table_route_value_records") or []),
        "source_template_detected_table_count": source_summary.get("template_detected_table_count", 0),
        "table_route_value_normalizer_record_count": len(normalizer_records),
        "normalized_table_value_record_count": len(normalized_values),
        "normalized_table_count": len({r.get("table_id") for r in normalized_values}),
        "review_only_source_skipped_count": diagnostics.get("review_only_source_skipped_count", 0),
        "skipped_unmapped_value_count": diagnostics.get("skipped_unmapped_value_count", 0),
        "skipped_unknown_template_value_count": diagnostics.get("skipped_unknown_template_value_count", 0),
        "lep_context_suppressed_record_count": diagnostics.get("lep_context_suppressed_record_count", 0),
        "lep_row_derived_manual_page_reference_record_count": diagnostics.get("lep_row_derived_manual_page_reference_record_count", 0),
        "lep_row_derived_page_rev_or_sequence_value_record_count": diagnostics.get("lep_row_derived_page_rev_or_sequence_value_record_count", 0),
        "covered_part_number_record_count": field_count("covered_part_number"),
        "part_number_coverage_context_record_count": field_count("part_number_coverage_context"),
        "manual_page_reference_record_count": field_count("manual_page_reference"),
        "page_rev_or_sequence_value_record_count": field_count("page_rev_or_sequence_value"),
        "lep_context_record_count": field_count("lep_context"),
        "ipl_part_number_record_count": field_count("ipl_part_number"),
        "ipl_figure_item_or_quantity_record_count": field_count("ipl_figure_item_or_quantity"),
        "ipl_text_record_count": field_count("ipl_text"),
        "ipl_context_record_count": field_count("ipl_context"),
        "generic_table_value_record_count": field_count("generic_table_value"),
        "part_number_coverage_template_value_count": template_count("part_number_coverage_list"),
        "list_effective_pages_template_value_count": template_count("list_of_effective_pages"),
        "ipl_split_column_template_value_count": template_count("ipl_split_column_table"),
        "generic_template_value_count": template_count("generic_table"),
        "unsafe_table_route_value_normalizer_record_count": count_where(normalizer_records, lambda r: r.get("unsafe_table_route_value_normalization")) + count_where(normalized_values, lambda r: r.get("unsafe_table_route_normalized_value")),
        "answer_permission_count": count_where(normalizer_records, lambda r: r.get("answer_permission")) + count_where(normalized_values, lambda r: r.get("answer_permission")),
        "can_answer_directly_count": count_where(normalizer_records, lambda r: r.get("can_answer_directly")) + count_where(normalized_values, lambda r: r.get("can_answer_directly")),
        "can_prove_claims_count": count_where(normalizer_records, lambda r: r.get("can_prove_claims")) + count_where(normalized_values, lambda r: r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": count_where(normalizer_records, lambda r: r.get("source_truth_mutation_allowed")) + count_where(normalized_values, lambda r: r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": count_where(normalizer_records, lambda r: r.get("postgres_write_attempted")) + count_where(normalized_values, lambda r: r.get("postgres_write_attempted")),
        "qdrant_write_attempt_count": count_where(normalizer_records, lambda r: r.get("qdrant_write_attempted")) + count_where(normalized_values, lambda r: r.get("qdrant_write_attempted")),
        "opensearch_write_attempt_count": count_where(normalizer_records, lambda r: r.get("opensearch_write_attempted")) + count_where(normalized_values, lambda r: r.get("opensearch_write_attempted")),
    }
    return summary


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    keys = (
        "min_source_cell_extraction_records",
        "min_source_value_records",
        "min_normalizer_records",
        "min_normalized_records",
        "min_normalized_tables",
        "min_covered_part_number_records",
        "min_manual_page_reference_records",
        "min_lep_row_derived_manual_page_reference_records",
        "max_lep_context_records",
        "min_ipl_part_number_records",
        "max_unsafe_records",
        "max_answer_permission_count",
        "max_source_truth_mutation_allowed",
        "require_table_route_cell_extractor_quality_pass",
        "require_no_answer_permission",
    )
    return {key: getattr(args, key, None) for key in keys}


def evaluate_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> tuple[str, list[str]]:
    failures: list[str] = []
    def require(cond: bool, reason: str) -> None:
        if not cond:
            failures.append(reason)

    if thresholds.get("require_table_route_cell_extractor_quality_pass"):
        require(summary.get("source_table_route_cell_extractor_quality_status") == "PASS", "source_table_route_cell_extractor_quality_not_pass")
    require(summary.get("source_table_route_cell_extraction_record_count", 0) >= (thresholds.get("min_source_cell_extraction_records") or 1), "source_cell_extraction_record_count_below_min")
    require(summary.get("source_table_value_record_count", 0) >= (thresholds.get("min_source_value_records") or 1), "source_value_record_count_below_min")
    require(summary.get("table_route_value_normalizer_record_count", 0) >= (thresholds.get("min_normalizer_records") or 1), "normalizer_record_count_below_min")
    require(summary.get("normalized_table_value_record_count", 0) >= (thresholds.get("min_normalized_records") or 1), "normalized_record_count_below_min")
    require(summary.get("normalized_table_count", 0) >= (thresholds.get("min_normalized_tables") or 1), "normalized_table_count_below_min")
    require(summary.get("covered_part_number_record_count", 0) >= (thresholds.get("min_covered_part_number_records") or 0), "covered_part_number_record_count_below_min")
    require(summary.get("manual_page_reference_record_count", 0) >= (thresholds.get("min_manual_page_reference_records") or 0), "manual_page_reference_record_count_below_min")
    require(summary.get("lep_row_derived_manual_page_reference_record_count", 0) >= (thresholds.get("min_lep_row_derived_manual_page_reference_records") or 0), "lep_row_derived_manual_page_reference_record_count_below_min")
    if thresholds.get("max_lep_context_records") is not None:
        require(summary.get("lep_context_record_count", 0) <= thresholds.get("max_lep_context_records"), "lep_context_record_count_above_max")
    require(summary.get("ipl_part_number_record_count", 0) >= (thresholds.get("min_ipl_part_number_records") or 0), "ipl_part_number_record_count_below_min")
    require(summary.get("unsafe_table_route_value_normalizer_record_count", 0) <= (thresholds.get("max_unsafe_records") if thresholds.get("max_unsafe_records") is not None else 0), "unsafe_records_above_limit")
    require(summary.get("answer_permission_count", 0) <= (thresholds.get("max_answer_permission_count") if thresholds.get("max_answer_permission_count") is not None else 0), "answer_permission_above_limit")
    require(summary.get("source_truth_mutation_allowed_count", 0) <= (thresholds.get("max_source_truth_mutation_allowed") if thresholds.get("max_source_truth_mutation_allowed") is not None else 0), "source_truth_mutation_allowed_above_limit")
    require(summary.get("postgres_write_attempt_count", 0) == 0 and summary.get("qdrant_write_attempt_count", 0) == 0 and summary.get("opensearch_write_attempt_count", 0) == 0, "write_attempts_detected")
    if thresholds.get("require_no_answer_permission"):
        require(summary.get("answer_permission_count", 0) == 0 and summary.get("can_answer_directly_count", 0) == 0 and summary.get("can_prove_claims_count", 0) == 0, "answer_or_claim_permission_detected")
    return ("PASS" if not failures else "FAIL"), failures


def build_report(source_report: Mapping[str, Any], output_dir: Path, thresholds: Mapping[str, Any]) -> dict[str, Any]:
    records, normalized_values, diagnostics = build_normalized_records(source_report)
    summary = build_summary(source_report, records, normalized_values, diagnostics)
    quality_status, failures = evaluate_quality(summary, thresholds)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "source_report_schema_version": source_report.get("schema_version"),
        "source_report_status": source_report.get("status"),
        "summary": summary,
        "quality_fail_reasons": failures,
        "table_route_value_normalizer_records": records,
        "table_route_normalized_value_records": normalized_values,
        "safety_contract": {
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "retrieval_only": True,
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table route value normalizer.")
    parser.add_argument("--table-route-cell-extractor", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-source-cell-extraction-records", type=int, default=1)
    parser.add_argument("--min-source-value-records", type=int, default=1)
    parser.add_argument("--min-normalizer-records", type=int, default=1)
    parser.add_argument("--min-normalized-records", type=int, default=1)
    parser.add_argument("--min-normalized-tables", type=int, default=1)
    parser.add_argument("--min-covered-part-number-records", type=int, default=0)
    parser.add_argument("--min-manual-page-reference-records", type=int, default=0)
    parser.add_argument("--min-lep-row-derived-manual-page-reference-records", type=int, default=0)
    parser.add_argument("--max-lep-context-records", type=int, default=None)
    parser.add_argument("--min-ipl-part-number-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-route-cell-extractor-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def write_outputs(report: Mapping[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_route_value_normalizer_v1.json"
    write_json(report_path, report)
    write_jsonl(output_dir / "trace_net_table_route_value_normalizer_v1_records.jsonl", report.get("table_route_value_normalizer_records") or [])
    write_jsonl(output_dir / "trace_net_table_route_value_normalizer_v1_values.jsonl", report.get("table_route_normalized_value_records") or [])
    write_json(output_dir / "trace_net_table_route_value_normalizer_v1_summary.json", report.get("summary") or {})
    quality_payload = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": report.get("quality_status"),
        "quality_status": report.get("quality_status"),
        "generated_at": utc_now(),
        "summary": report.get("summary") or {},
        "quality_fail_reasons": report.get("quality_fail_reasons") or [],
    }
    write_json(output_dir / "trace_net_table_route_value_normalizer_v1_quality.json", quality_payload)
    write_json(output_dir / "trace_net_table_route_value_normalizer_v1_manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "status": report.get("status"),
        "quality_status": report.get("quality_status"),
        "report_path": str(report_path),
        "records_jsonl_path": str(output_dir / "trace_net_table_route_value_normalizer_v1_records.jsonl"),
        "values_jsonl_path": str(output_dir / "trace_net_table_route_value_normalizer_v1_values.jsonl"),
    })
    return report_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    source_report = read_json(args.table_route_cell_extractor)
    thresholds = thresholds_from_args(args)
    report = build_report(source_report, args.output_dir, thresholds)
    report_path = write_outputs(report, args.output_dir)
    print("TRACE-Net Table Route Value Normalizer v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "source_table_route_cell_extraction_record_count",
        "source_table_value_record_count",
        "source_template_detected_table_count",
        "table_route_value_normalizer_record_count",
        "normalized_table_value_record_count",
        "normalized_table_count",
        "review_only_source_skipped_count",
        "covered_part_number_record_count",
        "manual_page_reference_record_count",
        "page_rev_or_sequence_value_record_count",
        "lep_context_record_count",
        "lep_context_suppressed_record_count",
        "lep_row_derived_manual_page_reference_record_count",
        "lep_row_derived_page_rev_or_sequence_value_record_count",
        "ipl_part_number_record_count",
        "ipl_figure_item_or_quantity_record_count",
        "ipl_text_record_count",
        "unsafe_table_route_value_normalizer_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {report['summary'].get(key)}")
    print(f" report_path: {report_path}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
