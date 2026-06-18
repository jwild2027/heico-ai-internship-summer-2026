from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tiff.trace_net_page_route_manifest_v1_quality import (
    PASS,
    FAIL,
    SCHEMA_VERSION,
    PageRouteManifestQualityThresholds,
    evaluate_quality,
)

ARTIFACT_NAME = "TRACE-Net Page Route Manifest v1"
REPORT_FILENAME = "trace_net_page_route_manifest_v1.json"
QUALITY_FILENAME = "trace_net_page_route_manifest_v1_quality.json"
CARDS_JSONL_FILENAME = "trace_net_page_route_manifest_v1_cards.jsonl"
SUMMARY_FILENAME = "trace_net_page_route_manifest_v1_summary.json"
MANIFEST_FILENAME = "trace_net_page_route_manifest_v1_manifest.json"

ROUTE_TABLE = "table"
ROUTE_IMAGE = "image_visual"
ROUTE_TEXT = "normal_text"
ROUTE_BLANK = "blank_candidate"
ROUTE_REVIEW = "review"


class PageRouteManifestError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 6)


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise PageRouteManifestError(f"JSON payload is not an object: {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True))
            f.write("\n")


def _page_number_from_string(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).replace("\\", "/")
    candidates: List[int] = []
    for pattern in (
        r"metadata_page_(\d+)",
        r"(?:^|[_/\-])p(\d{1,8})(?:\D|$)",
        r"(?:^|/)(\d{8})\.(?:tif|tiff|png|jpg|jpeg)$",
        r"(?:^|/)(\d{1,8})(?:\D|$)",
    ):
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            try:
                number = int(match.group(1))
            except Exception:
                continue
            if number > 0:
                candidates.append(number)
    if not candidates:
        return None
    # Prefer the last useful number; TRACE-Net page ids often end with p000013.
    return candidates[-1]


def _page_number_from_card(card: Mapping[str, Any]) -> Optional[int]:
    for key in ("page_number", "source_page_number", "page_index"):
        number = _safe_int(card.get(key))
        if number > 0:
            return number
    for key in ("page_id", "source_page_id", "image_filename", "resolved_page_id", "target_page_id"):
        number = _page_number_from_string(card.get(key))
        if number:
            return number
    for alias in card.get("page_aliases") or []:
        number = _page_number_from_string(alias)
        if number:
            return number
    return None


def _aliases_for_source(source: Mapping[str, Any]) -> List[str]:
    aliases = set(str(a) for a in (source.get("page_aliases") or []) if str(a).strip())
    for key in ("source_page_id", "page_id", "image_filename", "page_label", "physical_page_label"):
        value = source.get(key)
        if value:
            aliases.add(str(value))
    page_number = _page_number_from_card(source)
    if page_number:
        aliases.update({
            f"metadata_page_{page_number:06d}",
            f"p{page_number:06d}",
            f"{page_number:08d}",
            f"{page_number:08d}.tif",
            f"t_p_120_1176_p{page_number:06d}",
        })
    return sorted(aliases)


def _counter_from_page_cards(cards: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(_safe_int(card.get(key)) for card in cards)


def _artifact_keys(cards: Sequence[Mapping[str, Any]]) -> List[str]:
    keys: set[str] = set()
    for card in cards:
        for key in card.get("artifact_keys") or []:
            if key:
                keys.add(str(key))
    return sorted(keys)


def _category_counts(cards: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for card in cards:
        category_counts = card.get("evidence_category_counts")
        if isinstance(category_counts, Mapping):
            for key, value in category_counts.items():
                counts[str(key)] += _safe_int(value)
        else:
            for category in card.get("evidence_categories") or []:
                counts[str(category)] += 1
    return dict(sorted(counts.items()))


def _score_table(table_count: int, ocr_count: int, image_count: int, artifact_keys: Sequence[str]) -> Tuple[float, List[str]]:
    if table_count <= 0:
        return 0.0, []
    score = 0.42 + min(0.25, 0.05 * table_count)
    reasons = ["table_evidence_artifact_present"]
    haystack = " ".join(artifact_keys).lower()
    if "table_line_geometry" in haystack:
        score += 0.14
        reasons.append("table_line_geometry_artifact_present")
    if "table_full_region_recovery" in haystack:
        score += 0.10
        reasons.append("table_full_region_recovery_artifact_present")
    if "table_bbox" in haystack:
        score += 0.08
        reasons.append("table_bbox_artifact_present")
    if "table_cell" in haystack or "normalizer" in haystack:
        score += 0.08
        reasons.append("table_cell_or_normalizer_artifact_present")
    if ocr_count > 0:
        score += 0.05
        reasons.append("ocr_text_evidence_supports_table_route")
    if image_count > 0:
        score += 0.03
        reasons.append("image_or_ink_evidence_supports_table_route")
    return _clip(score), reasons


def _score_image(image_count: int, ocr_count: int, artifact_keys: Sequence[str]) -> Tuple[float, List[str]]:
    if image_count <= 0:
        return 0.0, []
    score = 0.42 + min(0.28, 0.06 * image_count)
    reasons = ["image_visual_evidence_artifact_present"]
    haystack = " ".join(artifact_keys).lower()
    if any(token in haystack for token in ("visual_diagram", "figure", "callout", "ink")):
        score += 0.16
        reasons.append("visual_diagram_or_callout_artifact_present")
    if ocr_count > 0:
        score += 0.04
        reasons.append("ocr_text_evidence_supports_visual_route")
    return _clip(score), reasons


def _score_text(ocr_count: int, table_count: int, image_count: int, artifact_keys: Sequence[str]) -> Tuple[float, List[str]]:
    if ocr_count <= 0:
        return 0.05 if table_count == 0 and image_count == 0 else 0.0, []
    score = 0.45 + min(0.30, 0.06 * ocr_count)
    reasons = ["ocr_text_evidence_artifact_present"]
    haystack = " ".join(artifact_keys).lower()
    if any(token in haystack for token in ("source", "ingest", "document", "ocr")):
        score += 0.10
        reasons.append("source_or_ocr_artifact_present")
    if table_count > 0 or image_count > 0:
        score -= 0.08
        reasons.append("specialized_route_evidence_competes_with_text_route")
    return _clip(score), reasons


def _ink_score(value: Any) -> float:
    return _clip(_safe_float(value))


def _strong_ink_route(ink_card: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not ink_card:
        return None
    route = str(ink_card.get("ink_primary_route") or "")
    if route in {ROUTE_TABLE, ROUTE_IMAGE, ROUTE_TEXT, ROUTE_BLANK}:
        return route
    return None


def _apply_ink_boosts(
    route_scores: Dict[str, float],
    routing_reasons: List[str],
    ink_card: Optional[Mapping[str, Any]],
    *,
    table_count: int,
    image_count: int,
    ocr_count: int,
    no_specialized_evidence: bool,
) -> Tuple[Dict[str, float], List[str], Dict[str, Any]]:
    if not ink_card:
        return route_scores, routing_reasons, {"page_ink_route_evidence_available": False}

    ink_primary_route = _strong_ink_route(ink_card)
    table_likelihood = _ink_score(ink_card.get("table_grid_likelihood"))
    image_likelihood = _ink_score(ink_card.get("diagram_likelihood"))
    text_likelihood = _ink_score(ink_card.get("text_likelihood"))
    blank_likelihood = _ink_score(ink_card.get("blank_likelihood"))
    horizontal_lines = _safe_int(ink_card.get("horizontal_line_count"))
    vertical_lines = _safe_int(ink_card.get("vertical_line_count"))
    intersections = _safe_int(ink_card.get("intersection_count"))

    boosts: Dict[str, float] = {ROUTE_TABLE: 0.0, ROUTE_IMAGE: 0.0, ROUTE_TEXT: 0.0, ROUTE_BLANK: 0.0}
    reasons: List[str] = ["page_ink_route_evidence_available"]

    # Ink can strengthen an already-evidenced route. It should not create a
    # table or visual route by itself unless the page has very strong pixel
    # evidence and some corroborating non-blank evidence. This keeps text
    # columns and noisy scans from turning hundreds of pages into tables.
    if table_count > 0 and table_likelihood >= 0.55:
        boosts[ROUTE_TABLE] += min(0.12, 0.05 + 0.08 * table_likelihood)
        reasons.append("ink_table_grid_supports_table_route")
    elif table_count == 0 and (ocr_count > 0 or image_count > 0) and table_likelihood >= 0.94 and intersections >= 120:
        route_scores[ROUTE_TABLE] = max(route_scores.get(ROUTE_TABLE, 0.0), 0.48)
        reasons.append("very_strong_ink_table_grid_requires_review")

    if image_count > 0 and image_likelihood >= 0.45:
        boosts[ROUTE_IMAGE] += min(0.10, 0.04 + 0.08 * image_likelihood)
        reasons.append("ink_diagram_signal_supports_image_route")

    if (ocr_count > 0 or no_specialized_evidence) and text_likelihood >= 0.55:
        boosts[ROUTE_TEXT] += min(0.08, 0.03 + 0.05 * text_likelihood)
        reasons.append("ink_text_density_supports_text_route")

    if no_specialized_evidence and blank_likelihood >= 0.65:
        route_scores[ROUTE_BLANK] = max(route_scores.get(ROUTE_BLANK, 0.0), 0.88)
        reasons.append("ink_blank_signal_supports_blank_route")

    for route, boost in boosts.items():
        if boost:
            route_scores[route] = _clip(route_scores.get(route, 0.0) + boost)

    if ink_primary_route:
        reasons.append(f"ink_primary_route_{ink_primary_route}")

    metadata = {
        "page_ink_route_evidence_available": True,
        "page_ink_route_evidence_status": ink_card.get("ink_route_evidence_status"),
        "ink_primary_route": ink_primary_route,
        "ink_density": _safe_float(ink_card.get("ink_density")),
        "ink_blank_likelihood": blank_likelihood,
        "ink_text_likelihood": text_likelihood,
        "ink_table_grid_likelihood": table_likelihood,
        "ink_diagram_likelihood": image_likelihood,
        "ink_horizontal_line_count": horizontal_lines,
        "ink_vertical_line_count": vertical_lines,
        "ink_intersection_count": intersections,
        "ink_route_boosts": {route: round(value, 6) for route, value in boosts.items() if value},
        "ink_route_reasons": reasons,
    }
    return route_scores, routing_reasons + reasons, metadata


def _ink_disagreement_review_reasons(primary_route: str, ink_metadata: Mapping[str, Any]) -> List[str]:
    if not ink_metadata.get("page_ink_route_evidence_available"):
        return []
    ink_primary = ink_metadata.get("ink_primary_route")
    if not ink_primary or ink_primary == primary_route:
        return []

    table_likelihood = _safe_float(ink_metadata.get("ink_table_grid_likelihood"))
    diagram_likelihood = _safe_float(ink_metadata.get("ink_diagram_likelihood"))
    blank_likelihood = _safe_float(ink_metadata.get("ink_blank_likelihood"))
    intersections = _safe_int(ink_metadata.get("ink_intersection_count"))
    reasons: List[str] = []

    # Ink disagreement is advisory unless the pixel evidence is very strong.
    # The first ink pass is intentionally sensitive and may classify text columns
    # or dense page structure as table-like. Do not flood review for mild
    # blank-vs-table disagreements.
    if primary_route == ROUTE_BLANK and ink_primary == ROUTE_TABLE and table_likelihood >= 0.97 and intersections >= 160:
        reasons.append("strong_ink_table_signal_differs_from_blank_route")
    elif primary_route == ROUTE_BLANK and ink_primary == ROUTE_IMAGE and diagram_likelihood >= 0.92:
        reasons.append("strong_ink_visual_signal_differs_from_blank_route")
    elif primary_route == ROUTE_TABLE and ink_primary != ROUTE_TABLE and table_likelihood < 0.45:
        reasons.append("ink_signal_weak_for_table_route")
    elif primary_route == ROUTE_IMAGE and ink_primary == ROUTE_TABLE and table_likelihood >= 0.92 and intersections >= 140:
        reasons.append("strong_ink_table_signal_competes_with_image_route")
    elif primary_route != ROUTE_BLANK and ink_primary == ROUTE_BLANK and blank_likelihood >= 0.88:
        reasons.append("strong_ink_blank_signal_competes_with_nonblank_route")

    return reasons


def _secondary_routes(primary: str, scores: Mapping[str, float]) -> List[str]:
    routes: List[str] = []
    for route, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        if route == primary:
            continue
        if route == ROUTE_REVIEW:
            continue
        threshold = 0.25 if route != ROUTE_BLANK else 0.60
        if score >= threshold:
            routes.append(route)
    return routes


def _choose_route(scores: Mapping[str, float], safe_for_routing: bool, conflict: bool) -> Tuple[str, float, bool, List[str]]:
    if not safe_for_routing:
        return ROUTE_REVIEW, 1.0, True, ["unsafe_or_not_safe_for_routing_evidence"]
    if conflict:
        # Keep strongest route as primary but require review.
        pass
    ranked = sorted(((route, score) for route, score in scores.items() if route != ROUTE_REVIEW), key=lambda item: (-item[1], item[0]))
    top_route, top_score = ranked[0]
    if top_score <= 0.0:
        return ROUTE_REVIEW, 0.25, True, ["no_route_evidence_available"]
    if top_route == ROUTE_BLANK and top_score >= 0.60:
        return ROUTE_BLANK, top_score, False, ["metadata_page_without_trace_net_evidence"]
    if top_score < 0.35:
        return ROUTE_REVIEW, top_score, True, ["weak_route_confidence"]
    return top_route, top_score, conflict, []


def build_route_card(
    source_card: Optional[Mapping[str, Any]],
    evidence_cards: Sequence[Mapping[str, Any]],
    artifact_detector_path: Path,
    ink_card: Optional[Mapping[str, Any]] = None,
    page_ink_route_evidence_path: Optional[Path] = None,
) -> Dict[str, Any]:
    source_card = source_card or {}
    page_number = _page_number_from_card(source_card) if source_card else None
    if page_number is None:
        for card in evidence_cards:
            page_number = _page_number_from_card(card)
            if page_number:
                break

    artifact_page_ids = sorted({str(card.get("page_id")) for card in evidence_cards if card.get("page_id")})
    page_id = artifact_page_ids[0] if artifact_page_ids else str(source_card.get("source_page_id") or source_card.get("page_id") or f"unresolved_page_{page_number or 'unknown'}")
    source_page_id = source_card.get("source_page_id")
    aliases = set(_aliases_for_source(source_card)) if source_card else set()
    aliases.update(artifact_page_ids)

    artifact_keys = _artifact_keys(evidence_cards)
    category_counts = _category_counts(evidence_cards)
    table_count = _counter_from_page_cards(evidence_cards, "table_evidence_artifact_count")
    image_count = _counter_from_page_cards(evidence_cards, "image_visual_evidence_artifact_count")
    ocr_count = _counter_from_page_cards(evidence_cards, "ocr_text_evidence_artifact_count")
    human_review_count = _counter_from_page_cards(evidence_cards, "human_review_evidence_artifact_count")
    unsafe_count = _counter_from_page_cards(evidence_cards, "unsafe_artifact_count")
    safe_count = _counter_from_page_cards(evidence_cards, "safe_artifact_count")
    evidence_count = _counter_from_page_cards(evidence_cards, "artifact_count")

    table_score, table_reasons = _score_table(table_count, ocr_count, image_count, artifact_keys)
    image_score, image_reasons = _score_image(image_count, ocr_count, artifact_keys)
    text_score, text_reasons = _score_text(ocr_count, table_count, image_count, artifact_keys)
    no_specialized_evidence = table_count == 0 and image_count == 0 and ocr_count == 0
    blank_score = 0.72 if source_card and no_specialized_evidence else (0.10 if source_card else 0.0)

    # Route safety is based on safe routing evidence, not merely on the
    # presence of quarantined unsafe artifacts. Unsafe artifacts remain visible
    # in evidence_summary, but they should not force a route unsafe when the
    # Artifact Detector already excluded them from safe_for_routing evidence.
    safe_for_routing = safe_count > 0 or bool(source_card)
    route_scores = {
        ROUTE_TABLE: table_score,
        ROUTE_IMAGE: image_score,
        ROUTE_TEXT: text_score,
        ROUTE_BLANK: _clip(blank_score),
    }
    base_route_scores = dict(route_scores)
    routing_reasons = []
    routing_reasons.extend(table_reasons)
    routing_reasons.extend(image_reasons)
    routing_reasons.extend(text_reasons)
    route_scores, routing_reasons, ink_metadata = _apply_ink_boosts(
        route_scores,
        routing_reasons,
        ink_card,
        table_count=table_count,
        image_count=image_count,
        ocr_count=ocr_count,
        no_specialized_evidence=no_specialized_evidence,
    )

    positive_scores = [score for score in (route_scores[ROUTE_TABLE], route_scores[ROUTE_IMAGE], route_scores[ROUTE_TEXT]) if score >= 0.50]
    top_two = sorted([route_scores[ROUTE_TABLE], route_scores[ROUTE_IMAGE], route_scores[ROUTE_TEXT]], reverse=True)[:2]
    conflict = len(positive_scores) >= 2 and (top_two[0] - top_two[1] <= 0.12)

    primary_route, route_confidence, review_required, extra_reasons = _choose_route(route_scores, safe_for_routing, conflict)
    ink_review_reasons = _ink_disagreement_review_reasons(primary_route, ink_metadata)
    if ink_review_reasons:
        review_required = True
    secondary_routes = _secondary_routes(primary_route, route_scores)
    review_score = _clip((0.70 if review_required else 0.0) + (0.15 if human_review_count else 0.0) + (0.15 if conflict else 0.0) + (0.10 if ink_review_reasons else 0.0))

    routing_reasons.extend(extra_reasons)
    routing_reasons.extend(ink_review_reasons)
    if human_review_count > 0:
        routing_reasons.append("human_review_artifact_present")
    if conflict:
        routing_reasons.append("route_scores_conflict")
    if primary_route == ROUTE_BLANK:
        routing_reasons.append("no_table_image_or_ocr_artifacts_for_source_page")
    routing_reasons = sorted(set(routing_reasons))

    return {
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "source_page_id": source_page_id,
        "page_number": page_number,
        "image_filename": source_card.get("image_filename"),
        "page_aliases": sorted(str(a) for a in aliases if str(a).strip()),
        "primary_route": primary_route,
        "secondary_routes": secondary_routes,
        "route_confidence": _clip(route_confidence),
        "review_required": bool(review_required),
        "safe_for_routing": bool(safe_for_routing),
        "blank_score": route_scores[ROUTE_BLANK],
        "text_score": route_scores[ROUTE_TEXT],
        "table_score": route_scores[ROUTE_TABLE],
        "image_visual_score": route_scores[ROUTE_IMAGE],
        "review_score": review_score,
        "routing_reasons": routing_reasons,
        "route_scores": {**route_scores, ROUTE_REVIEW: review_score},
        "base_route_scores": base_route_scores,
        "ink_route_integration": ink_metadata,
        "page_ink_route_evidence_available": bool(ink_metadata.get("page_ink_route_evidence_available")),
        "ink_primary_route": ink_metadata.get("ink_primary_route"),
        "ink_route_disagreement_review_reasons": ink_review_reasons,
        "evidence_summary": {
            "artifact_count": evidence_count,
            "safe_artifact_count": safe_count,
            "unsafe_artifact_count": unsafe_count,
            "artifact_keys": artifact_keys,
            "evidence_category_counts": category_counts,
            "table_evidence_artifact_count": table_count,
            "image_visual_evidence_artifact_count": image_count,
            "ocr_text_evidence_artifact_count": ocr_count,
            "human_review_evidence_artifact_count": human_review_count,
            "artifact_page_ids": artifact_page_ids,
            "artifact_detector_path": str(artifact_detector_path),
            "page_ink_route_evidence_path": str(page_ink_route_evidence_path) if page_ink_route_evidence_path else None,
        },
        "artifact_detector_page_artifact_count": len(evidence_cards),
        "source_metadata_available": bool(source_card),
        "metadata_only_or_blank_candidate": bool(primary_route == ROUTE_BLANK and no_specialized_evidence),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }


def build_page_route_manifest_report(
    artifact_detector: Path,
    output_dir: Path,
    page_ink_route_evidence: Optional[Path] = None,
    thresholds: Optional[PageRouteManifestQualityThresholds] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    detector_payload = read_json(Path(artifact_detector))
    artifact_detector_quality_status = detector_payload.get("quality_status")
    detector_summary = detector_payload.get("summary") if isinstance(detector_payload.get("summary"), Mapping) else {}
    source_page_cards = [card for card in detector_payload.get("source_page_cards") or [] if isinstance(card, Mapping)]
    page_artifact_cards = [card for card in detector_payload.get("page_artifact_cards") or [] if isinstance(card, Mapping)]

    ink_payload: Dict[str, Any] = {}
    ink_summary: Mapping[str, Any] = {}
    ink_cards_by_number: Dict[int, Mapping[str, Any]] = {}
    page_ink_route_evidence_quality_status: Optional[str] = None
    if page_ink_route_evidence:
        ink_payload = read_json(Path(page_ink_route_evidence))
        page_ink_route_evidence_quality_status = str(ink_payload.get("quality_status") or "UNKNOWN")
        ink_summary = ink_payload.get("summary") if isinstance(ink_payload.get("summary"), Mapping) else {}
        for card in ink_payload.get("ink_evidence_cards") or []:
            if not isinstance(card, Mapping):
                continue
            number = _page_number_from_card(card)
            if number:
                ink_cards_by_number[number] = card

    evidence_by_number: Dict[int, List[Mapping[str, Any]]] = defaultdict(list)
    evidence_without_number: List[Mapping[str, Any]] = []
    for card in page_artifact_cards:
        # Metadata-only cards are represented by source_page_cards and would double-count blank candidates.
        if card.get("page_artifact_detection_status") == "SOURCE_METADATA_PAGE_ONLY":
            continue
        number = _page_number_from_card(card)
        if number:
            evidence_by_number[number].append(card)
        else:
            evidence_without_number.append(card)

    route_cards: List[Dict[str, Any]] = []
    seen_evidence_ids: set[int] = set()
    for source in sorted(source_page_cards, key=lambda c: (_page_number_from_card(c) or 10**12, str(c.get("source_page_id") or ""))):
        number = _page_number_from_card(source)
        evidence_cards = evidence_by_number.get(number or -1, [])
        for card in evidence_cards:
            seen_evidence_ids.add(id(card))
        route_cards.append(build_route_card(
            source,
            evidence_cards,
            Path(artifact_detector),
            ink_card=ink_cards_by_number.get(number or -1),
            page_ink_route_evidence_path=Path(page_ink_route_evidence) if page_ink_route_evidence else None,
        ))

    # Include artifact-only pages that did not join to source metadata.
    for number, cards in sorted(evidence_by_number.items()):
        if all(id(card) in seen_evidence_ids for card in cards):
            continue
        route_cards.append(build_route_card(
            None,
            cards,
            Path(artifact_detector),
            ink_card=ink_cards_by_number.get(number),
            page_ink_route_evidence_path=Path(page_ink_route_evidence) if page_ink_route_evidence else None,
        ))
        for card in cards:
            seen_evidence_ids.add(id(card))
    for card in evidence_without_number:
        if id(card) not in seen_evidence_ids:
            number = _page_number_from_card(card)
            route_cards.append(build_route_card(
                None,
                [card],
                Path(artifact_detector),
                ink_card=ink_cards_by_number.get(number or -1),
                page_ink_route_evidence_path=Path(page_ink_route_evidence) if page_ink_route_evidence else None,
            ))

    route_counts = Counter(str(card.get("primary_route")) for card in route_cards)
    safe_count = sum(1 for card in route_cards if card.get("safe_for_routing"))
    unsafe_count = sum(1 for card in route_cards if not card.get("safe_for_routing"))
    answer_permission_count = sum(1 for card in route_cards if card.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for card in route_cards if card.get("source_truth_mutation_allowed"))

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "TRACE_NET_PAGE_ROUTE_MANIFEST_BUILT",
        "artifact_detector_path": str(artifact_detector),
        "artifact_detector_quality_status": artifact_detector_quality_status,
        "page_ink_route_evidence_quality_status": page_ink_route_evidence_quality_status,
        "page_ink_route_evidence_card_count": _safe_int(ink_summary.get("ink_evidence_card_count")),
        "page_ink_route_evidence_available_card_count": sum(1 for card in route_cards if card.get("page_ink_route_evidence_available")),
        "ink_route_disagreement_review_card_count": sum(1 for card in route_cards if card.get("ink_route_disagreement_review_reasons")),
        "ink_boosted_route_card_count": sum(1 for card in route_cards if (card.get("ink_route_integration") or {}).get("ink_route_boosts")),
        "artifact_detector_artifact_card_count": _safe_int(detector_summary.get("artifact_card_count")),
        "artifact_detector_page_artifact_card_count": len(page_artifact_cards),
        "source_page_card_count": len(source_page_cards),
        "page_route_card_count": len(route_cards),
        "source_page_route_card_count": sum(1 for card in route_cards if card.get("source_metadata_available")),
        "artifact_only_page_route_card_count": sum(1 for card in route_cards if not card.get("source_metadata_available")),
        "safe_for_routing_route_card_count": safe_count,
        "unsafe_route_card_count": unsafe_count,
        "primary_route_counts": dict(sorted(route_counts.items())),
        "table_primary_route_count": route_counts.get(ROUTE_TABLE, 0),
        "image_visual_primary_route_count": route_counts.get(ROUTE_IMAGE, 0),
        "normal_text_primary_route_count": route_counts.get(ROUTE_TEXT, 0),
        "blank_candidate_primary_route_count": route_counts.get(ROUTE_BLANK, 0),
        "review_primary_route_count": route_counts.get(ROUTE_REVIEW, 0),
        "metadata_only_or_blank_candidate_count": sum(1 for card in route_cards if card.get("metadata_only_or_blank_candidate")),
        "review_required_route_card_count": sum(1 for card in route_cards if card.get("review_required")),
        "table_route_evidence_page_count": sum(1 for card in route_cards if _safe_int(card.get("evidence_summary", {}).get("table_evidence_artifact_count")) > 0),
        "image_visual_route_evidence_page_count": sum(1 for card in route_cards if _safe_int(card.get("evidence_summary", {}).get("image_visual_evidence_artifact_count")) > 0),
        "ocr_text_route_evidence_page_count": sum(1 for card in route_cards if _safe_int(card.get("evidence_summary", {}).get("ocr_text_evidence_artifact_count")) > 0),
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_name": ARTIFACT_NAME,
        "status": "TRACE_NET_PAGE_ROUTE_MANIFEST_BUILT",
        "created_at_utc": _utc_now(),
        "quality_status": "UNKNOWN",
        "summary": summary,
        "page_route_cards": route_cards,
    }
    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["summary"]["quality_status"] = quality["quality_status"]
    report["summary"]["quality_fail_reasons"] = quality.get("quality_fail_reasons", [])
    report["summary"]["checks"] = quality.get("checks", {})

    if write_outputs:
        report_path = output_dir / REPORT_FILENAME
        quality_path = output_dir / QUALITY_FILENAME
        cards_path = output_dir / CARDS_JSONL_FILENAME
        summary_path = output_dir / SUMMARY_FILENAME
        manifest_path = output_dir / MANIFEST_FILENAME
        write_json(report_path, report)
        write_json(quality_path, quality)
        write_json(summary_path, report["summary"])
        write_jsonl(cards_path, route_cards)
        write_json(manifest_path, {
            "schema_version": SCHEMA_VERSION,
            "report_path": str(report_path),
            "quality_path": str(quality_path),
            "summary_path": str(summary_path),
            "cards_jsonl_path": str(cards_path),
            "quality_status": quality["quality_status"],
        })
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)
    return report


def thresholds_from_args(args: argparse.Namespace) -> PageRouteManifestQualityThresholds:
    return PageRouteManifestQualityThresholds(
        min_page_route_cards=args.min_page_route_cards,
        min_source_page_route_cards=args.min_source_page_route_cards,
        min_table_route_cards=args.min_table_route_cards,
        min_safe_for_routing_cards=args.min_safe_for_routing_cards,
        max_unsafe_route_cards=args.max_unsafe_route_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_artifact_detector_quality_pass=args.require_artifact_detector_quality_pass,
        require_page_ink_route_evidence_quality_pass=args.require_page_ink_route_evidence_quality_pass,
        min_page_ink_route_evidence_cards=args.min_page_ink_route_evidence_cards,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=ARTIFACT_NAME)
    parser.add_argument("--artifact-detector", type=Path, required=True)
    parser.add_argument("--page-ink-route-evidence", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-page-route-cards", type=int, default=1)
    parser.add_argument("--min-source-page-route-cards", type=int, default=0)
    parser.add_argument("--min-table-route-cards", type=int, default=0)
    parser.add_argument("--min-safe-for-routing-cards", type=int, default=1)
    parser.add_argument("--min-page-ink-route-evidence-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-route-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-artifact-detector-quality-pass", action="store_true")
    parser.add_argument("--require-page-ink-route-evidence-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def print_report(report: Mapping[str, Any]) -> None:
    summary = report.get("summary", {})
    print(ARTIFACT_NAME)
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "page_route_card_count",
        "source_page_route_card_count",
        "artifact_only_page_route_card_count",
        "table_primary_route_count",
        "image_visual_primary_route_count",
        "normal_text_primary_route_count",
        "blank_candidate_primary_route_count",
        "review_primary_route_count",
        "metadata_only_or_blank_candidate_count",
        "review_required_route_card_count",
        "table_route_evidence_page_count",
        "image_visual_route_evidence_page_count",
        "ocr_text_route_evidence_page_count",
        "safe_for_routing_route_card_count",
        "unsafe_route_card_count",
        "artifact_detector_quality_status",
        "page_ink_route_evidence_quality_status",
        "page_ink_route_evidence_card_count",
        "page_ink_route_evidence_available_card_count",
        "ink_route_disagreement_review_card_count",
        "ink_boosted_route_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report.get('report_path')}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_page_route_manifest_report(
        artifact_detector=args.artifact_detector,
        output_dir=args.output_dir,
        page_ink_route_evidence=args.page_ink_route_evidence,
        thresholds=thresholds_from_args(args),
    )
    print_report(report)
    return 0 if report.get("quality_status") == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
