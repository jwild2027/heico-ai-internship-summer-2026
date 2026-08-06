"""TRACE-Net Universal Fishnet Retry Engine v1.

This module builds a read-only, per-page retry/review plan across TRACE-Net
extractor families. It does not run OCR/table/vision extractors and it does
not mutate source truth. It turns already-created page registry, table,
visual, and ink/layout artifacts into one auditable fishnet plan.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_fishnet_retry_engine_v1"
ALGORITHM_NAME = "trace_net_universal_fishnet_retry_planner_v1"

LAYER_DEFINITIONS = [
    {
        "fishnet_layer": 0,
        "layer_name": "normal_extraction_inventory",
        "purpose": "Record which extractor outputs already exist for this page.",
    },
    {
        "fishnet_layer": 1,
        "layer_name": "ocr_cleanup_and_sparse_page_validation",
        "purpose": "Retry or validate weak OCR, sparse-ink pages, and near-blank pages without treating ink as truth.",
    },
    {
        "fishnet_layer": 2,
        "layer_name": "region_tile_and_cell_retry",
        "purpose": "Use table tiles, visual regions, and normalized rows/cells when whole-page extraction is weak.",
    },
    {
        "fishnet_layer": 3,
        "layer_name": "specialized_extractor_retry",
        "purpose": "Route pages to table, visual/callout, part catalog, or context extractors only when signals justify it.",
    },
    {
        "fishnet_layer": 4,
        "layer_name": "ocr_catalog_graph_source_compare",
        "purpose": "Compare extractor outputs against OCR, catalog/parts, graph, source trace, citations, RAG eligibility, and trust authority.",
    },
    {
        "fishnet_layer": 5,
        "layer_name": "trust_downgrade_block_or_human_review",
        "purpose": "Keep weak or unverified records retrieval-only, downgrade trust, block answer use, or send to human review.",
    },
]

RETRIEVAL_ONLY_AUTHORITY = "fishnet_retry_planner_only"
SAFETY_BUCKET = "fishnet_retry_plan"

FORBIDDEN_USER_TEXT_MARKERS = [
    "local_data\\",
    "local_data/",
    "rescarta_exports",
    "C:\\Users\\",
    "TIFF path:",
    "OCR path:",
    "Source URL:",
    "OCR text: [b",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    joined = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def read_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        records = payload.get("records")
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
        for key in ("clean_snippet_claims", "snippet_claims", "claims", "pages"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def index_by_page(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for record in records:
        page_id = record.get("page_id")
        if isinstance(page_id, str) and page_id:
            out[page_id] = record
    return out


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_str_list(value: Any) -> list[str]:
    out: list[str] = []
    for item in as_list(value):
        if item is None:
            continue
        if isinstance(item, dict):
            label = item.get("element_type") or item.get("route") or item.get("name") or item.get("id")
            if label:
                out.append(str(label))
        else:
            out.append(str(item))
    return out


def int_value(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def page_number_from_id(page_id: str) -> int | None:
    match = re.search(r"p(\d{6})$", page_id)
    if match:
        return int(match.group(1))
    return None


def contains_forbidden_user_text(value: Any) -> bool:
    text = ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, (list, tuple)):
        text = " ".join(str(v) for v in value)
    elif isinstance(value, dict):
        # Only inspect short user-facing fields; provenance paths are allowed in
        # source artifacts but are not copied into fishnet user-facing text.
        fields = [
            value.get("action"),
            value.get("reason"),
            value.get("retry_route"),
            value.get("layer_name"),
            value.get("review_reason"),
        ]
        text = " ".join(str(v) for v in fields if v is not None)
    else:
        text = str(value)
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in FORBIDDEN_USER_TEXT_MARKERS)


def classify_ocr_state(registry_record: dict[str, Any], ink_record: dict[str, Any]) -> str:
    traits = set(as_str_list(registry_record.get("page_traits")))
    bucket_counts = registry_record.get("candidate_bucket_counts") or {}
    source_text_count = int_value(bucket_counts.get("source_text_evidence"))
    page_has_ocr = registry_record.get("has_ocr") is True or source_text_count > 0 or "ocr_text_present" in traits
    if ink_record.get("source_confirmed_blank"):
        return "source_confirmed_blank"
    if page_has_ocr:
        return "ocr_present"
    if ink_record.get("ink_blank_candidate"):
        return "low_ink_needs_source_validation"
    return "ocr_missing_or_unknown"


def make_action(layer: int, action: str, retry_route: str, reason: str, extractor_family: str, *, priority: str = "normal", answer_use: str = "route_or_review_only") -> dict[str, Any]:
    return {
        "action_id": stable_id("fishact", layer, action, retry_route, reason, extractor_family, length=12),
        "fishnet_layer": layer,
        "action": action,
        "retry_route": retry_route,
        "reason": reason,
        "extractor_family": extractor_family,
        "priority": priority,
        "answer_use": answer_use,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
    }


def dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any, Any]] = set()
    out: list[dict[str, Any]] = []
    for action in actions:
        key = (action.get("fishnet_layer"), action.get("action"), action.get("retry_route"))
        if key in seen:
            continue
        seen.add(key)
        out.append(action)
    return sorted(out, key=lambda a: (int_value(a.get("fishnet_layer")), str(a.get("priority")), str(a.get("action"))))


def build_fishnet_record(
    registry_record: dict[str, Any],
    table_record: dict[str, Any] | None,
    figure_record: dict[str, Any] | None,
    ink_record: dict[str, Any] | None,
) -> dict[str, Any]:
    table_record = table_record or {}
    figure_record = figure_record or {}
    ink_record = ink_record or {}

    page_id = str(registry_record.get("page_id"))
    page_number = registry_record.get("page_number") or page_number_from_id(page_id)
    traits = as_str_list(registry_record.get("page_traits"))
    detected_elements = as_str_list(registry_record.get("detected_elements"))
    registry_routes = as_str_list(registry_record.get("recommended_extraction_routes"))
    registry_fishnet = as_list(registry_record.get("fishnet_retry_plan"))
    comparison_targets = as_str_list(registry_record.get("comparison_targets"))

    candidate_bucket_counts = registry_record.get("candidate_bucket_counts") or {}
    if not isinstance(candidate_bucket_counts, dict):
        candidate_bucket_counts = {}
    answer_support_candidate_count = int_value(registry_record.get("answer_support_candidate_count"))
    if answer_support_candidate_count == 0:
        answer_support_candidate_count = int_value(candidate_bucket_counts.get("source_text_evidence")) + int_value(candidate_bucket_counts.get("verified_part_evidence"))

    ocr_state = classify_ocr_state(registry_record, ink_record)
    layout_class = str(ink_record.get("calibrated_layout_class") or figure_record.get("visual_type") or "unknown_layout")
    visual_type = str(figure_record.get("visual_type") or ink_record.get("calibrated_visual_type") or "none")

    table_row_count = int_value(table_record.get("normalized_row_count") or table_record.get("row_count"))
    table_cell_count = int_value(table_record.get("normalized_cell_count") or table_record.get("cell_count"))
    table_repair_count = int_value(table_record.get("normalized_repair_count") or table_record.get("repair_count"))
    table_answer_support_rows = int_value(table_record.get("answer_support_row_count"))
    table_type = str(table_record.get("table_type") or "none")

    visual_needs_review = bool(figure_record.get("needs_human_review"))
    requires_catalog_compare = bool(figure_record.get("requires_catalog_compare"))
    linked_part_candidates = as_str_list(figure_record.get("linked_part_candidates"))
    callout_labels = as_str_list(figure_record.get("callout_labels"))
    needs_vision_model = bool(ink_record.get("needs_vision_model") or (visual_needs_review and visual_type not in {"none", "chart_or_plot_candidate"}))
    source_confirmed_blank = bool(ink_record.get("source_confirmed_blank"))
    ink_blank_candidate = bool(ink_record.get("ink_blank_candidate"))
    sparse_ink_page = layout_class == "sparse_ink_text_or_source_trace"

    actions: list[dict[str, Any]] = []
    actions.append(make_action(0, "inventory_existing_extractor_outputs", "existing_artifact_inventory", "Always preserve what existing OCR/source/table/visual/context extractors produced.", "registry"))
    actions.append(make_action(4, "compare_against_source_graph_and_citations", "graph_source_citation_compare", "Every fishnet outcome must remain source-resolved and citation-gated before answer use.", "graph"))
    actions.append(make_action(5, "enforce_trust_authority_gate", "trust_authority_gate", "Fishnet output cannot answer directly and must pass trust authority before answer support.", "trust"))

    if source_confirmed_blank:
        actions.append(make_action(1, "confirm_blank_without_losing_source_trace", "blank_page_review_route", "Low ink was confirmed blank by source/context checks; keep source trace but do not infer missing content.", "ocr", priority="high"))
    elif ocr_state == "ocr_present":
        actions.append(make_action(1, "ocr_cleanup_available_if_needed", "ocr_cleanup_retry", "OCR/source text exists; cleanup retry may improve snippets but cannot change source truth.", "ocr"))
    elif ocr_state == "low_ink_needs_source_validation" or sparse_ink_page:
        actions.append(make_action(1, "validate_sparse_low_ink_page", "sparse_ink_source_validation_route", "Low ink is not treated as blank unless OCR/source/context/table/part signals agree.", "ocr", priority="high"))
    else:
        actions.append(make_action(1, "retry_missing_or_unknown_ocr", "ocr_region_retry_or_human_review", "OCR is missing or unknown; retry OCR regions or send to human review before evidence use.", "ocr", priority="high"))

    table_signaled = table_row_count > 0 or table_cell_count > 0 or "table_structure_route" in registry_routes or "table_cell_normalizer_route" in registry_routes or "table" in table_type
    if table_signaled:
        actions.append(make_action(2, "validate_table_rows_and_cells", "table_cell_normalizer_route", "Table-like evidence exists; validate rows/cells and keep uncertain rows retrieval-only.", "table", priority="high"))
        actions.append(make_action(4, "compare_table_parts_against_catalog_graph", "table_catalog_graph_compare", "Structured table rows must be compared with part/catalog/graph evidence before answer support.", "table"))
        if table_repair_count > 0:
            actions.append(make_action(2, "review_repaired_table_cells", "table_repair_review_route", "Part-row repairs exist; keep repair metadata and verify catalog support.", "table", priority="high"))
        if table_answer_support_rows == 0 and table_row_count > 0:
            actions.append(make_action(5, "keep_unverified_table_rows_retrieval_only", "table_trust_downgrade_route", "Rows exist but no answer-support rows were identified; do not promote to claims.", "table"))

    visual_signaled = visual_type not in {"none", "unknown", ""} or bool(callout_labels) or bool(linked_part_candidates) or "visual_region_route" in registry_routes
    if visual_signaled:
        actions.append(make_action(2, "validate_visual_regions_and_callouts", "visual_region_retry_route", "Visual/figure/chart signals require region/callout validation before evidence use.", "visual", priority="high" if visual_needs_review else "normal"))
        if bool(callout_labels):
            actions.append(make_action(3, "extract_and_check_visual_callouts", "callout_candidate_route", "Callout labels are retrieval helpers until checked against OCR/catalog/graph.", "visual"))
        if bool(linked_part_candidates) or requires_catalog_compare:
            actions.append(make_action(4, "compare_visual_parts_against_catalog_graph", "catalog_graph_visual_compare", "Visual part candidates must be compared with catalog/graph before trust upgrade.", "visual", priority="high"))
        if needs_vision_model:
            actions.append(make_action(3, "send_to_vision_model_pilot", "vision_model_pilot_route", "Use a vision model only as advisory interpretation for hard visual pages.", "vision", priority="high"))
        if visual_needs_review:
            actions.append(make_action(5, "human_review_for_unverified_visual_page", "human_review_visual_route", "Visual evidence is unverified and remains retrieval-only until review/validation.", "review", priority="high"))

    if not bool(registry_record.get("context_v2_present")):
        actions.append(make_action(3, "optional_context_v2_expansion", "context_v2_generation_route", "ContextV2 can improve routing but cannot prove answers.", "context"))

    if answer_support_candidate_count > 0:
        actions.append(make_action(4, "verify_answer_support_citations", "citation_authority_compare", "Answer-support candidates exist; verify citation, page ID, source trace, and authority before answer use.", "citation", priority="high"))

    if not actions:
        actions.append(make_action(5, "human_review_no_route", "human_review_route", "No safe route could be selected; send to review.", "review", priority="high"))

    actions = dedupe_actions(actions)
    extractor_families = sorted({str(a.get("extractor_family")) for a in actions if a.get("extractor_family")})
    retry_routes = sorted({str(a.get("retry_route")) for a in actions if a.get("retry_route")})
    pages_needing_review = any(a.get("extractor_family") == "review" for a in actions)
    pages_needing_retry = any(str(a.get("retry_route", "")).endswith("retry") or "retry" in str(a.get("retry_route", "")) for a in actions)

    layers_present = sorted({int_value(a.get("fishnet_layer")) for a in actions})
    fishnet_retry_plan = []
    for layer_def in LAYER_DEFINITIONS:
        layer_no = layer_def["fishnet_layer"]
        layer_actions = [a for a in actions if int_value(a.get("fishnet_layer")) == layer_no]
        fishnet_retry_plan.append({
            **layer_def,
            "active": bool(layer_actions),
            "actions": layer_actions,
        })

    record = {
        "schema_version": SCHEMA_VERSION,
        "fishnet_plan_id": stable_id("fishnet", page_id),
        "page_id": page_id,
        "page_number": page_number,
        "record_type": "fishnet_retry_plan",
        "safety_bucket": SAFETY_BUCKET,
        "authority": RETRIEVAL_ONLY_AUTHORITY,
        "algorithm": ALGORITHM_NAME,
        "page_traits": traits,
        "detected_elements": detected_elements,
        "registry_recommended_routes": registry_routes,
        "registry_fishnet_layer_count": len(registry_fishnet),
        "comparison_targets": sorted(set(comparison_targets + ["ocr", "catalog_or_part_graph", "source_trace", "citations", "trust_authority"])),
        "ocr_state": ocr_state,
        "layout_class": layout_class,
        "visual_type": visual_type,
        "table_type": table_type,
        "source_confirmed_blank": source_confirmed_blank,
        "ink_blank_candidate": ink_blank_candidate,
        "sparse_ink_page": sparse_ink_page,
        "table_row_count": table_row_count,
        "table_cell_count": table_cell_count,
        "table_repair_count": table_repair_count,
        "table_answer_support_row_count": table_answer_support_rows,
        "visual_needs_review": visual_needs_review,
        "visual_requires_catalog_compare": requires_catalog_compare,
        "visual_linked_part_candidate_count": len(linked_part_candidates),
        "visual_callout_candidate_count": len(callout_labels),
        "needs_vision_model": needs_vision_model,
        "answer_support_candidate_count": answer_support_candidate_count,
        "candidate_bucket_counts": candidate_bucket_counts,
        "fishnet_layers_present": layers_present,
        "fishnet_retry_plan": fishnet_retry_plan,
        "retry_actions": actions,
        "retry_action_count": len(actions),
        "retry_routes": retry_routes,
        "extractor_families": extractor_families,
        "extractor_family_count": len(extractor_families),
        "needs_retry": pages_needing_retry,
        "needs_human_review": pages_needing_review,
        "graph_attachment_plan": {
            "status": "planned_read_only",
            "nodes_to_attach": ["Page", "FishnetRetryPlan"],
            "edges_to_attach": ["Page -> HAS_FISHNET_RETRY_PLAN -> FishnetRetryPlan"],
            "postgreSQL_writeback_status": "not_performed_in_v1",
            "can_mutate_source_truth": False,
        },
        "answer_use_policy": "route_and_review_only_not_evidence",
        "can_embed": False,
        "can_retrieve": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "final_answer_allowed": False,
    }
    record["unsafe_reasons"] = safety_reasons_for_record(record)
    record["safe_for_fishnet_planning"] = not record["unsafe_reasons"]
    return record


def safety_reasons_for_record(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not record.get("page_id"):
        reasons.append("missing_page_id")
    if record.get("can_answer_directly") is not False:
        reasons.append("can_answer_directly_not_false")
    if record.get("can_prove_claims") is not False:
        reasons.append("can_prove_claims_not_false")
    if record.get("can_mutate_source_truth") is not False:
        reasons.append("can_mutate_source_truth_not_false")
    if record.get("final_answer_allowed") is not False:
        reasons.append("final_answer_allowed_not_false")
    if not record.get("fishnet_retry_plan"):
        reasons.append("missing_fishnet_retry_plan")
    for action in record.get("retry_actions", []):
        if action.get("can_mutate_source_truth") is not False:
            reasons.append("action_can_mutate_source_truth")
        if action.get("can_answer_directly") is not False:
            reasons.append("action_can_answer_directly")
        if contains_forbidden_user_text(action):
            reasons.append("forbidden_marker_in_user_facing_action")
            break
    return sorted(set(reasons))


def build_summary(records: list[dict[str, Any]], source_summaries: dict[str, Any] | None = None) -> dict[str, Any]:
    source_summaries = source_summaries or {}
    layer_counts: Counter[int] = Counter()
    action_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    layout_counts: Counter[str] = Counter()
    ocr_counts: Counter[str] = Counter()
    table_type_counts: Counter[str] = Counter()
    visual_type_counts: Counter[str] = Counter()
    unsafe_count = 0
    direct_answer_allowed = 0
    prove_claims = 0
    mutate_truth = 0
    final_allowed = 0
    missing_page_id = 0
    pages_with_plan = 0
    pages_with_review = 0
    pages_with_retry = 0
    pages_needing_vision = 0
    source_confirmed_blank = 0
    sparse_ink = 0
    table_retry_pages = 0
    visual_retry_pages = 0
    ocr_retry_pages = 0
    pages_with_answer_support_candidates = 0

    for record in records:
        if not record.get("page_id"):
            missing_page_id += 1
        if record.get("fishnet_retry_plan"):
            pages_with_plan += 1
        if record.get("needs_human_review"):
            pages_with_review += 1
        if record.get("needs_retry"):
            pages_with_retry += 1
        if record.get("needs_vision_model"):
            pages_needing_vision += 1
        if record.get("source_confirmed_blank"):
            source_confirmed_blank += 1
        if record.get("sparse_ink_page"):
            sparse_ink += 1
        if int_value(record.get("answer_support_candidate_count")) > 0:
            pages_with_answer_support_candidates += 1
        if record.get("unsafe_reasons"):
            unsafe_count += 1
        if record.get("can_answer_directly") is not False:
            direct_answer_allowed += 1
        if record.get("can_prove_claims") is not False:
            prove_claims += 1
        if record.get("can_mutate_source_truth") is not False:
            mutate_truth += 1
        if record.get("final_answer_allowed") is not False:
            final_allowed += 1

        layout_counts[str(record.get("layout_class"))] += 1
        ocr_counts[str(record.get("ocr_state"))] += 1
        table_type_counts[str(record.get("table_type"))] += 1
        visual_type_counts[str(record.get("visual_type"))] += 1
        for layer in record.get("fishnet_layers_present", []):
            layer_counts[int_value(layer)] += 1
        for action in record.get("retry_actions", []):
            action_counts[str(action.get("action"))] += 1
            route_counts[str(action.get("retry_route"))] += 1
            family = str(action.get("extractor_family"))
            family_counts[family] += 1
            if family == "table":
                table_retry_pages += 1
            elif family in {"visual", "vision"}:
                visual_retry_pages += 1
            elif family == "ocr":
                ocr_retry_pages += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM_NAME,
        "fishnet_record_count": len(records),
        "pages_with_retry_plan_count": pages_with_plan,
        "pages_with_review_count": pages_with_review,
        "pages_with_retry_count": pages_with_retry,
        "pages_needing_vision_model_count": pages_needing_vision,
        "source_confirmed_blank_page_count": source_confirmed_blank,
        "sparse_ink_page_count": sparse_ink,
        "pages_with_answer_support_candidates_count": pages_with_answer_support_candidates,
        "table_retry_action_count": table_retry_pages,
        "visual_retry_action_count": visual_retry_pages,
        "ocr_retry_action_count": ocr_retry_pages,
        "missing_page_id_count": missing_page_id,
        "unsafe_fishnet_record_count": unsafe_count,
        "direct_answer_allowed_count": direct_answer_allowed,
        "claim_proof_allowed_count": prove_claims,
        "source_truth_mutation_allowed_count": mutate_truth,
        "final_answer_allowed_count": final_allowed,
        "fishnet_layer_counts": {str(k): v for k, v in sorted(layer_counts.items())},
        "retry_action_counts": dict(action_counts),
        "retry_route_counts": dict(route_counts),
        "extractor_family_counts": dict(family_counts),
        "extractor_family_count": len(family_counts),
        "layout_class_counts": dict(layout_counts),
        "ocr_state_counts": dict(ocr_counts),
        "table_type_counts": dict(table_type_counts),
        "visual_type_counts": dict(visual_type_counts),
        "source_summaries": source_summaries,
    }


def quality_checks(
    summary: dict[str, Any],
    *,
    require_page_count: int | None = None,
    min_fishnet_records: int = 1,
    min_pages_with_retry_plan: int = 1,
    min_pages_with_review_or_retry: int = 0,
    min_extractor_family_count: int = 1,
    min_table_retry_actions: int = 0,
    min_visual_retry_actions: int = 0,
    min_ocr_retry_actions: int = 0,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    count = int_value(summary.get("fishnet_record_count"))
    add("min_fishnet_records", count >= min_fishnet_records, count, f">= {min_fishnet_records}")
    if require_page_count is not None:
        add("require_page_count", count == require_page_count, count, f"== {require_page_count}")
    plan_count = int_value(summary.get("pages_with_retry_plan_count"))
    add("min_pages_with_retry_plan", plan_count >= min_pages_with_retry_plan, plan_count, f">= {min_pages_with_retry_plan}")
    review_or_retry = int_value(summary.get("pages_with_review_count")) + int_value(summary.get("pages_with_retry_count"))
    add("min_pages_with_review_or_retry", review_or_retry >= min_pages_with_review_or_retry, review_or_retry, f">= {min_pages_with_review_or_retry}")
    fam_count = int_value(summary.get("extractor_family_count"))
    add("min_extractor_family_count", fam_count >= min_extractor_family_count, fam_count, f">= {min_extractor_family_count}")
    add("min_table_retry_actions", int_value(summary.get("table_retry_action_count")) >= min_table_retry_actions, summary.get("table_retry_action_count"), f">= {min_table_retry_actions}")
    add("min_visual_retry_actions", int_value(summary.get("visual_retry_action_count")) >= min_visual_retry_actions, summary.get("visual_retry_action_count"), f">= {min_visual_retry_actions}")
    add("min_ocr_retry_actions", int_value(summary.get("ocr_retry_action_count")) >= min_ocr_retry_actions, summary.get("ocr_retry_action_count"), f">= {min_ocr_retry_actions}")
    add("missing_page_id_count_zero", int_value(summary.get("missing_page_id_count")) == 0, summary.get("missing_page_id_count"), "== 0")
    add("unsafe_fishnet_record_count_zero", int_value(summary.get("unsafe_fishnet_record_count")) == 0, summary.get("unsafe_fishnet_record_count"), "== 0")
    add("direct_answer_allowed_count_zero", int_value(summary.get("direct_answer_allowed_count")) == 0, summary.get("direct_answer_allowed_count"), "== 0")
    add("claim_proof_allowed_count_zero", int_value(summary.get("claim_proof_allowed_count")) == 0, summary.get("claim_proof_allowed_count"), "== 0")
    add("source_truth_mutation_allowed_count_zero", int_value(summary.get("source_truth_mutation_allowed_count")) == 0, summary.get("source_truth_mutation_allowed_count"), "== 0")
    add("final_answer_allowed_count_zero", int_value(summary.get("final_answer_allowed_count")) == 0, summary.get("final_answer_allowed_count"), "== 0")
    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {"status": status, "checks": checks}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# TRACE-Net Universal Fishnet Retry Engine v1",
        "",
        f"**Status:** {payload.get('status')}",
        f"**Quality:** {payload.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "fishnet_record_count",
        "pages_with_retry_plan_count",
        "pages_with_review_count",
        "pages_with_retry_count",
        "pages_needing_vision_model_count",
        "source_confirmed_blank_page_count",
        "sparse_ink_page_count",
        "table_retry_action_count",
        "visual_retry_action_count",
        "ocr_retry_action_count",
        "unsafe_fishnet_record_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend([
        "",
        "## Safety contract",
        "",
        "- Fishnet retry plans are route/review metadata only.",
        "- They cannot answer directly.",
        "- They cannot prove claims.",
        "- They cannot mutate source truth.",
        "- Every later answer use still requires source resolution, citation, and authority gates.",
        "",
    ])
    return "\n".join(lines)


def html_report(markdown: str) -> str:
    return "<html><body><pre>" + html.escape(markdown) + "</pre></body></html>\n"


def build_trace_net_fishnet_retry_engine(
    *,
    page_registry_path: str | Path,
    table_cell_normalizer_path: str | Path | None = None,
    figure_chart_understanding_path: str | Path | None = None,
    visual_ink_layout_calibrator_path: str | Path | None = None,
    evidence_consensus_summary_path: str | Path | None = None,
    output_dir: str | Path = "local_data/organization/trace_net/fishnet_retry_engine",
    require_page_count: int | None = None,
    min_fishnet_records: int = 1,
    min_pages_with_retry_plan: int = 1,
    min_pages_with_review_or_retry: int = 0,
    min_extractor_family_count: int = 1,
    min_table_retry_actions: int = 0,
    min_visual_retry_actions: int = 0,
    min_ocr_retry_actions: int = 0,
    write_quality: bool = False,
) -> dict[str, Any]:
    page_registry_payload = read_json(page_registry_path, {})
    page_records = records_from_payload(page_registry_payload)
    table_payload = read_json(table_cell_normalizer_path, {})
    figure_payload = read_json(figure_chart_understanding_path, {})
    ink_payload = read_json(visual_ink_layout_calibrator_path, {})
    evidence_summary = read_json(evidence_consensus_summary_path, {})

    if not page_records:
        raise ValueError("page registry contains no records")

    table_by_page = index_by_page(records_from_payload(table_payload))
    figure_by_page = index_by_page(records_from_payload(figure_payload))
    ink_by_page = index_by_page(records_from_payload(ink_payload))

    records = [
        build_fishnet_record(
            registry_record=page_record,
            table_record=table_by_page.get(str(page_record.get("page_id"))),
            figure_record=figure_by_page.get(str(page_record.get("page_id"))),
            ink_record=ink_by_page.get(str(page_record.get("page_id"))),
        )
        for page_record in page_records
    ]
    records.sort(key=lambda r: (int_value(r.get("page_number"), 999999), str(r.get("page_id"))))

    source_summaries = {
        "page_registry_quality_status": page_registry_payload.get("quality_status") or (page_registry_payload.get("quality") or {}).get("status") or "",
        "table_cell_normalizer_quality_status": table_payload.get("quality_status") or (table_payload.get("quality") or {}).get("status") or "",
        "figure_chart_understanding_quality_status": figure_payload.get("quality_status") or (figure_payload.get("quality") or {}).get("status") or "",
        "visual_ink_layout_calibrator_quality_status": ink_payload.get("quality_status") or (ink_payload.get("quality") or {}).get("status") or "",
        "evidence_consensus_status": evidence_summary.get("status") or evidence_summary.get("quality_status") or "",
    }
    summary = build_summary(records, source_summaries=source_summaries)
    quality = quality_checks(
        summary,
        require_page_count=require_page_count,
        min_fishnet_records=min_fishnet_records,
        min_pages_with_retry_plan=min_pages_with_retry_plan,
        min_pages_with_review_or_retry=min_pages_with_review_or_retry,
        min_extractor_family_count=min_extractor_family_count,
        min_table_retry_actions=min_table_retry_actions,
        min_visual_retry_actions=min_visual_retry_actions,
        min_ocr_retry_actions=min_ocr_retry_actions,
    )

    now = utc_now()
    out_dir = Path(output_dir)
    report_path = out_dir / "trace_net_fishnet_retry_engine_v1.json"
    records_path = out_dir / "trace_net_fishnet_retry_engine_v1_records.jsonl"
    actions_path = out_dir / "trace_net_fishnet_retry_engine_v1_actions.jsonl"
    routes_path = out_dir / "trace_net_fishnet_retry_engine_v1_routes.jsonl"
    summary_path = out_dir / "trace_net_fishnet_retry_engine_v1_summary.json"
    manifest_path = out_dir / "trace_net_fishnet_retry_engine_v1_manifest.json"
    quality_path = out_dir / "trace_net_fishnet_retry_engine_v1_quality.json"
    md_path = out_dir / "trace_net_fishnet_retry_engine_v1.md"
    html_path = out_dir / "trace_net_fishnet_retry_engine_v1.html"

    actions = []
    routes = []
    for record in records:
        for action in record.get("retry_actions", []):
            row = {"page_id": record["page_id"], "page_number": record.get("page_number"), **action}
            actions.append(row)
            routes.append({
                "page_id": record["page_id"],
                "page_number": record.get("page_number"),
                "retry_route": action.get("retry_route"),
                "extractor_family": action.get("extractor_family"),
                "fishnet_layer": action.get("fishnet_layer"),
                "priority": action.get("priority"),
            })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM_NAME,
        "created_at": now,
        "inputs": {
            "page_registry": str(page_registry_path),
            "table_cell_normalizer": str(table_cell_normalizer_path) if table_cell_normalizer_path else None,
            "figure_chart_understanding": str(figure_chart_understanding_path) if figure_chart_understanding_path else None,
            "visual_ink_layout_calibrator": str(visual_ink_layout_calibrator_path) if visual_ink_layout_calibrator_path else None,
            "evidence_consensus_summary": str(evidence_consensus_summary_path) if evidence_consensus_summary_path else None,
        },
        "outputs": {
            "report_path": str(report_path),
            "records_path": str(records_path),
            "actions_path": str(actions_path),
            "routes_path": str(routes_path),
            "summary_path": str(summary_path),
            "manifest_path": str(manifest_path),
            "quality_path": str(quality_path),
            "markdown_path": str(md_path),
            "html_path": str(html_path),
        },
        "read_only": True,
        "postgreSQL_writeback_status": "not_performed_in_v1",
        "qdrant_writeback_status": "not_performed_in_v1",
        "source_truth_mutations_performed": 0,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM_NAME,
        "created_at": now,
        "status": "FISHNET_RETRY_ENGINE_BUILT",
        "quality_status": quality["status"],
        "record_count": len(records),
        "records": records,
        "summary": summary,
        "quality": quality,
        "manifest": manifest,
        "answer_status": "FISHNET_RETRY_PLANS_ONLY",
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
    }

    write_json(report_path, payload)
    write_jsonl(records_path, records)
    write_jsonl(actions_path, actions)
    write_jsonl(routes_path, routes)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    md = markdown_report(payload)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html_report(md), encoding="utf-8")

    return payload


def check_trace_net_fishnet_retry_engine_quality(
    *,
    report_path: str | Path,
    require_page_count: int | None = None,
    min_fishnet_records: int = 1,
    min_pages_with_retry_plan: int = 1,
    min_pages_with_review_or_retry: int = 0,
    min_extractor_family_count: int = 1,
    min_table_retry_actions: int = 0,
    min_visual_retry_actions: int = 0,
    min_ocr_retry_actions: int = 0,
    write_json_quality: bool = False,
) -> dict[str, Any]:
    payload = read_json(report_path, {})
    if not isinstance(payload, dict) or not payload:
        raise ValueError(f"could not read fishnet report: {report_path}")
    summary = payload.get("summary") or build_summary(records_from_payload(payload))
    quality = quality_checks(
        summary,
        require_page_count=require_page_count,
        min_fishnet_records=min_fishnet_records,
        min_pages_with_retry_plan=min_pages_with_retry_plan,
        min_pages_with_review_or_retry=min_pages_with_review_or_retry,
        min_extractor_family_count=min_extractor_family_count,
        min_table_retry_actions=min_table_retry_actions,
        min_visual_retry_actions=min_visual_retry_actions,
        min_ocr_retry_actions=min_ocr_retry_actions,
    )
    if write_json_quality:
        quality_path = Path(report_path).with_name("trace_net_fishnet_retry_engine_v1_quality.json")
        write_json(quality_path, quality)
    return quality


def add_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page-registry", required=True)
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--figure-chart-understanding")
    parser.add_argument("--visual-ink-layout-calibrator")
    parser.add_argument("--evidence-consensus-summary")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/fishnet_retry_engine")
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-fishnet-records", type=int, default=1)
    parser.add_argument("--min-pages-with-retry-plan", type=int, default=1)
    parser.add_argument("--min-pages-with-review-or-retry", type=int, default=0)
    parser.add_argument("--min-extractor-family-count", type=int, default=1)
    parser.add_argument("--min-table-retry-actions", type=int, default=0)
    parser.add_argument("--min-visual-retry-actions", type=int, default=0)
    parser.add_argument("--min-ocr-retry-actions", type=int, default=0)
    parser.add_argument("--quality", action="store_true")


def add_check_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-fishnet-records", type=int, default=1)
    parser.add_argument("--min-pages-with-retry-plan", type=int, default=1)
    parser.add_argument("--min-pages-with-review-or-retry", type=int, default=0)
    parser.add_argument("--min-extractor-family-count", type=int, default=1)
    parser.add_argument("--min-table-retry-actions", type=int, default=0)
    parser.add_argument("--min-visual-retry-actions", type=int, default=0)
    parser.add_argument("--min-ocr-retry-actions", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")


def print_build_result(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    manifest = payload["manifest"]
    print("TRACE-Net universal fishnet retry engine v1")
    print(f" Status: {payload['status']}")
    print(f" Quality status: {payload['quality_status']}")
    for key in [
        "fishnet_record_count",
        "pages_with_retry_plan_count",
        "pages_with_review_count",
        "pages_with_retry_count",
        "pages_needing_vision_model_count",
        "source_confirmed_blank_page_count",
        "sparse_ink_page_count",
        "table_retry_action_count",
        "visual_retry_action_count",
        "ocr_retry_action_count",
        "unsafe_fishnet_record_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {manifest['outputs']['report_path']}")
    print(f" quality_path: {manifest['outputs']['quality_path']}")


def print_quality_result(quality: dict[str, Any], payload: dict[str, Any] | None = None) -> None:
    summary = (payload or {}).get("summary", {}) if payload else {}
    print("TRACE-Net universal fishnet retry engine v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "fishnet_record_count",
        "pages_with_retry_plan_count",
        "pages_with_review_count",
        "pages_with_retry_count",
        "pages_needing_vision_model_count",
        "source_confirmed_blank_page_count",
        "sparse_ink_page_count",
        "table_retry_action_count",
        "visual_retry_action_count",
        "ocr_retry_action_count",
        "unsafe_fishnet_record_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        if key in summary:
            print(f" {key}: {summary.get(key)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Universal Fishnet Retry Engine v1")
    add_build_args(parser)
    args = parser.parse_args(argv)
    try:
        payload = build_trace_net_fishnet_retry_engine(
            page_registry_path=args.page_registry,
            table_cell_normalizer_path=args.table_cell_normalizer,
            figure_chart_understanding_path=args.figure_chart_understanding,
            visual_ink_layout_calibrator_path=args.visual_ink_layout_calibrator,
            evidence_consensus_summary_path=args.evidence_consensus_summary,
            output_dir=args.output_dir,
            require_page_count=args.require_page_count,
            min_fishnet_records=args.min_fishnet_records,
            min_pages_with_retry_plan=args.min_pages_with_retry_plan,
            min_pages_with_review_or_retry=args.min_pages_with_review_or_retry,
            min_extractor_family_count=args.min_extractor_family_count,
            min_table_retry_actions=args.min_table_retry_actions,
            min_visual_retry_actions=args.min_visual_retry_actions,
            min_ocr_retry_actions=args.min_ocr_retry_actions,
            write_quality=args.quality,
        )
        print_build_result(payload)
        return 0 if payload["quality_status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover - CLI safety
        print(f"TRACE-Net fishnet retry engine failed: {exc}")
        return 2


def quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Universal Fishnet Retry Engine v1 quality")
    add_check_args(parser)
    args = parser.parse_args(argv)
    try:
        payload = read_json(args.report_path, {})
        quality = check_trace_net_fishnet_retry_engine_quality(
            report_path=args.report_path,
            require_page_count=args.require_page_count,
            min_fishnet_records=args.min_fishnet_records,
            min_pages_with_retry_plan=args.min_pages_with_retry_plan,
            min_pages_with_review_or_retry=args.min_pages_with_review_or_retry,
            min_extractor_family_count=args.min_extractor_family_count,
            min_table_retry_actions=args.min_table_retry_actions,
            min_visual_retry_actions=args.min_visual_retry_actions,
            min_ocr_retry_actions=args.min_ocr_retry_actions,
            write_json_quality=args.write_json,
        )
        print_quality_result(quality, payload if isinstance(payload, dict) else None)
        return 0 if quality["status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover - CLI safety
        print(f"TRACE-Net fishnet retry quality check failed: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
