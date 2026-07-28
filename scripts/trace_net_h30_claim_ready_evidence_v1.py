#!/usr/bin/env python3
"""TRACE-Net H30 Phase 2 route-scoped claim-ready evidence selection.

The canonical typed envelope remains the complete audit view. This layer rebuilds
that typed view after graph and exact-page enrichment, then creates a separate
route/entity-scoped selection for answer-mode classification and answer writing.

It does not retrieve evidence, change route ranking, grant answer permission,
call an LLM, or mutate source truth. Legacy evidence lists and the complete typed
audit remain present and unchanged.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_claim_ready_evidence_v1"
VERSION = "v1"
SCHEMA_VERSION = "trace_net_claim_ready_evidence_v1"
STATUS = "TRACE_NET_H30_CLAIM_READY_EVIDENCE_V1"

SOURCE_BUCKETS: Tuple[str, ...] = (
    "direct_evidence",
    "candidate_evidence",
    "visual_guidance",
    "semantic_guidance",
    "contradictions",
    "source_resolution",
)
RAW_BUCKETS: Tuple[str, ...] = SOURCE_BUCKETS + ("authority_evidence",)

PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?|"
    r"[A-Z]{2,}\d{4,}(?:[-./][A-Z0-9]+)*)\b",
    re.I,
)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
WORD_RE = re.compile(r"[A-Za-z0-9]+")

ROUTE_CLAIMS: Dict[str, Tuple[str, ...]] = {
    "exact_identifier_lookup": ("part_identity",),
    "guided_part_discovery": ("part_identity",),
    "ata_system_discovery": ("document_overview",),
    "nomenclature_function_search": ("nomenclature",),
    "exact_table_ipl_lookup": ("table_item",),
    "visual_figure_callout_lookup": ("figure_callout",),
    "procedure_task_lookup": ("procedure_step",),
    "warning_caution_note_lookup": ("warning_or_caution",),
    "authority_eligibility_verification": ("authority_approval",),
    "document_page_navigation": ("page_location",),
    "graph_relationship_reasoning": ("assembly_relationship",),
    "semantic_discovery": ("document_overview",),
    "cross_source_comparison": ("comparison",),
    "contradiction_resolution": ("contradiction",),
    "ocr_scan_recovery": ("ocr_text",),
    "high_degree_entity_aggregation": ("document_overview",),
    "multi_question_research": ("document_overview",),
}

NO_SELECTION_ROUTES = {
    "safe_general_chat",
    "clarification_no_evidence",
}

SAFETY_CONTRACT = {
    "read_only": True,
    "legacy_evidence_preserved": True,
    "complete_typed_audit_preserved": True,
    "claim_ready_is_consumer_view_not_new_evidence": True,
    "retrieval_changed": False,
    "ranking_changed": False,
    "route_changed": False,
    "llm_call_added": False,
    "guidance_never_promoted_to_proof": True,
    "conflicts_never_promoted_to_proof": True,
    "answer_permission": False,
    "final_answer_allowed": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _compact(value: Any, limit: int = 12000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _bool_env(
    environ: Mapping[str, str],
    name: str,
    default: bool = False,
) -> bool:
    raw = str(environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def load_claim_ready_config(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    try:
        maximum = int(env.get("TRACE_NET_H30_CLAIM_READY_EVIDENCE_MAX_RECORDS", "32"))
    except (TypeError, ValueError):
        maximum = 32
    return {
        "enabled": _bool_env(
            env,
            "TRACE_NET_H30_CLAIM_READY_EVIDENCE_ENABLED",
            False,
        ),
        "max_records": max(1, min(64, maximum)),
    }


def _query_atoms(result: Mapping[str, Any]) -> Dict[str, Any]:
    top = result.get("query_atoms")
    if isinstance(top, Mapping):
        return dict(top)
    envelope = result.get("evidence_envelope")
    if isinstance(envelope, Mapping) and isinstance(envelope.get("query_atoms"), Mapping):
        return dict(envelope["query_atoms"])
    return {}


def _string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _targets(result: Mapping[str, Any]) -> Dict[str, Any]:
    atoms = _query_atoms(result)
    exact_parts = _string_list(atoms.get("exact_part_numbers"))
    mode = str(atoms.get("identifier_mode") or "none").strip().lower()
    clue = str(
        atoms.get("normalized_identifier")
        or atoms.get("part_prefix")
        or atoms.get("part_contains")
        or atoms.get("part_suffix")
        or atoms.get("family_identifier")
        or ""
    ).strip()
    if not exact_parts and mode == "exact" and clue:
        exact_parts = [clue]
    return {
        "identifier_mode": mode,
        "identifier_clue": _norm(clue),
        "exact_parts": {_norm(value) for value in exact_parts if _norm(value)},
        "pages": {str(value).casefold() for value in _string_list(atoms.get("page_ids"))},
        "atas": {str(value).upper() for value in _string_list(atoms.get("ata_exact"))},
        "ata_prefix": str(atoms.get("ata_prefix") or "").upper(),
        "figures": {_norm(value) for value in _string_list(atoms.get("figures"))},
        "items": {_norm(value) for value in _string_list(atoms.get("items"))},
        "nomenclature_terms": {
            token.casefold()
            for value in _string_list(atoms.get("nomenclature_terms"))
            for token in re.findall(r"[A-Za-z0-9]{3,}", value)
        },
        "requested_claims": {
            str(value)
            for value in _string_list(atoms.get("requested_claims"))
        },
    }


def _raw_record(
    envelope: Mapping[str, Any],
    typed: Mapping[str, Any],
) -> Dict[str, Any]:
    bucket = str(typed.get("source_bucket") or "")
    try:
        index = int(typed.get("source_index"))
    except (TypeError, ValueError):
        return {}
    rows = envelope.get(bucket)
    if not isinstance(rows, list) or index < 0 or index >= len(rows):
        return {}
    value = rows[index]
    return dict(value) if isinstance(value, Mapping) else {}


def _record_blob(typed: Mapping[str, Any], raw: Mapping[str, Any]) -> str:
    return _compact(
        {
            "typed": {
                "claim_types": typed.get("claim_types"),
                "modality": typed.get("modality"),
                "identity": typed.get("identity"),
                "source_trace": typed.get("source_trace"),
                "excerpt": typed.get("excerpt"),
            },
            "raw": raw,
        },
        30000,
    )


def _part_values(blob: str, typed: Mapping[str, Any]) -> List[str]:
    identity = _mapping(typed.get("identity"))
    values = _string_list(identity.get("part_numbers"))
    candidate = str(identity.get("candidate") or "").strip()
    if candidate:
        values.append(candidate)
    values.extend(PART_RE.findall(blob))
    output: List[str] = []
    seen = set()
    for value in values:
        normalized = _norm(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _identifier_match(values: Sequence[str], targets: Mapping[str, Any]) -> bool:
    exact = set(targets.get("exact_parts") or set())
    if exact:
        return bool(exact.intersection(values))
    clue = str(targets.get("identifier_clue") or "")
    mode = str(targets.get("identifier_mode") or "none")
    if not clue or mode == "none":
        return True
    if mode in {"prefix", "family"}:
        return any(value.startswith(clue) for value in values)
    if mode == "suffix":
        return any(value.endswith(clue) for value in values)
    if mode in {"contains", "partial"}:
        return any(clue in value for value in values)
    if mode == "exact":
        return any(value == clue for value in values)
    return any(clue in value for value in values)


def _page_match(blob: str, typed: Mapping[str, Any], pages: Iterable[str]) -> bool:
    wanted = {str(value).casefold() for value in pages}
    if not wanted:
        return True
    trace = _mapping(typed.get("source_trace"))
    found = {str(trace.get("page_id") or "").casefold()}
    found.update(value.casefold() for value in PAGE_RE.findall(blob))
    found.discard("")
    return bool(wanted.intersection(found))


def _ata_match(blob: str, typed: Mapping[str, Any], targets: Mapping[str, Any]) -> bool:
    wanted = {str(value).upper() for value in targets.get("atas") or set()}
    prefix = str(targets.get("ata_prefix") or "")
    identity = _mapping(typed.get("identity"))
    found = {str(identity.get("ata") or "").upper()}
    found.update(value.upper() for value in ATA_RE.findall(blob))
    found.discard("")
    if wanted:
        # Some graph/source-resolution rows are route-scoped to the requested ATA
        # but carry only a page trace. Keep those rows when no conflicting ATA is
        # printed; reject only an explicit different ATA.
        return not found or bool(wanted.intersection(found))
    if prefix:
        return not found or any(value.startswith(prefix) for value in found)
    return True


def _terms_match(blob: str, terms: Iterable[str]) -> bool:
    wanted = {str(value).casefold() for value in terms if str(value).strip()}
    if not wanted:
        return True
    low = blob.casefold()
    tokens = set(token.casefold() for token in WORD_RE.findall(blob))
    return any(term in tokens or term in low for term in wanted)


def _claim_compatible(
    typed: Mapping[str, Any],
    route: str,
    targets: Mapping[str, Any],
) -> bool:
    claims = {str(value) for value in typed.get("claim_types") or []}
    required = set(ROUTE_CLAIMS.get(route, ()))
    requested = set(targets.get("requested_claims") or set())
    if requested:
        required |= requested
    if not required:
        return True
    return bool(required.intersection(claims))


def _relevance(
    *,
    route: str,
    typed: Mapping[str, Any],
    raw: Mapping[str, Any],
    targets: Mapping[str, Any],
) -> Tuple[bool, List[str], str]:
    if route in NO_SELECTION_ROUTES:
        return False, [], "route_has_no_technical_evidence_selection"

    blob = _record_blob(typed, raw)
    values = _part_values(blob, typed)
    pages = targets.get("pages") or set()
    terms = targets.get("nomenclature_terms") or set()
    modality = str(typed.get("modality") or "")
    bucket = str(typed.get("source_bucket") or "")
    reasons: List[str] = []

    if not _claim_compatible(typed, route, targets):
        return False, reasons, "claim_type_not_compatible"
    reasons.append("claim_type_compatible")

    if route == "exact_identifier_lookup":
        if not _identifier_match(values, targets):
            return False, reasons, "exact_identifier_mismatch"
        reasons.append("exact_identifier_match")
    elif route == "guided_part_discovery":
        if not _identifier_match(values, targets):
            return False, reasons, "partial_identifier_mismatch"
        reasons.append("partial_identifier_match")
    elif route == "nomenclature_function_search":
        if not _terms_match(blob, terms):
            return False, reasons, "nomenclature_term_mismatch"
        reasons.append("nomenclature_term_match")
    elif route == "ata_system_discovery":
        if not _ata_match(blob, typed, targets):
            return False, reasons, "ata_mismatch"
        reasons.append("ata_match")
    elif route == "exact_table_ipl_lookup":
        if not (_identifier_match(values, targets) and _page_match(blob, typed, pages)):
            return False, reasons, "table_entity_mismatch"
        if modality not in {"table", "ocr", "textual_source", "source_resolution"}:
            return False, reasons, "table_modality_mismatch"
        reasons.extend(["table_entity_match", "table_compatible_modality"])
    elif route == "visual_figure_callout_lookup":
        if not _page_match(blob, typed, pages):
            return False, reasons, "visual_page_mismatch"
        if modality not in {"visual", "ocr", "textual_source", "summary"} and bucket != "visual_guidance":
            return False, reasons, "visual_modality_mismatch"
        reasons.extend(["visual_page_match", "visual_compatible_modality"])
    elif route in {
        "procedure_task_lookup",
        "warning_caution_note_lookup",
        "document_page_navigation",
    }:
        if not _page_match(blob, typed, pages):
            return False, reasons, "requested_page_mismatch"
        reasons.append("requested_page_match")
    elif route == "graph_relationship_reasoning":
        if not _identifier_match(values, targets):
            return False, reasons, "graph_entity_mismatch"
        if modality not in {"graph", "textual_source", "source_resolution", "summary"}:
            return False, reasons, "graph_modality_mismatch"
        reasons.extend(["graph_entity_match", "graph_compatible_modality"])
    elif route == "authority_eligibility_verification":
        if values and not _identifier_match(values, targets):
            return False, reasons, "authority_entity_mismatch"
        if "authority_approval" not in set(typed.get("claim_types") or []):
            return False, reasons, "authority_claim_missing"
        reasons.append("authority_claim_match")
    elif route == "ocr_scan_recovery":
        if pages and not _page_match(blob, typed, pages):
            return False, reasons, "ocr_page_mismatch"
        if modality not in {"ocr", "table", "textual_source", "summary"}:
            return False, reasons, "ocr_modality_mismatch"
        reasons.append("ocr_compatible_modality")
    elif route in {"cross_source_comparison", "contradiction_resolution"}:
        if values and not _identifier_match(values, targets):
            return False, reasons, "comparison_entity_mismatch"
        reasons.append("comparison_or_conflict_scope_match")
    else:
        # Semantic, aggregation, and multi-question routes are already scoped by
        # the route planner. They still require a compatible claim type.
        reasons.append("route_scoped_guidance")

    if typed.get("conflicted"):
        reasons.append("conflict_preserved")
    if typed.get("claim_support_allowed"):
        reasons.append("direct_claim_support")
    elif typed.get("guidance_only"):
        reasons.append("guidance_only")

    return True, reasons, ""


def _score(record: Mapping[str, Any]) -> Tuple[int, int, int, int]:
    selection = _mapping(record.get("selection"))
    return (
        1 if record.get("conflicted") else 0,
        1 if record.get("claim_support_allowed") else 0,
        1 if record.get("source_bucket") == "candidate_evidence" else 0,
        -int(record.get("source_index") or 0),
    )


def _authority_rows(
    envelope: Mapping[str, Any],
    targets: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    for row in _rows(envelope.get("authority_evidence")):
        blob = _compact(row, 20000)
        values = [_norm(value) for value in PART_RE.findall(blob) if _norm(value)]
        if values and not _identifier_match(values, targets):
            continue
        selected.append(row)
    return selected


def validate_claim_ready_evidence(
    *,
    full_records: Sequence[Mapping[str, Any]],
    selected_records: Sequence[Mapping[str, Any]],
    legacy_before: Mapping[str, int],
    legacy_after: Mapping[str, int],
) -> Dict[str, Any]:
    failures: List[str] = []
    full_ids = {str(row.get("record_id") or "") for row in full_records}
    selected_ids = [str(row.get("record_id") or "") for row in selected_records]
    if len(selected_ids) != len(set(selected_ids)):
        failures.append("duplicate_selected_record_id")
    if not set(selected_ids).issubset(full_ids):
        failures.append("selected_record_not_in_complete_typed_audit")
    if dict(legacy_before) != dict(legacy_after):
        failures.append("legacy_evidence_lists_changed")
    for row in selected_records:
        if row.get("guidance_only") and row.get("claim_support_allowed"):
            failures.append("guidance_promoted_to_claim_support")
        if row.get("conflicted") and row.get("claim_support_allowed"):
            failures.append("conflict_promoted_to_claim_support")
        if row.get("claim_support_allowed") and row.get("source_bucket") != "direct_evidence":
            failures.append("non_direct_record_promoted_to_claim_support")
    failures = list(dict.fromkeys(failures))
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "accepted": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "complete_typed_record_count": len(full_records),
        "selected_record_count": len(selected_records),
        "legacy_evidence_preserved": dict(legacy_before) == dict(legacy_after),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }


def _rebuild_typed_view(
    envelope: Mapping[str, Any],
    route: str,
) -> Dict[str, Any]:
    from scripts.trace_net_h30_typed_evidence_envelope_v1 import build_typed_evidence_view
    return build_typed_evidence_view(envelope, route=route)


def build_claim_ready_evidence(
    result: Mapping[str, Any],
    *,
    typed_view: Optional[Mapping[str, Any]] = None,
    max_records: int = 32,
) -> Dict[str, Any]:
    route = str(result.get("route") or "")
    envelope = _mapping(result.get("evidence_envelope"))
    targets = _targets(result)
    fresh = dict(typed_view) if isinstance(typed_view, Mapping) else _rebuild_typed_view(envelope, route)
    full_records = _rows(fresh.get("records"))
    legacy_before = {bucket: len(_rows(envelope.get(bucket))) for bucket in RAW_BUCKETS}

    selected: List[Dict[str, Any]] = []
    rejected = Counter()
    for typed in full_records:
        raw = _raw_record(envelope, typed)
        keep, reasons, rejected_reason = _relevance(
            route=route,
            typed=typed,
            raw=raw,
            targets=targets,
        )
        if not keep:
            rejected[rejected_reason or "not_selected"] += 1
            continue
        copied = dict(typed)
        copied["selection"] = {
            "selected": True,
            "route": route,
            "reasons": reasons,
            "source_bucket": typed.get("source_bucket"),
            "source_index": typed.get("source_index"),
        }
        selected.append(copied)

    selected.sort(key=_score, reverse=True)
    selected = selected[: max(1, min(64, int(max_records)))]

    selected_indexes: Dict[str, set[int]] = {}
    for row in selected:
        bucket = str(row.get("source_bucket") or "")
        try:
            index = int(row.get("source_index"))
        except (TypeError, ValueError):
            continue
        selected_indexes.setdefault(bucket, set()).add(index)

    by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    for bucket in SOURCE_BUCKETS:
        raw_rows = _rows(envelope.get(bucket))
        indexes = selected_indexes.get(bucket, set())
        by_bucket[bucket] = [
            dict(row)
            for index, row in enumerate(raw_rows)
            if index in indexes
        ]
    by_bucket["authority_evidence"] = _authority_rows(envelope, targets)

    legacy_after = {bucket: len(_rows(envelope.get(bucket))) for bucket in RAW_BUCKETS}
    validation = validate_claim_ready_evidence(
        full_records=full_records,
        selected_records=selected,
        legacy_before=legacy_before,
        legacy_after=legacy_after,
    )
    bucket_counts = Counter(str(row.get("source_bucket") or "") for row in selected)
    claim_counts = Counter(
        str(claim)
        for row in selected
        for claim in (row.get("claim_types") or [])
    )
    return {
        "status": STATUS,
        "module": MODULE,
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "quality_status": validation["quality_status"],
        "route": route,
        "typed_view_rebuilt_after_final_enrichment": True,
        "records": selected,
        "by_bucket": by_bucket,
        "coverage": {
            "complete_typed_record_count": len(full_records),
            "selected_record_count": len(selected),
            "rejected_record_count": max(0, len(full_records) - len(selected)),
            "selected_bucket_counts": dict(bucket_counts),
            "selected_claim_type_counts": dict(claim_counts),
            "rejected_reason_counts": dict(rejected),
            "legacy_bucket_counts": legacy_before,
            "complete_typed_audit_preserved": True,
            "consumer_view_only": True,
        },
        "query_scope": {
            "identifier_mode": targets["identifier_mode"],
            "identifier_clue": targets["identifier_clue"],
            "exact_parts": sorted(targets["exact_parts"]),
            "pages": sorted(targets["pages"]),
            "atas": sorted(targets["atas"]),
            "ata_prefix": targets["ata_prefix"],
            "nomenclature_terms": sorted(targets["nomenclature_terms"]),
            "route_claims": list(ROUTE_CLAIMS.get(route, ())),
        },
        "validation": validation,
        "contract": {
            "complete_typed_audit_preserved": True,
            "legacy_evidence_preserved": True,
            "claim_ready_records_are_subset_of_typed_audit": True,
            "answer_modes_should_prefer_claim_ready_records": True,
            "writer_should_prefer_claim_ready_buckets": True,
            "retrieval_and_ranking_unchanged": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        },
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def claim_ready_health(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    config = load_claim_ready_config(environ)
    return {
        "status": STATUS,
        "quality_status": "PASS",
        "enabled": bool(config.get("enabled")),
        "max_records": int(config.get("max_records") or 32),
        "schema_version": SCHEMA_VERSION,
        "typed_view_rebuilt_after_final_enrichment": True,
        "complete_typed_audit_preserved": True,
        "legacy_evidence_preserved": True,
        "consumer_view_only": True,
        "retrieval_changed": False,
        "ranking_changed": False,
        "route_changed": False,
        "llm_call_added": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def install_claim_ready_evidence(
    module: MutableMapping[str, Any],
) -> None:
    marker = "_TRACE_NET_H30_CLAIM_READY_EVIDENCE_V1_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["CognitiveRuntime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health

    def process_v1(
        self: Any,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        config = load_claim_ready_config()
        result["claim_ready_evidence_enabled"] = bool(config.get("enabled"))
        if not config.get("enabled"):
            result["claim_ready_evidence_status"] = {
                "quality_status": "SKIPPED",
                "reason": "disabled_by_configuration",
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
            return result

        envelope = result.get("evidence_envelope")
        if not isinstance(envelope, Mapping):
            result["claim_ready_evidence_status"] = {
                "quality_status": "FAIL",
                "reason": "missing_evidence_envelope",
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
            return result

        route = str(result.get("route") or "")
        fresh = _rebuild_typed_view(envelope, route)
        updated = dict(envelope)
        updated["typed_evidence"] = _rows(fresh.get("records"))
        updated["typed_evidence_coverage"] = _mapping(fresh.get("coverage"))
        updated["typed_evidence_validation"] = _mapping(fresh.get("validation"))
        updated["typed_evidence_contract"] = _mapping(fresh.get("contract"))
        temporary = dict(result)
        temporary["evidence_envelope"] = updated
        selected = build_claim_ready_evidence(
            temporary,
            typed_view=fresh,
            max_records=int(config.get("max_records") or 32),
        )
        updated["claim_ready_evidence"] = selected
        result["evidence_envelope"] = updated
        result["claim_ready_evidence_status"] = {
            "quality_status": selected["quality_status"],
            "schema_version": selected["schema_version"],
            "complete_typed_record_count": selected["coverage"]["complete_typed_record_count"],
            "selected_record_count": selected["coverage"]["selected_record_count"],
            "rejected_record_count": selected["coverage"]["rejected_record_count"],
            "typed_view_rebuilt_after_final_enrichment": True,
            "legacy_evidence_preserved": selected["validation"]["legacy_evidence_preserved"],
            "validation": selected["validation"],
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        safety = result.get("safety_contract")
        if isinstance(safety, MutableMapping):
            safety["claim_ready_evidence_consumer_view"] = True
            safety["complete_typed_audit_preserved"] = True
            safety["answer_permission"] = False
            safety["final_answer_allowed"] = False
            safety["source_truth_mutation_allowed"] = False
        return result

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        health = claim_ready_health()
        result["claim_ready_evidence"] = health
        result["claim_ready_evidence_enabled"] = bool(health.get("enabled"))
        result["claim_ready_evidence_consumer_view_only"] = True
        result["typed_view_rebuilt_after_final_enrichment"] = True
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    runtime_cls.process = process_v1
    runtime_cls.health = health_v1
    module[marker] = True


__all__ = [
    "MODULE",
    "VERSION",
    "SCHEMA_VERSION",
    "STATUS",
    "SOURCE_BUCKETS",
    "ROUTE_CLAIMS",
    "build_claim_ready_evidence",
    "validate_claim_ready_evidence",
    "load_claim_ready_config",
    "claim_ready_health",
    "install_claim_ready_evidence",
]
