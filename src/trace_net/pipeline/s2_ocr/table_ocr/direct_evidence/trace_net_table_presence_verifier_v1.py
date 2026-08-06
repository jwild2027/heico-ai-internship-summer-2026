"""TRACE-Net Table Presence Verifier v1.

Read-only hybrid table-presence gate for TRACE-Net table localization.

This module addresses the failure mode where weak/legacy table candidates cause
non-table pages (chapter/image/text pages, figures, paragraph columns, or page
furniture) to receive table bboxes. It verifies table presence before a bbox is
allowed to flow into localization/extraction.

The verifier combines:
- route/dispatch context when available
- structure bbox selector decisions
- visual line/row/column diagnostics
- scoped row/cell/value counts
- OCR enrichment hints such as part-number matches
- optional source-image ink/layout metrics inside the selected bbox

The output is a routing/QA artifact, not source truth. It can suppress false
positive table candidates and recommend normal_text/image_visual/blank routing,
but it never mutates source truth and never grants answer authority.

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
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_table_presence_verifier_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_presence_verifier_v1_quality"
STATUS_BUILT = "TABLE_PRESENCE_VERIFIER_BUILT"
STATUS_NOT_READY = "TABLE_PRESENCE_VERIFIER_NOT_READY"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_presence_verifier")

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{2,6}(?:-\d{1,4})?\b")
TABLE_WORD_RE = re.compile(r"\b(table|item|part|part\s*number|nomenclature|qty|quantity|effectivity|units?|assy|figure|find\s*no|model)\b", re.I)
NON_TABLE_WORD_RE = re.compile(r"\b(chapter|introduction|description|operation|warning|caution|figure|photo|illustration|aircraft|diagram)\b", re.I)

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

TABLE_ROUTES = {"table", "table_candidate", "table_route"}
ANTI_TABLE_ROUTES = {"blank_candidate", "blank", "image_visual", "visual", "normal_text", "text", "normal"}

INCOMPLETE_VISUAL_TABLE_FLAGS = {
    "visual_candidate_cuts_table_columns",
    "visual_candidate_cuts_table_rows",
    "visual_candidate_over_tightened_area",
    "visual_candidate_too_short_for_row_count",
    "visual_candidate_header_band_not_preserved",
    "visual_candidate_low_input_x_overlap",
    "visual_candidate_low_input_y_overlap",
    "visual_candidate_quality_not_pass",
    "visual_candidate_not_refined",
    "visual_refinement_not_applied",
}

WEAK_TABLE_STRUCTURE_FLAGS = {
    "weak_horizontal_table_signal",
    "weak_vertical_table_signal",
    "visual_candidate_weak_row_structure",
    "visual_candidate_weak_column_structure",
    "weak_row_structure_flag",
    "weak_column_structure_flag",
    "localized_bbox_still_broad",
}


def table_route_challenge(structure: Mapping[str, Any], visual: Mapping[str, Any] | None, scoped: Mapping[str, Any] | None) -> dict[str, Any]:
    """Challenge route-primary table candidates with independent completeness evidence.

    A table route is useful routing authority, but it must not automatically turn
    visually incomplete or weakly localized candidates into confirmed tables. This
    helper keeps the page in the table workflow when evidence is still table-like,
    but demotes it to weak/review and recommends a conservative full-table
    enclosure if the visual candidate appears to cut columns/rows/header bands.
    """
    flags = set(str(v) for v in as_list(structure.get("review_flags")) + as_list((visual or {}).get("review_flags")))
    issues: list[str] = []
    for flag in sorted(flags & INCOMPLETE_VISUAL_TABLE_FLAGS):
        issues.append(flag)
    for flag in sorted(flags & WEAK_TABLE_STRUCTURE_FLAGS):
        issues.append(flag)
    if structure.get("structure_visual_candidate_rejected") is True:
        issues.append("structure_rejected_visual_candidate")
    selected_source = str(structure.get("structure_selected_bbox_source") or "")
    if selected_source == "conservative_input_bbox_fallback":
        issues.append("conservative_input_bbox_selected")
    width_ratio = as_float(structure.get("visual_to_input_width_ratio"))
    height_ratio = as_float(structure.get("visual_to_input_height_ratio"))
    area_ratio = as_float(structure.get("visual_to_input_area_ratio"))
    if width_ratio is not None and width_ratio < 0.72:
        issues.append("visual_candidate_width_under_table_extent")
    if height_ratio is not None and height_ratio < 0.55:
        issues.append("visual_candidate_height_under_table_extent")
    if area_ratio is not None and area_ratio < 0.28:
        issues.append("visual_candidate_area_under_table_extent")

    row_count = as_int((scoped or {}).get("scoped_row_count") or structure.get("scoped_row_count"), 0)
    cell_count = as_int((scoped or {}).get("scoped_cell_count") or structure.get("scoped_cell_count"), 0)
    value_count = as_int((scoped or {}).get("scoped_value_record_count") or structure.get("scoped_value_record_count"), 0)
    strong_legacy_table_volume = row_count >= 20 and cell_count >= 100 and value_count >= 100

    # Severe means a visually tight candidate should not be trusted as the table
    # crop. It does not necessarily mean the page is not a table; it means we
    # should reconstruct/enclose the full table conservatively before extraction.
    severe = (
        "structure_rejected_visual_candidate" in issues
        or "visual_candidate_cuts_table_columns" in issues
        or "visual_candidate_cuts_table_rows" in issues
        or "visual_candidate_header_band_not_preserved" in issues
        or "visual_candidate_width_under_table_extent" in issues
        or "visual_candidate_height_under_table_extent" in issues
    )
    weak_structure = bool(flags & WEAK_TABLE_STRUCTURE_FLAGS)
    challenged = bool(severe or (weak_structure and len(issues) >= 2))
    return {
        "table_route_challenged": challenged,
        "table_route_challenge_severe": bool(severe),
        "table_route_challenge_issues": list(dict.fromkeys(issues)),
        "strong_legacy_table_volume": strong_legacy_table_volume,
        "full_table_enclosure_recommended": challenged,
    }


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


def as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def normalize_route(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def normalize_bbox(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        if all(k in value for k in ("x0", "y0", "x1", "y1")):
            x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("x0", "y0", "x1", "y1"))
        elif all(k in value for k in ("left", "top", "right", "bottom")):
            x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("left", "top", "right", "bottom"))
        elif all(k in value for k in ("x", "y", "width", "height")):
            x = as_float(value.get("x")); y = as_float(value.get("y")); w = as_float(value.get("width")); h = as_float(value.get("height"))
            if x is None or y is None or w is None or h is None:
                return None
            x0, y0, x1, y1 = x, y, x + w, y + h
        else:
            return None
        coord = str(value.get("coordinate_system") or "pixels")
    elif isinstance(value, (list, tuple)) and len(value) >= 4:
        x0, y0, x1, y1 = (as_float(v) for v in value[:4])
        coord = "pixels"
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
        "coordinate_system": coord,
    }


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


def get_records(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(r) for r in payload if isinstance(r, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(r) for r in value if isinstance(r, Mapping)]
    return []


def structure_records(payload: Any) -> list[dict[str, Any]]:
    return get_records(payload, ("table_structure_bbox_localizer_records", "records", "structure_records"))


def visual_records(payload: Any) -> list[dict[str, Any]]:
    return get_records(payload, ("table_visual_bbox_localizer_records", "records", "localized_records"))


def scoped_records(payload: Any) -> list[dict[str, Any]]:
    return get_records(payload, ("scoped_table_records", "records", "table_bbox_scoped_cell_records"))


def ocr_records(payload: Any) -> list[dict[str, Any]]:
    return get_records(payload, ("table_ocr_bbox_enrichment_cards", "cards", "records"))


ROUTE_LIST_KEYS = (
    "page_route_cards",
    "route_dispatch_cards",
    "processor_contract_cards",
    "route_dispatch_coverage_cards",
    "route_contract_audit_cards",
    "page_route_records",
    "page_routes",
    "route_records",
    "dispatch_records",
    "records",
    "routes",
    "pages",
)

PAGE_ID_KEYS = (
    "page_id",
    "source_page_id",
    "source_page",
    "page",
    "page_key",
    "page_identifier",
)

PRIMARY_ROUTE_KEYS = (
    "primary_route",
    "primary_dispatch_route",
    "primary_processor_route",
    "primary_allowed_route",
    "selected_primary_route",
    "assigned_primary_route",
    "page_primary_route",
    "dispatch_primary_route",
    "route",
    "page_route",
    "assigned_route",
    "route_name",
    "route_type",
)

SECONDARY_ROUTE_KEYS = (
    "secondary_routes",
    "allowed_secondary_routes",
    "allowed_routes",
    "candidate_routes",
    "dispatch_routes",
    "routes",
)


def route_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(r) for r in payload if isinstance(r, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ROUTE_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(r) for r in value if isinstance(r, Mapping)]
    # Some manifests are maps keyed by page_id.
    pages = payload.get("page_route_manifest") or payload.get("route_manifest") or payload.get("page_routes_by_id")
    if isinstance(pages, Mapping):
        out = []
        for page_id, data in pages.items():
            if isinstance(data, Mapping):
                rec = dict(data)
                rec.setdefault("page_id", page_id)
                out.append(rec)
        return out
    return []


def first_route_value(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return None


def infer_primary_route(record: Mapping[str, Any]) -> Any:
    direct = first_route_value(record, PRIMARY_ROUTE_KEYS)
    if direct not in (None, "", []):
        return direct
    # Route dispatch manifests sometimes keep route options as small records.
    for key in SECONDARY_ROUTE_KEYS:
        routes = record.get(key)
        if not isinstance(routes, list):
            continue
        for item in routes:
            if not isinstance(item, Mapping):
                continue
            role = normalize_route(item.get("route_role") or item.get("dispatch_role") or item.get("policy_status") or item.get("route_policy_status"))
            is_primary = bool(item.get("is_primary") or item.get("primary") or item.get("selected_as_primary"))
            if is_primary or role in {"primary", "primary_route_allowed", "primary_dispatch_allowed", "selected_primary"}:
                return first_route_value(item, PRIMARY_ROUTE_KEYS) or item.get("name") or item.get("route")
    return None


def infer_secondary_routes(record: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for key in SECONDARY_ROUTE_KEYS:
        value = record.get(key)
        for item in as_list(value):
            if isinstance(item, Mapping):
                route = first_route_value(item, PRIMARY_ROUTE_KEYS) or item.get("name") or item.get("route")
            else:
                route = item
            norm = normalize_route(route)
            if norm and norm not in out:
                out.append(norm)
    return out


def build_page_route_index(*payloads: Any) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for rec in route_records(payload):
            page_id = str(first_route_value(rec, PAGE_ID_KEYS) or "")
            if not page_id:
                continue
            route = infer_primary_route(rec)
            normalized_route = normalize_route(route)
            secondary = infer_secondary_routes(rec)
            existing = index.get(page_id)
            # Prefer explicit primary routes. Do not let a dispatch card without a parseable
            # primary route overwrite a good page-route-manifest entry.
            if existing and not normalized_route:
                merged_secondary = list(dict.fromkeys([*existing.get("secondary_routes", []), *secondary]))
                existing["secondary_routes"] = merged_secondary
                continue
            if existing and existing.get("primary_route") and not normalized_route:
                continue
            if existing and existing.get("primary_route") and normalized_route == existing.get("primary_route"):
                merged_secondary = list(dict.fromkeys([*existing.get("secondary_routes", []), *secondary]))
                existing["secondary_routes"] = merged_secondary
                continue
            index[page_id] = {
                "page_id": page_id,
                "primary_route": normalized_route,
                "raw_primary_route": route,
                "secondary_routes": secondary,
                "route_record": rec,
            }
    return index


def index_by_page_and_table(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_table: dict[str, dict[str, Any]] = {}
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        table_id = str(record.get("table_id") or "")
        page_id = str(record.get("page_id") or "")
        if table_id:
            by_table[table_id] = record
        if page_id:
            by_page[page_id].append(record)
    return by_table, by_page


def match_aux_record(candidate: Mapping[str, Any], by_table: Mapping[str, dict[str, Any]], by_page: Mapping[str, list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, str]:
    table_id = str(candidate.get("table_id") or "")
    page_id = str(candidate.get("page_id") or "")
    if table_id and table_id in by_table:
        return by_table[table_id], "table_id"
    page_records = list(by_page.get(page_id, []))
    if len(page_records) == 1:
        return page_records[0], "page_id_single_record"
    if page_records:
        ready = [r for r in page_records if r.get("bbox_scoped_extraction_ready") or r.get("crop_candidate_ready") or r.get("table_localization_quality_pass")]
        if len(ready) == 1:
            return ready[0], "page_id_single_ready_record"
        if ready:
            return ready[0], "page_id_first_ready_record"
        return page_records[0], "page_id_first_record"
    return None, "no_match"


def collect_text(*records: Mapping[str, Any] | None) -> str:
    chunks: list[str] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        for key in ("text", "normalized_text", "ocr_text", "page_text", "table_type", "caption", "title", "heading"):
            if record.get(key):
                chunks.append(normalize_text(record.get(key)))
        for value in as_list(record.get("value_records"))[:80]:
            if isinstance(value, Mapping):
                chunks.append(normalize_text(value.get("normalized_text") or value.get("text") or value.get("value")))
        for value in as_list(record.get("cells"))[:80]:
            if isinstance(value, Mapping):
                chunks.append(normalize_text(value.get("normalized_text") or value.get("text") or value.get("value")))
    return " ".join(c for c in chunks if c)


def image_path_candidates(page_id: str, image_root: str | Path | None = None, explicit: Any = None, max_scan: int = 25000) -> Path | None:
    paths = []
    if explicit:
        paths.append(Path(str(explicit)))
    root = Path(image_root) if image_root else None
    for p in paths:
        if p.exists():
            return p
        if root and not p.is_absolute() and (root / p).exists():
            return root / p
    if not root or not root.exists() or not page_id:
        return None
    # Use page number suffix and full page_id as fuzzy matches.
    suffix = ""
    m = re.search(r"p(\d{3,6})\b", page_id)
    if m:
        suffix = m.group(1)
    scanned = 0
    for path in root.rglob("*"):
        if scanned >= max_scan:
            break
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        scanned += 1
        name = path.name.lower()
        if page_id.lower() in name or (suffix and suffix in name):
            return path
    return None


def run_count(mask: list[bool]) -> int:
    count = 0
    in_run = False
    for v in mask:
        if v and not in_run:
            count += 1
            in_run = True
        elif not v:
            in_run = False
    return count


def compute_ink_metrics(image_path: str | Path | None, bbox: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not image_path:
        return {"image_available": False, "ink_metrics_available": False}
    try:
        from PIL import Image, ImageStat
    except Exception:
        return {"image_available": False, "ink_metrics_available": False, "image_error": "pillow_unavailable"}
    p = Path(image_path)
    if not p.exists():
        return {"image_available": False, "ink_metrics_available": False, "image_error": "image_not_found"}
    try:
        with Image.open(p) as img:
            rgb = img.convert("RGB")
            width, height = rgb.size
            box = normalize_bbox(bbox) if bbox else None
            if box:
                x0 = max(0, min(width - 1, int(round(float(box["x0"])))))
                y0 = max(0, min(height - 1, int(round(float(box["y0"])))))
                x1 = max(x0 + 1, min(width, int(round(float(box["x1"])))))
                y1 = max(y0 + 1, min(height, int(round(float(box["y1"])))))
                crop = rgb.crop((x0, y0, x1, y1))
            else:
                crop = rgb
            # Downsample for cheap deterministic metrics.
            max_dim = 650
            cw, ch = crop.size
            scale = min(1.0, max_dim / max(cw, ch)) if max(cw, ch) else 1.0
            if scale < 1.0:
                crop = crop.resize((max(1, int(cw * scale)), max(1, int(ch * scale))))
            gray = crop.convert("L")
            pixels = list(gray.getdata())
            if not pixels:
                return {"image_available": True, "ink_metrics_available": False, "image_path": str(p)}
            dark = [v < 205 for v in pixels]
            very_dark = [v < 110 for v in pixels]
            dark_ratio = sum(dark) / len(dark)
            very_dark_ratio = sum(very_dark) / len(very_dark)
            gw, gh = gray.size
            rows = []
            cols = []
            for y in range(gh):
                row = dark[y * gw:(y + 1) * gw]
                rows.append(sum(row) / max(1, gw))
            for x in range(gw):
                total = 0
                for y in range(gh):
                    total += dark[y * gw + x]
                cols.append(total / max(1, gh))
            row_band_runs = run_count([v > 0.025 for v in rows])
            col_band_runs = run_count([v > 0.025 for v in cols])
            horizontal_rule_runs = run_count([v > 0.32 for v in rows])
            vertical_rule_runs = run_count([v > 0.22 for v in cols])
            stat = ImageStat.Stat(crop)
            # Average channel variance is a cheap photo/figure proxy.
            color_variance = round(sum(stat.var) / max(1, len(stat.var)), 6)
            image_like_color_variance = color_variance > 900 and dark_ratio > 0.12 and horizontal_rule_runs < 4 and vertical_rule_runs < 4
            return {
                "image_available": True,
                "ink_metrics_available": True,
                "image_path": str(p),
                "image_width": width,
                "image_height": height,
                "ink_dark_pixel_ratio": round(dark_ratio, 6),
                "ink_very_dark_pixel_ratio": round(very_dark_ratio, 6),
                "ink_row_band_run_count": row_band_runs,
                "ink_column_band_run_count": col_band_runs,
                "ink_horizontal_rule_run_count": horizontal_rule_runs,
                "ink_vertical_rule_run_count": vertical_rule_runs,
                "ink_color_variance": color_variance,
                "image_like_color_region": bool(image_like_color_variance),
            }
    except Exception as exc:
        return {"image_available": False, "ink_metrics_available": False, "image_path": str(p), "image_error": type(exc).__name__}


def signal_score(structure: Mapping[str, Any], visual: Mapping[str, Any] | None, scoped: Mapping[str, Any] | None, ocr: Mapping[str, Any] | None, route: Mapping[str, Any] | None, ink: Mapping[str, Any], text: str) -> tuple[int, int, list[str], list[str], str]:
    positive = 0
    negative = 0
    pos: list[str] = []
    neg: list[str] = []
    route_name = normalize_route((route or {}).get("primary_route"))

    def add_pos(points: int, name: str) -> None:
        nonlocal positive
        positive += points
        pos.append(name)

    def add_neg(points: int, name: str) -> None:
        nonlocal negative
        negative += points
        neg.append(name)

    if route_name in TABLE_ROUTES:
        add_pos(4, "route_primary_table")
    elif route_name in ANTI_TABLE_ROUTES:
        add_neg(8, f"route_primary_{route_name}")

    row_count = as_int((scoped or {}).get("scoped_row_count") or structure.get("scoped_row_count"), 0)
    cell_count = as_int((scoped or {}).get("scoped_cell_count") or structure.get("scoped_cell_count"), 0)
    value_count = as_int((scoped or {}).get("scoped_value_record_count") or structure.get("scoped_value_record_count"), 0)
    if row_count >= 20:
        add_pos(3, "many_scoped_rows")
    elif row_count >= 8:
        add_pos(1, "some_scoped_rows")
    if cell_count >= 100:
        add_pos(3, "many_scoped_cells")
    elif cell_count >= 30:
        add_pos(1, "some_scoped_cells")
    if value_count >= 100:
        add_pos(2, "many_scoped_values")

    h_runs = as_int(structure.get("horizontal_line_run_count") or (visual or {}).get("horizontal_line_run_count"), 0)
    v_runs = as_int(structure.get("vertical_line_run_count") or (visual or {}).get("vertical_line_run_count"), 0)
    row_bands = as_int(structure.get("row_band_run_count") or (visual or {}).get("row_band_run_count"), 0)
    col_bands = as_int(structure.get("column_band_run_count") or (visual or {}).get("column_band_run_count"), 0)
    if h_runs >= 8 or row_bands >= 18:
        add_pos(2, "visual_repeated_row_structure")
    elif h_runs >= 2 or row_bands >= 8:
        add_pos(1, "weak_visual_row_structure")
    if v_runs >= 6 or col_bands >= 12:
        add_pos(2, "visual_repeated_column_structure")
    elif v_runs >= 2 or col_bands >= 6:
        add_pos(1, "weak_visual_column_structure")
    if structure.get("multi_column_vertical_merge_applied") or (visual or {}).get("multi_column_vertical_merge_applied"):
        add_pos(1, "split_column_table_geometry")
    if structure.get("structure_selected_bbox_ready"):
        add_pos(1, "structure_selected_bbox_ready")
    if structure.get("structure_visual_candidate_accepted"):
        add_pos(1, "structure_validated_visual_candidate")

    part_matches = as_int((ocr or {}).get("part_number_ocr_match_count") or (ocr or {}).get("part_number_match_count"), 0)
    matched_ocr = as_int((ocr or {}).get("matched_ocr_bbox_count") or (ocr or {}).get("matched_ocr_token_count"), 0)
    if part_matches > 0 or PART_NUMBER_RE.search(text):
        add_pos(2, "part_number_or_code_table_tokens")
    if matched_ocr >= 12:
        add_pos(1, "many_matched_ocr_tokens")
    if TABLE_WORD_RE.search(text):
        add_pos(1, "table_header_vocabulary")

    if ink.get("ink_metrics_available"):
        ink_rows = as_int(ink.get("ink_row_band_run_count"), 0)
        ink_cols = as_int(ink.get("ink_column_band_run_count"), 0)
        ink_h = as_int(ink.get("ink_horizontal_rule_run_count"), 0)
        ink_v = as_int(ink.get("ink_vertical_rule_run_count"), 0)
        if ink_rows >= 12:
            add_pos(2, "ink_repeated_row_bands")
        elif ink_rows >= 5:
            add_pos(1, "ink_some_row_bands")
        if ink_cols >= 8:
            add_pos(2, "ink_repeated_column_bands")
        elif ink_cols >= 4:
            add_pos(1, "ink_some_column_bands")
        if ink_h >= 3:
            add_pos(1, "ink_horizontal_rules")
        if ink_v >= 3:
            add_pos(1, "ink_vertical_rules")
        if ink.get("image_like_color_region"):
            add_neg(4, "image_like_color_region")
        if ink_rows < 4 and ink_cols < 3 and row_count < 8 and cell_count < 30:
            add_neg(4, "weak_hybrid_ink_table_signal")

    flags = set(str(v) for v in as_list(structure.get("review_flags")) + as_list((visual or {}).get("review_flags")))
    if "weak_horizontal_table_signal" in flags or "visual_candidate_weak_row_structure" in flags:
        add_neg(2, "weak_row_structure_flag")
    if "weak_vertical_table_signal" in flags or "visual_candidate_weak_column_structure" in flags:
        add_neg(2, "weak_column_structure_flag")
    if "localized_bbox_still_broad" in flags and row_count < 12:
        add_neg(2, "broad_bbox_without_table_structure")
    if NON_TABLE_WORD_RE.search(text) and positive < 9:
        add_neg(2, "non_table_document_vocabulary")

    if route_name in {"blank_candidate", "blank"}:
        recommended = "blank_candidate"
    elif route_name in {"image_visual", "visual"} or "image_like_color_region" in neg:
        recommended = "image_visual"
    elif route_name in {"normal_text", "text", "normal"} or "non_table_document_vocabulary" in neg:
        recommended = "normal_text"
    else:
        recommended = "table"
    return positive, negative, pos, neg, recommended


def decide_presence(
    positive: int,
    negative: int,
    route: Mapping[str, Any] | None,
    recommended_route: str,
    route_challenge: Mapping[str, Any] | None = None,
) -> tuple[str, float, bool]:
    route_name = normalize_route((route or {}).get("primary_route"))
    route_challenge = route_challenge or {}
    if route_name in ANTI_TABLE_ROUTES and route_name not in TABLE_ROUTES:
        confidence = min(0.98, 0.65 + max(0, negative - positive) * 0.035)
        return "not_table", round(confidence, 6), False

    net = positive - negative

    # A route-primary table is no longer absolute. If independent structure QA
    # says the visual candidate cuts columns/rows/header bands or needed broad
    # fallback, keep it in the table workflow but demote to weak/review so the
    # next stage reconstructs a safer full-table enclosure instead of trusting a
    # tight partial crop.
    if route_name in TABLE_ROUTES and route_challenge.get("table_route_challenged"):
        if positive >= 8 and net >= 1:
            return "weak_table", 0.74 if route_challenge.get("table_route_challenge_severe") else 0.8, True
        return "not_table", 0.62, False

    if positive >= 11 and net >= 5:
        return "confirmed_table", round(min(0.97, 0.62 + net * 0.035), 6), True
    if positive >= 7 and net >= 2:
        return "weak_table", round(min(0.82, 0.50 + net * 0.035), 6), True
    if recommended_route != "table" and negative >= positive:
        return "not_table", round(min(0.95, 0.55 + (negative - positive) * 0.04), 6), False
    if positive >= 6 and net >= 0:
        return "weak_table", 0.55, True
    return "not_table", round(min(0.92, 0.58 + max(0, negative - positive) * 0.035), 6), False


def make_presence_record(
    structure: Mapping[str, Any],
    *,
    visual: Mapping[str, Any] | None,
    scoped: Mapping[str, Any] | None,
    ocr: Mapping[str, Any] | None,
    route: Mapping[str, Any] | None,
    image_root: str | Path | None = None,
    max_image_files_scanned: int = 25000,
) -> dict[str, Any]:
    page_id = str(structure.get("page_id") or "")
    table_id = str(structure.get("table_id") or "")
    selected_box = normalize_bbox(structure.get("structure_selected_table_bbox") or structure.get("localized_table_bbox") or structure.get("input_bbox"))
    explicit_image = structure.get("image_path") or (visual or {}).get("image_path") or (ocr or {}).get("image_path")
    image_path = image_path_candidates(page_id, image_root=image_root, explicit=explicit_image, max_scan=max_image_files_scanned)
    ink = compute_ink_metrics(image_path, selected_box)
    text = collect_text(structure, visual, scoped, ocr)
    positive, negative, pos_signals, neg_signals, recommended_route = signal_score(structure, visual, scoped, ocr, route, ink, text)
    route_challenge = table_route_challenge(structure, visual, scoped)
    label, confidence, allowed = decide_presence(positive, negative, route, recommended_route, route_challenge)
    if label == "not_table" and recommended_route == "table":
        # If the score says not-table but there is no better route signal, send to review instead of rerouting hard.
        recommended_route = "review_table_candidate"
    route_name = normalize_route((route or {}).get("primary_route"))
    suppressed = not allowed
    review_flags = list(dict.fromkeys([*as_list(structure.get("review_flags")), *as_list((visual or {}).get("review_flags")), *neg_signals]))
    if route_challenge.get("table_route_challenged"):
        review_flags.append("route_primary_table_challenged_by_structure_qa")
        if route_challenge.get("full_table_enclosure_recommended"):
            review_flags.append("full_table_enclosure_reconstruction_recommended")
    if suppressed:
        review_flags.append("table_candidate_suppressed_by_presence_verifier")
    if route_name in ANTI_TABLE_ROUTES:
        review_flags.append("upstream_route_not_table")
    downstream_action = "allow_table_bbox_localization"
    if label == "weak_table" and route_challenge.get("full_table_enclosure_recommended"):
        downstream_action = "allow_table_workflow_but_reconstruct_full_table_enclosure"
    elif suppressed:
        downstream_action = "suppress_table_bbox_and_review_or_reroute"
    return {
        "schema_version": SCHEMA_VERSION,
        "table_presence_verifier_id": stable_id("tblpresence", page_id, table_id, label, positive, negative),
        "page_id": page_id,
        "table_id": table_id,
        "structure_bbox_localizer_id": structure.get("table_structure_bbox_localizer_id"),
        "visual_bbox_localizer_id": (visual or {}).get("visual_bbox_localizer_id"),
        "bbox_scoped_table_record_id": (scoped or {}).get("scoped_table_record_id"),
        "table_ocr_bbox_enrichment_id": (ocr or {}).get("table_ocr_bbox_enrichment_id"),
        "route_primary": route_name or None,
        "route_raw_primary": (route or {}).get("raw_primary_route"),
        "table_presence_label": label,
        "table_presence_confidence": confidence,
        "table_presence_positive_score": positive,
        "table_presence_negative_score": negative,
        "positive_table_signals": pos_signals,
        "negative_table_signals": neg_signals,
        "table_localization_allowed": allowed,
        "table_localization_suppressed": suppressed,
        "recommended_route": "table" if allowed else recommended_route,
        "recommended_downstream_action": downstream_action,
        "false_positive_table_candidate": suppressed,
        "table_route_challenged": bool(route_challenge.get("table_route_challenged")),
        "table_route_challenge_severe": bool(route_challenge.get("table_route_challenge_severe")),
        "table_route_challenge_issues": route_challenge.get("table_route_challenge_issues") or [],
        "full_table_enclosure_recommended": bool(route_challenge.get("full_table_enclosure_recommended")),
        "strong_legacy_table_volume": bool(route_challenge.get("strong_legacy_table_volume")),
        "selected_bbox_for_presence_check": selected_box,
        "structure_selected_bbox_source": structure.get("structure_selected_bbox_source"),
        "structure_visual_candidate_accepted": structure.get("structure_visual_candidate_accepted"),
        "structure_visual_candidate_rejected": structure.get("structure_visual_candidate_rejected"),
        "scoped_row_count": as_int((scoped or {}).get("scoped_row_count") or structure.get("scoped_row_count"), 0),
        "scoped_cell_count": as_int((scoped or {}).get("scoped_cell_count") or structure.get("scoped_cell_count"), 0),
        "scoped_value_record_count": as_int((scoped or {}).get("scoped_value_record_count") or structure.get("scoped_value_record_count"), 0),
        "part_number_ocr_match_count": as_int((ocr or {}).get("part_number_ocr_match_count") or (ocr or {}).get("part_number_match_count"), 0),
        "matched_ocr_bbox_count": as_int((ocr or {}).get("matched_ocr_bbox_count") or (ocr or {}).get("matched_ocr_token_count"), 0),
        **ink,
        "review_required": bool(review_flags) or suppressed,
        "review_flags": list(dict.fromkeys(str(f) for f in review_flags if f)),
        "record_role": "hybrid_table_presence_gate",
        "routing_only": True,
        "retrieval_only": True,
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
        "unsafe_table_presence_verifier_record": False,
    }


def unsafe_record_count(records: list[Mapping[str, Any]]) -> int:
    count = 0
    for record in records:
        if record.get("unsafe_table_presence_verifier_record"):
            count += 1
            continue
        for key in SAFETY_FALSE_KEYS:
            if record.get(key) is True:
                count += 1
                break
    return count


def summarize(records: list[dict[str, Any]], *, structure_payload: Any = None, visual_payload: Any = None, scoped_payload: Any = None, ocr_payload: Any = None, route_index: Mapping[str, Any] | None = None, source_counts: Mapping[str, int] | None = None) -> dict[str, Any]:
    label_counts = Counter(r.get("table_presence_label") for r in records)
    route_counts = Counter(r.get("recommended_route") for r in records)
    source_counts = source_counts or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "source_table_structure_bbox_localizer_quality_status": payload_quality_status(structure_payload),
        "source_table_visual_bbox_localizer_quality_status": payload_quality_status(visual_payload),
        "source_table_bbox_scoped_cell_extraction_quality_status": payload_quality_status(scoped_payload),
        "source_table_ocr_bbox_enrichment_quality_status": payload_quality_status(ocr_payload),
        "source_structure_record_count": source_counts.get("structure", len(records)),
        "source_visual_record_count": source_counts.get("visual", 0),
        "source_scoped_table_record_count": source_counts.get("scoped", 0),
        "source_ocr_enrichment_card_count": source_counts.get("ocr", 0),
        "route_manifest_page_count": len(route_index or {}),
        "table_presence_record_count": len(records),
        "table_presence_decision_record_count": sum(1 for r in records if r.get("table_presence_label") in {"confirmed_table", "weak_table", "not_table"}),
        "confirmed_table_record_count": label_counts.get("confirmed_table", 0),
        "weak_table_record_count": label_counts.get("weak_table", 0),
        "not_table_record_count": label_counts.get("not_table", 0),
        "table_localization_allowed_record_count": sum(1 for r in records if r.get("table_localization_allowed")),
        "table_localization_suppressed_record_count": sum(1 for r in records if r.get("table_localization_suppressed")),
        "false_positive_table_candidate_count": sum(1 for r in records if r.get("false_positive_table_candidate")),
        "table_route_confirmed_count": sum(1 for r in records if r.get("route_primary") in TABLE_ROUTES and r.get("table_presence_label") == "confirmed_table"),
        "table_route_challenged_count": sum(1 for r in records if r.get("table_route_challenged")),
        "table_route_demoted_to_weak_count": sum(1 for r in records if r.get("route_primary") in TABLE_ROUTES and r.get("table_presence_label") == "weak_table"),
        "full_table_enclosure_recommended_count": sum(1 for r in records if r.get("full_table_enclosure_recommended")),
        "non_table_route_suppressed_count": sum(1 for r in records if r.get("route_primary") in ANTI_TABLE_ROUTES and r.get("table_localization_suppressed")),
        "image_visual_reroute_recommended_count": route_counts.get("image_visual", 0),
        "normal_text_reroute_recommended_count": route_counts.get("normal_text", 0),
        "blank_candidate_suppressed_count": route_counts.get("blank_candidate", 0),
        "review_table_candidate_count": route_counts.get("review_table_candidate", 0),
        "image_available_record_count": sum(1 for r in records if r.get("image_available")),
        "hybrid_ink_metrics_record_count": sum(1 for r in records if r.get("ink_metrics_available")),
        "weak_hybrid_ink_table_signal_count": sum(1 for r in records if "weak_hybrid_ink_table_signal" in r.get("negative_table_signals", [])),
        "image_like_color_region_count": sum(1 for r in records if r.get("image_like_color_region")),
        "unsafe_table_presence_verifier_record_count": unsafe_record_count(records),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed") or r.get("can_mutate_source_truth")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempted")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempted")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempted")),
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

    add("source_structure_records", summary.get("source_structure_record_count", 0) >= get("min_source_structure_records", 1), f"records={summary.get('source_structure_record_count', 0)} minimum={get('min_source_structure_records', 1)}")
    add("presence_records", summary.get("table_presence_record_count", 0) >= get("min_presence_records", 1), f"records={summary.get('table_presence_record_count', 0)} minimum={get('min_presence_records', 1)}")
    add("presence_decisions", summary.get("table_presence_decision_record_count", 0) >= get("min_presence_decisions", 1), f"decisions={summary.get('table_presence_decision_record_count', 0)} minimum={get('min_presence_decisions', 1)}")
    add("localization_allowed_min", summary.get("table_localization_allowed_record_count", 0) >= get("min_localization_allowed_records", 0), f"allowed={summary.get('table_localization_allowed_record_count', 0)} minimum={get('min_localization_allowed_records', 0)}")
    add("suppressed_min", summary.get("table_localization_suppressed_record_count", 0) >= get("min_suppressed_candidates", 0), f"suppressed={summary.get('table_localization_suppressed_record_count', 0)} minimum={get('min_suppressed_candidates', 0)}")
    add("unsafe_records", summary.get("unsafe_table_presence_verifier_record_count", 0) <= get("max_unsafe_records", 0), f"unsafe={summary.get('unsafe_table_presence_verifier_record_count', 0)} max={get('max_unsafe_records', 0)}")
    add("answer_permission", summary.get("answer_permission_count", 0) <= get("max_answer_permission_count", 0), f"count={summary.get('answer_permission_count', 0)} max={get('max_answer_permission_count', 0)}")
    add("source_truth_mutation_allowed", summary.get("source_truth_mutation_allowed_count", 0) <= get("max_source_truth_mutation_allowed", 0), f"count={summary.get('source_truth_mutation_allowed_count', 0)} max={get('max_source_truth_mutation_allowed', 0)}")
    add("postgres_writes", summary.get("postgres_write_attempt_count", 0) == 0, f"count={summary.get('postgres_write_attempt_count', 0)}")
    add("qdrant_writes", summary.get("qdrant_write_attempt_count", 0) == 0, f"count={summary.get('qdrant_write_attempt_count', 0)}")
    add("opensearch_writes", summary.get("opensearch_write_attempt_count", 0) == 0, f"count={summary.get('opensearch_write_attempt_count', 0)}")
    if get("require_table_structure_bbox_localizer_quality_pass", False):
        add("source_table_structure_bbox_localizer_quality_pass", summary.get("source_table_structure_bbox_localizer_quality_status") == "PASS", f"status={summary.get('source_table_structure_bbox_localizer_quality_status')}")
    if get("require_table_visual_bbox_localizer_quality_pass", False):
        add("source_table_visual_bbox_localizer_quality_pass", summary.get("source_table_visual_bbox_localizer_quality_status") == "PASS", f"status={summary.get('source_table_visual_bbox_localizer_quality_status')}")
    if get("require_table_bbox_scoped_cell_extraction_quality_pass", False):
        add("source_table_bbox_scoped_cell_extraction_quality_pass", summary.get("source_table_bbox_scoped_cell_extraction_quality_status") == "PASS", f"status={summary.get('source_table_bbox_scoped_cell_extraction_quality_status')}")
    if get("require_table_ocr_bbox_enrichment_quality_pass", False):
        add("source_table_ocr_bbox_enrichment_quality_pass", summary.get("source_table_ocr_bbox_enrichment_quality_status") == "PASS", f"status={summary.get('source_table_ocr_bbox_enrichment_quality_status')}")
    if get("require_all_records_have_presence_decision", False):
        add("all_records_have_presence_decision", summary.get("table_presence_decision_record_count", 0) == summary.get("table_presence_record_count", -1), f"decisions={summary.get('table_presence_decision_record_count', 0)} records={summary.get('table_presence_record_count', -1)}")
    status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    return status, checks


def build_report(
    *,
    table_structure_bbox_localizer_path: str | Path,
    table_visual_bbox_localizer_path: str | Path | None = None,
    table_bbox_scoped_cell_extraction_path: str | Path | None = None,
    table_ocr_bbox_enrichment_path: str | Path | None = None,
    page_route_manifest_path: str | Path | None = None,
    route_dispatch_manifest_path: str | Path | None = None,
    image_root: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    max_image_files_scanned: int = 25000,
    thresholds: Mapping[str, Any] | argparse.Namespace | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    structure_payload = read_json(table_structure_bbox_localizer_path, default={})
    visual_payload = read_json(table_visual_bbox_localizer_path, default={})
    scoped_payload = read_json(table_bbox_scoped_cell_extraction_path, default={})
    ocr_payload = read_json(table_ocr_bbox_enrichment_path, default={})
    route_payload = read_json(page_route_manifest_path, default={})
    dispatch_payload = read_json(route_dispatch_manifest_path, default={})

    structures = structure_records(structure_payload)
    visuals = visual_records(visual_payload)
    scoped = scoped_records(scoped_payload)
    ocrs = ocr_records(ocr_payload)
    visual_by_table, visual_by_page = index_by_page_and_table(visuals)
    scoped_by_table, scoped_by_page = index_by_page_and_table(scoped)
    ocr_by_table, ocr_by_page = index_by_page_and_table(ocrs)
    routes = build_page_route_index(route_payload, dispatch_payload)

    records: list[dict[str, Any]] = []
    for structure in structures:
        visual, _ = match_aux_record(structure, visual_by_table, visual_by_page)
        scoped_record, _ = match_aux_record(structure, scoped_by_table, scoped_by_page)
        ocr_record, _ = match_aux_record(structure, ocr_by_table, ocr_by_page)
        page_id = str(structure.get("page_id") or "")
        route = routes.get(page_id)
        records.append(make_presence_record(
            structure,
            visual=visual,
            scoped=scoped_record,
            ocr=ocr_record,
            route=route,
            image_root=image_root,
            max_image_files_scanned=max_image_files_scanned,
        ))

    summary = summarize(records, structure_payload=structure_payload, visual_payload=visual_payload, scoped_payload=scoped_payload, ocr_payload=ocr_payload, route_index=routes, source_counts={"structure": len(structures), "visual": len(visuals), "scoped": len(scoped), "ocr": len(ocrs)})
    quality_status, checks = quality_checks(summary, thresholds)
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "quality": {"schema_version": QUALITY_SCHEMA_VERSION, "status": quality_status, "checks": checks},
        "table_presence_verifier_records": records,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_table_presence_verifier_v1.json"
    records_path = out / "trace_net_table_presence_verifier_v1_records.jsonl"
    allowed_path = out / "trace_net_table_presence_verifier_v1_allowed_table_records.jsonl"
    suppressed_path = out / "trace_net_table_presence_verifier_v1_suppressed_candidates.jsonl"
    summary_path = out / "trace_net_table_presence_verifier_v1_summary.json"
    quality_path = out / "trace_net_table_presence_verifier_v1_quality.json"
    manifest_path = out / "trace_net_table_presence_verifier_v1_manifest.json"
    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(allowed_path, [r for r in records if r.get("table_localization_allowed")])
    write_jsonl(suppressed_path, [r for r in records if r.get("table_localization_suppressed")])
    write_json(summary_path, summary)
    if write_quality:
        write_json(quality_path, {"schema_version": QUALITY_SCHEMA_VERSION, "status": quality_status, "summary": summary, "checks": checks})
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "allowed_table_records_path": str(allowed_path),
        "suppressed_candidates_path": str(suppressed_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_paths": {
            "table_structure_bbox_localizer": str(table_structure_bbox_localizer_path),
            "table_visual_bbox_localizer": str(table_visual_bbox_localizer_path) if table_visual_bbox_localizer_path else None,
            "table_bbox_scoped_cell_extraction": str(table_bbox_scoped_cell_extraction_path) if table_bbox_scoped_cell_extraction_path else None,
            "table_ocr_bbox_enrichment": str(table_ocr_bbox_enrichment_path) if table_ocr_bbox_enrichment_path else None,
            "page_route_manifest": str(page_route_manifest_path) if page_route_manifest_path else None,
            "route_dispatch_manifest": str(route_dispatch_manifest_path) if route_dispatch_manifest_path else None,
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
    report["quality_path"] = str(quality_path)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net table presence verifier v1 artifacts.")
    p.add_argument("--table-structure-bbox-localizer", required=True)
    p.add_argument("--table-visual-bbox-localizer")
    p.add_argument("--table-bbox-scoped-cell-extraction")
    p.add_argument("--table-ocr-bbox-enrichment")
    p.add_argument("--page-route-manifest")
    p.add_argument("--route-dispatch-manifest")
    p.add_argument("--image-root")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--max-image-files-scanned", type=int, default=25000)
    p.add_argument("--min-source-structure-records", type=int, default=1)
    p.add_argument("--min-presence-records", type=int, default=1)
    p.add_argument("--min-presence-decisions", type=int, default=1)
    p.add_argument("--min-localization-allowed-records", type=int, default=0)
    p.add_argument("--min-suppressed-candidates", type=int, default=0)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-table-structure-bbox-localizer-quality-pass", action="store_true")
    p.add_argument("--require-table-visual-bbox-localizer-quality-pass", action="store_true")
    p.add_argument("--require-table-bbox-scoped-cell-extraction-quality-pass", action="store_true")
    p.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    p.add_argument("--require-all-records-have-presence-decision", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_report(
        table_structure_bbox_localizer_path=args.table_structure_bbox_localizer,
        table_visual_bbox_localizer_path=args.table_visual_bbox_localizer,
        table_bbox_scoped_cell_extraction_path=args.table_bbox_scoped_cell_extraction,
        table_ocr_bbox_enrichment_path=args.table_ocr_bbox_enrichment,
        page_route_manifest_path=args.page_route_manifest,
        route_dispatch_manifest_path=args.route_dispatch_manifest,
        image_root=args.image_root,
        output_dir=args.output_dir,
        max_image_files_scanned=args.max_image_files_scanned,
        thresholds=args,
        write_quality=args.quality,
    )
    summary = report.get("summary", {})
    print("TRACE-Net Table Presence Verifier v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "source_structure_record_count",
        "source_visual_record_count",
        "source_scoped_table_record_count",
        "source_ocr_enrichment_card_count",
        "route_manifest_page_count",
        "table_presence_record_count",
        "confirmed_table_record_count",
        "weak_table_record_count",
        "not_table_record_count",
        "table_localization_allowed_record_count",
        "table_localization_suppressed_record_count",
        "false_positive_table_candidate_count",
        "table_route_challenged_count",
        "table_route_demoted_to_weak_count",
        "full_table_enclosure_recommended_count",
        "non_table_route_suppressed_count",
        "image_visual_reroute_recommended_count",
        "normal_text_reroute_recommended_count",
        "review_table_candidate_count",
        "hybrid_ink_metrics_record_count",
        "weak_hybrid_ink_table_signal_count",
        "image_like_color_region_count",
        "unsafe_table_presence_verifier_record_count",
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
