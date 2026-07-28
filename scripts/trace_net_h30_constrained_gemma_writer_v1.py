#!/usr/bin/env python3
"""TRACE-Net H30 Phase 4 constrained single-call Gemma writer.

The final Phase 3 deterministic answer is converted into a compact, claim-ready
writer packet. Gemma receives only that packet and must return a strict JSON
object. TRACE-Net renders the JSON deterministically, validates every identifier
and citation against the existing registry, and falls back to the already-valid
Phase 3 answer on any error.

This layer does not retrieve evidence, rerank records, choose a route, grant
answer authority, or mutate source truth. The legacy free-form writer is
suppressed while this layer is enabled, so the maximum added model-call count is
one per request.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from scripts.trace_net_h30_public_answer_contract_v1 import (
    parse_public_answer,
    render_public_answer,
    validate_public_answer_contract,
)

MODULE = "trace_net_h30_constrained_gemma_writer_v1"
VERSION = "v1"
STATUS = "TRACE_NET_H30_CONSTRAINED_GEMMA_WRITER_V1"
PATCH_ID = "trace_net_h30_phase4_constrained_gemma_writer_v1"
SCHEMA_VERSION = "trace_net_constrained_writer_packet_v1"
OUTPUT_SCHEMA_VERSION = "trace_net_constrained_writer_output_v1"

DEFAULT_CANARY_ROUTES: Tuple[str, ...] = (
    "exact_identifier_lookup",
    "exact_table_ipl_lookup",
    "ata_system_discovery",
)

CITATION_RE = re.compile(r"\[(\d{1,3})\]")
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?|"
    r"[A-Z]{2,}\d{4,}(?:[-./][A-Z0-9]+)*)\b",
    re.I,
)
FIGURE_RE = re.compile(r"\bfigure\s+\d+(?:\s+sheet\s+\d+)?\b", re.I)

ANSWER_ANCHOR_PATTERNS: Tuple[str, ...] = (
    "best indexed match",
    "appears in the indexed source records",
    "matching candidates are listed below",
    "strongest nomenclature matches",
    "source-location leads",
    "appears in the available ipl/table evidence",
)

PACKET_FORBIDDEN_KEYS = {
    "evidence_envelope",
    "typed_evidence",
    "claim_ready_evidence",
    "query_atoms",
    "coverage",
    "retrieval_tunnels",
    "identifier_blob",
    "source_trace",
    "route_scores",
    "raw_response",
}

SAFETY_CONTRACT = {
    "read_only": True,
    "single_model_call_maximum": True,
    "legacy_freeform_writer_suppressed": True,
    "phase3_deterministic_fallback_preserved": True,
    "structured_output_required": True,
    "raw_evidence_envelope_excluded": True,
    "guidance_not_promoted_to_proof": True,
    "retrieval_changed": False,
    "ranking_changed": False,
    "route_changed": False,
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


def _clean(value: Any, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _bool_env(environ: Mapping[str, str], name: str, default: bool) -> bool:
    raw = str(environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def load_constrained_writer_config(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    routes = tuple(
        value.strip()
        for value in str(
            env.get(
                "TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES",
                ",".join(DEFAULT_CANARY_ROUTES),
            )
        ).split(",")
        if value.strip()
    )
    try:
        max_citations = int(env.get("TRACE_NET_H30_CONSTRAINED_WRITER_MAX_CITATIONS", "16"))
    except (TypeError, ValueError):
        max_citations = 16
    try:
        max_output_chars = int(env.get("TRACE_NET_H30_CONSTRAINED_WRITER_MAX_OUTPUT_CHARS", "12000"))
    except (TypeError, ValueError):
        max_output_chars = 12000
    return {
        "enabled": _bool_env(env, "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", False),
        "routes": routes or DEFAULT_CANARY_ROUTES,
        "max_citations": max(1, min(32, max_citations)),
        "max_output_chars": max(1000, min(30000, max_output_chars)),
        "require_evidence_and_limits_exact_copy": _bool_env(
            env,
            "TRACE_NET_H30_CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS",
            True,
        ),
    }


def legacy_freeform_writer_should_be_suppressed(
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    return bool(load_constrained_writer_config(environ).get("enabled"))


def _registry_by_id(registry: Sequence[Mapping[str, Any]]) -> Dict[int, Dict[str, Any]]:
    output: Dict[int, Dict[str, Any]] = {}
    for raw in registry:
        try:
            citation_id = int(raw.get("citation_id") or 0)
        except (TypeError, ValueError):
            continue
        if citation_id > 0:
            output[citation_id] = dict(raw)
    return output


def _section_lines(content: str) -> Dict[str, List[str]]:
    parsed = parse_public_answer(content)
    sections = parsed.get("sections") if isinstance(parsed, Mapping) else {}
    return {
        "Answer": [str(value) for value in (sections.get("Answer") or []) if str(value).strip()],
        "Evidence": [str(value) for value in (sections.get("Evidence") or []) if str(value).strip()],
        "Limits": [str(value) for value in (sections.get("Limits") or []) if str(value).strip()],
    }


def _authority_for_citations(
    citation_ids: Sequence[int],
    registry_map: Mapping[int, Mapping[str, Any]],
) -> str:
    rows = [registry_map[value] for value in citation_ids if value in registry_map]
    if any(row.get("can_prove_claims") for row in rows):
        return "proof"
    if any(str(row.get("authority") or "") == "supporting" for row in rows):
        return "literal_page_source"
    return "guidance"


def _reduced_registry_entry(entry: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "citation_id": int(entry.get("citation_id") or 0),
        "authority": "proof" if entry.get("can_prove_claims") else str(entry.get("authority") or "guidance"),
        "claim_scope": str(entry.get("claim_scope") or "candidate_or_guidance"),
        "class": _clean(entry.get("class"), 120),
        "candidate_value": _clean(entry.get("candidate_value"), 240),
        "page_id": _clean(entry.get("page_id"), 240),
        "ata": _clean(entry.get("ata"), 80),
        "ata_codes": [_clean(value, 80) for value in (entry.get("ata_codes") or []) if _clean(value, 80)],
        "nomenclature": [_clean(value, 160) for value in (entry.get("nomenclature") or []) if _clean(value, 160)],
        "value": _clean(entry.get("value"), 800),
    }


def _answer_anchor_phrases(text: str) -> List[str]:
    low = re.sub(r"\s+", " ", str(text or "")).casefold()
    return [phrase for phrase in ANSWER_ANCHOR_PATTERNS if phrase in low]


def _protected_tokens(text: str) -> Dict[str, List[Any]]:
    return {
        "citations": sorted({int(value) for value in CITATION_RE.findall(str(text or ""))}),
        "parts": sorted({value.upper() for value in PART_RE.findall(str(text or ""))}),
        "atas": sorted({value.upper() for value in ATA_RE.findall(str(text or ""))}),
        "pages": sorted({value.upper() for value in PAGE_RE.findall(str(text or ""))}),
        "figures": sorted({value.casefold() for value in FIGURE_RE.findall(str(text or ""))}),
    }


def build_writer_packet(
    *,
    query: str,
    result: Mapping[str, Any],
    registry: Sequence[Mapping[str, Any]],
    max_citations: int = 16,
) -> Dict[str, Any]:
    """Build a compact packet from the final deterministic answer and registry.

    Raw typed evidence, graph records, route telemetry, and the evidence envelope
    are intentionally excluded.
    """
    content = str(result.get("content") or "").strip()
    sections = _section_lines(content)
    registry_map = _registry_by_id(registry)
    used_ids = _protected_tokens(content)["citations"][: max(1, int(max_citations))]

    claims: List[Dict[str, Any]] = []
    for line in sections["Answer"] + sections["Evidence"]:
        citation_ids = sorted({int(value) for value in CITATION_RE.findall(line)})
        claims.append({
            "text": _clean(line, 1800),
            "citation_ids": citation_ids,
            "authority": _authority_for_citations(citation_ids, registry_map),
        })

    packet = {
        "schema_version": SCHEMA_VERSION,
        "question": _clean(query, 2000),
        "route": str(result.get("route") or ""),
        "answer_mode": str(_mapping(result.get("answer_mode")).get("mode") or ""),
        "deterministic_sections": {
            "answer": list(sections["Answer"]),
            "evidence": list(sections["Evidence"]),
            "limits": list(sections["Limits"]),
        },
        "claims": claims,
        "citation_registry": [
            _reduced_registry_entry(registry_map[citation_id])
            for citation_id in used_ids
            if citation_id in registry_map
        ],
        "allowed": _protected_tokens(query + "\n" + content),
        "required_answer_phrases": _answer_anchor_phrases("\n".join(sections["Answer"])),
        "rules": {
            "return_json_only": True,
            "output_schema": OUTPUT_SCHEMA_VERSION,
            "one_call_only": True,
            "no_new_facts": True,
            "no_new_identifiers": True,
            "no_new_citations": True,
            "evidence_and_limits_must_be_copied_exactly": True,
            "guidance_cannot_become_proof": True,
            "authority_claims_require_proof_authority": True,
        },
    }
    return packet


def validate_packet(packet: Mapping[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    blob = json.dumps(packet, ensure_ascii=False, sort_keys=True)
    for key in PACKET_FORBIDDEN_KEYS:
        if f'"{key}"' in blob:
            failures.append(f"forbidden_packet_key:{key}")
    if packet.get("schema_version") != SCHEMA_VERSION:
        failures.append("packet_schema_version_invalid")
    if not str(packet.get("question") or "").strip():
        failures.append("packet_question_missing")
    sections = _mapping(packet.get("deterministic_sections"))
    if not sections.get("answer") or not sections.get("evidence"):
        failures.append("packet_deterministic_sections_incomplete")
    allowed = _mapping(packet.get("allowed"))
    registry_ids = {
        int(row.get("citation_id") or 0)
        for row in _rows(packet.get("citation_registry"))
        if int(row.get("citation_id") or 0) > 0
    }
    if not set(allowed.get("citations") or []).issubset(registry_ids):
        failures.append("packet_allowed_citation_missing_from_registry")
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "accepted": not failures,
        "failures": list(dict.fromkeys(failures)),
    }


def render_writer_prompt(packet: Mapping[str, Any]) -> str:
    packet_json = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    return f"""You are TRACE-Net's constrained wording step.

