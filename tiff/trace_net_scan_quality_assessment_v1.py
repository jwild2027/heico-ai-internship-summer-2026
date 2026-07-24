"""TRACE-Net scan-quality assessment v1.

Scan quality is metadata, never a page route or page type.  The module is
read-only and deliberately refuses to infer blur from OCR errors, user wording,
or a low word count.  A positive blur finding requires two independent
image-derived signals: low sharpness and broad edge spread.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_scan_quality_assessment_v1"
VERSION = "v1"
STATUS = "TRACE_NET_SCAN_QUALITY_ASSESSMENT_V1"
SCHEMA_VERSION = "trace_net_scan_quality_v1"

QUALITY_STATES = ("clear", "degraded", "uncertain")
OCR_LEGIBILITY_STATES = ("high", "medium", "low", "unknown")

# These describe scan condition and are forbidden as page route/type labels.
# OCR_SCAN_RECOVERY is intentionally allowed because it is a query route, not a
# page classification.
FORBIDDEN_ROUTE_QUALITY_TERMS = (
    "blurry",
    "blurred",
    "focus_blur",
    "motion_blur",
    "low_contrast",
    "poor_scan",
    "degraded_scan",
    "scan_quality",
    "cropped_scan",
    "damaged_scan",
)

DEFAULT_THRESHOLDS = {
    "blur_sharpness_max": 0.07,
    "blur_edge_spread_min": 5.0,
    "low_contrast_max": 0.12,
    "noise_min": 0.70,
    "skew_degrees_min": 1.5,
    "crop_fraction_min": 0.02,
    "minimum_dpi": 150.0,
    "minimum_short_edge_pixels": 1000,
    "clear_image_signal_count": 2,
}

SAFETY_CONTRACT = {
    "scan_quality_is_not_page_route": True,
    "query_wording_cannot_set_scan_quality": True,
    "ocr_failure_alone_cannot_set_blur": True,
    "positive_blur_requires_two_image_signals": True,
    "uncertain_cases_abstain": True,
    "page_route_mutation_allowed": False,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}


def _compact_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def route_quality_violations(labels: Iterable[Any]) -> list[str]:
    violations: list[str] = []
    for raw in labels:
        label = _compact_label(raw)
        if not label:
            continue
        if any(term in label for term in FORBIDDEN_ROUTE_QUALITY_TERMS):
            violations.append(str(raw))
    return list(dict.fromkeys(violations))


def validate_route_labels(labels: Iterable[Any]) -> dict[str, Any]:
    values = [str(item) for item in labels if str(item or "").strip()]
    violations = route_quality_violations(values)
    if violations:
        raise ValueError(
            "scan quality cannot be used as a page route/type label: "
            + ", ".join(violations)
        )
    return {
        "quality_status": "PASS",
        "label_count": len(values),
        "violation_count": 0,
        "violations": [],
        "scan_quality_is_not_page_route": True,
    }


def validate_route_record(record: Mapping[str, Any]) -> dict[str, Any]:
    labels: list[Any] = [record.get("primary_route"), record.get("legacy_route")]
    for key in ("secondary_routes", "candidate_routes"):
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            labels.extend(value)
    violations = route_quality_violations(labels)
    return {
        "quality_status": "PASS" if not violations else "FAIL",
        "violation_count": len(violations),
        "violations": violations,
        "scan_quality_is_not_page_route": not violations,
    }


def _number(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _normalized(value: Any) -> float | None:
    parsed = _number(value)
    if parsed is None:
        return None
    if parsed > 1.0 and parsed <= 100.0:
        parsed /= 100.0
    return max(0.0, min(1.0, parsed))


def _first_number(metrics: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = _number(metrics.get(key))
        if value is not None:
            return value
    return None


def _first_normalized(metrics: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = _normalized(metrics.get(key))
        if value is not None:
            return value
    return None


def _laplacian_to_normalized(value: float | None) -> float | None:
    if value is None:
        return None
    # Raw Laplacian variance is unbounded.  This monotonic transform keeps it in
    # [0,1] without pretending the value is comparable across scanner families.
    return max(0.0, min(1.0, value / (value + 500.0)))


def _extract_metrics(record: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in ("image_features", "image_quality_metrics", "scan_quality_metrics"):
        value = record.get(key)
        if isinstance(value, Mapping):
            merged.update(value)
    # Permit already-computed image measurements at the record top level.  Do
    # not copy OCR text, query text, route reasons, or model judgments.
    for key in (
        "sharpness_score",
        "normalized_sharpness",
        "laplacian_variance",
        "variance_of_laplacian",
        "edge_spread_pixels",
        "local_contrast",
        "contrast_score",
        "noise_score",
        "skew_degrees",
        "crop_fraction",
        "cropped_fraction",
        "width",
        "height",
        "dpi",
        "dpi_x",
        "dpi_y",
        "ocr_confidence",
        "ocr_character_coverage",
        "layout_reading_order_conflict",
        "blur_measurement_calibrated",
    ):
        if key in record and key not in merged:
            merged[key] = record[key]
    return merged


def metrics_from_luma_grid(grid: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Compute small, dependency-free image metrics from a grayscale grid.

    Values may be 0..255 or 0..1.  This helper is intended for tests, smoke
    checks, and small samples; the 5 TB production pipeline may supply equivalent
    metrics from its optimized image-processing workers.
    """
    rows = [list(row) for row in grid]
    if len(rows) < 3 or min((len(row) for row in rows), default=0) < 3:
        raise ValueError("luma grid must be at least 3x3")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("luma grid must be rectangular")
    scale = 255.0 if max(max(row) for row in rows) > 1.0 else 1.0
    norm = [[max(0.0, min(1.0, float(value) / scale)) for value in row] for row in rows]
    flat = [value for row in norm for value in row]
    contrast = min(1.0, pstdev(flat) * 2.0)

    gradients: list[float] = []
    laplacians: list[float] = []
    height = len(norm)
    for y in range(height):
        for x in range(width - 1):
            gradients.append(abs(norm[y][x + 1] - norm[y][x]))
    for y in range(height - 1):
        for x in range(width):
            gradients.append(abs(norm[y + 1][x] - norm[y][x]))
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            center = norm[y][x]
            lap = abs(
                4.0 * center
                - norm[y - 1][x]
                - norm[y + 1][x]
                - norm[y][x - 1]
                - norm[y][x + 1]
            )
            laplacians.append(lap)

    ordered = sorted(gradients)
    p90 = ordered[int(0.90 * (len(ordered) - 1))] if ordered else 0.0
    lap_mean = fmean(laplacians) if laplacians else 0.0
    sharpness = min(1.0, 0.65 * p90 + 0.35 * min(1.0, lap_mean))
    weak = sum(value >= 0.025 for value in gradients)
    strong = sum(value >= 0.25 for value in gradients)
    edge_spread = 0.0 if weak == 0 else min(8.0, weak / max(strong, 1))
    return {
        "sharpness_score": round(sharpness, 6),
        "edge_spread_pixels": round(edge_spread, 6),
        "local_contrast": round(contrast, 6),
        "width": width,
        "height": height,
        "measurement_source": "luma_grid",
    }


