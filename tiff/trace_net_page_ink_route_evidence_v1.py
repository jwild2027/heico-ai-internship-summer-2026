from __future__ import annotations

import argparse
import io
import json
import math
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PIL import Image, ImageOps

try:  # numpy is already used by the image/OCR stack in most TRACE-Net environments.
    import numpy as np
except Exception:  # pragma: no cover - exercised only in very constrained environments.
    np = None  # type: ignore[assignment]

SCHEMA_VERSION = "trace_net_page_ink_route_evidence_v1"
QUALITY_SCHEMA_VERSION = "trace_net_page_ink_route_evidence_v1_quality"
PASS = "PASS"
FAIL = "FAIL"

ROUTE_BLANK = "blank_candidate"
ROUTE_TEXT = "normal_text"
ROUTE_TABLE = "table"
ROUTE_IMAGE = "image_visual"
ROUTE_REVIEW = "review"

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass
class InkRouteEvidenceThresholds:
    min_ink_evidence_cards: int = 1
    min_source_page_ink_evidence_cards: int = 1
    min_image_analyzed_cards: int = 1
    max_image_read_error_cards: int = 0
    max_unsafe_ink_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_page_route_manifest_quality_pass: bool = False
    require_no_answer_permission: bool = False


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except Exception:
        return default


def _round6(value: float) -> float:
    return round(float(value), 6)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def infer_page_number_from_value(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value)
    # Prefer explicit p000013 style ids, then any 6/8-digit TIFF stem, then trailing digits.
    patterns = [r"p(\d{6})", r"metadata_page_(\d+)", r"(\d{8})", r"(\d{6})", r"(\d+)$"]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            num = _safe_int(m.group(1), -1)
            if num >= 0:
                return num
    return None


def canonical_page_id(page_number: int) -> str:
    return f"t_p_route_p{page_number:06d}"


def canonical_source_page_id(page_number: int) -> str:
    return f"metadata_page_{page_number:06d}"


def metadata_image_filename(page_number: int, ext: str = ".tif") -> str:
    return f"{page_number:08d}{ext}"


def parse_metadata_zip_index(metadata_zip: Path) -> Tuple[Dict[int, str], Dict[str, Any]]:
    page_image_by_number: Dict[int, str] = {}
    metadata: Dict[str, Any] = {
        "metadata_zip_path": str(metadata_zip),
        "metadata_zip_available": False,
        "metadata_zip_image_count": 0,
    }
    if not metadata_zip or not Path(metadata_zip).exists():
        return page_image_by_number, metadata

    with zipfile.ZipFile(metadata_zip) as zf:
        names = zf.namelist()
        metadata["metadata_zip_available"] = True
        metadata["metadata_xml_present"] = any(Path(name).name.lower() == "metadata.xml" for name in names)
        image_names = [name for name in names if Path(name).suffix.lower() in IMAGE_EXTENSIONS]
        image_names.sort()
        metadata["metadata_zip_image_count"] = len(image_names)
        for idx, name in enumerate(image_names, start=1):
            page_number = infer_page_number_from_value(Path(name).stem) or idx
            # If duplicate numeric stems appear, keep the first sorted image.
            page_image_by_number.setdefault(page_number, name)
    return page_image_by_number, metadata


