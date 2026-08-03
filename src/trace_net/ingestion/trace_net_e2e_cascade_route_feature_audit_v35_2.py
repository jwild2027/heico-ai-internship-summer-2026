from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import statistics
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageFilter
except Exception:  # pragma: no cover - quality check will fail gracefully if Pillow is missing
    Image = None  # type: ignore
    ImageFilter = None  # type: ignore

MODULE = "trace_net_e2e_cascade_route_feature_audit_v35_2"
VERSION = "v35.2"
STATUS_READY = "E2E_CASCADE_ROUTE_FEATURE_AUDIT_READY"
ROUTE_NAMES = {"blank_candidate", "normal_text", "table", "image_visual", "review"}
IMAGE_ROUTE_NAMES = {"image_visual", "diagram_candidate", "technical_drawing_candidate", "callout_diagram_candidate"}


@dataclass(frozen=True)
class PageImageRecord:
    page_number: int
    page_id: str
    filename: str
    zip_member: str
    width: int
    height: int
    sha256_16: str


def _natural_tiff_key(name: str) -> Tuple[int, str]:
    stem = Path(name).stem
    digits = "".join(ch for ch in stem if ch.isdigit())
    if digits:
        return int(digits), name
    return 10**9, name


def _page_id(prefix: str, page_number: int) -> str:
    return f"{prefix}_p{page_number:06d}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _read_manual_diagram_pages(path: Path, page_id_prefix: str) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"manual screened diagram page CSV not found: {path}")
    rows: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = (row.get("page_id") or row.get("Page ID") or row.get("page") or "").strip()
            if not pid:
                page_number_raw = (row.get("page_number") or row.get("page_num") or row.get("Page Number") or "").strip()
                if page_number_raw:
                    try:
                        pid = _page_id(page_id_prefix, int(page_number_raw))
                    except Exception:
                        pid = ""
            if not pid:
                filename = (row.get("filename") or row.get("file") or "").strip()
                digits = "".join(ch for ch in Path(filename).stem if ch.isdigit())
                if digits:
                    pid = _page_id(page_id_prefix, int(digits))
            if pid:
                rows[pid] = dict(row)
    return rows


def _discover_tiff_pages_from_zip(zip_path: Path, page_id_prefix: str) -> List[PageImageRecord]:
    if Image is None:
        raise RuntimeError("Pillow is required to inspect TIFF pages")
    if not zip_path.exists():
        raise FileNotFoundError(f"page bundle ZIP not found: {zip_path}")
    records: List[PageImageRecord] = []
    with zipfile.ZipFile(zip_path) as zf:
        tiff_members = [
            n for n in zf.namelist()
            if n.lower().endswith((".tif", ".tiff")) and not n.endswith("/")
        ]
        tiff_members.sort(key=_natural_tiff_key)
        for idx, member in enumerate(tiff_members, 1):
            raw = zf.read(member)
            sha = hashlib.sha256(raw).hexdigest()[:16]
            with Image.open(io.BytesIO(raw)) as im:
                width, height = im.size
            page_number = _natural_tiff_key(member)[0]
            if page_number == 10**9:
                page_number = idx
            records.append(PageImageRecord(
                page_number=page_number,
                page_id=_page_id(page_id_prefix, page_number),
                filename=Path(member).name,
                zip_member=member,
                width=width,
                height=height,
                sha256_16=sha,
            ))
    return records


def _iter_candidate_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        if isinstance(obj.get("page_id"), str):
            yield obj
        for key in ("route_dispatch_cards", "dispatch_cards", "cards", "records", "pages", "items", "route_candidates"):
            val = obj.get(key)
            if isinstance(val, list):
                for item in val:
                    yield from _iter_candidate_dicts(item)
        # Some reports are dicts keyed by page id.
        for key, val in obj.items():
            if isinstance(key, str) and key.startswith("t_p_") and isinstance(val, dict):
                merged = dict(val)
                merged.setdefault("page_id", key)
                yield from _iter_candidate_dicts(merged)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_candidate_dicts(item)


def _simple_route_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        s = value.strip()
        if not s or s.startswith("{") or s.startswith("["):
            return None
        if s in ROUTE_NAMES or s in IMAGE_ROUTE_NAMES:
            return s
    return None