def assess_scan_quality(
    metrics: Mapping[str, Any] | None,
    *,
    page_route: str | None = None,
    query_text: str | None = None,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess scan condition without changing or inferring the page route.

    ``query_text`` is accepted only to make the non-influence contract explicit;
    it is never used in the decision.
    """
    validate_route_labels([page_route] if page_route else [])
    values = dict(metrics or {})
    limits = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        limits.update(thresholds)

    sharpness = _first_normalized(values, ("sharpness_score", "normalized_sharpness"))
    if sharpness is None:
        sharpness = _laplacian_to_normalized(
            _first_number(values, ("laplacian_variance", "variance_of_laplacian"))
        )
    edge_spread = _first_number(values, ("edge_spread_pixels",))
    contrast = _first_normalized(values, ("local_contrast", "contrast_score"))
    noise = _first_normalized(values, ("noise_score",))
    skew = _first_number(values, ("skew_degrees",))
    crop_fraction = _first_normalized(values, ("crop_fraction", "cropped_fraction"))
    width = _first_number(values, ("width", "pixel_width"))
    height = _first_number(values, ("height", "pixel_height"))
    dpi = _first_number(values, ("dpi",))
    if dpi is None:
        dpi_values = [
            value
            for value in (
                _first_number(values, ("dpi_x",)),
                _first_number(values, ("dpi_y",)),
            )
            if value is not None
        ]
        dpi = min(dpi_values) if dpi_values else None

    ocr_confidence = _first_normalized(values, ("ocr_confidence",))
    ocr_coverage = _first_normalized(values, ("ocr_character_coverage",))
    layout_issue = bool(values.get("layout_reading_order_conflict"))

    basis: list[str] = []
    image_signal_count = 0
    for name, value in (
        ("sharpness_score", sharpness),
        ("edge_spread_pixels", edge_spread),
        ("local_contrast", contrast),
        ("noise_score", noise),
        ("skew_degrees", skew),
        ("crop_fraction", crop_fraction),
        ("image_resolution", min(width, height) if width is not None and height is not None else None),
        ("dpi", dpi),
    ):
        if value is not None:
            basis.append(name)
            image_signal_count += 1

    blur_measurement_calibrated = values.get("blur_measurement_calibrated") is True
    blur_evidence_complete = (
        blur_measurement_calibrated
        and sharpness is not None
        and edge_spread is not None
    )
    blur_detected = bool(
        blur_evidence_complete
        and sharpness <= float(limits["blur_sharpness_max"])
        and edge_spread >= float(limits["blur_edge_spread_min"])
    )
    blur_confidence = 0.0
    if blur_evidence_complete:
        sharp_component = max(
            0.0,
            min(1.0, (float(limits["blur_sharpness_max"]) - sharpness) / max(float(limits["blur_sharpness_max"]), 1e-9)),
        )
        spread_component = max(
            0.0,
            min(1.0, (edge_spread - float(limits["blur_edge_spread_min"])) / max(float(limits["blur_edge_spread_min"]), 1e-9)),
        )
        blur_confidence = round((sharp_component + spread_component) / 2.0, 6) if blur_detected else 0.0

    blank_page = _compact_label(page_route) == "blank_candidate"
    low_contrast = bool(
        not blank_page
        and contrast is not None
        and contrast <= float(limits["low_contrast_max"])
    )
    heavy_noise = bool(noise is not None and noise >= float(limits["noise_min"]))
    skewed = bool(skew is not None and abs(skew) >= float(limits["skew_degrees_min"]))
    cropped = bool(crop_fraction is not None and crop_fraction >= float(limits["crop_fraction_min"]))
    low_resolution = False
    if dpi is not None and dpi < float(limits["minimum_dpi"]):
        low_resolution = True
    if width is not None and height is not None and min(width, height) < int(limits["minimum_short_edge_pixels"]):
        low_resolution = True

    degradations: list[str] = []
    if blur_detected:
        degradations.append("focus_or_motion_blur")
    if low_contrast:
        degradations.append("low_contrast")
    if heavy_noise:
        degradations.append("heavy_noise")
    if skewed:
        degradations.append("skew")
    if cropped:
        degradations.append("cropped_content")
    if low_resolution:
        degradations.append("low_resolution")

    if degradations:
        quality_state = "degraded"
    elif image_signal_count >= int(limits["clear_image_signal_count"]):
        quality_state = "clear"
    else:
        quality_state = "uncertain"

    if ocr_confidence is None and ocr_coverage is None:
        legibility = "unknown"
    else:
        score_values = [value for value in (ocr_confidence, ocr_coverage) if value is not None]
        score = fmean(score_values)
        legibility = "high" if score >= 0.80 else "medium" if score >= 0.50 else "low"

    return {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS,
        "schema_version": SCHEMA_VERSION,
        "quality_status": "PASS",
        "quality_state": quality_state,
        "degradation_types": degradations,
        "blur_detected": blur_detected,
        "blur_confidence": blur_confidence,
        "blur_assessment_complete": blur_evidence_complete,
        "blur_measurement_calibrated": blur_measurement_calibrated,
        "low_contrast_detected": low_contrast,
        "heavy_noise_detected": heavy_noise,
        "skew_detected": skewed,
        "cropping_detected": cropped,
        "low_resolution_detected": low_resolution,
        "resolution_sufficient": not low_resolution if (dpi is not None or (width is not None and height is not None)) else None,
        "ocr_legibility_state": legibility,
        "layout_reconstruction_issue": layout_issue,
        "measurement_count": image_signal_count,
        "assessment_basis": basis,
        "page_route": page_route,
        "page_route_preserved": True,
        "scan_quality_is_not_page_route": True,
        "query_text_influenced_assessment": False,
        "ocr_failure_alone_can_set_blur": False,
        "positive_blur_requires_two_image_signals": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def assess_scan_quality_from_record(
    record: Mapping[str, Any],
    *,
    page_route: str | None = None,
) -> dict[str, Any]:
    return assess_scan_quality(
        _extract_metrics(record),
        page_route=page_route,
        query_text=None,
    )


def validate_scan_quality_record(record: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    state = str(record.get("quality_state") or "")
    if state not in QUALITY_STATES:
        failures.append("invalid_quality_state")
    if record.get("scan_quality_is_not_page_route") is not True:
        failures.append("scan_quality_route_separation_missing")
    if record.get("query_text_influenced_assessment") is not False:
        failures.append("query_text_influenced_scan_quality")
    if record.get("blur_detected") is True:
        basis = set(record.get("assessment_basis") or [])
        if not {"sharpness_score", "edge_spread_pixels"}.issubset(basis):
            failures.append("blur_without_two_image_signals")
        if record.get("blur_assessment_complete") is not True:
            failures.append("blur_without_complete_assessment")
        if record.get("blur_measurement_calibrated") is not True:
            failures.append("blur_without_calibrated_measurement")
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "page_records", "scan_records"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
    raise ValueError("input must be a record list or contain records/page_records/scan_records")


def build_scan_quality_manifest(
    *,
    input_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    source = Path(input_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = _records(payload)
    output_rows: list[dict[str, Any]] = []
    state_counts = {state: 0 for state in QUALITY_STATES}
    blur_count = 0
    for row in rows:
        route_validation = validate_route_record(row)
        if route_validation["quality_status"] != "PASS":
            raise ValueError("route/type contains scan-quality label: " + ", ".join(route_validation["violations"]))
        route = str(row.get("primary_route") or row.get("route") or "").strip() or None
        assessment = assess_scan_quality_from_record(row, page_route=route)
        state_counts[assessment["quality_state"]] += 1
        blur_count += int(assessment["blur_detected"] is True)
        output_rows.append({
            "page_id": row.get("page_id"),
            "page_number": row.get("page_number") or row.get("canonical_page_number"),
            "primary_route": route,
            "scan_quality": assessment,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
    result = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS,
        "quality_status": "PASS",
        "summary": {
            "source_path": str(source),
            "record_count": len(output_rows),
            "quality_state_counts": state_counts,
            "blur_detected_count": blur_count,
            "route_quality_label_violation_count": 0,
            "scan_quality_is_not_page_route": True,
            "query_wording_can_set_scan_quality": False,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "records": output_rows,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net scan-quality metadata without changing page routes")
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args(argv)
    result = build_scan_quality_manifest(input_path=args.input_path, output_path=args.output_path)
    print("status=" + STATUS)
    print("quality_status=" + str(result["quality_status"]))
    print("record_count=" + str(result["summary"]["record_count"]))
    print("blur_detected_count=" + str(result["summary"]["blur_detected_count"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
