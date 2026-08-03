from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_table_row_context_source_expander_v1"
STATUS_BUILT = "TRACE_NET_TABLE_ROW_CONTEXT_SOURCE_EXPANDER_BUILT"
STATUS_CHECKED = "TRACE_NET_TABLE_ROW_CONTEXT_SOURCE_EXPANDER_QUALITY_CHECKED"
SCHEMA_VERSION = "trace_net_table_row_context_source_expander_v1"

PART_RE = re.compile(r"\b\d{2,3}-\d{4,6}-\d{2,4}\b")
BAD_FILENAME_RE = re.compile(r"\.(?:tif|tiff|png|jpe?g|webp|json|csv|txt)$", re.I)
DESC_FIELD_HINTS = (
    "description",
    "desc",
    "nomenclature",
    "name",
    "part_name",
    "item_name",
    "title",
    "label",
)
TEXT_FIELD_HINTS = (
    "text",
    "ocr",
    "raw",
    "value",
    "display",
    "normalized",
)
PART_FIELD_HINTS = (
    "part_number",
    "covered_part_number",
    "ipl_part_number",
)
NUMERIC_ONLY_RE = re.compile(r"^[\s\-+.,/0-9]+$")

REJECTED_DESCRIPTION_FIELD_HINTS = (
    "category_aware_label",
    "source_community_label",
    "refined_label",
    "community_label",
    "community",
    "dc:title",
    "trace_net:",
    "context_v2_present",
    "ocr_present",
)
REJECTED_DESCRIPTION_SOURCE_PATTERNS = (
    "category_aware_leiden_overlay",
    "community_aware_retrieval",
    "dublin_core_crosswalk",
    "dublin_core_crosswalk_refined",
    "dublin_core_crosswalk_refinement",
    "leiden",
)
REJECTED_DESCRIPTION_TEXT_PATTERNS = (
    "trace-net page ",
    "part family community",
    "visual part / diagram review community",
    "table + parts + diagram review community",
    "review community",
    "community",
)
OFFICIAL_DESCRIPTION_FIELD_HINTS = (
    "description",
    "desc",
    "nomenclature",
    "part_description",
    "item_description",
    "ipl_text",
    "part_name",
    "item_name",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha1_short(text: str, n: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:n]


def as_path(value: Any) -> Path:
    return value if isinstance(value, Path) else Path(str(value))


def load_json(path: Any) -> Any:
    p = as_path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = as_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Any, records: Iterable[Mapping[str, Any]]) -> None:
    p = as_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def norm_part(value: Any) -> str:
    text = safe_str(value).upper().strip()
    m = PART_RE.search(text)
    return m.group(0) if m else text


def value_from_record(r: Mapping[str, Any]) -> str:
    for k in ("raw_value", "display_value", "normalized_value", "value", "text", "cell_text", "ocr_text"):
        v = r.get(k)
        if v not in (None, ""):
            return safe_str(v).strip()
    return ""


def field_from_record(r: Mapping[str, Any]) -> str:
    return safe_str(r.get("field_name") or r.get("field_role") or r.get("column_name") or r.get("label") or "")


def is_part_number_like(value: str) -> bool:
    v = value.strip()
    if not v:
        return False
    return bool(PART_RE.fullmatch(v)) or bool(PART_RE.search(v))


def is_bad_description(value: Any) -> bool:
    text = safe_str(value).strip()
    if not text:
        return True
    if len(text) < 3:
        return True
    if len(text) > 220:
        # Long OCR paragraphs are useful context but not a clean nomenclature candidate.
        return True
    if BAD_FILENAME_RE.search(text):
        return True
    if NUMERIC_ONLY_RE.fullmatch(text):
        return True
    if is_part_number_like(text):
        return True
    lowered = text.lower()
    if lowered in {"none", "null", "n/a", "na", "unknown", "missing", "true", "false"}:
        return True
    if lowered.startswith("trace-net table evidence"):
        return True
    return False


def is_official_description_field(field: str) -> bool:
    f = safe_str(field).lower()
    return any(h in f for h in OFFICIAL_DESCRIPTION_FIELD_HINTS)


