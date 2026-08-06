#!/usr/bin/env python3
"""OpenWebUI F-grade fix v2 for the RAG project.

This overlay fixes two observed user-facing failures:

1. General capability questions are answered deterministically as safe general
   chat instead of being sent through semantic manual retrieval.
2. Illustrated-parts-list requests are rendered as a conservative field-status
   answer. Only exact-identifier, citation-ready proof rows may populate item,
   nomenclature, quantity, or page fields. Missing fields are explicitly marked
   not proven.

The overlay is read-only. It does not write databases, mutate source truth,
execute retrieval, or add an LLM call.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from src.trace_net.writing.trace_net_h30_public_answer_contract_v1 import (
    render_public_answer,
    validate_public_answer_contract,
)

MODULE = "trace_net_h30_openwebui_f_grade_fix_v2"
STATUS = "TRACE_NET_H30_OPENWEBUI_F_GRADE_FIX_V2"
PATCH_ID = "trace_net_openwebui_f_grade_fix_v2"

PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{2,3})?\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+_p\d{6}\b", re.I)

CAPABILITY_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bwhat kinds? of questions can (?:you|this system) answer\b",
        r"\bwhat questions can (?:you|this system) answer\b",
        r"\bwhat can (?:you|this system) (?:answer|do) (?:with|using) (?:the )?(?:indexed )?(?:aircraft )?manual\b",
        r"\bwhat (?:are|is) (?:your|the system(?:'s)?) capabilities\b",
        r"\bhow can (?:you|this system) help (?:with|using) (?:the )?(?:indexed )?(?:aircraft )?manual\b",
    )
)

INTERNAL_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bphase\d+(?:_\d+)*_[a-z0-9_()]+\b",
        r"\b[a-z0-9_]+_removed_\d+_[a-z0-9_()]+\b",
        r"\btrace_net_[a-z0-9_]+\b",
        r"\bentity_gate_[a-z0-9_]+\b",
        r"\bpacket_deterministic_sections_incomplete\b",
        r"\bwriter_mode\b",
        r"\bquality_status\b",
    )
)

FIELD_ALIASES: Dict[str, Sequence[str]] = {
    "Item": ("item", "item_number", "item_no", "ipl_item", "figure_item"),
    "Nomenclature": (
        "nomenclature", "part_name", "component_name", "description",
        "part_description",
    ),
    "Quantity": (
        "quantity", "qty", "quantity_per_assembly", "units_per_assy",
        "units_per_assembly",
    ),
}


def _rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _query_part(query: str) -> str:
    match = PART_RE.search(str(query or ""))
    return match.group(0).upper() if match else ""


def is_capabilities_question(query: str) -> bool:
    """Recognize general system-capability questions, not technical lookups."""
    text = _clean(query)
    if not text or PART_RE.search(text):
        return False
    return any(pattern.search(text) for pattern in CAPABILITY_PATTERNS)


def contains_internal_diagnostic(text: str) -> bool:
    return any(pattern.search(str(text or "")) for pattern in INTERNAL_PATTERNS)


def render_capabilities_answer() -> str:
    answer = "\n".join((
        "Using the indexed aircraft manual, I can help with:",
        "",
        "- Exact part-number and identifier lookups.",
        "- Partial part-number discovery when only a fragment is known.",
        "- Nomenclature, component-name, ATA, page, figure, and document navigation.",
        "- Illustrated-parts-list fields such as item, nomenclature, and quantity when a citation-ready row supports them.",
        "- Figures, diagrams, and callout leads, with visual guidance kept separate from proof.",
        "- Source-backed procedures, warnings, cautions, and notes.",
        "- Assembly-relationship and cross-source questions when explicit relationship records are available.",
        "- OCR recovery and semantic discovery across difficult scanned pages.",
        "- Authority checks when explicit approval, eligibility, effectivity, or applicability fields are present.",
    ))
    evidence = [
        "This is a capabilities overview; it does not assert a technical fact about a specific part, aircraft, or maintenance task."
    ]
    limits = [
        "Technical facts are treated as confirmed only when a source-resolved record and citation support the requested claim.",
        "Candidate, semantic, graph, OCR, summary, table-derived, and visual guidance are not promoted to proof by themselves.",
    ]
    return render_public_answer(answer, evidence, limits)


def _citation_id(row: Mapping[str, Any]) -> int:
    for key in ("citation_id", "citation_number", "citation_index"):
        try:
            value = int(row.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _page(row: Mapping[str, Any]) -> str:
    for key in ("page_id", "source_page_id", "trace_page_id", "page"):
        value = _clean(row.get(key))
        if value:
            return value
    try:
        blob = json.dumps(row, ensure_ascii=False, sort_keys=True)
    except Exception:
        blob = str(row)
    match = PAGE_RE.search(blob)
    return match.group(0) if match else ""


def _is_proof_row(row: Mapping[str, Any]) -> bool:
    return bool(
        str(row.get("authority") or "").strip().lower() == "proof"
        or row.get("can_prove_claims") is True
        or row.get("claim_support_allowed") is True
        or row.get("final_answer_eligible") is True
    )


def _row_blob(row: Mapping[str, Any]) -> str:
    try:
        return json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(row)


def _exact_identifier_supported(row: Mapping[str, Any], requested_part: str) -> bool:
    if not requested_part:
        return False
    observed = {value.upper() for value in PART_RE.findall(_row_blob(row))}
    return requested_part.upper() in observed


def _iter_nested_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_nested_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_nested_mappings(child)


def _scalar_text(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return _clean(value)
    if isinstance(value, list):
        values = [_scalar_text(item) for item in value]
        return ", ".join(item for item in values if item)
    return ""


def _nested_field_value(row: Mapping[str, Any], aliases: Sequence[str]) -> str:
    alias_set = {alias.casefold() for alias in aliases}
    for mapping in _iter_nested_mappings(row):
        for key, value in mapping.items():
            if str(key).casefold() not in alias_set:
                continue
            text = _scalar_text(value)
            if text:
                return text
    return ""


def _unique_rows(rows: Sequence[Mapping[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        key = (_page(row), _citation_id(row), _row_blob(row)[:500])
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
        if len(output) >= limit:
            break
    return output


def _registry(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = _rows(result.get("citation_registry"))
    rows.sort(key=lambda row: (_citation_id(row) or 10_000, _page(row)))
    return rows


def _with_citation(text: str, citation_id: int) -> str:
    line = text.rstrip(".") + "."
    if citation_id > 0:
        line = line[:-1] + f" [{citation_id}]."
    return line


def render_table_field_answer(query: str, result: Mapping[str, Any]) -> str:
    """Render exact-identifier IPL fields conservatively and deterministically."""
    part = _query_part(query)
    registry = _registry(result)
    exact_proof = _unique_rows([
        row for row in registry
        if _is_proof_row(row) and _exact_identifier_supported(row, part)
    ])
    exact_guidance = _unique_rows([
        row for row in registry
        if not _is_proof_row(row) and _exact_identifier_supported(row, part)
    ], limit=4)

    recovered: Dict[str, Dict[str, Any]] = {}
    for label, aliases in FIELD_ALIASES.items():
        for row in exact_proof:
            value = _nested_field_value(row, aliases)
            if value:
                recovered[label] = {
                    "value": value,
                    "citation_id": _citation_id(row),
                }
                break

    page_record: Dict[str, Any] = {}
    for row in exact_proof:
        page = _page(row)
        if page:
            page_record = {"value": page, "citation_id": _citation_id(row)}
            break
    if page_record:
        recovered["Page"] = page_record

    required_labels = ("Item", "Nomenclature", "Quantity", "Page")
    if recovered:
        answer = (
            f"The citation-ready IPL fields recovered for `{part}` are listed below."
            if part else
            "The citation-ready IPL fields recovered are listed below."
        )
        evidence: List[str] = []
        for label in required_labels:
            record = recovered.get(label)
            if not record:
                continue
            value = str(record["value"])
            rendered_value = f"`{value}`" if label in {"Item", "Quantity", "Page"} else value
            evidence.append(_with_citation(
                f"{label}: {rendered_value}",
                int(record.get("citation_id") or 0),
            ))
    else:
        answer = (
            f"No citation-ready IPL row was confirmed for `{part}`."
            if part else
            "No citation-ready IPL row was confirmed."
        )
        evidence = []
        for row in exact_guidance:
            page = _page(row)
            if page:
                evidence.append(_with_citation(
                    f"Candidate IPL page: `{page}`",
                    _citation_id(row),
                ))
        if not evidence:
            evidence = [
                "No exact-identifier, citation-ready IPL row was available for the requested fields."
            ]

    limits: List[str] = []
    for label in required_labels:
        if label not in recovered:
            limits.append(f"{label}: not proven from an exact-identifier, citation-ready IPL row.")
    if recovered:
        limits.append("Only the field values explicitly listed in Evidence are treated as source-backed.")
    else:
        limits.append("Candidate pages and search matches are navigation guidance, not confirmed IPL field values.")

    content = render_public_answer(answer, evidence, limits)
    assert not contains_internal_diagnostic(content)
    return content


def _merge_validation(
    *,
    content: str,
    query: str,
    result: Mapping[str, Any],
    route: str,
    validate_answer: Any,
    safe_general: bool = False,
) -> Dict[str, Any]:
    validation_result = dict(result)
    validation_result["route"] = route
    try:
        base = dict(validate_answer(content, query, validation_result))
    except Exception as exc:
        base = {
            "accepted": False,
            "quality_status": "FAIL",
            "failures": [f"validator_exception:{type(exc).__name__}"],
        }
    contract = validate_public_answer_contract(content, route=route)
    failures = list(base.get("failures") or [])
    failures.extend(contract.get("failures") or [])
    failures = list(dict.fromkeys(str(item) for item in failures if str(item)))

    if safe_general:
        accepted = bool(contract.get("accepted")) and not contains_internal_diagnostic(content)
        final_failures = [] if accepted else failures
    else:
        accepted = bool(base.get("accepted")) and bool(contract.get("accepted")) and not failures
        final_failures = failures

    return {
        **base,
        "accepted": accepted,
        "quality_status": "PASS" if accepted else "FAIL",
        "failures": final_failures,
        "public_answer_contract": contract,
        "technical_validator_result": base,
    }


def install_openwebui_f_grade_fix(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_OPENWEBUI_F_GRADE_FIX_V2_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health
    validate_answer = module["validate_answer"]
    extract_latest_user = module["extract_latest_user"]

    def process_openwebui_f_grade_fix(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        query = extract_latest_user(payload)

        if is_capabilities_question(query):
            content = render_capabilities_answer()
            result: Dict[str, Any] = {
                "route": "safe_general_chat",
                "route_before_openwebui_f_grade_fix": "not_executed",
                "answer_mode": {"mode": "safe_general_chat"},
                "citation_registry": [],
                "retrieval_tunnels_used": [],
                "content": content,
                "writer_mode": "openwebui_f_grade_fix_v2_capabilities",
                "answer_permission": False,
                "final_answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
            result["post_answer_validation"] = _merge_validation(
                content=content,
                query=query,
                result=result,
                route="safe_general_chat",
                validate_answer=validate_answer,
                safe_general=True,
            )
            result["openwebui_f_grade_fix"] = {
                "status": STATUS,
                "patch_id": PATCH_ID,
                "applied": True,
                "reason": "capabilities_short_circuit",
                "retrieval_executed": False,
                "gemma_call_count_added": 0,
                "gemma_call_avoided": True,
                "route_changed": True,
                "final_route": "safe_general_chat",
                "source_truth_mutation_allowed": False,
                "write_attempt_count": 0,
            }
            return result

        result = dict(current_process(self, payload))
        route = str(result.get("route") or "")
        if route != "exact_table_ipl_lookup":
            result["openwebui_f_grade_fix"] = {
                "status": STATUS,
                "patch_id": PATCH_ID,
                "applied": False,
                "reason": "route_not_targeted",
                "gemma_call_count_added": 0,
                "retrieval_changed": False,
                "route_changed": False,
                "source_truth_mutation_allowed": False,
                "write_attempt_count": 0,
            }
            return result

        prior = str(result.get("content") or "")
        content = render_table_field_answer(query, result)
        validation = _merge_validation(
            content=content,
            query=query,
            result=result,
            route=route,
            validate_answer=validate_answer,
            safe_general=False,
        )
        result["content"] = content
        result["post_answer_validation"] = validation
        result["writer_mode_before_openwebui_f_grade_fix"] = result.get("writer_mode")
        result["writer_mode"] = "openwebui_f_grade_fix_v2_table"
        result["openwebui_f_grade_fix"] = {
            "status": STATUS,
            "patch_id": PATCH_ID,
            "quality_status": validation.get("quality_status"),
            "applied": True,
            "reason": "deterministic_exact_ipl_field_status",
            "changed": content.strip() != prior.strip(),
            "prior_internal_diagnostic_present": contains_internal_diagnostic(prior),
            "final_internal_diagnostic_present": contains_internal_diagnostic(content),
            "gemma_call_count_added": 0,
            "retrieval_changed": False,
            "route_changed": False,
            "source_truth_mutation_allowed": False,
            "write_attempt_count": 0,
        }
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    def health_openwebui_f_grade_fix(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result.update({
            "openwebui_f_grade_fix_enabled": True,
            "openwebui_f_grade_fix_status": STATUS,
            "capabilities_short_circuit_enabled": True,
            "capabilities_short_circuit_adds_gemma_call": False,
            "exact_ipl_deterministic_field_status_enabled": True,
            "exact_ipl_internal_diagnostic_suppression": True,
            "exact_ipl_exact_identifier_proof_gate": True,
            "openwebui_f_grade_fix_source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.process = process_openwebui_f_grade_fix
    runtime_cls.health = health_openwebui_f_grade_fix
    module[marker] = True
