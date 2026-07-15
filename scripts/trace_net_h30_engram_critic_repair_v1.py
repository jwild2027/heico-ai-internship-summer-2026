#!/usr/bin/env python3
"""Policy-aware Self-RAG checks and bounded CRAG repair for TRACE-Net H30.

The deterministic router critic remains the safety floor. This module adds only
the allowlisted checks selected by the compiled Engram policy, filters them by
route applicability, records every result, and maps failed checks to bounded,
read-only repair functions.

Engram cannot invent queries, execute arbitrary code, write databases, grant
answer permission, or promote guidance to proof.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from scripts.trace_net_h30_retrieval_completion_v1 import (
    _lead_rows,
    build_claim_results,
)

MODULE = "trace_net_h30_engram_critic_repair_v1"

ALL_TECHNICAL_ROUTES = {
    "exact_identifier_lookup",
    "guided_part_discovery",
    "ata_system_discovery",
    "nomenclature_function_search",
    "exact_table_ipl_lookup",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "authority_eligibility_verification",
    "document_page_navigation",
    "graph_relationship_reasoning",
    "semantic_discovery",
    "cross_source_comparison",
    "contradiction_resolution",
    "ocr_scan_recovery",
    "high_degree_entity_aggregation",
    "multi_question_research",
}

SPECIALIZED_ROUTES = {
    "exact_table_ipl_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "contradiction_resolution",
    "ocr_scan_recovery",
    "high_degree_entity_aggregation",
    "document_page_navigation",
    "multi_question_research",
}

EXACT_ENTITY_ROUTES = {
    "exact_identifier_lookup",
    "visual_figure_callout_lookup",
    "exact_table_ipl_lookup",
    "ocr_scan_recovery",
    "multi_question_research",
    "high_degree_entity_aggregation",
    "document_page_navigation",
}

CHECK_ROUTES: Dict[str, set[str]] = {
    "query_clue_boundary": {
        "nomenclature_function_search",
        "ocr_scan_recovery",
        "high_degree_entity_aggregation",
    },
    "identifier_shape_valid": {
        "guided_part_discovery",
        "document_page_navigation",
        "exact_identifier_lookup",
    },
    "exact_entity_mismatch": EXACT_ENTITY_ROUTES,
    "wrong_tunnel_for_route": SPECIALIZED_ROUTES,
    "guidance_promoted_to_proof": ALL_TECHNICAL_ROUTES,
    "authority_requires_explicit_evidence": {
        "authority_eligibility_verification",
        "multi_question_research",
    },
    "top_result_matches_exact_entity": {
        "document_page_navigation",
    },
    "no_token_level_ocr_spam": {
        "document_page_navigation",
        "ocr_scan_recovery",
    },
    "no_internal_identifier_exposure": {
        "document_page_navigation",
        "ocr_scan_recovery",
        "high_degree_entity_aggregation",
        "multi_question_research",
    },
    "actual_ocr_record_required": {
        "ocr_scan_recovery",
    },
    "aggregation_coverage_required": {
        "high_degree_entity_aggregation",
    },
    "claim_buckets_present": {
        "multi_question_research",
    },
    "claim_buckets_collapsed": {
        "multi_question_research",
    },
    "direct_source_attempted": {
        "exact_identifier_lookup",
        "document_page_navigation",
        "exact_table_ipl_lookup",
        "ocr_scan_recovery",
        "high_degree_entity_aggregation",
        "multi_question_research",
    },
}

HINT_ROUTES: Dict[str, set[str]] = {
    "retry_specialized_tunnel": SPECIALIZED_ROUTES,
    "retry_authority_fields": {
        "authority_eligibility_verification",
        "multi_question_research",
    },
    "rerank_exact_entity": EXACT_ENTITY_ROUTES,
    "collapse_page_rows": {
        "document_page_navigation",
        "ocr_scan_recovery",
        "high_degree_entity_aggregation",
    },
    "sanitize_internal_ids": {
        "document_page_navigation",
        "ocr_scan_recovery",
        "high_degree_entity_aggregation",
        "multi_question_research",
    },
    "retry_ocr_records": {
        "ocr_scan_recovery",
    },
    "expand_aggregation_coverage": {
        "high_degree_entity_aggregation",
    },
    "rebuild_claim_buckets": {
        "multi_question_research",
    },
    "retry_direct_source_resolution": {
        "exact_identifier_lookup",
        "document_page_navigation",
        "exact_table_ipl_lookup",
        "ocr_scan_recovery",
        "high_degree_entity_aggregation",
        "multi_question_research",
    },
}

CHECK_TO_HINTS: Dict[str, Tuple[str, ...]] = {
    "wrong_tunnel_for_route": ("retry_specialized_tunnel",),
    "authority_requires_explicit_evidence": ("retry_authority_fields",),
    "exact_entity_mismatch": (
        "rerank_exact_entity",
        "collapse_page_rows",
    ),
    "top_result_matches_exact_entity": (
        "rerank_exact_entity",
        "collapse_page_rows",
    ),
    "no_token_level_ocr_spam": ("collapse_page_rows",),
    "no_internal_identifier_exposure": ("sanitize_internal_ids",),
    "actual_ocr_record_required": ("retry_ocr_records",),
    "aggregation_coverage_required": (
        "expand_aggregation_coverage",
    ),
    "claim_buckets_present": ("rebuild_claim_buckets",),
    "claim_buckets_collapsed": ("rebuild_claim_buckets",),
    "direct_source_attempted": (
        "retry_direct_source_resolution",
    ),
}

INTERNAL_ID_RE = re.compile(
    r"(?:[A-Za-z_]+::[^\s;]+)|(?:\b[a-f0-9]{16,}\b)",
    re.I,
)
PART_RE = re.compile(
    r"\b\d{2,3}-\d{5}(?:-\d{3})?\b",
    re.I,
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _compact(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
            )
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _policy(plan: Any) -> Mapping[str, Any]:
    return _mapping(_value(plan, "engram_policy", {}))


def _policy_values(
    plan: Any,
    section: str,
    field: str,
) -> List[str]:
    value = _mapping(_policy(plan).get(section)).get(field, [])
    return [
        str(item)
        for item in value
        if item
    ] if isinstance(value, list) else []


def _coverage(envelope: Any) -> MutableMapping[str, Any]:
    value = _value(envelope, "coverage", {})
    return value if isinstance(value, MutableMapping) else {}


def _requested_parts(atoms: Any) -> List[str]:
    return [
        str(value).upper()
        for value in _value(atoms, "exact_part_numbers", []) or []
        if value
    ]


def _row_blob(row: Mapping[str, Any]) -> str:
    return _compact(dict(row), 8000).upper()


def _row_contains_requested(
    row: Mapping[str, Any],
    requested_parts: Sequence[str],
) -> bool:
    if not requested_parts:
        return True
    blob = _row_blob(row)
    return any(part.upper() in blob for part in requested_parts)


def _all_evidence_rows(envelope: Any) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for name in (
        "direct_evidence",
        "candidate_evidence",
        "visual_guidance",
        "semantic_guidance",
        "authority_evidence",
    ):
        output.extend(
            dict(row)
            for row in _value(envelope, name, []) or []
            if isinstance(row, Mapping)
        )
    coverage = _coverage(envelope)
    for name in (
        "navigation_leads",
        "ocr_evidence",
        "aggregate_records",
        "table_guidance",
    ):
        output.extend(
            dict(row)
            for row in coverage.get(name, []) or []
            if isinstance(row, Mapping)
        )
    return output


def _internal_identifier_rows(
    envelope: Any,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    coverage = _coverage(envelope)
    groups = {
        "navigation_leads": coverage.get("navigation_leads", []),
        "ocr_evidence": coverage.get("ocr_evidence", []),
        "aggregate_records": coverage.get("aggregate_records", []),
    }
    for group, rows in groups.items():
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            for field in (
                "document",
                "source",
                "source_id",
                "record_id",
                "point_id",
                "id",
            ):
                value = _compact(row.get(field), 1000)
                if value and INTERNAL_ID_RE.search(value):
                    findings.append({
                        "group": group,
                        "index": index,
                        "field": field,
                    })
    return findings


def _specialized_tunnel_satisfied(
    route: str,
    envelope: Any,
) -> bool:
    used = [
        str(value).lower()
        for value in _value(
            envelope,
            "retrieval_tunnels_used",
            [],
        ) or []
    ]
    coverage = _coverage(envelope)

    marker_map = {
        "document_page_navigation": (
            "navigation",
            "page",
            "direct_source",
            "visual",
        ),
        "ocr_scan_recovery": ("ocr",),
        "high_degree_entity_aggregation": (
            "aggregation",
            "coverage",
            "direct_source",
        ),
        "exact_table_ipl_lookup": (
            "table",
            "ipl",
            "direct_source",
        ),
        "procedure_task_lookup": ("procedure",),
        "warning_caution_note_lookup": (
            "warning",
            "caution",
            "note",
        ),
        "contradiction_resolution": (
            "contradiction",
            "revision",
            "crosscheck",
            "cross_check",
        ),
        "multi_question_research": (
            "claim",
            "decomposition",
            "direct_source",
        ),
    }
    markers = marker_map.get(route, ())
    if any(
        marker in tunnel
        for marker in markers
        for tunnel in used
    ):
        return True

    if (
        route == "document_page_navigation"
        and coverage.get("navigation_leads")
    ):
        return True
    if (
        route == "ocr_scan_recovery"
        and coverage.get("ocr_evidence")
    ):
        return True
    if (
        route == "high_degree_entity_aggregation"
        and coverage.get("aggregate_records")
    ):
        return True
    if (
        route == "multi_question_research"
        and coverage.get("claim_results")
    ):
        return True
    if (
        route == "exact_table_ipl_lookup"
        and (
            coverage.get("table_guidance")
            or _value(envelope, "direct_evidence", [])
        )
    ):
        return True
    return not markers


def _check_one(
    check: str,
    plan: Any,
    atoms: Any,
    envelope: Any,
) -> Dict[str, Any]:
    route = str(_value(plan, "primary_route", ""))
    requested_parts = _requested_parts(atoms)
    coverage = _coverage(envelope)

    status = "PASS"
    reason = "check_satisfied"
    details: Dict[str, Any] = {}

    if check == "query_clue_boundary":
        low = str(_value(atoms, "normalized_query", "")).lower()
        terms = {
            str(value).lower()
            for value in _value(
                atoms,
                "nomenclature_terms",
                [],
            ) or []
        }
        cover_is_standalone = bool(
            re.search(r"(?<![a-z0-9])cover(?![a-z0-9])", low)
        )
        bad = (
            ("recover" in low or "coverage" in low)
            and not cover_is_standalone
            and "cover" in terms
        )
        if bad:
            status = "FAIL"
            reason = "substring_clue_leaked_across_token_boundary"

    elif check == "identifier_shape_valid":
        validator = _value(
            plan,
            "_identifier_validator",
            None,
        )
        values = [
            _value(atoms, "part_prefix"),
            _value(atoms, "part_contains"),
            _value(atoms, "part_suffix"),
        ]
        invalid = []
        for value in values:
            if not value:
                continue
            if callable(validator):
                valid = bool(validator(str(value)))
            else:
                normalized = re.sub(
                    r"[^A-Z0-9]",
                    "",
                    str(value).upper(),
                )
                valid = (
                    2 <= len(normalized) <= 16
                    and any(ch.isdigit() for ch in normalized)
                )
            if not valid:
                invalid.append(str(value))
        if invalid:
            status = "FAIL"
            reason = "partial_identifier_is_not_identifier_shaped"
            details["invalid_fragments"] = invalid

    elif check == "exact_entity_mismatch":
        mismatches = []
        for row in _all_evidence_rows(envelope):
            observed = {
                value.upper()
                for value in PART_RE.findall(_row_blob(row))
            }
            if (
                requested_parts
                and observed
                and not observed.intersection(
                    set(requested_parts)
                )
            ):
                mismatches.append(sorted(observed))
        if mismatches:
            status = "FAIL"
            reason = "remaining_evidence_explicitly_names_other_entities"
            details["mismatch_count"] = len(mismatches)

    elif check == "wrong_tunnel_for_route":
        if not _specialized_tunnel_satisfied(route, envelope):
            status = "FAIL"
            reason = "selected_route_did_not_execute_specialized_tunnel"

    elif check == "guidance_promoted_to_proof":
        promoted = []
        for group_name in (
            "candidate_evidence",
            "visual_guidance",
            "semantic_guidance",
        ):
            for row in _value(envelope, group_name, []) or []:
                if not isinstance(row, Mapping):
                    continue
                proof_role = str(
                    row.get("proof_role") or ""
                ).lower()
                if (
                    proof_role in {
                        "source_truth",
                        "direct_proof",
                        "authority",
                    }
                    or row.get("answer_permission") is True
                ):
                    promoted.append(group_name)
        if promoted:
            status = "FAIL"
            reason = "guidance_record_claims_proof_or_answer_permission"
            details["groups"] = sorted(set(promoted))

    elif check == "authority_requires_explicit_evidence":
        authority_requested = (
            route == "authority_eligibility_verification"
            or "authority" in {
                str(value)
                for value in _value(
                    atoms,
                    "requested_claims",
                    [],
                ) or []
            }
        )
        if (
            authority_requested
            and not _value(
                envelope,
                "authority_evidence",
                [],
            )
        ):
            status = "FAIL"
            reason = "explicit_authority_evidence_not_found"

    elif check == "top_result_matches_exact_entity":
        leads = _lead_rows(envelope, requested_parts)
        exact_positions = [
            index
            for index, row in enumerate(leads)
            if _row_contains_requested(row, requested_parts)
        ]
        if exact_positions and exact_positions[0] != 0:
            status = "FAIL"
            reason = "exact_entity_lead_is_not_ranked_first"
            details["first_exact_position"] = exact_positions[0]
        elif requested_parts and not exact_positions:
            status = "WARN"
            reason = "no_exact_entity_lead_available_to_rank"

    elif check == "no_token_level_ocr_spam":
        rows = []
        for row in coverage.get("ocr_evidence", []) or []:
            if isinstance(row, Mapping):
                rows.append(dict(row))
        for row in coverage.get("navigation_leads", []) or []:
            if (
                isinstance(row, Mapping)
                and str(row.get("source_type") or "").lower()
                == "ocr"
            ):
                rows.append(dict(row))
        page_counts: Dict[str, int] = {}
        explicit_token_rows = 0
        for row in rows:
            page = str(row.get("page_id") or "")
            if page:
                page_counts[page] = page_counts.get(page, 0) + 1
            kind = " ".join(
                str(row.get(key) or "").lower()
                for key in (
                    "record_type",
                    "candidate_type",
                    "source_type",
                )
            )
            if "token" in kind:
                explicit_token_rows += 1
        noisy_pages = [
            page for page, count in page_counts.items()
            if count > 3
        ]
        if explicit_token_rows or noisy_pages:
            status = "FAIL"
            reason = "token_level_ocr_rows_not_collapsed"
            details.update({
                "explicit_token_row_count": explicit_token_rows,
                "noisy_pages": noisy_pages,
            })

    elif check == "no_internal_identifier_exposure":
        findings = _internal_identifier_rows(envelope)
        if findings:
            status = "FAIL"
            reason = "internal_retrieval_identifier_present"
            details["finding_count"] = len(findings)

    elif check == "actual_ocr_record_required":
        if not coverage.get("ocr_evidence"):
            status = "FAIL"
            reason = "matching_ocr_record_not_resolved"

    elif check == "aggregation_coverage_required":
        local = _mapping(
            coverage.get("retrieval_completion")
        )
        required_fields = {
            "scanned_file_count",
            "matched_file_count",
            "coverage_complete_for_candidate_files",
        }
        missing = [
            field for field in required_fields
            if field not in local
        ]
        if missing:
            status = "FAIL"
            reason = "aggregation_coverage_metadata_missing"
            details["missing_fields"] = sorted(missing)

    elif check in {
        "claim_buckets_present",
        "claim_buckets_collapsed",
    }:
        claims = [
            str(value)
            for value in _value(
                atoms,
                "requested_claims",
                [],
            ) or []
            if value
        ]
        results = _mapping(coverage.get("claim_results"))
        missing = [
            claim for claim in claims
            if claim not in results
        ]
        malformed = [
            claim for claim, result in results.items()
            if not isinstance(result, Mapping)
            or not str(result.get("status") or "")
        ]
        if missing or (
            check == "claim_buckets_collapsed"
            and malformed
        ):
            status = "FAIL"
            reason = (
                "claim_buckets_missing"
                if missing
                else "claim_buckets_collapsed_or_malformed"
            )
            details["missing_claims"] = missing
            details["malformed_claims"] = malformed

    elif check == "direct_source_attempted":
        used = [
            str(value).lower()
            for value in _value(
                envelope,
                "retrieval_tunnels_used",
                [],
            ) or []
        ]
        attempted = any(
            any(
                marker in tunnel
                for marker in (
                    "direct_source",
                    "normal_source_truth",
                    "exact_source",
                    "table_resolution",
                    "source_resolution",
                )
            )
            for tunnel in used
        )
        if not attempted:
            status = "FAIL"
            reason = "direct_source_resolution_not_attempted"

    else:
        status = "SKIP"
        reason = "check_not_registered"

    return {
        "check": check,
        "status": status,
        "reason": reason,
        "details": details,
        "route": route,
        "read_only": True,
    }


def evaluate_policy_checks(
    plan: Any,
    atoms: Any,
    envelope: Any,
    base_critic: Mapping[str, Any],
) -> Dict[str, Any]:
    """Run only selected, route-applicable Engram critic checks."""
    route = str(_value(plan, "primary_route", ""))
    selected = _policy_values(
        plan,
        "critic_policy",
        "checks",
    )
    selected_hints = _policy_values(
        plan,
        "repair_policy",
        "hints",
    )

    executed: List[str] = []
    skipped: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []

    for check in selected:
        allowed_routes = CHECK_ROUTES.get(check)
        if allowed_routes is None:
            skipped.append({
                "check": check,
                "reason": "check_not_registered",
            })
            continue
        if route not in allowed_routes:
            skipped.append({
                "check": check,
                "reason": "not_applicable_to_route",
                "route": route,
            })
            continue
        executed.append(check)
        results.append(
            _check_one(check, plan, atoms, envelope)
        )

    policy_failures = [
        result["check"]
        for result in results
        if result.get("status") == "FAIL"
    ]
    policy_warnings = [
        result["check"]
        for result in results
        if result.get("status") == "WARN"
    ]

    recommended: List[str] = []
    for check in policy_failures:
        for hint in CHECK_TO_HINTS.get(check, ()):
            if (
                hint in selected_hints
                and route in HINT_ROUTES.get(hint, set())
                and hint not in recommended
            ):
                recommended.append(hint)

    base_failures = list(
        dict.fromkeys(base_critic.get("failures") or [])
    )
    base_warnings = list(
        dict.fromkeys(base_critic.get("warnings") or [])
    )
    policy_failure_codes = [
        f"engram_check:{check}"
        for check in policy_failures
    ]
    policy_warning_codes = [
        f"engram_check:{check}"
        for check in policy_warnings
    ]
    combined_failures = list(
        dict.fromkeys(base_failures + policy_failure_codes)
    )
    combined_warnings = list(
        dict.fromkeys(base_warnings + policy_warning_codes)
    )
    policy_retry_required = bool(
        policy_failures and recommended
    )
    retry_required = bool(
        base_critic.get("retry_required")
        or policy_retry_required
    )

    output = dict(base_critic)
    output.update({
        "quality_status": (
            "PASS"
            if not combined_failures
            else "RETRY"
        ),
        "failures": combined_failures,
        "warnings": combined_warnings,
        "retry_required": retry_required,
        "base_failures": base_failures,
        "base_retry_required": bool(
            base_critic.get("retry_required")
        ),
        "policy_checks_selected": selected,
        "policy_checks_executed": executed,
        "policy_checks_skipped": skipped,
        "policy_check_results": results,
        "policy_failures": policy_failures,
        "policy_warnings": policy_warnings,
        "policy_repair_hints_selected": selected_hints,
        "policy_repair_hints_recommended": recommended,
        "policy_retry_required": policy_retry_required,
        "policy_checked_read_only": True,
        "policy_answer_permission": False,
        "policy_source_truth": False,
    })
    return output


def _dedupe_by_page(
    rows: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        page = str(row.get("page_id") or "")
        key = page or _compact(row, 2000)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _rerank_exact(
    rows: Iterable[Mapping[str, Any]],
    requested_parts: Sequence[str],
) -> List[Dict[str, Any]]:
    indexed = [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
    ]
    return sorted(
        indexed,
        key=lambda row: (
            0 if _row_contains_requested(
                row,
                requested_parts,
            ) else 1,
        ),
    )


def _sanitize_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    output = dict(row)
    for field in (
        "document",
        "source",
        "source_id",
        "record_id",
        "point_id",
        "id",
    ):
        value = _compact(output.get(field), 1000)
        if value and INTERNAL_ID_RE.search(value):
            output.pop(field, None)
    return output


def _post_repair_normalize(
    hint: str,
    atoms: Any,
    envelope: Any,
) -> Dict[str, Any]:
    coverage = _coverage(envelope)
    requested_parts = _requested_parts(atoms)
    metrics: Dict[str, Any] = {}

    if hint == "rerank_exact_entity":
        for name in (
            "direct_evidence",
            "candidate_evidence",
            "visual_guidance",
            "semantic_guidance",
        ):
            rows = _value(envelope, name, [])
            if isinstance(rows, list):
                setattr(
                    envelope,
                    name,
                    _rerank_exact(rows, requested_parts),
                )
        for name in (
            "navigation_leads",
            "ocr_evidence",
            "aggregate_records",
        ):
            rows = coverage.get(name, [])
            if isinstance(rows, list):
                coverage[name] = _rerank_exact(
                    rows,
                    requested_parts,
                )
        metrics["reranked_for_exact_entity"] = True

    elif hint == "collapse_page_rows":
        for name in (
            "navigation_leads",
            "ocr_evidence",
            "aggregate_records",
        ):
            rows = coverage.get(name, [])
            if isinstance(rows, list):
                before = len(rows)
                coverage[name] = _dedupe_by_page(rows)
                metrics[f"{name}_removed"] = (
                    before - len(coverage[name])
                )

    elif hint == "sanitize_internal_ids":
        total = 0
        for name in (
            "navigation_leads",
            "ocr_evidence",
            "aggregate_records",
        ):
            rows = coverage.get(name, [])
            if not isinstance(rows, list):
                continue
            sanitized = []
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                before = _internal_identifier_rows_from_row(row)
                sanitized.append(_sanitize_row(row))
                total += before
            coverage[name] = sanitized
        coverage["internal_identifier_sanitized"] = True
        metrics["sanitized_field_count"] = total

    elif hint == "rebuild_claim_buckets":
        coverage["claim_results"] = build_claim_results(
            atoms,
            envelope,
        )
        metrics["claim_bucket_count"] = len(
            coverage["claim_results"]
        )

    return metrics


def _internal_identifier_rows_from_row(
    row: Mapping[str, Any],
) -> int:
    count = 0
    for field in (
        "document",
        "source",
        "source_id",
        "record_id",
        "point_id",
        "id",
    ):
        value = _compact(row.get(field), 1000)
        if value and INTERNAL_ID_RE.search(value):
            count += 1
    return count


def _run_retrieval_hint(
    runtime: Any,
    hint: str,
    plan: Any,
    atoms: Any,
    envelope: Any,
    router: Mapping[str, Any],
) -> Dict[str, Any]:
    route = str(_value(plan, "primary_route", ""))
    query = str(_value(atoms, "latest_query", ""))
    parts = _requested_parts(atoms)
    actions: List[str] = []

    if hint == "retry_specialized_tunnel":
        if route == "document_page_navigation" and parts:
            queries = [
                (
                    "Find the strongest exact source page, document, "
                    f"figure, table, and OCR location for part {parts[0]}"
                )
            ]
        else:
            builder = router.get("specialized_route_queries")
            queries = (
                builder(route, query, atoms, maximum=2)
                if callable(builder)
                else [query]
            )
        for index, item in enumerate(queries[:2], 1):
            runtime.add_unified(
                envelope,
                item,
                f"engram_crag_specialized_{index}",
            )
            actions.append("unified_specialized_query")

    elif hint == "retry_authority_fields":
        target = parts[0] if parts else "the requested component"
        runtime.add_unified(
            envelope,
            (
                "Search only explicit approval, effectivity, eligibility, "
                "interchangeability, applicability, and installation-authority "
                f"fields for {target}"
            ),
            "engram_crag_authority_fields",
        )
        actions.append("authority_field_query")

    elif hint == "retry_ocr_records":
        target = parts[0] if parts else query
        runtime.add_unified(
            envelope,
            (
                "Resolve stored OCR records, OCR engine, confidence, page, "
                f"and source trace for {target}"
            ),
            "engram_crag_ocr_records",
        )
        actions.append("ocr_record_query")

    elif hint == "expand_aggregation_coverage":
        target = parts[0] if parts else query
        runtime.add_unified(
            envelope,
            (
                "Aggregate every indexed source-backed page and document "
                f"reference for {target} with coverage totals and capping"
            ),
            "engram_crag_aggregation_coverage",
        )
        actions.append("aggregation_coverage_query")

    elif hint == "retry_direct_source_resolution":
        target = parts[0] if parts else query
        runtime.add_unified(
            envelope,
            (
                "Resolve citation-ready source page, document, field, OCR, "
                f"table, visual, and source-trace evidence for {target}"
            ),
            "engram_crag_direct_source",
        )
        actions.append("direct_source_query")

    return {
        "route": route,
        "actions": actions,
    }


def execute_policy_repair(
    runtime: Any,
    plan: Any,
    atoms: Any,
    envelope: Any,
    critic: Mapping[str, Any],
    *,
    original_repair: Callable[..., None],
    router: Mapping[str, Any],
) -> bool:
    """Execute at most one selected, route-applicable repair hint."""
    route = str(_value(plan, "primary_route", ""))
    selected_hints = [
        hint
        for hint in critic.get(
            "policy_repair_hints_selected",
            [],
        ) or []
        if route in HINT_ROUTES.get(str(hint), set())
    ]
    if not selected_hints:
        return False

    repairs = _value(envelope, "crag_repairs", [])
    if not isinstance(repairs, list):
        return True
    budget = int(_value(plan, "repair_budget", 0) or 0)
    if len(repairs) >= budget:
        return True

    recommended = [
        str(value)
        for value in critic.get(
            "policy_repair_hints_recommended",
            [],
        ) or []
    ]
    attempted = {
        str(row.get("repair_hint"))
        for row in repairs
        if isinstance(row, Mapping)
        and row.get("source") == MODULE
    }
    candidate = next(
        (
            hint
            for hint in selected_hints
            if hint in recommended
            and hint not in attempted
        ),
        None,
    )
    if not candidate:
        # Policy-only failures with no remaining selected repair fail closed.
        # Base deterministic failures may still use the legacy bounded fallback.
        return not bool(critic.get("base_failures"))

    pre = _run_retrieval_hint(
        runtime,
        candidate,
        plan,
        atoms,
        envelope,
        router,
    )

    # The already-installed retrieval-completion wrapper performs its local,
    # read-only artifact resolution even when the underlying legacy repair sees
    # an empty failure list.
    original_repair(
        runtime,
        plan,
        atoms,
        envelope,
        {"failures": [], "retry_required": False},
    )

    post = _post_repair_normalize(
        candidate,
        atoms,
        envelope,
    )

    record = {
        "repair": "engram_policy_repair",
        "repair_hint": candidate,
        "source": MODULE,
        "triggered_by_checks": [
            check
            for check in critic.get(
                "policy_failures",
                [],
            ) or []
            if candidate in CHECK_TO_HINTS.get(
                str(check),
                (),
            )
        ],
        "route": route,
        "actions": pre.get("actions", []),
        "post_repair_metrics": post,
        "status": "APPLIED",
        "bounded": True,
        "read_only": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }
    repairs.append(record)

    coverage = _coverage(envelope)
    history = coverage.setdefault(
        "engram_policy_repair_execution",
        [],
    )
    if isinstance(history, list):
        history.append(dict(record))
    coverage["repair_count"] = len(repairs)
    return True


def install_engram_critic_repair(
    router: MutableMapping[str, Any],
) -> None:
    """Install policy-aware critic and repair wrappers after retrieval v2."""
    if router.get("_H30_ENGRAM_CRITIC_REPAIR_V1_INSTALLED"):
        return

    runtime_cls = router["CognitiveRuntime"]
    original_critic = runtime_cls.critic
    original_repair = runtime_cls.repair
    original_health = runtime_cls.health

    def critic_v4(
        self: Any,
        plan: Any,
        atoms: Any,
        envelope: Any,
    ) -> Dict[str, Any]:
        # Preserve deterministic safety and route checks.
        setattr(
            plan,
            "_identifier_validator",
            router.get("valid_identifier_fragment"),
        )
        base = original_critic(
            self,
            plan,
            atoms,
            envelope,
        )
        result = evaluate_policy_checks(
            plan,
            atoms,
            envelope,
            base,
        )
        coverage = _coverage(envelope)
        coverage["engram_policy_critic"] = {
            "quality_status": result.get("quality_status"),
            "selected_checks": result.get(
                "policy_checks_selected",
                [],
            ),
            "executed_checks": result.get(
                "policy_checks_executed",
                [],
            ),
            "skipped_checks": result.get(
                "policy_checks_skipped",
                [],
            ),
            "check_results": result.get(
                "policy_check_results",
                [],
            ),
            "recommended_repair_hints": result.get(
                "policy_repair_hints_recommended",
                [],
            ),
            "read_only": True,
        }
        return result

    def repair_v4(
        self: Any,
        plan: Any,
        atoms: Any,
        envelope: Any,
        critic: Mapping[str, Any],
    ) -> None:
        handled = execute_policy_repair(
            self,
            plan,
            atoms,
            envelope,
            critic,
            original_repair=original_repair,
            router=router,
        )
        if not handled:
            original_repair(
                self,
                plan,
                atoms,
                envelope,
                critic,
            )

    def health_v4(self: Any) -> Dict[str, Any]:
        result = original_health(self)
        result.update({
            "policy_aware_self_rag": True,
            "policy_aware_crag": True,
            "engram_critic_check_count": len(CHECK_ROUTES),
            "engram_repair_hint_count": len(HINT_ROUTES),
            "route_applicability_filtering": True,
            "one_policy_repair_per_iteration": True,
            "unselected_checks_not_executed": True,
            "unselected_repairs_not_executed": True,
            "deterministic_critic_safety_floor": True,
            "read_only_policy_repairs": True,
        })
        return result

    runtime_cls.critic = critic_v4
    runtime_cls.repair = repair_v4
    runtime_cls.health = health_v4
    router["_H30_ENGRAM_CRITIC_REPAIR_V1_INSTALLED"] = True
