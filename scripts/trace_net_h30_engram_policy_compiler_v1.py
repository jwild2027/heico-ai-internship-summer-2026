#!/usr/bin/env python3
"""Validated Engram policy compiler for the live TRACE-Net H30 runtime.

Selected Engram atoms may express bounded preferences for retrieval order,
criticism, repair, and presentation. This module validates those preferences
against fixed allowlists. It never executes retrieval, writes a database,
promotes guidance to proof, or grants answer permission.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping, Sequence

MODULE = "trace_net_h30_engram_policy_compiler_v1"

ALLOWED_ROUTES = {
    "safe_general_chat", "exact_identifier_lookup", "guided_part_discovery",
    "ata_system_discovery", "nomenclature_function_search",
    "exact_table_ipl_lookup", "visual_figure_callout_lookup",
    "procedure_task_lookup", "warning_caution_note_lookup",
    "authority_eligibility_verification", "document_page_navigation",
    "graph_relationship_reasoning", "semantic_discovery",
    "cross_source_comparison", "contradiction_resolution",
    "ocr_scan_recovery", "high_degree_entity_aggregation",
    "multi_question_research", "clarification_no_evidence",
}
ALLOWED_EVIDENCE_TYPES = {
    "source_citation", "visual", "table", "ocr", "candidate",
    "semantic", "graph", "record",
}
ALLOWED_RANKING_PROFILES = {
    "route_default", "exact_entity_navigation", "semantic_discovery",
    "ocr_recovery", "aggregation", "claim_by_claim",
}
ALLOWED_GROUPING = {"none", "page_id", "document", "claim"}
ALLOWED_CRITIC_CHECKS = {
    "query_clue_boundary", "identifier_shape_valid", "exact_entity_mismatch",
    "wrong_tunnel_for_route", "guidance_promoted_to_proof",
    "authority_requires_explicit_evidence", "top_result_matches_exact_entity",
    "no_token_level_ocr_spam", "no_internal_identifier_exposure",
    "actual_ocr_record_required", "aggregation_coverage_required",
    "claim_buckets_present", "claim_buckets_collapsed",
    "direct_source_attempted",
}
ALLOWED_REPAIR_HINTS = {
    "retry_specialized_tunnel", "retry_authority_fields",
    "rerank_exact_entity", "collapse_page_rows", "sanitize_internal_ids",
    "retry_ocr_records", "expand_aggregation_coverage",
    "rebuild_claim_buckets", "retry_direct_source_resolution",
}
ALLOWED_PRESENTATION_TEMPLATES = {
    "route_default", "strongest_then_supporting", "ocr_recovery",
    "coverage_summary", "claim_by_claim", "evidence_summary",
}
DEFAULT_EVIDENCE_ORDER = [
    "source_citation", "table", "visual", "ocr", "candidate",
    "semantic", "graph", "record",
]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _allowed_unique(values: Iterable[Any], allowed: set[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for raw in values:
        value = str(raw or "").strip()
        if value in allowed and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def compile_engram_policy(
    engram_memory: Mapping[str, Any],
    route: str,
    requested_claims: Sequence[str],
) -> Dict[str, Any]:
    """Compile selected memory atoms into a small validated runtime policy."""
    validated_route = str(route or "")
    if validated_route not in ALLOWED_ROUTES:
        validated_route = "clarification_no_evidence"

    claims = {str(value) for value in requested_claims if value}
    retrieval: Dict[str, Any] = {
        "route": validated_route,
        "ranking_profile": "route_default",
        "preferred_evidence_order": [],
        "group_by": "none",
        "specialized_tunnel_first": False,
        "direct_source_before_fallback": False,
        "exact_entity_gate": False,
    }
    critic_checks: List[str] = []
    repair_hints: List[str] = []
    presentation: Dict[str, Any] = {
        "template": "route_default",
        "primary_result_limit": 8,
        "supporting_result_limit": 0,
        "hide_internal_ids": True,
        "show_proof_boundary": False,
        "show_authority_warning": False,
        "collapse_by_page": False,
    }
    source_atom_ids: List[str] = []
    source_rule_ids: List[str] = []
    rejected_effect_count = 0

    atoms = engram_memory.get("atoms", [])
    if not isinstance(atoms, list):
        atoms = []

    for raw_atom in atoms:
        atom = _mapping(raw_atom)
        atom_id = str(atom.get("atom_id") or "")
        canonical_id = str(atom.get("canonical_rule_id") or atom_id)
        effects = _mapping(atom.get("policy_effects"))
        if not effects:
            continue
        if atom_id:
            source_atom_ids.append(atom_id)
        if canonical_id:
            source_rule_ids.append(canonical_id)

        retrieval_effect = _mapping(effects.get("retrieval_policy"))
        raw_order = retrieval_effect.get("preferred_evidence_order", [])
        order = _allowed_unique(
            raw_order if isinstance(raw_order, list) else [],
            ALLOWED_EVIDENCE_TYPES,
        )
        if isinstance(raw_order, list):
            rejected_effect_count += max(0, len(raw_order) - len(order))
        if order and not retrieval["preferred_evidence_order"]:
            retrieval["preferred_evidence_order"] = order

        ranking = str(retrieval_effect.get("ranking_profile") or "")
        if ranking:
            if ranking in ALLOWED_RANKING_PROFILES:
                if retrieval["ranking_profile"] == "route_default":
                    retrieval["ranking_profile"] = ranking
            else:
                rejected_effect_count += 1

        group_by = str(retrieval_effect.get("group_by") or "")
        if group_by:
            if group_by in ALLOWED_GROUPING:
                if retrieval["group_by"] == "none":
                    retrieval["group_by"] = group_by
            else:
                rejected_effect_count += 1

        for key in (
            "specialized_tunnel_first",
            "direct_source_before_fallback",
            "exact_entity_gate",
        ):
            if retrieval_effect.get(key) is True:
                retrieval[key] = True

        critic_effect = _mapping(effects.get("critic_policy"))
        checks = critic_effect.get("checks", [])
        valid_checks = _allowed_unique(
            checks if isinstance(checks, list) else [],
            ALLOWED_CRITIC_CHECKS,
        )
        if isinstance(checks, list):
            rejected_effect_count += max(0, len(checks) - len(valid_checks))
        for check in valid_checks:
            if check not in critic_checks:
                critic_checks.append(check)

        repair_effect = _mapping(effects.get("repair_policy"))
        hints = repair_effect.get("hints", [])
        valid_hints = _allowed_unique(
            hints if isinstance(hints, list) else [],
            ALLOWED_REPAIR_HINTS,
        )
        if isinstance(hints, list):
            rejected_effect_count += max(0, len(hints) - len(valid_hints))
        for hint in valid_hints:
            if hint not in repair_hints:
                repair_hints.append(hint)

        presentation_effect = _mapping(effects.get("presentation_policy"))
        template = str(presentation_effect.get("template") or "")
        if template:
            if template in ALLOWED_PRESENTATION_TEMPLATES:
                if presentation["template"] == "route_default":
                    presentation["template"] = template
            else:
                rejected_effect_count += 1
        if "primary_result_limit" in presentation_effect:
            presentation["primary_result_limit"] = _bounded_int(
                presentation_effect.get("primary_result_limit"),
                presentation["primary_result_limit"], 1, 8,
            )
        if "supporting_result_limit" in presentation_effect:
            presentation["supporting_result_limit"] = _bounded_int(
                presentation_effect.get("supporting_result_limit"),
                presentation["supporting_result_limit"], 0, 12,
            )
        for key in ("hide_internal_ids", "show_proof_boundary", "collapse_by_page"):
            if presentation_effect.get(key) is True:
                presentation[key] = True
        if presentation_effect.get("show_authority_warning") is True:
            presentation["show_authority_warning"] = True

    if not retrieval["preferred_evidence_order"]:
        retrieval["preferred_evidence_order"] = list(DEFAULT_EVIDENCE_ORDER)

    authority_requested = (
        validated_route == "authority_eligibility_verification"
        or "authority" in claims
    )
    presentation["show_authority_warning"] = bool(
        authority_requested and presentation["show_authority_warning"]
    )

    payload = {
        "module": MODULE,
        "quality_status": "PASS",
        "route": validated_route,
        "requested_claims": sorted(claims),
        "retrieval_policy": retrieval,
        "critic_policy": {"checks": critic_checks},
        "repair_policy": {"hints": repair_hints},
        "presentation_policy": presentation,
        "source_atom_ids": list(dict.fromkeys(source_atom_ids)),
        "source_canonical_rule_ids": list(dict.fromkeys(source_rule_ids)),
        "rejected_effect_count": rejected_effect_count,
        "validated_against_allowlist": True,
        "executes_retrieval": False,
        "citable": False,
        "answer_permission": False,
        "source_truth": False,
        "source_truth_mutation_allowed": False,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload["policy_hash"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:20]
    return payload


def build_working_memory(
    question: str,
    atoms: Any,
    plan: Any,
    engram_policy: Mapping[str, Any],
) -> Dict[str, Any]:
    """Create fresh, non-persistent working memory for one request."""
    return {
        "question": str(question or ""),
        "route": str(_value(plan, "primary_route", "")),
        "requested_claims": list(_value(atoms, "requested_claims", []) or []),
        "requested_part_numbers": list(_value(atoms, "exact_part_numbers", []) or []),
        "searches_attempted": [],
        "evidence_found": {
            "direct": 0, "candidate": 0, "visual": 0,
            "semantic": 0, "authority": 0,
        },
        "evidence_rejected_count": 0,
        "best_result": "",
        "unresolved_fields": [],
        "repair_budget_remaining": int(_value(plan, "repair_budget", 0) or 0),
        "engram_policy_hash": str(engram_policy.get("policy_hash") or ""),
        "temporary_answer_state": True,
        "persist_source_truth": False,
    }


def refresh_working_memory(
    working_memory: Mapping[str, Any],
    envelope: Any,
    plan: Any,
) -> Dict[str, Any]:
    """Refresh request-local state after retrieval or repair."""
    result = dict(working_memory)
    coverage = _mapping(_value(envelope, "coverage", {}))
    direct = list(_value(envelope, "direct_evidence", []) or [])
    candidate = list(_value(envelope, "candidate_evidence", []) or [])
    visual = list(_value(envelope, "visual_guidance", []) or [])
    semantic = list(_value(envelope, "semantic_guidance", []) or [])
    authority = list(_value(envelope, "authority_evidence", []) or [])
    repairs = list(_value(envelope, "crag_repairs", []) or [])

    result["searches_attempted"] = list(dict.fromkeys(
        str(value)
        for value in (_value(envelope, "retrieval_tunnels_used", []) or [])
        if value
    ))
    result["evidence_found"] = {
        "direct": len(direct), "candidate": len(candidate),
        "visual": len(visual), "semantic": len(semantic),
        "authority": len(authority),
    }
    result["evidence_rejected_count"] = int(
        coverage.get("entity_mismatch_drop_count") or 0
    )
    result["repair_budget_remaining"] = max(
        0, int(_value(plan, "repair_budget", 0) or 0) - len(repairs),
    )

    best = ""
    for rows in (direct, visual, candidate, semantic):
        if not rows:
            continue
        row = rows[0]
        if isinstance(row, Mapping):
            page = str(row.get("page_id") or "")
            value = str(
                row.get("normalized_value") or row.get("value")
                or row.get("subject") or row.get("candidate_value") or ""
            )
            best = "; ".join(item for item in (page, value[:300]) if item)
        if best:
            break
    result["best_result"] = best

    unresolved: List[str] = []
    if not direct:
        unresolved.append("citation_ready_source_evidence")
    claims = set(result.get("requested_claims") or [])
    if "authority" in claims and not authority:
        unresolved.append("explicit_authority_evidence")
    if "ocr" in claims and not coverage.get("ocr_evidence"):
        unresolved.append("matching_ocr_record")
    if "table_value" in claims and not coverage.get("table_guidance") and not direct:
        unresolved.append("matching_table_record")
    result["unresolved_fields"] = unresolved
    return result
