"""TRACE-Net route confidence resolver v1.

This module converts OCR/router scan-pack pages into scalable routing decisions.
It does not require human review. Ambiguous pages are kept safe through
multi-route execution and validator gates instead of being forced into one route.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from tiff.trace_net_scan_quality_assessment_v1 import (
        assess_scan_quality_from_record,
        validate_route_labels,
    )
except ModuleNotFoundError:  # direct execution from tiff/
    from trace_net_scan_quality_assessment_v1 import (
        assess_scan_quality_from_record,
        validate_route_labels,
    )

MODULE = "trace_net_route_confidence_resolver_v1"
STATUS = "TRACE_NET_ROUTE_CONFIDENCE_RESOLVER_BUILT"
VERSION = "v1"

CANONICAL_LABELS = [
    "blank_candidate",
    "cover_or_title_page",
    "normal_text",
    "procedure_or_description",
    "table_or_index",
    "detailed_parts_list",
    "image_visual_diagram",
    "mixed_text_and_figure",
    "review_required",
]

# Scan condition is separate metadata.  It may never become a page route.
validate_route_labels(CANONICAL_LABELS)

PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-[A-Za-z0-9]{3,}\b")
DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}/?\d{0,2}\b", re.I)

PROCEDURE_TERMS = [
    "description and operation",
    "description",
    "operation",
    "general",
    "removal",
    "installation",
    "inspection",
    "repair",
    "cleaning",
    "check",
    "adjustment",
    "disassembly",
    "assembly",
]
TABLE_INDEX_TERMS = [
    "lep",
    "contents",
    "service bulletin",
    "record of revisions",
    "issued inserted",
    "chapter",
    "section",
    "subject",
    "page date",
    "vendor",
    "numerical index",
    "airline stock number",
    "vendor code",
]
DPL_TERMS = [
    "part number",
    "assy number",
    "ch-sec-un-fig",
    "fig item",
    "fig-item",
    "nomenclature",
    "units per assy",
    "units",
    "detailed parts list",
    "airline part number",
]
VISUAL_TERMS = [
    "figure",
    "seat backrest",
    "seat belt",
    "ashtray",
    "floatable seat bottom",
    "view a",
    "fastener",
    "skin ply",
    "abraded area",
    "vacuum",
    "tape",
    "120tp",
]
# Concrete visual labels are terms that usually describe a drawn object or
# callout.  Generic IPL words such as figure/item/view are deliberately not
# enough to make a page a visual diagram because IPL tables commonly contain
# CH-SEC-UN-FIG and item references on every row.
VISUAL_CONCRETE_TERMS = [
    "seat backrest",
    "seat belt",
    "ashtray",
    "floatable seat bottom",
    "fastener",
    "skin ply",
    "abraded area",
    "vacuum",
    "tape",
]
VISUAL_GENERIC_IPL_TERMS = [
    "figure",
    "fig",
    "item",
    "view",
    "parts list",
    "illustrated parts list",
    "ch-sec-un-fig",
    "assy number",
]
COVER_STRONG_TERMS = [
    "component maintenance manual",
    "passenger seats",
    "this publication supersedes",
    "publication covers",
    "publication identity",
]
COVER_WEAK_HEADER_TERMS = [
    "revision",
    "embraer",
    "t.p.",
]

ROUTE_PROCESSORS = {
    "blank_candidate": "blank_candidate_confirmation_scan",
    "cover_or_title_page": "front_matter_identity_scan",
    "normal_text": "normal_text_page_context_scan",
    "procedure_or_description": "procedure_description_context_scan",
    "table_or_index": "table_ocr_table_candidate_scan",
    "detailed_parts_list": "detailed_parts_list_extraction_scan",
    "image_visual_diagram": "image_visual_ocr_and_vision_queue_scan",
    "mixed_text_and_figure": "mixed_text_visual_split_scan",
    "review_required": "validator_gated_review_resolution_scan",
}

EMBED_POLICY = {
    "blank_candidate": "do_not_embed_blank_candidates",
    "cover_or_title_page": "embed_short_publication_identity_summary_only",
    "normal_text": "embed_ocr_chunks_and_page_context_summary_after_validator_pass",
    "procedure_or_description": "embed_procedure_chunks_with_strong_page_trace_after_validator_pass",
    "table_or_index": "embed_table_summary_or_evidence_cards_only_after_validator_pass",
    "detailed_parts_list": "embed_extracted_part_evidence_cards_and_summaries_after_validator_pass",
    "image_visual_diagram": "embed_only_ocr_supported_visual_context_cards_after_validator_pass",
    "mixed_text_and_figure": "embed_text_and_ocr_supported_visual_context_separately_after_validator_pass",
    "review_required": "do_not_embed_until_validator_resolution",
}

WRITE_ZEROES = {
    "unsafe_record_count": 0,
    "answer_permission_count": 0,
    "can_answer_directly_count": 0,
    "can_prove_claims_count": 0,
    "source_truth_mutation_allowed_count": 0,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
}


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "page_number",
        "page_id",
        "legacy_route",
        "primary_route",
        "secondary_routes",
        "route_confidence_score",
        "route_confidence_band",
        "scan_quality_state",
        "blur_detected",
        "auto_resolved",
        "multi_route_required",
        "validator_required",
        "do_not_embed",
        "candidate_routes",
        "route_reasons",
        "validator_contracts",
        "ocr_text_word_count",
        "part_number_count",
        "source_member",
        "source_image_path",
        "ocr_text_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            out = dict(row)
            for key in ["secondary_routes", "candidate_routes", "route_reasons", "validator_contracts"]:
                if isinstance(out.get(key), (list, dict)):
                    out[key] = json.dumps(out[key], sort_keys=True)
            writer.writerow(out)


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Route Confidence Resolver v1",
        "",
        "This artifact replaces page-by-page human review as the scaling gate.",
        "It emits high-confidence automatic route decisions and sends uncertain pages",
        "to multi-route/validator-gated processing instead of guessing.",
        "",
        "## Summary",
        "",
    ]
    for key in sorted(summary):
        lines.append(f"- **{key}**: `{summary[key]}`")
    lines.extend([
        "",
        "## Safety contract",
        "",
        "No Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).lower()


def _count_terms(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term in text)


def _part_numbers(record: Mapping[str, Any], text: str) -> list[str]:
    vals = record.get("part_number_tokens") or []
    if isinstance(vals, list):
        found = [str(v) for v in vals if str(v).strip()]
    else:
        found = []
    found.extend(PART_NUMBER_RE.findall(text))
    seen: set[str] = set()
    out: list[str] = []
    for token in found:
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _word_count(record: Mapping[str, Any], text: str) -> int:
    for key in ["ocr_text_word_count", "ocr_word_count", "word_count"]:
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return len(re.findall(r"\b\w+\b", text))


# Small, explicit, deterministic ink-field contract (no recursive/arbitrary
# searching). The OCR scan pack spreads ``ink_ratio_estimate`` at the top level of
# each record; the 509 audit uses ``ink_ratio``; older records used
# ``ink_density`` / ``dark_pixel_ratio`` / ``foreground_ratio``. All are accepted
# at the top level and inside the canonical nested feature containers below.
_INK_ALIASES: tuple[str, ...] = (
    "ink_ratio_estimate",
    "ink_ratio",
    "ink_density",
    "dark_pixel_ratio",
    "foreground_ratio",
)
_INK_FEATURE_CONTAINERS: tuple[str, ...] = (
    "image_features",
    "page_ink_features",
    "ink_features",
)


def _coerce_ink_value(value: Any) -> float | None:
    """Return a float ink ratio, or None if the value is absent/invalid so the
    lookup can fall through to the next alias rather than masking it with 0.0."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _ink_density(record: Mapping[str, Any]) -> float:
    for key in _INK_ALIASES:
        value = _coerce_ink_value(record.get(key))
        if value is not None:
            return value
    for container in _INK_FEATURE_CONTAINERS:
        features = record.get(container)
        if isinstance(features, Mapping):
            for key in _INK_ALIASES:
                value = _coerce_ink_value(features.get(key))
                if value is not None:
                    return value
    return 0.0


