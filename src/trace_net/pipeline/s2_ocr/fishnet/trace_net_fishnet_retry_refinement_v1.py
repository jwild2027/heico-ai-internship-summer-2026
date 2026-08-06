"""TRACE-Net Fishnet Action Severity / Retry Disposition Refinement v1.

This module refines the raw universal fishnet retry plan into a less-noisy,
priority-aware action plan. It keeps the TRACE-Net safety boundary intact:
fishnet can route, retry, review, and block, but it cannot answer, prove claims,
or mutate source truth.
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
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_fishnet_retry_refinement_v1"
ALGORITHM = "trace_net_fishnet_action_severity_retry_disposition_refinement_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/fishnet_retry_refined")

BASELINE_ACTIONS = {
    "inventory_existing_extractor_outputs",
    "compare_against_source_graph_and_citations",
    "verify_answer_support_citations",
    "enforce_trust_authority_gate",
}

BLANK_HANDLING_ACTIONS = {
    "confirm_blank_without_losing_source_trace",
}

OPTIONAL_ACTIONS = {
    "optional_context_v2_expansion",
    "ocr_cleanup_available_if_needed",
}

REVIEW_ACTION_PATTERNS = (
    "human_review",
    "review_repaired_table_cells",
    "review_table_candidate",
    "manual_review",
)

BLOCK_OR_DOWNGRADE_PATTERNS = (
    "block_from_answer",
    "block_from_rag",
    "trust_downgrade",
    "downgrade",
    "keep_unverified_table_rows_retrieval_only",
)

TABLE_ACTIONS = {
    "validate_table_rows_and_cells",
    "compare_table_parts_against_catalog_graph",
    "review_repaired_table_cells",
    "keep_unverified_table_rows_retrieval_only",
}

VISUAL_ACTIONS = {
    "validate_visual_regions_and_callouts",
    "extract_and_check_visual_callouts",
    "send_to_vision_model_pilot",
    "compare_visual_parts_against_catalog_graph",
    "human_review_for_unverified_visual_page",
}

MEANINGFUL_TABLE_TYPES = {
    "parts_list_table",
    "list_of_effective_pages",
    "ata_index_table",
    "index_table",
    "revision_table",
    "vendor_table",
    "maintenance_table",
    "table_or_grid",
}

VISUAL_LAYOUT_CLASSES = {
    "parts_list_or_illustrated_parts",
    "parts_list_table",
    "mixed_table_and_diagram",
    "figure_or_diagram",
    "unknown_visual_layout",
}

CHART_LAYOUT_CLASSES = {
    "chart_or_plot",
}

TEXT_OR_BLANK_LAYOUT_CLASSES = {
    "blank",
    "text_heavy",
    "sparse_ink_text_or_source_trace",
}

FORBIDDEN_USER_VISIBLE_MARKERS = (
    "can_answer_directly: true",
    "can_prove_claims: true",
    "can_mutate_source_truth: true",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    joined = "||".join(str(p) for p in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def load_fishnet_report(path: Path) -> Dict[str, Any]:
    report = read_json(path)
    records = report.get("records")
    if not isinstance(records, list):
        raise ValueError(f"Fishnet report missing records list: {path}")
    return report


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _has_any(text: str, needles: Sequence[str]) -> bool:
    text_l = text.lower()
    return any(n.lower() in text_l for n in needles)


def is_meaningful_table(table_type: str, layout_class: str) -> bool:
    table_type_l = table_type.lower()
    layout_l = layout_class.lower()
    if table_type_l in {"", "none", "unknown_table"}:
        return False
    if table_type_l in MEANINGFUL_TABLE_TYPES:
        return True
    return "table" in table_type_l or layout_l in {"parts_list_table", "table_or_grid", "mixed_table_and_diagram"}


def is_visual_retry_relevant(record: Mapping[str, Any]) -> bool:
    layout = _lower(record.get("layout_class"))
    if layout in TEXT_OR_BLANK_LAYOUT_CLASSES:
        return False
    if record.get("source_confirmed_blank") is True or _lower(record.get("ocr_state")) == "source_confirmed_blank":
        return False
    if record.get("needs_vision_model") is True:
        return True
    visual_type = _lower(record.get("visual_type"))
    if "parts_diagram" in visual_type or "illustrated_parts" in visual_type or "figure" in visual_type or "diagram" in visual_type:
        return True
    if layout in VISUAL_LAYOUT_CLASSES or layout in CHART_LAYOUT_CLASSES:
        return True
    return False


def action_name(action: Mapping[str, Any]) -> str:
    return _lower(action.get("action"))


def route_name(action: Mapping[str, Any]) -> str:
    return _lower(action.get("retry_route"))


def classify_action(record: Mapping[str, Any], action: Mapping[str, Any]) -> Tuple[str, str, str]:
    """Return (category, priority, rationale) for one raw fishnet action."""
    name = action_name(action)
    route = route_name(action)
    layout = _lower(record.get("layout_class"))
    table_type = _lower(record.get("table_type"))
    ocr_state = _lower(record.get("ocr_state"))

    if name in BASELINE_ACTIONS:
        return "baseline_validation", "low", "always-on TRACE-Net safety validation"

    if name in BLANK_HANDLING_ACTIONS:
        return "blank_handling", "medium", "confirmed blank handling preserves source trace without inferring missing content"

    if any(pattern in name for pattern in BLOCK_OR_DOWNGRADE_PATTERNS):
        return "block_or_downgrade", "high", "record remains retrieval-only or downgraded until evidence is verified"

    if any(pattern in name for pattern in REVIEW_ACTION_PATTERNS):
        return "review_required", "high", "human/review route required before visual/table evidence can be trusted"

    if name in OPTIONAL_ACTIONS:
        return "optional_enrichment", "low", "available enrichment route, not a required retry"

    if name in TABLE_ACTIONS or "table" in name or "table" in route:
        if is_meaningful_table(table_type, layout):
            return "actual_retry", "medium", "meaningful table/list route needs row/cell validation or catalog comparison"
        return "optional_enrichment", "low", "table route is only exploratory because table type is unknown/none"

    if name in VISUAL_ACTIONS or "visual" in name or "vision" in name or "callout" in name or "visual" in route or "vision" in route:
        if is_visual_retry_relevant(record):
            if "human_review" in name:
                return "review_required", "high", "unverified visual evidence requires review"
            if "send_to_vision" in name or "vision_model" in route:
                return "actual_retry", "high", "calibrated visual page should go through advisory vision pilot"
            return "actual_retry", "medium", "calibrated visual page needs visual region/callout validation"
        return "optional_enrichment", "low", "visual route demoted because ink/layout calibration says blank or text-heavy"

    if "ocr" in name or "ocr" in route:
        if ocr_state == "source_confirmed_blank":
            return "blank_handling", "medium", "blank page gets source-trace confirmation instead of OCR retry"
        return "optional_enrichment", "low", "OCR cleanup is available if downstream evidence is weak"

    if "context" in name or "context" in route:
        return "optional_enrichment", "low", "ContextV2 expansion is retrieval guidance only"

    if "catalog" in name or "graph" in name or "citation" in name or "authority" in name:
        return "baseline_validation", "low", "comparison/gating action is safety validation, not retry"

    return "optional_enrichment", "low", "unrecognized action treated as optional enrichment to avoid false retry pressure"


def refine_action(record: Mapping[str, Any], action: Mapping[str, Any], index: int) -> Dict[str, Any]:
    category, priority, rationale = classify_action(record, action)
    page_id = _norm(record.get("page_id"))
    raw_action = _norm(action.get("action"))
    route = _norm(action.get("retry_route"))
    fishnet_layer = _norm(action.get("fishnet_layer"))
    refined = dict(action)
    refined.update({
        "refined_action_id": stable_id("fnact", page_id, index, raw_action, route),
        "page_id": page_id,
        "action_category": category,
        "severity": priority,
        "priority": priority,
        "rationale": rationale,
        "is_actual_retry": category == "actual_retry",
        "is_baseline_validation": category == "baseline_validation",
        "is_review_required": category == "review_required",
        "is_optional_enrichment": category == "optional_enrichment",
        "is_block_or_downgrade": category == "block_or_downgrade",
        "is_blank_handling": category == "blank_handling",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "final_answer_allowed": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "source_truth_mutations_performed": 0,
        "fishnet_layer": fishnet_layer,
        "action": raw_action,
        "retry_route": route,
    })
    return refined


def disposition_from_categories(categories: Mapping[str, int], record: Mapping[str, Any]) -> Tuple[str, str]:
    if categories.get("block_or_downgrade", 0) > 0:
        return "blocked_or_downgraded_until_verified", "high"
    if categories.get("review_required", 0) > 0:
        return "review_required", "high"
    if categories.get("actual_retry", 0) > 0:
        return "retry_required", "medium"
    if categories.get("blank_handling", 0) > 0 and _lower(record.get("ocr_state")) == "source_confirmed_blank":
        return "source_confirmed_blank_preserve_trace", "low"
    if categories.get("optional_enrichment", 0) > 0:
        return "baseline_validation_plus_optional_enrichment", "low"
    return "baseline_validation_only", "low"


def summarize_record_actions(actions: Sequence[Mapping[str, Any]]) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = defaultdict(list)
    for action in actions:
        groups[_norm(action.get("action_category"))].append(_norm(action.get("action")))
    return {
        "baseline_validation_actions": groups.get("baseline_validation", []),
        "actual_retry_actions": groups.get("actual_retry", []),
        "review_actions": groups.get("review_required", []),
        "optional_enrichment_actions": groups.get("optional_enrichment", []),
        "block_or_downgrade_actions": groups.get("block_or_downgrade", []),
        "blank_handling_actions": groups.get("blank_handling", []),
    }


def refine_fishnet_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = _norm(record.get("page_id"))
    raw_actions = record.get("retry_actions") or []
    if not isinstance(raw_actions, list):
        raw_actions = []

    refined_actions = [refine_action(record, action if isinstance(action, Mapping) else {}, i) for i, action in enumerate(raw_actions)]
    category_counts = Counter(_norm(a.get("action_category")) for a in refined_actions)
    disposition, priority = disposition_from_categories(category_counts, record)
    grouped_names = summarize_record_actions(refined_actions)

    actual_retry_routes = sorted({_norm(a.get("retry_route")) for a in refined_actions if a.get("action_category") == "actual_retry" and _norm(a.get("retry_route"))})
    review_routes = sorted({_norm(a.get("retry_route")) for a in refined_actions if a.get("action_category") == "review_required" and _norm(a.get("retry_route"))})
    optional_routes = sorted({_norm(a.get("retry_route")) for a in refined_actions if a.get("action_category") == "optional_enrichment" and _norm(a.get("retry_route"))})

    refined = {
        "fishnet_refinement_id": stable_id("fnref", page_id, SCHEMA_VERSION),
        "source_fishnet_record_id": record.get("fishnet_record_id") or record.get("record_id") or page_id,
        "page_id": page_id,
        "page_number": record.get("page_number"),
        "ocr_state": record.get("ocr_state"),
        "layout_class": record.get("layout_class"),
        "visual_type": record.get("visual_type"),
        "table_type": record.get("table_type"),
        "fishnet_disposition": disposition,
        "priority": priority,
        "needs_actual_retry": category_counts.get("actual_retry", 0) > 0,
        "needs_human_review": category_counts.get("review_required", 0) > 0,
        "needs_block_or_downgrade": category_counts.get("block_or_downgrade", 0) > 0,
        "has_optional_enrichment": category_counts.get("optional_enrichment", 0) > 0,
        "source_confirmed_blank": _lower(record.get("ocr_state")) == "source_confirmed_blank" or bool(record.get("source_confirmed_blank")),
        "baseline_validation_action_count": category_counts.get("baseline_validation", 0),
        "actual_retry_action_count": category_counts.get("actual_retry", 0),
        "review_action_count": category_counts.get("review_required", 0),
        "optional_enrichment_action_count": category_counts.get("optional_enrichment", 0),
        "block_or_downgrade_action_count": category_counts.get("block_or_downgrade", 0),
        "blank_handling_action_count": category_counts.get("blank_handling", 0),
        "action_category_counts": dict(category_counts),
        "retry_actions": refined_actions,
        "actual_retry_routes": actual_retry_routes,
        "review_routes": review_routes,
        "optional_enrichment_routes": optional_routes,
        "extractor_families": record.get("extractor_families") or [],
        "raw_retry_routes": record.get("retry_routes") or [],
        "raw_needs_retry": bool(record.get("needs_retry")),
        "raw_needs_human_review": bool(record.get("needs_human_review")),
        "raw_needs_vision_model": bool(record.get("needs_vision_model")),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "final_answer_allowed": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "source_truth_mutations_performed": 0,
        "answer_use_policy": "retry_plan_only_not_evidence",
    }
    refined.update(grouped_names)
    refined["unsafe_reasons"] = find_refined_record_unsafe_reasons(refined)
    refined["safe_for_graph_attachment_plan"] = len(refined["unsafe_reasons"]) == 0
    return refined


def find_refined_record_unsafe_reasons(record: Mapping[str, Any]) -> List[str]:
    reasons: List[str] = []
    page_id = _norm(record.get("page_id"))
    if not page_id:
        reasons.append("missing_page_id")
    if record.get("can_answer_directly") is not False:
        reasons.append("fishnet_can_answer_directly")
    if record.get("can_prove_claims") is not False:
        reasons.append("fishnet_can_prove_claims")
    if record.get("can_mutate_source_truth") is not False:
        reasons.append("fishnet_can_mutate_source_truth")
    if record.get("final_answer_allowed") is not False:
        reasons.append("fishnet_final_answer_allowed")
    if record.get("source_truth_mutations_performed") not in (0, None):
        reasons.append("source_truth_mutation_performed")
    # Only scan the short user-visible policy/rationale strings, not full provenance.
    visible_text = " ".join([
        _norm(record.get("answer_use_policy")),
        _norm(record.get("fishnet_disposition")),
        " ".join(_norm(a.get("rationale")) for a in record.get("retry_actions", []) if isinstance(a, Mapping)),
    ])
    if _has_any(visible_text, FORBIDDEN_USER_VISIBLE_MARKERS):
        reasons.append("forbidden_user_visible_marker")
    return reasons


def build_summary(refined_records: Sequence[Mapping[str, Any]], source_report: Mapping[str, Any]) -> Dict[str, Any]:
    records = list(refined_records)
    action_rows: List[Mapping[str, Any]] = []
    for record in records:
        for action in record.get("retry_actions", []):
            if isinstance(action, Mapping):
                action_rows.append(action)

    layout_counts = Counter(_norm(r.get("layout_class")) or "unknown" for r in records)
    ocr_counts = Counter(_norm(r.get("ocr_state")) or "unknown" for r in records)
    disposition_counts = Counter(_norm(r.get("fishnet_disposition")) for r in records)
    action_category_counts = Counter(_norm(a.get("action_category")) for a in action_rows)
    retry_route_counts = Counter(_norm(a.get("retry_route")) for a in action_rows if _norm(a.get("retry_route")))

    confirmed_blank_pages_with_visual_retry = 0
    text_heavy_pages_with_vision_retry = 0
    unknown_table_pages_with_table_answer_retry = 0
    actual_retry_page_count = 0
    review_page_count = 0
    optional_page_count = 0
    baseline_page_count = 0
    block_page_count = 0
    missing_page_id_count = 0
    unsafe_refined_action_count = 0

    for record in records:
        page_id = _norm(record.get("page_id"))
        if not page_id:
            missing_page_id_count += 1
        if record.get("baseline_validation_action_count", 0) > 0:
            baseline_page_count += 1
        if record.get("actual_retry_action_count", 0) > 0:
            actual_retry_page_count += 1
        if record.get("review_action_count", 0) > 0:
            review_page_count += 1
        if record.get("optional_enrichment_action_count", 0) > 0:
            optional_page_count += 1
        if record.get("block_or_downgrade_action_count", 0) > 0:
            block_page_count += 1

        layout = _lower(record.get("layout_class"))
        ocr_state = _lower(record.get("ocr_state"))
        table_type = _lower(record.get("table_type"))
        actual_actions = [a for a in record.get("retry_actions", []) if isinstance(a, Mapping) and a.get("action_category") == "actual_retry"]
        actual_action_text = " ".join(_norm(a.get("action")) + " " + _norm(a.get("retry_route")) for a in actual_actions)

        if ocr_state == "source_confirmed_blank" and _has_any(actual_action_text, ["visual", "vision", "callout"]):
            confirmed_blank_pages_with_visual_retry += 1
        if layout == "text_heavy" and _has_any(actual_action_text, ["vision_model", "send_to_vision"]):
            text_heavy_pages_with_vision_retry += 1
        if table_type in {"", "none", "unknown_table"} and _has_any(actual_action_text, ["table_cell", "table_catalog", "validate_table"]):
            unknown_table_pages_with_table_answer_retry += 1

        for action in record.get("retry_actions", []):
            if isinstance(action, Mapping):
                if action.get("can_answer_directly") is not False or action.get("can_prove_claims") is not False or action.get("can_mutate_source_truth") is not False:
                    unsafe_refined_action_count += 1

    unsafe_refined_record_count = sum(1 for r in records if r.get("unsafe_reasons"))
    direct_answer_allowed_count = sum(1 for r in records if r.get("can_answer_directly") is not False)
    claim_proof_allowed_count = sum(1 for r in records if r.get("can_prove_claims") is not False)
    source_truth_mutation_allowed_count = sum(1 for r in records if r.get("can_mutate_source_truth") is not False)
    final_answer_allowed_count = sum(1 for r in records if r.get("final_answer_allowed") is not False)

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "source_fishnet_schema_version": source_report.get("schema_version"),
        "source_fishnet_quality_status": source_report.get("quality_status") or source_report.get("quality", {}).get("status") or source_report.get("status"),
        "refined_fishnet_record_count": len(records),
        "source_fishnet_record_count": len(source_report.get("records", []) or []),
        "action_count": len(action_rows),
        "baseline_validation_action_count": action_category_counts.get("baseline_validation", 0),
        "actual_retry_action_count": action_category_counts.get("actual_retry", 0),
        "review_required_action_count": action_category_counts.get("review_required", 0),
        "optional_enrichment_action_count": action_category_counts.get("optional_enrichment", 0),
        "block_or_downgrade_action_count": action_category_counts.get("block_or_downgrade", 0),
        "blank_handling_action_count": action_category_counts.get("blank_handling", 0),
        "baseline_validation_page_count": baseline_page_count,
        "actual_retry_page_count": actual_retry_page_count,
        "review_required_page_count": review_page_count,
        "optional_enrichment_page_count": optional_page_count,
        "block_or_downgrade_page_count": block_page_count,
        "missing_page_id_count": missing_page_id_count,
        "unsafe_refined_record_count": unsafe_refined_record_count,
        "unsafe_refined_action_count": unsafe_refined_action_count,
        "direct_answer_allowed_count": direct_answer_allowed_count,
        "claim_proof_allowed_count": claim_proof_allowed_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "final_answer_allowed_count": final_answer_allowed_count,
        "confirmed_blank_pages_with_visual_retry_count": confirmed_blank_pages_with_visual_retry,
        "text_heavy_pages_with_vision_retry_count": text_heavy_pages_with_vision_retry,
        "unknown_table_pages_with_table_answer_retry_count": unknown_table_pages_with_table_answer_retry,
        "disposition_counts": dict(disposition_counts),
        "layout_class_counts": dict(layout_counts),
        "ocr_state_counts": dict(ocr_counts),
        "action_category_counts": dict(action_category_counts),
        "retry_route_counts": dict(retry_route_counts),
    }


def evaluate_quality(
    summary: Mapping[str, Any],
    *,
    require_page_count: Optional[int] = None,
    min_refined_records: int = 1,
    min_baseline_validation_pages: int = 1,
    require_actual_retry_less_than_page_count: bool = False,
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def check(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    record_count = int(summary.get("refined_fishnet_record_count", 0) or 0)
    actual_retry_page_count = int(summary.get("actual_retry_page_count", 0) or 0)
    if require_page_count is not None:
        check("require_page_count", record_count == require_page_count, record_count, require_page_count)
    check("min_refined_records", record_count >= min_refined_records, record_count, f">= {min_refined_records}")
    check(
        "min_baseline_validation_pages",
        int(summary.get("baseline_validation_page_count", 0) or 0) >= min_baseline_validation_pages,
        summary.get("baseline_validation_page_count", 0),
        f">= {min_baseline_validation_pages}",
    )
    if require_actual_retry_less_than_page_count:
        check(
            "actual_retry_page_count_less_than_page_count",
            actual_retry_page_count < record_count if record_count else False,
            actual_retry_page_count,
            f"< {record_count}",
        )
    for key in [
        "missing_page_id_count",
        "unsafe_refined_record_count",
        "unsafe_refined_action_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
        "final_answer_allowed_count",
        "confirmed_blank_pages_with_visual_retry_count",
        "text_heavy_pages_with_vision_retry_count",
        "unknown_table_pages_with_table_answer_retry_count",
    ]:
        check(key, int(summary.get(key, 0) or 0) == 0, summary.get(key, 0), 0)

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {"status": status, "checks": checks}


def make_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Fishnet Retry Refinement v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
        f"- Refined records: {summary.get('refined_fishnet_record_count')}",
        f"- Baseline validation pages: {summary.get('baseline_validation_page_count')}",
        f"- Actual retry pages: {summary.get('actual_retry_page_count')}",
        f"- Review-required pages: {summary.get('review_required_page_count')}",
        f"- Optional enrichment pages: {summary.get('optional_enrichment_page_count')}",
        f"- Unsafe refined records: {summary.get('unsafe_refined_record_count')}",
        f"- Direct-answer allowed records: {summary.get('direct_answer_allowed_count')}",
        f"- Source-truth mutation allowed records: {summary.get('source_truth_mutation_allowed_count')}",
        "",
        "## Safety Rule",
        "",
        "Fishnet refinement can route, retry, review, or block. It cannot answer directly, prove claims, or mutate source truth.",
        "",
        "## Dispositions",
        "",
    ]
    for key, value in sorted((summary.get("disposition_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def make_html(markdown_text: str) -> str:
    body = html.escape(markdown_text).replace("\n", "<br>\n")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Fishnet Retry Refinement v1</title></head><body><pre>{body}</pre></body></html>"


def build_fishnet_retry_refinement(
    fishnet_report_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    require_page_count: Optional[int] = None,
    min_refined_records: int = 1,
    min_baseline_validation_pages: int = 1,
    require_actual_retry_less_than_page_count: bool = False,
    write_quality: bool = False,
) -> Dict[str, Any]:
    source_report = load_fishnet_report(fishnet_report_path)
    records = [refine_fishnet_record(record if isinstance(record, Mapping) else {}) for record in source_report.get("records", [])]
    summary = build_summary(records, source_report)
    quality = evaluate_quality(
        summary,
        require_page_count=require_page_count,
        min_refined_records=min_refined_records,
        min_baseline_validation_pages=min_baseline_validation_pages,
        require_actual_retry_less_than_page_count=require_actual_retry_less_than_page_count,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_fishnet_retry_refinement_v1.json"
    records_path = output_dir / "trace_net_fishnet_retry_refinement_v1_records.jsonl"
    actions_path = output_dir / "trace_net_fishnet_retry_refinement_v1_actions.jsonl"
    routes_path = output_dir / "trace_net_fishnet_retry_refinement_v1_routes.jsonl"
    summary_path = output_dir / "trace_net_fishnet_retry_refinement_v1_summary.json"
    manifest_path = output_dir / "trace_net_fishnet_retry_refinement_v1_manifest.json"
    quality_path = output_dir / "trace_net_fishnet_retry_refinement_v1_quality.json"
    markdown_path = output_dir / "trace_net_fishnet_retry_refinement_v1.md"
    html_path = output_dir / "trace_net_fishnet_retry_refinement_v1.html"

    action_rows = [action for record in records for action in record.get("retry_actions", [])]
    route_rows = []
    for record in records:
        page_id = record.get("page_id")
        for route in record.get("actual_retry_routes", []):
            route_rows.append({"page_id": page_id, "route_type": "actual_retry", "retry_route": route})
        for route in record.get("review_routes", []):
            route_rows.append({"page_id": page_id, "route_type": "review_required", "retry_route": route})
        for route in record.get("optional_enrichment_routes", []):
            route_rows.append({"page_id": page_id, "route_type": "optional_enrichment", "retry_route": route})

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "created_at": utc_now_iso(),
        "source_fishnet_report_path": fishnet_report_path.as_posix(),
        "report_path": report_path.as_posix(),
        "records_path": records_path.as_posix(),
        "actions_path": actions_path.as_posix(),
        "routes_path": routes_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "quality_path": quality_path.as_posix(),
        "markdown_path": markdown_path.as_posix(),
        "html_path": html_path.as_posix(),
        "record_count": len(records),
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "created_at": manifest["created_at"],
        "status": "FISHNET_RETRY_REFINEMENT_BUILT",
        "quality_status": quality["status"],
        "source_fishnet_report_path": fishnet_report_path.as_posix(),
        "summary": summary,
        "quality": quality,
        "records": records,
        "report_path": report_path.as_posix(),
        "records_path": records_path.as_posix(),
        "actions_path": actions_path.as_posix(),
        "routes_path": routes_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
        "quality_path": quality_path.as_posix(),
    }

    markdown = make_markdown(report)
    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(actions_path, action_rows)
    write_jsonl(routes_path, route_rows)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    else:
        write_json(quality_path, quality)
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(make_html(markdown), encoding="utf-8")
    return report


def check_fishnet_retry_refinement_quality(
    report_path: Path,
    *,
    require_page_count: Optional[int] = None,
    min_refined_records: int = 1,
    min_baseline_validation_pages: int = 1,
    require_actual_retry_less_than_page_count: bool = False,
    write_json_flag: bool = False,
) -> Dict[str, Any]:
    report = read_json(report_path)
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError(f"Refinement report missing summary: {report_path}")
    quality = evaluate_quality(
        summary,
        require_page_count=require_page_count,
        min_refined_records=min_refined_records,
        min_baseline_validation_pages=min_baseline_validation_pages,
        require_actual_retry_less_than_page_count=require_actual_retry_less_than_page_count,
    )
    if write_json_flag:
        quality_path = report_path.with_name("trace_net_fishnet_retry_refinement_v1_quality.json")
        write_json(quality_path, quality)
    return quality


def add_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--fishnet-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-refined-records", type=int, default=1)
    parser.add_argument("--min-baseline-validation-pages", type=int, default=1)
    parser.add_argument("--require-actual-retry-less-than-page-count", action="store_true")
    parser.add_argument("--quality", action="store_true")


def add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-refined-records", type=int, default=1)
    parser.add_argument("--min-baseline-validation-pages", type=int, default=1)
    parser.add_argument("--require-actual-retry-less-than-page-count", action="store_true")
    parser.add_argument("--write-json", action="store_true")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fishnet retry refinement v1")
    add_build_args(parser)
    args = parser.parse_args(argv)
    report = build_fishnet_retry_refinement(
        args.fishnet_report,
        args.output_dir,
        require_page_count=args.require_page_count,
        min_refined_records=args.min_refined_records,
        min_baseline_validation_pages=args.min_baseline_validation_pages,
        require_actual_retry_less_than_page_count=args.require_actual_retry_less_than_page_count,
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net fishnet retry refinement v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "refined_fishnet_record_count",
        "baseline_validation_page_count",
        "actual_retry_page_count",
        "review_required_page_count",
        "optional_enrichment_page_count",
        "block_or_downgrade_page_count",
        "confirmed_blank_pages_with_visual_retry_count",
        "text_heavy_pages_with_vision_retry_count",
        "unknown_table_pages_with_table_answer_retry_count",
        "unsafe_refined_record_count",
        "unsafe_refined_action_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


def quality_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fishnet retry refinement v1 quality")
    add_quality_args(parser)
    args = parser.parse_args(argv)
    quality = check_fishnet_retry_refinement_quality(
        args.report_path,
        require_page_count=args.require_page_count,
        min_refined_records=args.min_refined_records,
        min_baseline_validation_pages=args.min_baseline_validation_pages,
        require_actual_retry_less_than_page_count=args.require_actual_retry_less_than_page_count,
        write_json_flag=args.write_json,
    )
    report = read_json(args.report_path)
    summary = report.get("summary", {})
    print("TRACE-Net fishnet retry refinement v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "refined_fishnet_record_count",
        "baseline_validation_page_count",
        "actual_retry_page_count",
        "review_required_page_count",
        "optional_enrichment_page_count",
        "confirmed_blank_pages_with_visual_retry_count",
        "text_heavy_pages_with_vision_retry_count",
        "unknown_table_pages_with_table_answer_retry_count",
        "unsafe_refined_record_count",
        "unsafe_refined_action_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        print(f" quality_path: {args.report_path.with_name('trace_net_fishnet_retry_refinement_v1_quality.json')}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