def rejection_reason_for_description(value: Any, field_name: Any = "", artifact: Any = "", source: Any = "") -> str:
    text = safe_str(value).strip()
    field = safe_str(field_name).lower()
    artifact_text = safe_str(artifact).replace("\\", "/").lower()
    source_text = safe_str(source).lower()
    lowered = text.lower()

    if is_bad_description(text):
        return "bad_description_value"
    if any(h in field for h in REJECTED_DESCRIPTION_FIELD_HINTS):
        return "rejected_metadata_or_community_field"
    if any(p in artifact_text for p in REJECTED_DESCRIPTION_SOURCE_PATTERNS):
        return "rejected_metadata_or_graph_artifact"
    if any(p in source_text for p in ("community", "dublin", "metadata", "graph")):
        return "rejected_metadata_or_graph_source"
    if any(p in lowered for p in REJECTED_DESCRIPTION_TEXT_PATTERNS):
        return "rejected_metadata_or_community_text"
    if not is_official_description_field(field):
        return "field_not_official_nomenclature"
    return ""


def field_has_hint(field: str, hints: Sequence[str]) -> bool:
    f = field.lower()
    return any(h in f for h in hints)


def iter_dicts(obj: Any, path: str = "") -> Iterator[Tuple[str, Mapping[str, Any]]]:
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            child = f"{path}.{k}" if path else str(k)
            yield from iter_dicts(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_dicts(v, f"{path}[{i}]")


def find_record_lists(data: Mapping[str, Any]) -> List[Sequence[Mapping[str, Any]]]:
    keys = (
        "records",
        "evidence_documents",
        "exact_search_documents",
        "normalized_values",
        "source_normalized_table_value_records",
        "cell_records",
        "cells",
        "rows",
        "documents",
    )
    lists: List[Sequence[Mapping[str, Any]]] = []
    for k in keys:
        v = data.get(k)
        if isinstance(v, list) and all(isinstance(x, dict) for x in v[:20]):
            lists.append(v)  # type: ignore[arg-type]
    return lists


def extract_source_trace_ids(r: Mapping[str, Any]) -> Dict[str, str]:
    st = r.get("source_trace") if isinstance(r.get("source_trace"), dict) else {}
    out = {
        "source_cell_id": safe_str(r.get("source_cell_id") or st.get("source_cell_id")),
        "source_value_record_id": safe_str(r.get("source_value_record_id") or st.get("source_value_record_id")),
        "source_value_id": safe_str(r.get("source_value_id") or st.get("source_value_id")),
        "source_evidence_id": safe_str(r.get("source_evidence_id") or r.get("evidence_id")),
    }
    return {k: v for k, v in out.items() if v}


def page_id_of(r: Mapping[str, Any]) -> str:
    st = r.get("source_trace") if isinstance(r.get("source_trace"), dict) else {}
    return safe_str(r.get("page_id") or r.get("source_page_id") or st.get("page_id"))


def table_id_of(r: Mapping[str, Any]) -> str:
    st = r.get("source_trace") if isinstance(r.get("source_trace"), dict) else {}
    return safe_str(r.get("table_id") or st.get("table_id"))


def row_index_of(r: Mapping[str, Any]) -> Optional[int]:
    value = r.get("row_index")
    if value is None:
        value = r.get("row_id")
    if value is None:
        st = r.get("source_trace") if isinstance(r.get("source_trace"), dict) else {}
        value = st.get("row_index") or st.get("row_id")
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return None


def column_index_of(r: Mapping[str, Any]) -> Optional[int]:
    value = r.get("column_index")
    if value is None:
        value = r.get("column_id")
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return None


def simplified_cell(r: Mapping[str, Any], artifact: str = "") -> Dict[str, Any]:
    return {
        "artifact": artifact,
        "page_id": page_id_of(r),
        "table_id": table_id_of(r),
        "row_index": row_index_of(r),
        "column_index": column_index_of(r),
        "field_name": field_from_record(r),
        "raw_value": safe_str(r.get("raw_value") or r.get("display_value") or r.get("value") or r.get("text")),
        "normalized_value": safe_str(r.get("normalized_value")),
        "search_text": safe_str(r.get("search_text"))[:350],
        "source_ids": extract_source_trace_ids(r),
        "record_id": safe_str(r.get("evidence_id") or r.get("document_id") or r.get("record_id") or r.get("cell_id")),
    }


def extract_visual_targets(image_visual_evidence_pack: Any) -> List[Dict[str, Any]]:
    data = load_json(image_visual_evidence_pack)
    records = data.get("records") if isinstance(data, dict) else []
    targets: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()
    for r in records or []:
        if not isinstance(r, dict):
            continue
        part = norm_part(r.get("linked_part_number"))
        if not part or not is_part_number_like(part):
            continue
        if not r.get("linked"):
            continue
        key = (part, safe_str(r.get("page_id")), safe_str(r.get("figure")))
        if key in seen:
            continue
        seen.add(key)
        targets.append({
            "linked_part_number": part,
            "citation_label": safe_str(r.get("citation_label")),
            "page_id": safe_str(r.get("page_id")),
            "page_number": r.get("page_number"),
            "figure": safe_str(r.get("figure")),
            "callout": safe_str(r.get("callout")),
            "linked_description": safe_str(r.get("linked_description")),
            "source_link_record_id": safe_str(r.get("source_link_record_id")),
            "source_trace_ready": bool(r.get("source_trace_ready")),
            "citation_ready": bool(r.get("citation_ready")),
        })
    return targets


def load_table_records(paths: Sequence[Any]) -> List[Tuple[str, Mapping[str, Any]]]:
    out: List[Tuple[str, Mapping[str, Any]]] = []
    for path in paths:
        if not path:
            continue
        p = as_path(path)
        if not p.exists():
            continue
        data = load_json(p)
        if not isinstance(data, dict):
            continue
        for records in find_record_lists(data):
            for r in records:
                if isinstance(r, dict):
                    out.append((str(p), r))
    return out


def group_rows(records: Sequence[Tuple[str, Mapping[str, Any]]]) -> Dict[Tuple[str, str, int], List[Tuple[str, Mapping[str, Any]]]]:
    rows: Dict[Tuple[str, str, int], List[Tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    for artifact, r in records:
        page_id = page_id_of(r)
        table_id = table_id_of(r)
        row = row_index_of(r)
        if page_id and table_id and row is not None:
            rows[(page_id, table_id, row)].append((artifact, r))
    return rows


def collect_anchor_records(part: str, records: Sequence[Tuple[str, Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    anchors: List[Dict[str, Any]] = []
    for artifact, r in records:
        text = json.dumps(r, ensure_ascii=False)
        if part not in text:
            continue
        value = norm_part(value_from_record(r) or r.get("normalized_value") or r.get("display_value") or text)
        field = field_from_record(r)
        is_direct_part_cell = value == part or safe_str(r.get("normalized_value")) == part or safe_str(r.get("display_value")) == part or safe_str(r.get("raw_value")) == part
        if is_direct_part_cell or field_has_hint(field, PART_FIELD_HINTS):
            anchors.append({
                "artifact": artifact,
                "page_id": page_id_of(r),
                "table_id": table_id_of(r),
                "row_index": row_index_of(r),
                "column_index": column_index_of(r),
                "field_name": field,
                "raw_value": safe_str(r.get("raw_value") or r.get("display_value")),
                "normalized_value": safe_str(r.get("normalized_value")),
                "record_id": safe_str(r.get("evidence_id") or r.get("document_id") or r.get("record_id")),
                "source_ids": extract_source_trace_ids(r),
            })
    # Stable de-dupe.
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for a in anchors:
        key = json.dumps(a, sort_keys=True)
        if key not in seen:
            seen.add(key)
            deduped.append(a)
    return deduped


def collect_row_context(anchor: Mapping[str, Any], rows: Mapping[Tuple[str, str, int], Sequence[Tuple[str, Mapping[str, Any]]]], window: int) -> List[Dict[str, Any]]:
    page_id = safe_str(anchor.get("page_id"))
    table_id = safe_str(anchor.get("table_id"))
    row = anchor.get("row_index")
    try:
        row_int = int(row)  # type: ignore[arg-type]
    except Exception:
        return []
    cells: List[Dict[str, Any]] = []
    for rix in range(row_int - window, row_int + window + 1):
        group = rows.get((page_id, table_id, rix), [])
        for artifact, rec in group:
            cell = simplified_cell(rec, artifact)
            cell["row_distance"] = abs(rix - row_int)
            cells.append(cell)
    cells.sort(key=lambda c: (c.get("row_index") if c.get("row_index") is not None else 999999, c.get("column_index") if c.get("column_index") is not None else 999999, c.get("field_name") or ""))
    return cells


def candidate_from_cell(cell: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    field = safe_str(cell.get("field_name"))
    artifact = safe_str(cell.get("artifact"))
    values = [safe_str(cell.get("raw_value")), safe_str(cell.get("normalized_value"))]
    for value in values:
        reason = rejection_reason_for_description(value, field, artifact, "row_context_cell")
        if reason:
            continue
        return {
            "description": value.strip(),
            "field_name": field,
            "source": "row_context_cell",
            "page_id": cell.get("page_id"),
            "table_id": cell.get("table_id"),
            "row_index": cell.get("row_index"),
            "column_index": cell.get("column_index"),
            "artifact": cell.get("artifact"),
            "source_ids": cell.get("source_ids", {}),
            "candidate_quality": "official_row_context_nomenclature",
        }
    return None


def rejected_candidate_from_cell(cell: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rejected: List[Dict[str, Any]] = []
    field = safe_str(cell.get("field_name"))
    artifact = safe_str(cell.get("artifact"))
    for source_key in ("raw_value", "normalized_value"):
        value = safe_str(cell.get(source_key))
        if not value:
            continue
        reason = rejection_reason_for_description(value, field, artifact, "row_context_cell")
        if not reason:
            continue
        rejected.append({
            "description": value.strip(),
            "field_name": field,
            "source": "row_context_cell",
            "source_key": source_key,
            "artifact": artifact,
            "row_index": cell.get("row_index"),
            "column_index": cell.get("column_index"),
            "rejection_reason": reason,
        })
    return rejected

def collect_description_candidates(row_context_cells: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for cell in row_context_cells:
        cand = candidate_from_cell(cell)
        if not cand:
            continue
        key = json.dumps(cand, sort_keys=True)
        if key not in seen:
            seen.add(key)
            candidates.append(cand)
    # Prefer explicit nomenclature fields, then description/name fields.
    def rank(c: Mapping[str, Any]) -> Tuple[int, int, str]:
        field = safe_str(c.get("field_name")).lower()
        if "nomenclature" in field:
            desc_rank = 0
        elif "description" in field or "desc" in field:
            desc_rank = 1
        elif "ipl_text" in field:
            desc_rank = 2
        else:
            desc_rank = 3
        row = c.get("row_index")
        try:
            row_rank = int(row)
        except Exception:
            row_rank = 999999
        return (desc_rank, row_rank, safe_str(c.get("description")))
    candidates.sort(key=rank)
    return candidates


def collect_rejected_description_candidates(row_context_cells: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rejected: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for cell in row_context_cells:
        for cand in rejected_candidate_from_cell(cell):
            key = json.dumps(cand, sort_keys=True)
            if key not in seen:
                seen.add(key)
                rejected.append(cand)
    return rejected


def list_json_artifacts(artifact_root: Optional[Any], explicit_artifacts: Sequence[Any], output_dir: Any, max_json_files: int, max_artifact_bytes: int) -> List[Path]:
    paths: List[Path] = []
    output_dir_resolved = as_path(output_dir).resolve()
    for item in explicit_artifacts or []:
        p = as_path(item)
        if p.exists() and p.suffix.lower() == ".json":
            paths.append(p)
    if artifact_root:
        root = as_path(artifact_root)
        if root.exists():
            for p in root.rglob("*.json"):
                try:
                    if output_dir_resolved in p.resolve().parents:
                        continue
                    if p.stat().st_size > max_artifact_bytes:
                        continue
                except OSError:
                    continue
                paths.append(p)
                if len(paths) >= max_json_files:
                    break
    # de-dupe stable
    out: List[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out[:max_json_files]


def scan_upstream_artifact(path: Path, target: Mapping[str, Any], anchor_ids: Mapping[str, str], max_hits_per_artifact: int = 25) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    try:
        data = load_json(path)
    except Exception as exc:
        return [{"artifact": str(path), "error": f"load_failed: {exc}"}]
    part = safe_str(target.get("linked_part_number"))
    anchor_values = {v for v in anchor_ids.values() if v}
    for obj_path, obj in iter_dicts(data):
        if len(hits) >= max_hits_per_artifact:
            break
        s = json.dumps(obj, ensure_ascii=False)
        match_reasons: List[str] = []
        if part and part in s:
            match_reasons.append("part_number")
        for aid in anchor_values:
            if aid and aid in s:
                match_reasons.append(f"source_id:{aid}")
        if not match_reasons:
            continue
        candidates: List[Dict[str, Any]] = []
        rejected_candidates: List[Dict[str, Any]] = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                continue
            field = str(k)
            value = safe_str(v).strip()
            reason = rejection_reason_for_description(value, field, str(path), "upstream_artifact_scan")
            if reason:
                if value and not is_bad_description(value):
                    rejected_candidates.append({"field_name": field, "description": value, "rejection_reason": reason})
                continue
            candidates.append({"field_name": field, "description": value, "candidate_quality": "official_upstream_nomenclature"})
        hits.append({
            "artifact": str(path),
            "object_path": obj_path,
            "match_reasons": sorted(set(match_reasons)),
            "description_candidates": candidates[:8],
            "rejected_description_candidates": rejected_candidates[:12],
            "keys": list(obj.keys())[:50],
            "preview": s[:900],
        })
    return hits

def merge_upstream_candidates(upstream_hits: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for hit in upstream_hits:
        artifact = hit.get("artifact")
        for cand in hit.get("description_candidates", []) or []:
            if not isinstance(cand, dict):
                continue
            desc = safe_str(cand.get("description"))
            field = safe_str(cand.get("field_name"))
            reason = rejection_reason_for_description(desc, field, artifact, "upstream_artifact_scan")
            if reason:
                continue
            enriched = {
                "description": desc,
                "field_name": field,
                "source": "upstream_artifact_scan",
                "artifact": artifact,
                "object_path": hit.get("object_path"),
                "match_reasons": hit.get("match_reasons", []),
                "candidate_quality": cand.get("candidate_quality", "official_upstream_nomenclature"),
            }
            key = json.dumps(enriched, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(enriched)
    return out


def merge_rejected_upstream_candidates(upstream_hits: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for hit in upstream_hits:
        for cand in hit.get("rejected_description_candidates", []) or []:
            if not isinstance(cand, dict):
                continue
            enriched = {
                "description": safe_str(cand.get("description")),
                "field_name": safe_str(cand.get("field_name")),
                "source": "upstream_artifact_scan",
                "artifact": hit.get("artifact"),
                "object_path": hit.get("object_path"),
                "match_reasons": hit.get("match_reasons", []),
                "rejection_reason": safe_str(cand.get("rejection_reason")),
            }
            key = json.dumps(enriched, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(enriched)
    return out

def build_source_expander(
    *,
    image_visual_evidence_pack: Any,
    table_route_evidence_packager: Any,
    table_exact_search_adapter: Any = None,
    source_artifacts: Sequence[Any] = (),
    artifact_root: Any = None,
    output_dir: Any,
    row_context_window: int = 3,
    max_json_files: int = 300,
    max_artifact_bytes: int = 25_000_000,
    min_linked_visual_parts: int = 1,
    min_row_context_records: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    out_dir = as_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = extract_visual_targets(image_visual_evidence_pack)
    table_paths = [table_route_evidence_packager]
    if table_exact_search_adapter:
        table_paths.append(table_exact_search_adapter)
    table_records = load_table_records(table_paths)
    rows = group_rows(table_records)
    upstream_paths = list_json_artifacts(artifact_root, source_artifacts, out_dir, max_json_files, max_artifact_bytes)

    records: List[Dict[str, Any]] = []
    missing_records: List[Dict[str, Any]] = []
    upstream_hit_count = 0
    row_context_cell_count = 0
    description_candidate_count = 0
    description_rejected_count = 0
    description_selected_count = 0
    source_trace_ready_count = 0

    for i, target in enumerate(targets, 1):
        part = target["linked_part_number"]
        anchors = collect_anchor_records(part, table_records)
        all_anchor_ids: Dict[str, str] = {}
        row_context_cells: List[Dict[str, Any]] = []
        for a in anchors:
            for k, v in (a.get("source_ids") or {}).items():
                if v:
                    all_anchor_ids[k] = v
            row_context_cells.extend(collect_row_context(a, rows, row_context_window))
        # de-dupe cells
        cell_seen: set[str] = set()
        deduped_cells: List[Dict[str, Any]] = []
        for c in row_context_cells:
            key = json.dumps(c, sort_keys=True)
            if key not in cell_seen:
                cell_seen.add(key)
                deduped_cells.append(c)
        row_context_cells = deduped_cells
        row_context_cell_count += len(row_context_cells)

        row_candidates = collect_description_candidates(row_context_cells)
        rejected_row_candidates = collect_rejected_description_candidates(row_context_cells)
        upstream_hits: List[Dict[str, Any]] = []
        for path in upstream_paths:
            # Skip the target derived artifacts already represented in rows unless explicitly useful through IDs.
            hits = scan_upstream_artifact(path, target, all_anchor_ids, max_hits_per_artifact=12)
            useful_hits = [h for h in hits if h.get("description_candidates") or h.get("rejected_description_candidates")]
            upstream_hits.extend(useful_hits)
        upstream_hit_count += len(upstream_hits)
        upstream_candidates = merge_upstream_candidates(upstream_hits)
        rejected_upstream_candidates = merge_rejected_upstream_candidates(upstream_hits)
        description_candidates = row_candidates + upstream_candidates
        rejected_description_candidates = rejected_row_candidates + rejected_upstream_candidates
        description_candidate_count += len(description_candidates)
        description_rejected_count += len(rejected_description_candidates)
        selected = description_candidates[0] if description_candidates else None
        if selected:
            description_selected_count += 1
        if target.get("source_trace_ready"):
            source_trace_ready_count += 1

        record = {
            "record_id": f"table_row_context_source_expander_{i:05d}_{sha1_short(part + safe_str(target.get('citation_label')))}",
            "schema_version": SCHEMA_VERSION,
            "source_visual_citation_label": target.get("citation_label"),
            "linked_part_number": part,
            "visual_page_id": target.get("page_id"),
            "visual_page_number": target.get("page_number"),
            "figure": target.get("figure"),
            "callout": target.get("callout"),
            "visual_source_trace_ready": bool(target.get("source_trace_ready")),
            "visual_citation_ready": bool(target.get("citation_ready")),
            "anchor_record_count": len(anchors),
            "source_anchor_ids": all_anchor_ids,
            "row_context_cell_count": len(row_context_cells),
            "row_context_cells": row_context_cells[:250],
            "description_candidate_count": len(description_candidates),
            "description_candidates": description_candidates[:40],
            "rejected_description_candidate_count": len(rejected_description_candidates),
            "rejected_description_candidates": rejected_description_candidates[:60],
            "selected_description": selected.get("description") if selected else "",
            "selected_description_source": selected if selected else {},
            "description_status": "selected" if selected else "missing",
            "description_missing_reason": "" if selected else "no_official_description_or_nomenclature_cell_found_after_strict_filter",
            "upstream_artifact_scan_count": len(upstream_paths),
            "upstream_hit_count": len(upstream_hits),
            "upstream_hits": upstream_hits[:50],
            "source_trace_ready": bool(target.get("source_trace_ready")),
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "write_attempt_count": 0,
            "unsafe": False,
        }
        records.append(record)
        if not selected:
            missing_records.append({
                "source_visual_citation_label": target.get("citation_label"),
                "linked_part_number": part,
                "visual_page_id": target.get("page_id"),
                "visual_page_number": target.get("page_number"),
                "figure": target.get("figure"),
                "anchor_record_count": len(anchors),
                "row_context_cell_count": len(row_context_cells),
                "upstream_artifact_scan_count": len(upstream_paths),
                "upstream_hit_count": len(upstream_hits),
                "reason": record["description_missing_reason"],
            })

    unsafe_count = sum(1 for r in records if r.get("unsafe"))
    answer_permission_count = sum(1 for r in records if r.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for r in records if r.get("source_truth_mutation_allowed"))
    write_attempt_count = sum(int(r.get("write_attempt_count") or 0) for r in records)
    linked_visual_part_count = len(targets)
    row_context_record_count = sum(1 for r in records if r.get("row_context_cell_count", 0) > 0)

    summary = {
        "linked_visual_part_count": linked_visual_part_count,
        "table_record_count": len(table_records),
        "row_group_count": len(rows),
        "source_artifact_scan_count": len(upstream_paths),
        "row_context_record_count": row_context_record_count,
        "row_context_cell_count": row_context_cell_count,
        "description_candidate_count": description_candidate_count,
        "description_rejected_count": description_rejected_count,
        "description_selected_count": description_selected_count,
        "description_missing_count": len(missing_records),
        "source_trace_ready_count": source_trace_ready_count,
        "upstream_hit_count": upstream_hit_count,
        "ready_for_nomenclature_expansion": True,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": write_attempt_count,
        "unsafe_record_count": unsafe_count,
    }

    checks = [
        {"name": "min_linked_visual_parts", "observed": linked_visual_part_count, "expected": f">= {min_linked_visual_parts}", "passed": linked_visual_part_count >= min_linked_visual_parts},
        {"name": "min_row_context_records", "observed": row_context_record_count, "expected": f">= {min_row_context_records}", "passed": row_context_record_count >= min_row_context_records},
        {"name": "min_source_trace_ready", "observed": source_trace_ready_count, "expected": f">= {min_source_trace_ready}", "passed": source_trace_ready_count >= min_source_trace_ready},
        {"name": "max_unsafe", "observed": unsafe_count, "expected": f"<= {max_unsafe}", "passed": unsafe_count <= max_unsafe},
        {"name": "max_answer_permission", "observed": answer_permission_count, "expected": f"<= {max_answer_permission}", "passed": answer_permission_count <= max_answer_permission},
        {"name": "max_source_truth_mutation_allowed", "observed": source_truth_mutation_allowed_count, "expected": f"<= {max_source_truth_mutation_allowed}", "passed": source_truth_mutation_allowed_count <= max_source_truth_mutation_allowed},
        {"name": "max_write_attempts", "observed": write_attempt_count, "expected": f"<= {max_write_attempts}", "passed": write_attempt_count <= max_write_attempts},
    ]
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"

    paths = {
        "expander": str(out_dir / f"{MODULE}.json"),
        "records_jsonl": str(out_dir / f"{MODULE}_records.jsonl"),
        "missing_jsonl": str(out_dir / f"{MODULE}_missing_descriptions.jsonl"),
        "records_csv": str(out_dir / f"{MODULE}_records.csv"),
        "quality_check": str(out_dir / f"{MODULE}_quality_check.json"),
    }

    result: Dict[str, Any] = {
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "module": MODULE,
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": now_utc(),
        "inputs": {
            "image_visual_evidence_pack": str(image_visual_evidence_pack),
            "table_route_evidence_packager": str(table_route_evidence_packager),
            "table_exact_search_adapter": str(table_exact_search_adapter) if table_exact_search_adapter else "",
            "source_artifacts": [str(x) for x in source_artifacts],
            "artifact_root": str(artifact_root) if artifact_root else "",
            "row_context_window": row_context_window,
            "max_json_files": max_json_files,
            "max_artifact_bytes": max_artifact_bytes,
        },
        "summary": summary,
        "checks": checks,
        "records": records,
        "missing_description_records": missing_records,
        "paths": paths,
        "safety_contract": {
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
        },
        "notes": [
            "This artifact expands table row/source context for linked visual parts; it does not grant answer permission.",
            "Strict nomenclature filtering rejects graph/community labels, Dublin Core page titles, booleans, and metadata labels as descriptions.",
            "A missing selected_description is a useful upstream extraction signal, not a failure when row context is present.",
        ],
    }

    write_json(paths["expander"], result)
    write_jsonl(paths["records_jsonl"], records)
    write_jsonl(paths["missing_jsonl"], missing_records)
    write_json(paths["quality_check"], {"status": STATUS_CHECKED, "quality_status": quality_status, "summary": summary, "checks": checks})

    with as_path(paths["records_csv"]).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "source_visual_citation_label", "linked_part_number", "visual_page_number", "figure", "anchor_record_count", "row_context_cell_count", "description_candidate_count", "selected_description", "description_status", "source_trace_ready"
        ])
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in writer.fieldnames or []})

    return result


def check_source_expander(
    *,
    expander: Any,
    output: Any = None,
    require_quality_pass: bool = False,
    min_linked_visual_parts: int = 1,
    min_row_context_records: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = load_json(expander)
    summary = data.get("summary", {}) if isinstance(data, dict) else {}
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_status is not PASS")
    checks = [
        ("linked_visual_part_count", summary.get("linked_visual_part_count", 0), min_linked_visual_parts, ">="),
        ("row_context_record_count", summary.get("row_context_record_count", 0), min_row_context_records, ">="),
        ("source_trace_ready_count", summary.get("source_trace_ready_count", 0), min_source_trace_ready, ">="),
        ("unsafe_record_count", summary.get("unsafe_record_count", 0), max_unsafe, "<="),
        ("answer_permission_count", summary.get("answer_permission_count", 0), max_answer_permission, "<="),
        ("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), max_source_truth_mutation_allowed, "<="),
        ("write_attempt_count", summary.get("write_attempt_count", 0), max_write_attempts, "<="),
    ]
    check_records: List[Dict[str, Any]] = []
    for name, observed, expected, op in checks:
        try:
            obs = int(observed)
        except Exception:
            obs = 0
        passed = obs >= expected if op == ">=" else obs <= expected
        check_records.append({"name": name, "observed": obs, "expected": f"{op} {expected}", "passed": passed})
        if not passed:
            failures.append(f"{name} check failed: {obs} {op} {expected}")
    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "status": STATUS_CHECKED,
        "quality_status": quality_status,
        "source_expander_quality_status": data.get("quality_status"),
        "summary": summary,
        "checks": check_records,
        "failures": failures,
    }
    if output:
        write_json(output, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net table row context source expander v1")
    p.add_argument("--image-visual-evidence-pack", required=True)
    p.add_argument("--table-route-evidence-packager", required=True)
    p.add_argument("--table-exact-search-adapter", default="")
    p.add_argument("--source-artifact", action="append", default=[])
    p.add_argument("--artifact-root", default="")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--row-context-window", type=int, default=3)
    p.add_argument("--max-json-files", type=int, default=300)
    p.add_argument("--max-artifact-bytes", type=int, default=25_000_000)
    p.add_argument("--min-linked-visual-parts", type=int, default=1)
    p.add_argument("--min-row-context-records", type=int, default=1)
    p.add_argument("--min-source-trace-ready", type=int, default=1)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def check_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net table row context source expander v1")
    p.add_argument("--expander", required=True)
    p.add_argument("--output", required=False, default="")
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--min-linked-visual-parts", type=int, default=1)
    p.add_argument("--min-row-context-records", type=int, default=1)
    p.add_argument("--min-source-trace-ready", type=int, default=1)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_source_expander(
        image_visual_evidence_pack=args.image_visual_evidence_pack,
        table_route_evidence_packager=args.table_route_evidence_packager,
        table_exact_search_adapter=args.table_exact_search_adapter or None,
        source_artifacts=args.source_artifact,
        artifact_root=args.artifact_root or None,
        output_dir=args.output_dir,
        row_context_window=args.row_context_window,
        max_json_files=args.max_json_files,
        max_artifact_bytes=args.max_artifact_bytes,
        min_linked_visual_parts=args.min_linked_visual_parts,
        min_row_context_records=args.min_row_context_records,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    for k in [
        "linked_visual_part_count", "row_context_record_count", "row_context_cell_count", "description_candidate_count", "description_rejected_count", "description_selected_count", "description_missing_count", "source_trace_ready_count", "source_artifact_scan_count", "upstream_hit_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"
    ]:
        print(f"{k}={s.get(k)}")
    print(f"expander={result.get('paths', {}).get('expander')}")
    return 0 if result.get("quality_status") == "PASS" else 1


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = check_parser().parse_args(argv)
    result = check_source_expander(
        expander=args.expander,
        output=args.output or None,
        require_quality_pass=args.require_quality_pass,
        min_linked_visual_parts=args.min_linked_visual_parts,
        min_row_context_records=args.min_row_context_records,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    for k in ["linked_visual_part_count", "row_context_record_count", "description_selected_count", "source_trace_ready_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"]:
        print(f"{k}={s.get(k)}")
    for f in result.get("failures", []):
        print(f"failure={f}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