def _legacy_route(record: Mapping[str, Any]) -> str:
    return str(record.get("accepted_route") or record.get("legacy_route") or record.get("route") or "").strip()


def _score_routes(record: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, list[str]], dict[str, Any]]:
    sample = record.get("ocr_sample_text") or record.get("sample_text") or ""
    full_text = record.get("ocr_text") or sample
    text = _norm_text(full_text)
    legacy = _legacy_route(record)
    words = _word_count(record, text)
    parts = _part_numbers(record, text)
    part_count = len(parts)
    ink = _ink_density(record)
    procedure_hits = _count_terms(text, PROCEDURE_TERMS)
    table_hits = _count_terms(text, TABLE_INDEX_TERMS)
    dpl_hits = _count_terms(text, DPL_TERMS)
    visual_hits = _count_terms(text, VISUAL_TERMS)
    concrete_visual_hits = _count_terms(text, VISUAL_CONCRETE_TERMS)
    generic_ipl_visual_hits = _count_terms(text, VISUAL_GENERIC_IPL_TERMS)
    strong_cover_hits = _count_terms(text, COVER_STRONG_TERMS)
    weak_cover_hits = _count_terms(text, COVER_WEAK_HEADER_TERMS)
    cover_hits = strong_cover_hits + weak_cover_hits
    date_hits = len(DATE_RE.findall(text))
    try:
        page_number_int = int(str(record.get("canonical_page_number") or record.get("page_number") or "0"))
    except ValueError:
        page_number_int = 0
    has_figure_caption = bool(re.search(r"\bfigure\s+\d+\b", text, re.I))
    has_row_structure = any(term in text for term in ["assy number", "ch-sec-un-fig", "item]", "fig item", "page date"])
    # Visual clamp: sparse diagram evidence must be concrete.  Generic IPL
    # references such as FIG/ITEM/CH-SEC-UN-FIG are table/list structure, not
    # proof that the page itself is a diagram.
    ipl_visual_blocker = (
        has_row_structure
        or part_count >= 2
        or table_hits >= 2
        or dpl_hits >= 2
        or (generic_ipl_visual_hits >= 3 and concrete_visual_hits == 0)
    )
    strong_sparse_diagram_signal = (
        words <= 110
        and part_count <= 1
        and not ipl_visual_blocker
        and (
            concrete_visual_hits >= 2
            or (concrete_visual_hits >= 1 and (has_figure_caption or "view a" in text))
        )
    )

    scores = {label: 0.0 for label in CANONICAL_LABELS}
    reasons: dict[str, list[str]] = {label: [] for label in CANONICAL_LABELS}

    if words <= 2 and part_count == 0 and (legacy == "blank_candidate" or ink < 0.035):
        scores["blank_candidate"] += 98
        reasons["blank_candidate"].append("empty_or_near_empty_ocr_low_signal")
    elif words <= 5 and part_count == 0:
        scores["blank_candidate"] += 75
        reasons["blank_candidate"].append("near_empty_ocr")

    # Front-matter clamp: do not let repeated manual headers/footers
    # (for example T.P. numbers, revision dates, or EMBRAER footer text)
    # steal content pages. A cover/title page needs strong title identity
    # and either the first page position or sparse front-matter layout.
    strong_cover_identity = strong_cover_hits >= 2
    sparse_front_matter_layout = words <= 140 and part_count <= 1 and not has_row_structure and table_hits <= 1 and dpl_hits <= 1 and procedure_hits <= 1
    first_page_cover = page_number_int == 1 and strong_cover_hits >= 1 and words <= 180 and part_count <= 1
    if first_page_cover:
        scores["cover_or_title_page"] += 100
        reasons["cover_or_title_page"].append("first_page_strong_publication_identity")
    elif strong_cover_identity and sparse_front_matter_layout and page_number_int <= 6:
        scores["cover_or_title_page"] += 88
        reasons["cover_or_title_page"].append("early_front_matter_strong_publication_identity")
    elif strong_cover_identity and sparse_front_matter_layout and weak_cover_hits >= 2 and page_number_int <= 12:
        scores["cover_or_title_page"] += 72
        reasons["cover_or_title_page"].append("early_sparse_publication_identity")
    elif weak_cover_hits >= 2 and strong_cover_hits == 0:
        reasons["cover_or_title_page"].append("header_footer_identity_ignored_without_strong_cover_terms")

    if procedure_hits >= 2 and words >= 60 and part_count <= 2:
        scores["procedure_or_description"] += 82
        reasons["procedure_or_description"].append("procedure_or_description_terms_with_paragraph_text")
    elif procedure_hits >= 1 and words >= 100 and part_count <= 3:
        scores["procedure_or_description"] += 62
        reasons["procedure_or_description"].append("procedure_terms_and_prose_density")

    if words >= 80 and part_count <= 2 and procedure_hits == 0 and table_hits <= 1 and dpl_hits <= 1 and visual_hits <= 1:
        scores["normal_text"] += 70
        reasons["normal_text"].append("paragraph_text_low_structured_signals")

    if table_hits >= 2 or (date_hits >= 8 and words >= 50):
        scores["table_or_index"] += 82
        reasons["table_or_index"].append("table_or_index_terms")
    elif has_row_structure and part_count < 8:
        scores["table_or_index"] += 66
        reasons["table_or_index"].append("row_structure_without_high_part_density")
    if legacy == "table" and words >= 20:
        scores["table_or_index"] += 8
        reasons["table_or_index"].append("legacy_table_signal")

    if part_count >= 10:
        scores["detailed_parts_list"] += 94
        reasons["detailed_parts_list"].append("high_part_number_density")
    elif part_count >= 3 and (dpl_hits >= 1 or has_row_structure):
        scores["detailed_parts_list"] += 82
        reasons["detailed_parts_list"].append("part_numbers_with_ipl_structure")
    elif dpl_hits >= 3 and has_row_structure:
        scores["detailed_parts_list"] += 72
        reasons["detailed_parts_list"].append("detailed_parts_list_column_signals")

    if legacy == "image_visual" and words <= 140 and part_count <= 2:
        scores["image_visual_diagram"] += 90
        reasons["image_visual_diagram"].append("legacy_image_visual_sparse_text")
    elif strong_sparse_diagram_signal:
        scores["image_visual_diagram"] += 82
        reasons["image_visual_diagram"].append("strong_concrete_visual_labels_sparse_non_table_text")
    elif has_figure_caption and words <= 90 and part_count == 0 and table_hits == 0 and dpl_hits == 0 and concrete_visual_hits >= 1:
        scores["image_visual_diagram"] += 72
        reasons["image_visual_diagram"].append("figure_caption_with_concrete_sparse_visual_text")
    elif generic_ipl_visual_hits >= 2 and concrete_visual_hits == 0:
        reasons["image_visual_diagram"].append("generic_ipl_visual_terms_ignored_without_concrete_diagram_evidence")

    if scores["image_visual_diagram"] >= 55 and scores["procedure_or_description"] >= 50:
        scores["mixed_text_and_figure"] += 78
        reasons["mixed_text_and_figure"].append("visual_and_prose_signals")
    elif has_figure_caption and words >= 120 and procedure_hits >= 1 and part_count <= 4:
        scores["mixed_text_and_figure"] += 70
        reasons["mixed_text_and_figure"].append("figure_caption_with_meaningful_prose")

    # Penalize common false positives.
    if part_count >= 8 or has_row_structure or ipl_visual_blocker:
        scores["image_visual_diagram"] = max(0, scores["image_visual_diagram"] - 60)
        reasons["image_visual_diagram"].append("penalty_table_or_ipl_structure_present")
    if procedure_hits >= 2 and part_count <= 2:
        scores["table_or_index"] = max(0, scores["table_or_index"] - 25)
        scores["detailed_parts_list"] = max(0, scores["detailed_parts_list"] - 25)
        reasons["table_or_index"].append("penalty_prose_procedure_dominant")
        reasons["detailed_parts_list"].append("penalty_prose_procedure_dominant")

    meta = {
        "legacy_route": legacy,
        "ocr_text_word_count": words,
        "part_number_count": part_count,
        "part_number_tokens": parts,
        "procedure_term_count": procedure_hits,
        "table_index_term_count": table_hits,
        "detailed_parts_term_count": dpl_hits,
        "visual_term_count": visual_hits,
        "concrete_visual_term_count": concrete_visual_hits,
        "generic_ipl_visual_term_count": generic_ipl_visual_hits,
        "ipl_visual_blocker": ipl_visual_blocker,
        "cover_term_count": cover_hits,
        "strong_cover_term_count": strong_cover_hits,
        "weak_cover_header_term_count": weak_cover_hits,
        "ink_density": ink,
        "has_row_structure": has_row_structure,
        "has_figure_caption": has_figure_caption,
    }
    return scores, reasons, meta