Return exactly one JSON object and no markdown fence or commentary:
{{
  "schema_version": "{OUTPUT_SCHEMA_VERSION}",
  "answer": ["one or more concise answer lines"],
  "evidence": ["evidence lines copied exactly from deterministic_sections.evidence"],
  "limits": ["limit lines copied exactly from deterministic_sections.limits"]
}}

Rules:
1. Use only the packet below. Do not use memory or outside knowledge.
2. Do not add, remove, merge, or change any evidence or limit line.
3. You may improve only the answer wording, and only without changing meaning.
4. Preserve every part number, ATA code, page id, figure reference, and citation from the deterministic answer.
5. Do not add a citation or identifier that is not in packet.allowed.
6. Guidance must remain guidance. Do not claim approval, fit, effectivity, safety, eligibility, interchangeability, or authority unless the packet explicitly supplies proof authority.
7. Do not reveal packet keys, internal implementation details, or JSON beyond the required output object.

CLAIM-READY WRITER PACKET
{packet_json}
"""


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
        return dict(value) if isinstance(value, Mapping) else {}
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        value = json.loads(raw[start : end + 1])
        return dict(value) if isinstance(value, Mapping) else {}
    except Exception:
        return {}


def _string_lines(value: Any, *, maximum: int = 32, max_chars: int = 3000) -> List[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    output: List[str] = []
    for item in values[:maximum]:
        line = _clean(item, max_chars)
        if line:
            output.append(line)
    return output


def parse_structured_writer_output(text: str) -> Dict[str, Any]:
    value = _extract_json_object(text)
    return {
        "schema_version": str(value.get("schema_version") or ""),
        "answer": _string_lines(value.get("answer"), maximum=6, max_chars=2200),
        "evidence": _string_lines(value.get("evidence"), maximum=32, max_chars=3000),
        "limits": _string_lines(value.get("limits"), maximum=16, max_chars=2400),
        "raw_object_present": bool(value),
        "unknown_keys": sorted(
            str(key)
            for key in value
            if str(key) not in {"schema_version", "answer", "evidence", "limits"}
        ),
    }


def validate_structured_output(
    structured: Mapping[str, Any],
    *,
    packet: Mapping[str, Any],
    require_exact_support_sections: bool = True,
) -> Dict[str, Any]:
    failures: List[str] = []
    if not structured.get("raw_object_present"):
        failures.append("structured_json_missing")
    if structured.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        failures.append("structured_schema_version_invalid")
    if structured.get("unknown_keys"):
        failures.append("structured_unknown_keys")
    answer = [str(value) for value in (structured.get("answer") or [])]
    evidence = [str(value) for value in (structured.get("evidence") or [])]
    limits = [str(value) for value in (structured.get("limits") or [])]
    if not answer:
        failures.append("structured_answer_empty")
    deterministic = _mapping(packet.get("deterministic_sections"))
    expected_evidence = [str(value) for value in (deterministic.get("evidence") or [])]
    expected_limits = [str(value) for value in (deterministic.get("limits") or [])]
    if require_exact_support_sections:
        if evidence != expected_evidence:
            failures.append("evidence_section_not_exact_copy")
        if limits != expected_limits:
            failures.append("limits_section_not_exact_copy")

    rendered = render_public_answer(answer, evidence, limits)
    allowed = _mapping(packet.get("allowed"))
    found = _protected_tokens(rendered)
    for key in ("citations", "parts", "atas", "pages", "figures"):
        if not set(found.get(key) or []).issubset(set(allowed.get(key) or [])):
            failures.append(f"structured_output_added_{key}")
    original_answer = "\n".join(str(value) for value in (deterministic.get("answer") or []))
    original_tokens = _protected_tokens(original_answer)
    candidate_answer = "\n".join(answer)
    candidate_tokens = _protected_tokens(candidate_answer)
    candidate_answer_low = re.sub(r"\s+", " ", candidate_answer).casefold()
    for phrase in packet.get("required_answer_phrases") or []:
        if str(phrase).casefold() not in candidate_answer_low:
            failures.append(f"answer_dropped_required_phrase:{phrase}")
    for key in ("citations", "parts", "atas", "pages", "figures"):
        if set(original_tokens.get(key) or []) != set(candidate_tokens.get(key) or []):
            failures.append(f"answer_dropped_or_changed_{key}")

    contract = validate_public_answer_contract(rendered, route=str(packet.get("route") or ""))
    if not contract.get("accepted"):
        failures.extend(f"public_contract:{value}" for value in (contract.get("failures") or []))
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "accepted": not failures,
        "failures": list(dict.fromkeys(failures)),
        "rendered": rendered,
        "public_contract": contract,
    }


def _eligible_for_call(
    *,
    result: Mapping[str, Any],
    config: Mapping[str, Any],
    registry: Sequence[Mapping[str, Any]],
) -> Tuple[bool, str]:
    if not config.get("enabled"):
        return False, "disabled"
    route = str(result.get("route") or "")
    if route not in set(config.get("routes") or ()):
        return False, "route_not_in_canary"
    if not bool(_mapping(result.get("post_answer_validation")).get("accepted")):
        return False, "phase3_answer_not_validated"
    content = str(result.get("content") or "")
    if not content.strip():
        return False, "phase3_answer_empty"
    if not registry:
        return False, "citation_registry_empty"
    if not CITATION_RE.search(content):
        return False, "no_cited_positive_evidence"
    if re.search(r"\bno indexed match was found\b|\bwas not found in the indexed document set\b", content, re.I):
        return False, "negative_control"
    return True, "eligible_canary_route"


def constrained_writer_health(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    config = load_constrained_writer_config(environ)
    return {
        "status": STATUS,
        "quality_status": "PASS",
        "enabled": bool(config.get("enabled")),
        "canary_routes": list(config.get("routes") or ()),
        "single_model_call_maximum": True,
        "legacy_freeform_writer_suppressed": bool(config.get("enabled")),
        "structured_output_required": True,
        "phase3_fallback_preserved": True,
        "raw_evidence_envelope_excluded": True,
        "retrieval_changed": False,
        "ranking_changed": False,
        "route_changed": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def install_constrained_gemma_writer(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_CONSTRAINED_GEMMA_WRITER_V1_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health
    citation_registry = module["citation_registry"]
    citation_registry_digest = module["citation_registry_digest"]
    validate_answer = module["validate_answer"]
    extract_latest_user = module["extract_latest_user"]
    synthesis_allowed_identifiers = module.get("synthesis_allowed_identifiers")
    http_json = module["http_json"]

    def process_constrained_writer(
        self: Any,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        config = load_constrained_writer_config()
        query = extract_latest_user(payload)
        registry = (
            citation_registry(result)
            if config.get("enabled")
            else _rows(result.get("citation_registry"))
        )
        old_content = str(result.get("content") or "")
        old_validation = _mapping(result.get("post_answer_validation"))
        eligible, reason = _eligible_for_call(result=result, config=config, registry=registry)

        telemetry: Dict[str, Any] = {
            "status": STATUS,
            "module": MODULE,
            "version": VERSION,
            "patch_id": PATCH_ID,
            "quality_status": "SKIPPED",
            "enabled": bool(config.get("enabled")),
            "route": str(result.get("route") or ""),
            "eligible": eligible,
            "reason": reason,
            "legacy_freeform_gemma_suppressed": bool(
                result.get("legacy_freeform_gemma_suppressed")
                or config.get("enabled")
            ),
            "call_attempted": False,
            "call_count": 0,
            "single_call_maximum": True,
            "packet_schema_version": SCHEMA_VERSION,
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "packet_validation": {},
            "structured_output_validation": {},
            "final_answer_validation": old_validation,
            "structured_output_parsed": False,
            "structured_output_accepted": False,
            "phase3_fallback_used": False,
            "gemma_call_count_added": 0,
            "retrieval_changed": False,
            "route_changed": False,
            "source_truth_mutation_allowed": False,
            "write_attempt_count": 0,
        }

        if not eligible:
            result["constrained_gemma_writer"] = telemetry
            if config.get("enabled"):
                result["citation_registry"] = registry
                result["citation_registry_size"] = len(registry)
                result["citation_registry_digest"] = citation_registry_digest(registry)
            return result

        packet = build_writer_packet(
            query=query,
            result=result,
            registry=registry,
            max_citations=int(config.get("max_citations") or 16),
        )
        packet_validation = validate_packet(packet)
        telemetry["packet_validation"] = packet_validation
        telemetry["packet"] = packet
        if not packet_validation.get("accepted"):
            telemetry.update({
                "quality_status": "FAIL",
                "reason": "packet_validation_failed",
                "phase3_fallback_used": True,
            })
            result["constrained_gemma_writer"] = telemetry
            return result

        gemma_payload = {
            "model": self.gemma_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return one strict JSON object using only the supplied claim-ready packet.",
                },
                {"role": "user", "content": render_writer_prompt(packet)},
            ],
            "temperature": 0,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        telemetry["call_attempted"] = True
        telemetry["call_count"] = 1
        telemetry["gemma_call_count_added"] = 1
        status, gemma = http_json(
            self.gemma_base_url + "/chat/completions",
            gemma_payload,
            api_key=self.gemma_api_key,
            timeout=self.timeout,
        )
        telemetry["http_status"] = status
        if status != 200:
            telemetry.update({
                "quality_status": "PASS",
                "reason": f"gemma_call_failed_status_{status}",
                "phase3_fallback_used": True,
            })
            result["writer_mode_before_constrained_writer"] = result.get("writer_mode")
            result["writer_mode"] = "phase3_deterministic_fallback_after_constrained_gemma_error"
            result["gemma_status"] = f"CONSTRAINED_GEMMA_CALL_FAILED_STATUS_{status}"
            result["constrained_gemma_writer"] = telemetry
            return result

        choices = gemma.get("choices") if isinstance(gemma, Mapping) else None
        raw_output = ""
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message")
            if isinstance(message, Mapping):
                raw_output = str(message.get("content") or "")
        structured = parse_structured_writer_output(raw_output[: int(config.get("max_output_chars") or 12000)])
        telemetry["structured_output_parsed"] = bool(structured.get("raw_object_present"))
        structured_validation = validate_structured_output(
            structured,
            packet=packet,
            require_exact_support_sections=bool(config.get("require_evidence_and_limits_exact_copy", True)),
        )
        telemetry["structured_output_validation"] = {
            key: value
            for key, value in structured_validation.items()
            if key != "rendered"
        }

        candidate = str(structured_validation.get("rendered") or "")
        extra_allowed = (
            synthesis_allowed_identifiers(query, result)
            if callable(synthesis_allowed_identifiers)
            else None
        )
        final_validation = validate_answer(
            candidate,
            query,
            result,
            extra_allowed=extra_allowed,
            registry=registry,
        ) if structured_validation.get("accepted") else {
            "quality_status": "FAIL",
            "accepted": False,
            "failures": list(structured_validation.get("failures") or []),
        }
        telemetry["final_answer_validation"] = final_validation

        if structured_validation.get("accepted") and final_validation.get("accepted"):
            result["content"] = candidate
            result["post_answer_validation"] = final_validation
            result["writer_mode_before_constrained_writer"] = result.get("writer_mode")
            result["writer_mode"] = "constrained_gemma_structured_output_validated"
            result["gemma_status"] = "CONSTRAINED_GEMMA_CALL_SUCCEEDED_AND_VALIDATED"
            telemetry.update({
                "quality_status": "PASS",
                "reason": "structured_output_validated",
                "structured_output_accepted": True,
                "phase3_fallback_used": False,
            })
        else:
            result["content"] = old_content
            result["post_answer_validation"] = old_validation
            result["writer_mode_before_constrained_writer"] = result.get("writer_mode")
            result["writer_mode"] = "phase3_deterministic_fallback_after_constrained_output_rejection"
            result["gemma_status"] = "CONSTRAINED_GEMMA_OUTPUT_REJECTED_PHASE3_FALLBACK"
            telemetry.update({
                "quality_status": "PASS",
                "reason": "structured_output_rejected",
                "structured_output_accepted": False,
                "phase3_fallback_used": True,
            })

        result["citation_registry"] = registry
        result["citation_registry_size"] = len(registry)
        result["citation_registry_digest"] = citation_registry_digest(registry)
        result["constrained_gemma_writer"] = telemetry
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    def health_constrained_writer(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        health = constrained_writer_health()
        result["constrained_gemma_writer"] = health
        result["constrained_gemma_writer_enabled"] = bool(health.get("enabled"))
        result["single_gemma_call_maximum"] = True
        result["legacy_freeform_writer_suppressed"] = bool(health.get("enabled"))
        result["phase3_deterministic_fallback_preserved"] = True
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    runtime_cls.process = process_constrained_writer
    runtime_cls.health = health_constrained_writer
    module[marker] = True


__all__ = [
    "MODULE",
    "VERSION",
    "STATUS",
    "PATCH_ID",
    "SCHEMA_VERSION",
    "OUTPUT_SCHEMA_VERSION",
    "DEFAULT_CANARY_ROUTES",
    "build_writer_packet",
    "validate_packet",
    "render_writer_prompt",
    "parse_structured_writer_output",
    "validate_structured_output",
    "load_constrained_writer_config",
    "legacy_freeform_writer_should_be_suppressed",
    "constrained_writer_health",
    "install_constrained_gemma_writer",
]