def _extract_manifest_routes(card: Dict[str, Any]) -> Tuple[Optional[str], List[str], bool]:
    malformed = False
    primary: Optional[str] = None
    routes: List[str] = []

    for key in ("primary_dispatch_route", "primary_route", "selected_route", "route"):
        val = card.get(key)
        simple = _simple_route_string(val)
        if simple:
            if not primary:
                primary = simple
            routes.append(simple)
        elif isinstance(val, str) and val.strip().startswith(("{", "[")):
            malformed = True

    for key in ("dispatch_routes", "allowed_dispatch_routes", "secondary_routes", "routes"):
        val = card.get(key)
        if isinstance(val, list):
            for item in val:
                simple = _simple_route_string(item)
                if simple:
                    routes.append(simple)
                elif isinstance(item, str) and item.strip().startswith(("{", "[")):
                    malformed = True

    policies = card.get("route_policies")
    if isinstance(policies, dict):
        for route_name, policy in policies.items():
            if route_name in ROUTE_NAMES and isinstance(policy, dict):
                if policy.get("is_primary") is True or policy.get("status") == "primary_route_allowed":
                    primary = route_name
                    routes.append(route_name)
                if policy.get("allowed") is True:
                    routes.append(route_name)

    clean_routes = []
    for r in routes:
        if r not in clean_routes:
            clean_routes.append(r)
    return primary, clean_routes, malformed