def _band(score: float, margin: float) -> str:
    if score >= 85 and margin >= 18:
        return "high"
    if score >= 65 and margin >= 8:
        return "medium"
    return "low"


def _storage_policy(primary: str, band: str, validator_required: bool) -> dict[str, Any]:
    if primary == "blank_candidate":
        return {"postgres_graph_record": True, "qdrant_embedding_allowed": False, "opensearch_index_allowed": False, "policy": EMBED_POLICY[primary]}
    if band == "high" and not validator_required and primary not in {"review_required"}:
        return {"postgres_graph_record": True, "qdrant_embedding_allowed": True, "opensearch_index_allowed": primary in {"table_or_index", "detailed_parts_list"}, "policy": EMBED_POLICY[primary]}
    return {"postgres_graph_record": True, "qdrant_embedding_allowed": False, "opensearch_index_allowed": False, "policy": EMBED_POLICY.get(primary, EMBED_POLICY["review_required"])}


def _resolve_record(record: Mapping[str, Any], *, high_threshold: float, medium_threshold: float) -> dict[str, Any]:
    scores, reasons_by_route, meta = _score_routes(record)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    primary, top_score = ranked[0]
    second, second_score = ranked[1]
    margin = top_score - second_score

    if top_score < medium_threshold:
        primary = "review_required"
        top_score = scores.get(primary, 0.0)
        margin = 0.0
        secondary_routes = [label for label, score in ranked[:3] if label != "review_required" and score > 0]
        confidence_band = "low"
        route_reasons = ["no_route_met_medium_confidence_threshold"]
    else:
        confidence_band = _band(top_score, margin)
        secondary_routes = [label for label, score in ranked[1:4] if score >= medium_threshold * 0.85 and label != primary]
        route_reasons = reasons_by_route.get(primary) or ["highest_route_score"]

    if confidence_band == "high" and top_score >= high_threshold and margin >= 18:
        auto_resolved = True
        multi_route_required = False
        validator_required = False
    elif confidence_band == "medium":
        auto_resolved = False
        multi_route_required = bool(secondary_routes)
        validator_required = True
    else:
        auto_resolved = False
        multi_route_required = True
        validator_required = True

    if primary in {"mixed_text_and_figure", "review_required"}:
        validator_required = True
        multi_route_required = True
        auto_resolved = False

    do_not_embed = validator_required or primary in {"blank_candidate", "review_required"}
    candidate_routes = [label for label, score in ranked if score > 0][:5]
    validator_contracts = [ROUTE_PROCESSORS.get(primary, ROUTE_PROCESSORS["review_required"])]
    for route in secondary_routes:
        validator_contracts.append(ROUTE_PROCESSORS.get(route, ROUTE_PROCESSORS["review_required"]))

    storage = _storage_policy(primary, confidence_band, validator_required)

    # Enforce the corpus-scale contract: quality labels can never be page
    # routes.  Scan quality is derived only from image measurements and is
    # attached as independent metadata.
    validate_route_labels([meta["legacy_route"], primary, *secondary_routes, *candidate_routes])
    scan_quality = assess_scan_quality_from_record(record, page_route=primary)

    page_number = record.get("canonical_page_number") or record.get("page_number")
    page_id = record.get("page_id") or (f"page_{page_number}" if page_number is not None else None)
    return {
        "module": MODULE,
        "version": VERSION,
        "page_number": page_number,
        "canonical_page_number": page_number,
        "page_id": page_id,
        "source_member": record.get("source_member"),
        "source_image_path": record.get("source_image_path"),
        "source_image_sha256": record.get("source_image_sha256"),
        "ocr_text_path": record.get("ocr_text_path"),
        "legacy_route": meta["legacy_route"],
        "primary_route": primary,
        "secondary_routes": secondary_routes,
        "candidate_routes": candidate_routes,
        "scan_quality": scan_quality,
        "scan_quality_state": scan_quality["quality_state"],
        "blur_detected": scan_quality["blur_detected"],
        "scan_quality_route_separated": True,
        "route_scores": {k: round(v, 3) for k, v in scores.items() if v > 0},
        "route_reasons": route_reasons,
        "route_confidence_score": round(float(max(scores.values()) if primary != "review_required" else 0.0), 3),
        "route_confidence_margin": round(float(margin), 3),
        "route_confidence_band": confidence_band,
        "auto_resolved": auto_resolved,
        "multi_route_required": multi_route_required,
        "validator_required": validator_required,
        "validator_contracts": validator_contracts,
        "do_not_embed": do_not_embed,
        "storage_policy": storage,
        "ocr_text_word_count": meta["ocr_text_word_count"],
        "part_number_count": meta["part_number_count"],
        "part_number_tokens": meta["part_number_tokens"],
        "signal_counts": {
            "procedure_term_count": meta["procedure_term_count"],
            "table_index_term_count": meta["table_index_term_count"],
            "detailed_parts_term_count": meta["detailed_parts_term_count"],
            "visual_term_count": meta["visual_term_count"],
            "concrete_visual_term_count": meta.get("concrete_visual_term_count", 0),
            "generic_ipl_visual_term_count": meta.get("generic_ipl_visual_term_count", 0),
            "ipl_visual_blocker": meta.get("ipl_visual_blocker", False),
            "cover_term_count": meta["cover_term_count"],
            "strong_cover_term_count": meta.get("strong_cover_term_count", 0),
            "weak_cover_header_term_count": meta.get("weak_cover_header_term_count", 0),
            "has_row_structure": meta["has_row_structure"],
            "has_figure_caption": meta["has_figure_caption"],
            "ink_density": meta["ink_density"],
        },
        "unsafe_record": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def _load_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records") or payload.get("page_records") or payload.get("scan_records") or []
    if not isinstance(records, list):
        raise ValueError("source scan pack does not contain a list of records")
    return [dict(r) for r in records]


def _taxonomy_labels(taxonomy_path: str | Path | None) -> list[str]:
    if not taxonomy_path:
        return CANONICAL_LABELS
    payload = _read_json(taxonomy_path)
    labels = [r.get("label") for r in payload.get("records", []) if r.get("label")]
    return labels or CANONICAL_LABELS


def build_route_confidence_resolver(
    *,
    scan_pack: str | Path,
    route_label_taxonomy: str | Path | None = None,
    output_dir: str | Path,
    high_threshold: float = 85.0,
    medium_threshold: float = 60.0,
    quality: bool = False,
) -> dict[str, Any]:
    scan_pack_path = Path(scan_pack)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    source_payload = _read_json(scan_pack_path)
    source_quality_status = source_payload.get("quality_status")
    source_records = _load_records(source_payload)
    taxonomy_labels = _taxonomy_labels(route_label_taxonomy)
    invalid_taxonomy_labels = sorted(set(CANONICAL_LABELS) - set(taxonomy_labels))

    records = [
        _resolve_record(record, high_threshold=high_threshold, medium_threshold=medium_threshold)
        for record in source_records
    ]

    route_counts = Counter(r["primary_route"] for r in records)
    confidence_counts = Counter(r["route_confidence_band"] for r in records)
    scan_quality_counts = Counter(r["scan_quality_state"] for r in records)
    blur_detected_count = sum(1 for r in records if r.get("blur_detected") is True)
    auto_resolved_count = sum(1 for r in records if r["auto_resolved"])
    multi_route_required_count = sum(1 for r in records if r["multi_route_required"])
    validator_required_count = sum(1 for r in records if r["validator_required"])
    do_not_embed_count = sum(1 for r in records if r["do_not_embed"])
    qdrant_embedding_allowed_count = sum(1 for r in records if (r.get("storage_policy") or {}).get("qdrant_embedding_allowed"))
    opensearch_index_allowed_count = sum(1 for r in records if (r.get("storage_policy") or {}).get("opensearch_index_allowed"))

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_scan_pack": str(scan_pack_path),
        "source_scan_pack_quality_status": source_quality_status,
        "route_label_taxonomy": str(route_label_taxonomy) if route_label_taxonomy else None,
        "source_record_count": len(source_records),
        "resolver_record_count": len(records),
        "canonical_route_label_count": len(CANONICAL_LABELS),
        "invalid_taxonomy_label_count": len(invalid_taxonomy_labels),
        "invalid_taxonomy_labels": invalid_taxonomy_labels,
        "primary_route_counts": dict(sorted(route_counts.items())),
        "route_confidence_band_counts": dict(sorted(confidence_counts.items())),
        "scan_quality_state_counts": dict(sorted(scan_quality_counts.items())),
        "blur_detected_count": blur_detected_count,
        "route_quality_label_violation_count": 0,
        "scan_quality_is_not_page_route": True,
        "auto_resolved_route_count": auto_resolved_count,
        "multi_route_required_count": multi_route_required_count,
        "validator_required_count": validator_required_count,
        "do_not_embed_count": do_not_embed_count,
        "qdrant_embedding_allowed_count": qdrant_embedding_allowed_count,
        "opensearch_index_allowed_count": opensearch_index_allowed_count,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "human_review_replaced_by_validator_gate": True,
        "ready_for_multi_route_processing": multi_route_required_count > 0,
        "ready_for_validator_gated_storage": validator_required_count > 0,
        **WRITE_ZEROES,
    }

    quality_status = "PASS"
    quality_failures: list[str] = []
    if source_quality_status not in {"PASS", None}:
        quality_status = "FAIL"
        quality_failures.append("source scan pack quality_status is not PASS")
    if len(records) != len(source_records):
        quality_status = "FAIL"
        quality_failures.append("resolver record count does not match source record count")
    if invalid_taxonomy_labels:
        quality_status = "FAIL"
        quality_failures.append("taxonomy is missing canonical route labels")
    if any(summary[k] for k in WRITE_ZEROES):
        quality_status = "FAIL"
        quality_failures.append("safety/write counters must remain zero")

    payload: dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS,
        "quality_status": quality_status,
        "quality_failures": quality_failures,
        "summary": summary,
        "records": records,
    }

    report_path = output / "trace_net_route_confidence_resolver_v1.json"
    records_path = output / "trace_net_route_confidence_resolver_v1_records.jsonl"
    csv_path = output / "trace_net_route_confidence_resolver_v1_records.csv"
    summary_path = output / "trace_net_route_confidence_resolver_v1_summary.json"
    md_path = output / "README_trace_net_route_confidence_resolver_v1.md"

    _write_json(report_path, payload)
    _write_jsonl(records_path, records)
    _write_csv(csv_path, records)
    _write_json(summary_path, summary)
    _write_markdown(md_path, payload)

    if quality:
        _write_json(output / "trace_net_route_confidence_resolver_v1_quality_check.json", {"quality_status": quality_status, "summary": summary, "failures": quality_failures})

    print(f"Status: {STATUS}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_auto_resolved: int = 0,
    min_multi_route_required: int = 0,
    min_validator_required: int = 0,
    require_source_quality_pass: bool = False,
    require_no_human_review_required: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unsafe: int | None = None,
    max_cover_or_title_page_routes: int | None = None,
    max_image_visual_diagram_routes: int | None = None,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary") or {}
    failures: list[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if int(summary.get("resolver_record_count") or 0) < min_records:
        failures.append(f"resolver_record_count below {min_records}")
    if int(summary.get("auto_resolved_route_count") or 0) < min_auto_resolved:
        failures.append(f"auto_resolved_route_count below {min_auto_resolved}")
    if int(summary.get("multi_route_required_count") or 0) < min_multi_route_required:
        failures.append(f"multi_route_required_count below {min_multi_route_required}")
    if int(summary.get("validator_required_count") or 0) < min_validator_required:
        failures.append(f"validator_required_count below {min_validator_required}")
    if require_source_quality_pass and summary.get("source_scan_pack_quality_status") != "PASS":
        failures.append("source scan pack quality_status is not PASS")
    route_counts = summary.get("primary_route_counts") or {}
    if max_cover_or_title_page_routes is not None:
        if int(route_counts.get("cover_or_title_page") or 0) > max_cover_or_title_page_routes:
            failures.append("too many cover_or_title_page primary routes")
    if max_image_visual_diagram_routes is not None:
        if int(route_counts.get("image_visual_diagram") or 0) > max_image_visual_diagram_routes:
            failures.append("too many image_visual_diagram primary routes")
    if require_no_human_review_required and int(summary.get("human_review_required_count") or 0) != 0:
        failures.append("human review is required")
    if max_unsafe is not None and int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("unsafe_record_count exceeds max")
    if require_no_answer_permission:
        for key in ["answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"]:
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key} must be zero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count must be zero")
    if require_no_write_attempts:
        for key in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key} must be zero")

    quality_status = "PASS" if not failures else "FAIL"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        out = path.with_name("trace_net_route_confidence_resolver_v1_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net route confidence resolver v1")
    parser.add_argument("--scan-pack", required=True)
    parser.add_argument("--route-label-taxonomy")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--high-threshold", type=float, default=85.0)
    parser.add_argument("--medium-threshold", type=float, default=60.0)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_route_confidence_resolver(
        scan_pack=args.scan_pack,
        route_label_taxonomy=args.route_label_taxonomy,
        output_dir=args.output_dir,
        high_threshold=args.high_threshold,
        medium_threshold=args.medium_threshold,
        quality=args.quality,
    )


def main_check(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net route confidence resolver v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-auto-resolved", type=int, default=0)
    parser.add_argument("--min-multi-route-required", type=int, default=0)
    parser.add_argument("--min-validator-required", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--max-cover-or-title-page-routes", type=int)
    parser.add_argument("--max-image-visual-diagram-routes", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_auto_resolved=args.min_auto_resolved,
        min_multi_route_required=args.min_multi_route_required,
        min_validator_required=args.min_validator_required,
        require_source_quality_pass=args.require_source_quality_pass,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        max_cover_or_title_page_routes=args.max_cover_or_title_page_routes,
        max_image_visual_diagram_routes=args.max_image_visual_diagram_routes,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main_build()