def collect_route_pages(page_route_manifest: Optional[Path], metadata_zip: Optional[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    route_pages: List[Dict[str, Any]] = []
    source_metadata: Dict[str, Any] = {}

    if page_route_manifest and Path(page_route_manifest).exists():
        payload = load_json(Path(page_route_manifest))
        source_metadata["page_route_manifest_path"] = str(page_route_manifest)
        source_metadata["page_route_manifest_quality_status"] = payload.get("quality_status")
        for card in payload.get("page_route_cards") or []:
            page_number = card.get("page_number")
            if page_number is None:
                page_number = infer_page_number_from_value(card.get("source_page_id")) or infer_page_number_from_value(card.get("page_id"))
            route_pages.append({
                "page_id": card.get("page_id") or (canonical_page_id(_safe_int(page_number)) if page_number else None),
                "source_page_id": card.get("source_page_id") or (canonical_source_page_id(_safe_int(page_number)) if page_number else None),
                "page_number": _safe_int(page_number) if page_number is not None else None,
                "page_route_primary_route": card.get("primary_route"),
                "page_route_secondary_routes": card.get("secondary_routes") or [],
                "page_route_confidence": card.get("route_confidence"),
                "page_route_safe_for_routing": card.get("safe_for_routing"),
            })

    if not route_pages and metadata_zip and Path(metadata_zip).exists():
        page_image_by_number, metadata = parse_metadata_zip_index(Path(metadata_zip))
        source_metadata.update(metadata)
        for page_number in sorted(page_image_by_number):
            route_pages.append({
                "page_id": canonical_page_id(page_number),
                "source_page_id": canonical_source_page_id(page_number),
                "page_number": page_number,
                "page_route_primary_route": None,
                "page_route_secondary_routes": [],
                "page_route_confidence": None,
                "page_route_safe_for_routing": True,
            })
    return route_pages, source_metadata


def find_image_path(image_root: Optional[Path], page: Mapping[str, Any]) -> Optional[Path]:
    if not image_root:
        return None
    root = Path(image_root)
    if not root.exists():
        return None

    candidates: List[Path] = []
    page_number = page.get("page_number")
    if page_number is not None:
        num = _safe_int(page_number)
        for ext in [".tif", ".tiff", ".png", ".jpg", ".jpeg"]:
            candidates.append(root / metadata_image_filename(num, ext))
            candidates.append(root / f"{num:06d}{ext}")
            candidates.append(root / f"p{num:06d}{ext}")
    for key in ["page_id", "source_page_id"]:
        val = page.get(key)
        if val:
            for ext in [".tif", ".tiff", ".png", ".jpg", ".jpeg"]:
                candidates.append(root / f"{val}{ext}")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Last resort: one recursive pass for a numeric TIFF name.
    if page_number is not None:
        name = metadata_image_filename(_safe_int(page_number))
        matches = list(root.rglob(name))[:1]
        if matches:
            return matches[0]
    return None


def open_page_image(
    page: Mapping[str, Any],
    image_root: Optional[Path],
    metadata_zip: Optional[Path],
    metadata_index: Mapping[int, str],
) -> Tuple[Optional[Image.Image], Dict[str, Any]]:
    page_number = _safe_int(page.get("page_number"), -1)
    details: Dict[str, Any] = {
        "image_source": None,
        "image_path": None,
        "metadata_zip_member": None,
        "image_read_error": None,
    }

    image_path = find_image_path(image_root, page)
    if image_path:
        try:
            img = Image.open(image_path)
            img.load()
            details.update({"image_source": "image_root", "image_path": str(image_path)})
            return img, details
        except Exception as exc:
            details["image_read_error"] = f"image_root_error:{type(exc).__name__}:{exc}"

    if metadata_zip and Path(metadata_zip).exists() and page_number in metadata_index:
        member = metadata_index[page_number]
        try:
            with zipfile.ZipFile(metadata_zip) as zf:
                data = zf.read(member)
            img = Image.open(io.BytesIO(data))
            img.load()
            details.update({"image_source": "metadata_zip", "metadata_zip_member": member, "image_read_error": None})
            return img, details
        except Exception as exc:
            details["image_read_error"] = f"metadata_zip_error:{type(exc).__name__}:{exc}"

    if not details.get("image_read_error"):
        details["image_read_error"] = "image_not_found"
    return None, details


def _resize_for_analysis(gray: Image.Image, max_side: int) -> Tuple[Image.Image, float]:
    width, height = gray.size
    if max(width, height) <= max_side:
        return gray, 1.0
    scale = max_side / float(max(width, height))
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return gray.resize(new_size, Image.Resampling.BILINEAR), scale


def _contiguous_runs(mask: Sequence[bool]) -> List[Tuple[int, int]]:
    runs: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for idx, val in enumerate(mask):
        if val and start is None:
            start = idx
        elif not val and start is not None:
            runs.append((start, idx - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def _line_runs_from_projection(binary: Any, axis: str, min_coverage_ratio: float) -> List[Tuple[int, int, float]]:
    if np is None:
        return []
    if axis == "horizontal":
        projection = binary.mean(axis=1)
    else:
        projection = binary.mean(axis=0)
    mask = projection >= float(min_coverage_ratio)
    runs: List[Tuple[int, int, float]] = []
    for start, end in _contiguous_runs(mask.tolist()):
        coverage = float(projection[start:end + 1].max()) if end >= start else 0.0
        runs.append((int(start), int(end), coverage))
    return runs


def _sample_component_count(binary: Any, max_components: int = 20000) -> Tuple[int, int, int]:
    if np is None:
        return 0, 0, 0
    # Downsampled binary only. Use 8-neighbor connected components in pure Python.
    h, w = binary.shape
    visited = np.zeros((h, w), dtype=bool)
    ys, xs = np.nonzero(binary)
    component_count = 0
    large_component_count = 0
    small_component_count = 0
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if visited[y0, x0]:
            continue
        component_count += 1
        if component_count > max_components:
            break
        stack = [(y0, x0)]
        visited[y0, x0] = True
        size = 0
        while stack:
            y, x = stack.pop()
            size += 1
            for yy in (y - 1, y, y + 1):
                if yy < 0 or yy >= h:
                    continue
                for xx in (x - 1, x, x + 1):
                    if xx < 0 or xx >= w or visited[yy, xx] or not binary[yy, xx]:
                        continue
                    visited[yy, xx] = True
                    stack.append((yy, xx))
        if size >= max(20, int(0.0025 * h * w)):
            large_component_count += 1
        elif size <= max(8, int(0.0005 * h * w)):
            small_component_count += 1
    return component_count, large_component_count, small_component_count


def analyze_image_ink(
    img: Image.Image,
    threshold: int = 220,
    max_analysis_side: int = 1200,
    component_analysis_side: int = 350,
) -> Dict[str, Any]:
    if np is None:
        raise RuntimeError("numpy is required for trace_net_page_ink_route_evidence_v1 image analysis")
    original_width, original_height = img.size
    gray = ImageOps.grayscale(img)
    analysis_gray, scale = _resize_for_analysis(gray, max_analysis_side)
    arr = np.asarray(analysis_gray, dtype=np.uint8)
    binary = arr < int(threshold)
    total_pixels = int(binary.size) or 1
    ink_pixels = int(binary.sum())
    ink_density = ink_pixels / total_pixels
    blank_space_ratio = 1.0 - ink_density

    horizontal_runs = _line_runs_from_projection(binary, "horizontal", min_coverage_ratio=0.35)
    vertical_runs = _line_runs_from_projection(binary, "vertical", min_coverage_ratio=0.35)
    strong_horizontal_runs = [run for run in horizontal_runs if run[2] >= 0.55]
    strong_vertical_runs = [run for run in vertical_runs if run[2] >= 0.55]

    intersections = 0
    if horizontal_runs and vertical_runs:
        for h_start, h_end, _ in horizontal_runs[:150]:
            y = (h_start + h_end) // 2
            for v_start, v_end, _ in vertical_runs[:150]:
                x = (v_start + v_end) // 2
                y0, y1 = max(0, y - 1), min(binary.shape[0], y + 2)
                x0, x1 = max(0, x - 1), min(binary.shape[1], x + 2)
                if bool(binary[y0:y1, x0:x1].any()):
                    intersections += 1

    comp_gray, _ = _resize_for_analysis(gray, component_analysis_side)
    comp_arr = np.asarray(comp_gray, dtype=np.uint8)
    comp_binary = comp_arr < int(threshold)
    component_count, large_component_count, small_component_count = _sample_component_count(comp_binary)

    h_count = len(horizontal_runs)
    v_count = len(vertical_runs)
    strong_h_count = len(strong_horizontal_runs)
    strong_v_count = len(strong_vertical_runs)

    table_grid_likelihood = min(1.0, (min(h_count, 10) / 10.0) * 0.35 + (min(v_count, 8) / 8.0) * 0.35 + (min(intersections, 50) / 50.0) * 0.30)
    if strong_h_count >= 2 and strong_v_count >= 2 and intersections >= 4:
        table_grid_likelihood = max(table_grid_likelihood, 0.82)
    elif h_count >= 2 and v_count >= 1:
        table_grid_likelihood = max(table_grid_likelihood, 0.45)

    blank_likelihood = max(0.0, min(1.0, 1.0 - (ink_density / 0.035)))
    if ink_density < 0.003 and h_count == 0 and v_count == 0:
        blank_likelihood = 1.0

    text_likelihood = 0.0
    if 0.003 <= ink_density <= 0.18:
        text_likelihood = min(1.0, 0.35 + min(small_component_count, 80) / 120.0 + min(component_count, 120) / 300.0)
    if table_grid_likelihood > 0.75:
        text_likelihood *= 0.75

    diagram_likelihood = min(1.0, large_component_count / 6.0 + (ink_density / 0.20) * 0.25)
    if table_grid_likelihood > 0.75:
        diagram_likelihood *= 0.60

    if blank_likelihood >= 0.85:
        ink_primary_route = ROUTE_BLANK
    elif table_grid_likelihood >= 0.62:
        ink_primary_route = ROUTE_TABLE
    elif diagram_likelihood >= 0.55:
        ink_primary_route = ROUTE_IMAGE
    elif text_likelihood >= 0.45:
        ink_primary_route = ROUTE_TEXT
    else:
        ink_primary_route = ROUTE_REVIEW

    return {
        "image_width": int(original_width),
        "image_height": int(original_height),
        "analysis_width": int(analysis_gray.size[0]),
        "analysis_height": int(analysis_gray.size[1]),
        "analysis_scale": _round6(scale),
        "ink_pixel_count": ink_pixels,
        "analysis_pixel_count": total_pixels,
        "ink_density": _round6(ink_density),
        "blank_space_ratio": _round6(blank_space_ratio),
        "horizontal_line_count": h_count,
        "vertical_line_count": v_count,
        "strong_horizontal_line_count": strong_h_count,
        "strong_vertical_line_count": strong_v_count,
        "intersection_count": int(intersections),
        "connected_component_count": int(component_count),
        "large_connected_component_count": int(large_component_count),
        "small_connected_component_count": int(small_component_count),
        "blank_likelihood": _round6(blank_likelihood),
        "text_likelihood": _round6(text_likelihood),
        "table_grid_likelihood": _round6(table_grid_likelihood),
        "diagram_likelihood": _round6(diagram_likelihood),
        "ink_primary_route": ink_primary_route,
    }


def build_ink_evidence_card(
    page: Mapping[str, Any],
    image_root: Optional[Path],
    metadata_zip: Optional[Path],
    metadata_index: Mapping[int, str],
    threshold: int,
    max_analysis_side: int,
    component_analysis_side: int,
) -> Dict[str, Any]:
    page_number = _safe_int(page.get("page_number"), -1)
    card: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "page_id": page.get("page_id") or (canonical_page_id(page_number) if page_number >= 0 else None),
        "source_page_id": page.get("source_page_id") or (canonical_source_page_id(page_number) if page_number >= 0 else None),
        "page_number": page_number if page_number >= 0 else None,
        "page_route_primary_route": page.get("page_route_primary_route"),
        "page_route_secondary_routes": page.get("page_route_secondary_routes") or [],
        "page_route_confidence": page.get("page_route_confidence"),
        "page_route_safe_for_routing": page.get("page_route_safe_for_routing"),
        "image_analyzed": False,
        "image_read_error": None,
        "ink_route_evidence_status": "IMAGE_NOT_ANALYZED",
        "safe_for_routing": True,
        "unsafe_ink_card": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "routing_reasons": [],
        "review_flags": [],
        "recommended_actions": [],
    }
    img, image_details = open_page_image(page, image_root, metadata_zip, metadata_index)
    card.update(image_details)
    if img is None:
        card["image_read_error"] = image_details.get("image_read_error") or "image_not_found"
        card["ink_route_evidence_status"] = "IMAGE_READ_ERROR"
        card["review_flags"].append("image_not_available_for_ink_route_evidence")
        card["recommended_actions"].append("resolve_source_page_image_before_ink_routing")
        return card

    try:
        metrics = analyze_image_ink(
            img,
            threshold=threshold,
            max_analysis_side=max_analysis_side,
            component_analysis_side=component_analysis_side,
        )
        card.update(metrics)
        card["image_analyzed"] = True
        card["ink_route_evidence_status"] = "INK_ROUTE_EVIDENCE_BUILT"
        if metrics["ink_primary_route"] == ROUTE_BLANK:
            card["routing_reasons"].append("low_ink_density_supports_blank_route")
        if metrics["ink_primary_route"] == ROUTE_TABLE:
            card["routing_reasons"].append("line_intersection_evidence_supports_table_route")
        if metrics["ink_primary_route"] == ROUTE_IMAGE:
            card["routing_reasons"].append("large_component_evidence_supports_image_visual_route")
        if metrics["ink_primary_route"] == ROUTE_TEXT:
            card["routing_reasons"].append("component_density_supports_normal_text_route")
        if metrics.get("table_grid_likelihood", 0.0) >= 0.45 and page.get("page_route_primary_route") != ROUTE_TABLE:
            card["review_flags"].append("ink_table_signal_differs_from_page_route_manifest")
        if metrics.get("blank_likelihood", 0.0) >= 0.85 and page.get("page_route_primary_route") not in [None, ROUTE_BLANK]:
            card["review_flags"].append("ink_blank_signal_differs_from_page_route_manifest")
    except Exception as exc:
        card["image_read_error"] = f"ink_analysis_error:{type(exc).__name__}:{exc}"
        card["ink_route_evidence_status"] = "INK_ANALYSIS_ERROR"
        card["review_flags"].append("ink_analysis_error")
        card["recommended_actions"].append("inspect_page_image_and_ink_thresholds")
    return card


def evaluate_quality(report: Mapping[str, Any], thresholds: Optional[InkRouteEvidenceThresholds] = None) -> Dict[str, Any]:
    thresholds = thresholds or InkRouteEvidenceThresholds()
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else report

    ink_evidence_card_count = _safe_int(summary.get("ink_evidence_card_count"))
    source_page_ink_evidence_card_count = _safe_int(summary.get("source_page_ink_evidence_card_count"))
    image_analyzed_card_count = _safe_int(summary.get("image_analyzed_card_count"))
    image_read_error_card_count = _safe_int(summary.get("image_read_error_card_count"))
    unsafe_ink_card_count = _safe_int(summary.get("unsafe_ink_card_count"))
    answer_permission_count = _safe_int(summary.get("answer_permission_count"))
    source_truth_mutation_allowed_count = _safe_int(summary.get("source_truth_mutation_allowed_count"))
    artifact_detector_quality_status = summary.get("artifact_detector_quality_status")
    page_route_manifest_quality_status = summary.get("page_route_manifest_quality_status")

    checks: Dict[str, bool] = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_ink_evidence_cards_met": ink_evidence_card_count >= thresholds.min_ink_evidence_cards,
        "min_source_page_ink_evidence_cards_met": source_page_ink_evidence_card_count >= thresholds.min_source_page_ink_evidence_cards,
        "min_image_analyzed_cards_met": image_analyzed_card_count >= thresholds.min_image_analyzed_cards,
        "image_read_error_cards_within_limit": image_read_error_card_count <= thresholds.max_image_read_error_cards,
        "unsafe_ink_cards_within_limit": unsafe_ink_card_count <= thresholds.max_unsafe_ink_cards,
        "answer_permission_within_limit": answer_permission_count <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": source_truth_mutation_allowed_count <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_page_route_manifest_quality_pass:
        checks["page_route_manifest_quality_pass"] = page_route_manifest_quality_status == PASS
    if thresholds.require_no_answer_permission:
        checks["no_answer_permission"] = answer_permission_count == 0

    quality_fail_reasons = [name for name, ok in checks.items() if not ok]
    quality_status = PASS if not quality_fail_reasons else FAIL
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "source_schema_version": report.get("schema_version"),
        "quality_status": quality_status,
        "status": quality_status,
        "checks": checks,
        "quality_fail_reasons": quality_fail_reasons,
        "ink_evidence_card_count": ink_evidence_card_count,
        "source_page_ink_evidence_card_count": source_page_ink_evidence_card_count,
        "image_analyzed_card_count": image_analyzed_card_count,
        "image_read_error_card_count": image_read_error_card_count,
        "unsafe_ink_card_count": unsafe_ink_card_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "artifact_detector_quality_status": artifact_detector_quality_status,
        "page_route_manifest_quality_status": page_route_manifest_quality_status,
    }


def build_page_ink_route_evidence_report(
    page_route_manifest: Optional[Path],
    output_dir: Path,
    metadata_zip: Optional[Path] = None,
    image_root: Optional[Path] = None,
    max_pages: Optional[int] = None,
    threshold: int = 220,
    max_analysis_side: int = 1200,
    component_analysis_side: int = 350,
    thresholds: Optional[InkRouteEvidenceThresholds] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    route_pages, source_metadata = collect_route_pages(page_route_manifest, metadata_zip)
    metadata_index, metadata_zip_summary = parse_metadata_zip_index(Path(metadata_zip)) if metadata_zip else ({}, {})

    if max_pages is not None and max_pages > 0:
        route_pages = route_pages[:max_pages]

    ink_cards: List[Dict[str, Any]] = []
    for page in route_pages:
        ink_cards.append(build_ink_evidence_card(
            page,
            image_root=Path(image_root) if image_root else None,
            metadata_zip=Path(metadata_zip) if metadata_zip else None,
            metadata_index=metadata_index,
            threshold=threshold,
            max_analysis_side=max_analysis_side,
            component_analysis_side=component_analysis_side,
        ))

    route_counts = Counter(card.get("ink_primary_route") for card in ink_cards if card.get("ink_primary_route"))
    status_counts = Counter(card.get("ink_route_evidence_status") for card in ink_cards)
    page_route_manifest_quality_status = source_metadata.get("page_route_manifest_quality_status")

    answer_permission_count = sum(1 for card in ink_cards if card.get("answer_permission"))
    can_answer_directly_count = sum(1 for card in ink_cards if card.get("can_answer_directly"))
    can_prove_claims_count = sum(1 for card in ink_cards if card.get("can_prove_claims"))
    source_truth_mutation_allowed_count = sum(1 for card in ink_cards if card.get("source_truth_mutation_allowed"))

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "TRACE_NET_PAGE_INK_ROUTE_EVIDENCE_BUILT",
        "page_route_manifest_path": str(page_route_manifest) if page_route_manifest else None,
        "page_route_manifest_quality_status": page_route_manifest_quality_status,
        "metadata_zip_path": str(metadata_zip) if metadata_zip else None,
        "metadata_zip_available": metadata_zip_summary.get("metadata_zip_available", False),
        "metadata_zip_image_count": metadata_zip_summary.get("metadata_zip_image_count", 0),
        "image_root": str(image_root) if image_root else None,
        "threshold": int(threshold),
        "max_analysis_side": int(max_analysis_side),
        "component_analysis_side": int(component_analysis_side),
        "ink_evidence_card_count": len(ink_cards),
        "source_page_ink_evidence_card_count": sum(1 for card in ink_cards if card.get("source_page_id")),
        "image_analyzed_card_count": sum(1 for card in ink_cards if card.get("image_analyzed")),
        "image_read_error_card_count": sum(1 for card in ink_cards if card.get("image_read_error")),
        "blank_likelihood_high_card_count": sum(1 for card in ink_cards if _safe_float(card.get("blank_likelihood")) >= 0.85),
        "table_grid_likelihood_high_card_count": sum(1 for card in ink_cards if _safe_float(card.get("table_grid_likelihood")) >= 0.62),
        "diagram_likelihood_high_card_count": sum(1 for card in ink_cards if _safe_float(card.get("diagram_likelihood")) >= 0.55),
        "text_likelihood_high_card_count": sum(1 for card in ink_cards if _safe_float(card.get("text_likelihood")) >= 0.45),
        "ink_primary_route_counts": dict(sorted((str(k), v) for k, v in route_counts.items())),
        "ink_route_evidence_status_counts": dict(sorted((str(k), v) for k, v in status_counts.items())),
        "unsafe_ink_card_count": sum(1 for card in ink_cards if card.get("unsafe_ink_card")),
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutations_performed": 0,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": summary["status"],
        "summary": summary,
        "ink_evidence_cards": ink_cards,
    }

    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["summary"]["quality_status"] = quality["quality_status"]
    report["summary"]["quality_fail_reasons"] = quality["quality_fail_reasons"]

    if write_outputs:
        report_path = output_dir / "trace_net_page_ink_route_evidence_v1.json"
        quality_path = output_dir / "trace_net_page_ink_route_evidence_v1_quality.json"
        summary_path = output_dir / "trace_net_page_ink_route_evidence_v1_summary.json"
        write_json(report_path, report)
        write_json(quality_path, quality)
        write_json(summary_path, summary)
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)
    return report


def _thresholds_from_args(args: argparse.Namespace) -> InkRouteEvidenceThresholds:
    return InkRouteEvidenceThresholds(
        min_ink_evidence_cards=args.min_ink_evidence_cards,
        min_source_page_ink_evidence_cards=args.min_source_page_ink_evidence_cards,
        min_image_analyzed_cards=args.min_image_analyzed_cards,
        max_image_read_error_cards=args.max_image_read_error_cards,
        max_unsafe_ink_cards=args.max_unsafe_ink_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_page_route_manifest_quality_pass=args.require_page_route_manifest_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Page Ink Route Evidence v1")
    parser.add_argument("--page-route-manifest", type=Path, required=False)
    parser.add_argument("--metadata-zip", type=Path, required=False)
    parser.add_argument("--image-root", type=Path, required=False)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--threshold", type=int, default=220)
    parser.add_argument("--max-analysis-side", type=int, default=1200)
    parser.add_argument("--component-analysis-side", type=int, default=350)
    parser.add_argument("--min-ink-evidence-cards", type=int, default=1)
    parser.add_argument("--min-source-page-ink-evidence-cards", type=int, default=1)
    parser.add_argument("--min-image-analyzed-cards", type=int, default=1)
    parser.add_argument("--max-image-read-error-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-ink-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-page-route-manifest-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_page_ink_route_evidence_report(
        page_route_manifest=args.page_route_manifest,
        metadata_zip=args.metadata_zip,
        image_root=args.image_root,
        output_dir=args.output_dir,
        max_pages=args.max_pages,
        threshold=args.threshold,
        max_analysis_side=args.max_analysis_side,
        component_analysis_side=args.component_analysis_side,
        thresholds=_thresholds_from_args(args),
    )
    summary = report.get("summary", {})
    print("TRACE-Net Page Ink Route Evidence v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "ink_evidence_card_count",
        "source_page_ink_evidence_card_count",
        "image_analyzed_card_count",
        "image_read_error_card_count",
        "blank_likelihood_high_card_count",
        "table_grid_likelihood_high_card_count",
        "diagram_likelihood_high_card_count",
        "text_likelihood_high_card_count",
        "unsafe_ink_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report.get('report_path')}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")
    return report


if __name__ == "__main__":  # pragma: no cover
    main()