def _load_route_index(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if not path or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    index: Dict[str, Dict[str, Any]] = {}
    for card in _iter_candidate_dicts(data):
        pid = card.get("page_id")
        if not isinstance(pid, str):
            continue
        primary, routes, malformed = _extract_manifest_routes(card)
        if pid not in index:
            index[pid] = {
                "page_id": pid,
                "manifest_primary_route": primary,
                "manifest_routes": routes,
                "manifest_malformed_route_value": malformed,
            }
        else:
            existing = index[pid]
            existing["manifest_primary_route"] = existing.get("manifest_primary_route") or primary
            merged = list(existing.get("manifest_routes") or [])
            for r in routes:
                if r not in merged:
                    merged.append(r)
            existing["manifest_routes"] = merged
            existing["manifest_malformed_route_value"] = bool(existing.get("manifest_malformed_route_value") or malformed)
    return index


def _load_image_from_zip(zip_path: Path, member: str):
    if Image is None:
        raise RuntimeError("Pillow is required")
    with zipfile.ZipFile(zip_path) as zf:
        raw = zf.read(member)
    return Image.open(io.BytesIO(raw)).convert("L")


def _binary_array(gray, size: int = 192) -> Tuple[List[List[int]], int, int]:
    # Downsample so the audit is fast and repeatable on Windows laptops.
    gray = gray.copy()
    gray.thumbnail((size, size))
    w, h = gray.size
    pix = list(gray.getdata())
    # Black/dark ink threshold for scanned manual pages.
    arr = [[1 if pix[y * w + x] < 220 else 0 for x in range(w)] for y in range(h)]
    return arr, w, h


def _projection_scores(arr: List[List[int]], w: int, h: int) -> Dict[str, Any]:
    total = max(1, w * h)
    ink = sum(sum(row) for row in arr)
    ink_density = ink / total

    row_counts = [sum(row) for row in arr]
    col_counts = [sum(arr[y][x] for y in range(h)) for x in range(w)]

    horizontal_long = sum(1 for c in row_counts if c / max(1, w) >= 0.55)
    vertical_long = sum(1 for c in col_counts if c / max(1, h) >= 0.55)
    horizontal_mid = sum(1 for c in row_counts if c / max(1, w) >= 0.25)
    vertical_mid = sum(1 for c in col_counts if c / max(1, h) >= 0.25)

    row_peak_count = sum(1 for c in row_counts if c / max(1, w) >= 0.08)
    col_peak_count = sum(1 for c in col_counts if c / max(1, h) >= 0.08)

    # Grid-like pages have both repeated horizontal and vertical long-ish lines.
    table_grid_score = min(1.0, (horizontal_long / 12.0) * 0.55 + (vertical_long / 8.0) * 0.45)
    line_structure_score = min(1.0, (horizontal_mid + vertical_mid) / 45.0)
    blank_score = max(0.0, min(1.0, (0.012 - ink_density) / 0.012))

    # A crude text proxy: many row peaks, fewer vertical peaks, moderate ink.
    text_score = 0.0
    if ink_density > 0.01:
        text_score = min(1.0, (row_peak_count / max(1.0, h * 0.45)) * 0.8 + (1.0 - min(1.0, vertical_long / 8.0)) * 0.2)

    return {
        "ink_density": round(ink_density, 6),
        "horizontal_long_line_count": horizontal_long,
        "vertical_long_line_count": vertical_long,
        "horizontal_mid_line_count": horizontal_mid,
        "vertical_mid_line_count": vertical_mid,
        "row_peak_count": row_peak_count,
        "col_peak_count": col_peak_count,
        "table_grid_score": round(table_grid_score, 4),
        "line_structure_score": round(line_structure_score, 4),
        "blank_score": round(blank_score, 4),
        "text_score": round(text_score, 4),
    }


def _connected_components(arr: List[List[int]], w: int, h: int, max_components: int = 600) -> Dict[str, Any]:
    seen = [[False] * w for _ in range(h)]
    comps: List[Tuple[int, int, int, int, int]] = []
    for y in range(h):
        for x in range(w):
            if not arr[y][x] or seen[y][x]:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            minx = maxx = x
            miny = maxy = y
            area = 0
            while stack:
                cx, cy = stack.pop()
                area += 1
                minx = min(minx, cx)
                maxx = max(maxx, cx)
                miny = min(miny, cy)
                maxy = max(maxy, cy)
                for nx, ny in ((cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)):
                    if 0 <= nx < w and 0 <= ny < h and arr[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if area >= 2:
                comps.append((area, minx, miny, maxx, maxy))
                if len(comps) >= max_components:
                    break
        if len(comps) >= max_components:
            break

    large = [c for c in comps if c[0] >= 25]
    wide = [c for c in comps if (c[3] - c[1] + 1) / max(1, w) > 0.15]
    tall = [c for c in comps if (c[4] - c[2] + 1) / max(1, h) > 0.15]
    return {
        "connected_component_count": len(comps),
        "large_component_count": len(large),
        "wide_component_count": len(wide),
        "tall_component_count": len(tall),
    }


def _edge_score(gray) -> Dict[str, Any]:
    if ImageFilter is None:
        return {"edge_density": 0.0}
    small = gray.copy()
    small.thumbnail((192, 192))
    edges = small.filter(ImageFilter.FIND_EDGES)
    vals = list(edges.getdata())
    edge_density = sum(1 for v in vals if v > 40) / max(1, len(vals))
    return {"edge_density": round(edge_density, 6)}


def _score_routes(features: Dict[str, Any]) -> Dict[str, float]:
    ink = _safe_float(features.get("ink_density"))
    blank = _safe_float(features.get("blank_score"))
    text = _safe_float(features.get("text_score"))
    grid = _safe_float(features.get("table_grid_score"))
    line_structure = _safe_float(features.get("line_structure_score"))
    edge = _safe_float(features.get("edge_density"))
    cc = _safe_float(features.get("connected_component_count"))
    hlong = _safe_float(features.get("horizontal_long_line_count"))
    vlong = _safe_float(features.get("vertical_long_line_count"))
    hmid = _safe_float(features.get("horizontal_mid_line_count"))
    vmid = _safe_float(features.get("vertical_mid_line_count"))

    # Deterministic baseline scores. v35.2 is an audit, not yet a final calibrated classifier.
    # The image/diagram affinity is intentionally biased toward high recall: many manual
    # diagrams have lots of small components but *not* table-grid line structure.
    component_score = min(1.0, cc / 260.0)
    non_table_score = 1.0 - min(1.0, grid)
    low_grid_line_score = 1.0 - min(1.0, line_structure)
    edge_score = min(1.0, edge / 0.25)
    moderate_ink_score = 1.0 - min(1.0, abs(ink - 0.065) / 0.09)
    low_horizontal_grid_score = 1.0 - min(1.0, hmid / 15.0)
    low_vertical_grid_score = 1.0 - min(1.0, vmid / 10.0)

    diagram_score = (
        0.30 * component_score
        + 0.18 * non_table_score
        + 0.20 * low_grid_line_score
        + 0.12 * edge_score
        + 0.10 * moderate_ink_score
        + 0.05 * low_horizontal_grid_score
        + 0.05 * low_vertical_grid_score
    )
    diagram_score = max(0.0, min(1.0, diagram_score))

    table_score = min(1.0, grid * 0.75 + min(1.0, (hlong + vlong) / 24.0) * 0.25)
    normal_text_score = min(1.0, text * 0.72 + (1.0 - diagram_score) * 0.16 + (1.0 - table_score) * 0.12)

    # Keep obviously blank pages from getting visual scores due to compression specks.
    if ink < 0.008:
        diagram_score *= 0.15
        table_score *= 0.2
        normal_text_score *= 0.3

    scores = {
        "blank_candidate": round(blank, 4),
        "normal_text": round(normal_text_score, 4),
        "table": round(table_score, 4),
        "image_visual": round(diagram_score, 4),
    }
    return scores


def _pick_route(scores: Dict[str, float]) -> Tuple[str, float, float, bool]:
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_route, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0
    margin = round(top_score - second_score, 4)
    uncertain = margin < 0.12 or top_score < 0.35
    return top_route, round(top_score, 4), margin, uncertain


def _feature_record(zip_path: Path, page: PageImageRecord, actual_diagram_pages: Dict[str, Dict[str, Any]], route_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    gray = _load_image_from_zip(zip_path, page.zip_member)
    arr, w, h = _binary_array(gray)
    features: Dict[str, Any] = {}
    features.update(_projection_scores(arr, w, h))
    features.update(_connected_components(arr, w, h))
    features.update(_edge_score(gray))

    scores = _score_routes(features)
    pred, conf, margin, uncertain = _pick_route(scores)
    actual_label = "diagram" if page.page_id in actual_diagram_pages else "non_diagram"
    route_info = route_index.get(page.page_id, {})
    manifest_routes = route_info.get("manifest_routes") or []
    manifest_image_visual = "image_visual" in manifest_routes or route_info.get("manifest_primary_route") == "image_visual"

    fishnet_action = "accept_route"
    reasons: List[str] = []
    if uncertain:
        fishnet_action = "review_required"
        reasons.append("close_or_low_route_score_margin")
    if pred == "image_visual" and scores.get("table", 0) > 0.55:
        fishnet_action = "dual_route_table_and_visual"
        reasons.append("table_score_competes_with_image_visual")
    if actual_label == "diagram" and pred != "image_visual":
        reasons.append("manual_label_diagram_predicted_non_visual")
    if actual_label == "non_diagram" and pred == "image_visual":
        reasons.append("manual_label_non_diagram_predicted_visual")

    return {
        "schema_version": "trace_net_cascade_route_feature_audit_v35_2_record",
        "page_id": page.page_id,
        "page_number": page.page_number,
        "filename": page.filename,
        "zip_member": page.zip_member,
        "width": page.width,
        "height": page.height,
        "sha256_16": page.sha256_16,
        "manual_label": actual_label,
        "manual_diagram_page": actual_label == "diagram",
        "manifest_primary_route": route_info.get("manifest_primary_route"),
        "manifest_routes": manifest_routes,
        "manifest_image_visual_candidate": manifest_image_visual,
        "manifest_malformed_route_value": bool(route_info.get("manifest_malformed_route_value")),
        "feature_summary": features,
        "route_scores": scores,
        "predicted_primary_route": pred,
        "prediction_confidence": conf,
        "prediction_margin": margin,
        "fishnet_uncertain": uncertain,
        "fishnet_action": fishnet_action,
        "fishnet_reasons": reasons,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "visual_proof_authority": False,
    }


def _confusion(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    tp = fp = tn = fn = 0
    for r in records:
        actual = bool(r.get("manual_diagram_page"))
        pred = r.get("predicted_primary_route") == "image_visual"
        if actual and pred:
            tp += 1
        elif actual and not pred:
            fn += 1
        elif not actual and pred:
            fp += 1
        else:
            tn += 1
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    accuracy = (tp + tn) / max(1, tp + tn + fp + fn)
    return {
        "binary_diagram_confusion_matrix": {
            "true_positive_diagram_predicted_visual": tp,
            "false_positive_non_diagram_predicted_visual": fp,
            "true_negative_non_diagram_predicted_non_visual": tn,
            "false_negative_diagram_predicted_non_visual": fn,
            "total": tp + fp + tn + fn,
        },
        "diagram_precision": round(precision, 4),
        "diagram_recall": round(recall, 4),
        "binary_accuracy": round(accuracy, 4),
    }


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _feature_column_count(records: Sequence[Dict[str, Any]]) -> int:
    keys = set()
    for r in records[:25]:
        keys.update((r.get("feature_summary") or {}).keys())
    return len(keys)


def quality_checks(report: Dict[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool):
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add("source_page_count", report.get("source_page_count"), f">= {args.min_source_pages}", report.get("source_page_count", 0) >= args.min_source_pages)
    add("feature_record_count", report.get("feature_record_count"), f">= {args.min_feature_records}", report.get("feature_record_count", 0) >= args.min_feature_records)
    add("manual_screened_diagram_page_count", report.get("manual_screened_diagram_page_count"), f">= {args.min_manual_screened_diagram_pages}", report.get("manual_screened_diagram_page_count", 0) >= args.min_manual_screened_diagram_pages)
    if args.expected_actual_diagram_pages is not None:
        add("actual_diagram_page_count", report.get("actual_diagram_page_count"), f"== {args.expected_actual_diagram_pages}", report.get("actual_diagram_page_count") == args.expected_actual_diagram_pages)
    add("feature_column_count", report.get("feature_column_count"), f">= {args.min_feature_columns}", report.get("feature_column_count", 0) >= args.min_feature_columns)
    add("confusion_matrix_total", report.get("confusion_matrix_total"), f">= {args.min_confusion_matrix_total}", report.get("confusion_matrix_total", 0) >= args.min_confusion_matrix_total)
    add("label_coverage_count", report.get("label_coverage_count"), f">= {args.min_label_coverage}", report.get("label_coverage_count", 0) >= args.min_label_coverage)
    add("answer_permission_count", report.get("answer_permission_count"), f"<= {args.max_answer_permission_count}", report.get("answer_permission_count", 0) <= args.max_answer_permission_count)
    add("source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count"), f"<= {args.max_source_truth_mutation_allowed}", report.get("source_truth_mutation_allowed_count", 0) <= args.max_source_truth_mutation_allowed)
    if args.require_no_answer_permission:
        add("require_no_answer_permission", report.get("answer_permission_count"), "== 0", report.get("answer_permission_count", 0) == 0)
    return checks


def build_feature_audit(
    *,
    page_bundle_zip: Path,
    route_dispatch_manifest: Optional[Path],
    manual_screened_diagram_pages: Path,
    output_dir: Path,
    page_id_prefix: str,
    max_pages: Optional[int] = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_pages = _discover_tiff_pages_from_zip(page_bundle_zip, page_id_prefix=page_id_prefix)
    if max_pages:
        source_pages = source_pages[:max_pages]
    manual_diagrams = _read_manual_diagram_pages(manual_screened_diagram_pages, page_id_prefix=page_id_prefix)
    route_index = _load_route_index(route_dispatch_manifest)

    records = [_feature_record(page_bundle_zip, p, manual_diagrams, route_index) for p in source_pages]
    confusion = _confusion(records)

    feature_records_path = output_dir / "trace_net_cascade_route_feature_records_v35_2.jsonl"
    confusion_path = output_dir / "trace_net_cascade_route_confusion_matrix_v35_2.json"
    report_path = output_dir / "trace_net_cascade_route_feature_audit_v35_2.json"
    inspect_md_path = output_dir / "trace_net_cascade_route_feature_audit_v35_2.md"

    _write_jsonl(feature_records_path, records)
    confusion_path.write_text(json.dumps(confusion, indent=2, sort_keys=True), encoding="utf-8")

    score_routes = Counter(r.get("predicted_primary_route") for r in records)
    manifest_visual = sum(1 for r in records if r.get("manifest_image_visual_candidate"))
    actual_diagram = sum(1 for r in records if r.get("manual_diagram_page"))
    fishnet_uncertain = sum(1 for r in records if r.get("fishnet_uncertain"))
    fishnet_actions = Counter(r.get("fishnet_action") for r in records)
    malformed = sum(1 for r in records if r.get("manifest_malformed_route_value"))

    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY,
        "quality_status": "UNSET",
        "source_page_count": len(source_pages),
        "route_index_page_count": len(route_index),
        "route_candidate_count": len(source_pages),
        "manual_screened_diagram_page_count": len(manual_diagrams),
        "actual_diagram_page_count": actual_diagram,
        "feature_record_count": len(records),
        "feature_column_count": _feature_column_count(records),
        "label_coverage_count": len(records),
        "route_manifest_image_visual_candidate_count": manifest_visual,
        "predicted_route_counts": dict(score_routes),
        "fishnet_uncertain_count": fishnet_uncertain,
        "fishnet_action_counts": dict(fishnet_actions),
        "manifest_malformed_route_value_count": malformed,
        "confusion_matrix_total": confusion["binary_diagram_confusion_matrix"]["total"],
        "diagram_precision": confusion["diagram_precision"],
        "diagram_recall": confusion["diagram_recall"],
        "binary_accuracy": confusion["binary_accuracy"],
        "binary_diagram_confusion_matrix": confusion["binary_diagram_confusion_matrix"],
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "visual_proof_authority_violation_count": 0,
        "contract": {
            "feature_audit_only": True,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "database_writes": False,
            "llava_called": False,
            "gemma_called": False,
            "manual_labels_used_for_audit_not_proof": True,
        },
        "report_path": str(report_path),
        "feature_records_jsonl_path": str(feature_records_path),
        "confusion_matrix_json_path": str(confusion_path),
        "inspect_md_path": str(inspect_md_path),
        "sample_records": records[:10],
    }

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    inspect_md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# TRACE-Net Cascade Route Feature Audit v35.2",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    for k in [
        "source_page_count", "actual_diagram_page_count", "feature_record_count", "feature_column_count",
        "route_manifest_image_visual_candidate_count", "diagram_precision", "diagram_recall", "binary_accuracy",
        "fishnet_uncertain_count", "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {k}: {report.get(k)}")
    lines += ["", "## Confusion matrix"]
    for k, v in (report.get("binary_diagram_confusion_matrix") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Contract", "- Feature audit only; it does not mutate source truth.", "- No LLaVA/Gemma calls are made in this stage.", "- Manual labels are used as route calibration/evaluation labels, not proof for answers.", ""]
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TRACE-Net Cascade Route Feature Audit v35.2")
    p.add_argument("--page-bundle-zip", required=True, type=Path)
    p.add_argument("--route-dispatch-manifest", required=False, type=Path)
    p.add_argument("--manual-screened-diagram-pages", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--page-id-prefix", default="t_p_120_1176")
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--min-source-pages", type=int, default=1)
    p.add_argument("--min-feature-records", type=int, default=1)
    p.add_argument("--min-manual-screened-diagram-pages", type=int, default=1)
    p.add_argument("--expected-actual-diagram-pages", type=int, default=None)
    p.add_argument("--min-feature-columns", type=int, default=10)
    p.add_argument("--min-confusion-matrix-total", type=int, default=1)
    p.add_argument("--min-label-coverage", type=int, default=1)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    report = build_feature_audit(
        page_bundle_zip=args.page_bundle_zip,
        route_dispatch_manifest=args.route_dispatch_manifest,
        manual_screened_diagram_pages=args.manual_screened_diagram_pages,
        output_dir=args.output_dir,
        page_id_prefix=args.page_id_prefix,
        max_pages=args.max_pages,
    )
    checks = quality_checks(report, args)
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    Path(report["report_path"]).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    Path(report["inspect_md_path"]).write_text(_render_markdown(report), encoding="utf-8")

    print("TRACE-Net Cascade Route Feature Audit v35.2")
    print(f" Status: {report['status']}")
    print(f" Quality status: {quality_status}")
    for k in [
        "source_page_count", "feature_record_count", "manual_screened_diagram_page_count", "actual_diagram_page_count",
        "route_manifest_image_visual_candidate_count", "predicted_route_counts", "diagram_precision", "diagram_recall",
        "binary_accuracy", "fishnet_uncertain_count", "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        print(f" {k}: {report.get(k)}")
    print(f" report_path: {report['report_path']}")
    print(f" feature_records_jsonl_path: {report['feature_records_jsonl_path']}")
    return 0 if (not args.quality or quality_status == "PASS") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
