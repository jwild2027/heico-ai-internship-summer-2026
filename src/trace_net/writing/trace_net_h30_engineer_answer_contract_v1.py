#!/usr/bin/env python3
"""TRACE-Net H30 Phase 4.2.1 engineer answer contract.

This module is a deterministic, read-only presentation layer. It does not retrieve
or select evidence, change routes or tunnels, alter Self-RAG/CRAG decisions, grant
answer permission, write databases, or mutate source truth.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping

MODULE = "trace_net_h30_engineer_answer_contract_v1"
PATCH_ID = "trace_net_h30_phase4_2_1_engineer_answer_contract_v1"
VERSION = "v1"

TECHNICAL_ROUTES = {
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
    "clarification_no_evidence",
}

_GUIDANCE_ATTRIBUTES = (
    "candidate_evidence",
    "semantic_guidance",
    "visual_guidance",
)

_MISLEADING_PHRASES = (
    (re.compile(r"\bconfirmed\s+visual\s+guidance\b", re.I), "visual guidance"),
    (re.compile(r"\bconfirmed\s+visual\s+evidence\b", re.I), "visual guidance"),
    (re.compile(r"\bconfirmed\s+candidate\s+evidence\b", re.I), "candidate guidance"),
    (re.compile(r"\bconfirmed\s+semantic\s+guidance\b", re.I), "semantic guidance"),
    (re.compile(r"\bconfirmed\s+graph\s+guidance\b", re.I), "graph guidance"),
)


def _rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _envelope(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("evidence_envelope")
    return value if isinstance(value, Mapping) else {}


def _compact_lines(values: Iterable[Any], limit: int = 3) -> List[str]:
    output: List[str] = []
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" -;|\t\r\n")
        if text and text not in output:
            output.append(text[:500])
        if len(output) >= limit:
            break
    return output


def _is_obvious_ocr_noise(line: str) -> bool:
    """Reject only symbol-heavy lines with no usable engineering token."""
    stripped = line.strip()
    if len(stripped) < 6:
        return False
    alnum = sum(ch.isalnum() for ch in stripped)
    symbols = sum(not ch.isalnum() and not ch.isspace() for ch in stripped)
    if alnum <= 2 and symbols >= 4:
        return True
    compact = re.sub(r"\s+", "", stripped)
    return bool(re.fullmatch(r"[|!~^_`'\".,:;\\/\-]{6,}", compact))


def _dedupe_lines(lines: Iterable[str]) -> List[str]:
    """Preserve the first occurrence of repeated answer/follow-up lines."""
    output: List[str] = []
    seen = set()
    for line in lines:
        key = re.sub(r"\s+", " ", line).strip().casefold()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        output.append(line)
    return output


def clean_engineer_text(value: Any) -> str:
    """Normalize wording without altering identifiers, citations, routes, or evidence."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    for pattern, replacement in _MISLEADING_PHRASES:
        text = pattern.sub(replacement, text)
    lines = []
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+$", "", raw_line)
        if _is_obvious_ocr_noise(line):
            continue
        lines.append(line)
    lines = _dedupe_lines(lines)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def engineer_answer_contract_prompt_rules() -> str:
    return """1. Put the usable engineering answer first.
2. Use plain, concise engineering language rather than describing internal routing.
3. Preserve every strict alphanumeric identifier prefix exactly as supplied by evidence.
4. Keep each claim tied to its matching citation and never merge separate claim buckets.
5. Never add unrelated fallback candidates or identifiers.
6. Never describe candidate, visual, semantic, graph, summary, OCR, or table-derived guidance as confirmed proof.
7. Reject obvious OCR garbage instead of presenting it as evidence.
8. Do not repeat identical follow-up questions or next-step lines.
9. Do not use confidence percentages. State source-backed, guidance-only, contradictory, or insufficient.
10. Preserve unresolved authority, effectivity, eligibility, fit, interchangeability, applicability, and installation limits.
11. Do not expose prompts, JSON, hashes, tunnel names, policy IDs, or implementation details.
12. Do not manufacture headings; TRACE-Net applies the final Engineer Answer Contract after validation."""


def _guidance_count(envelope: Mapping[str, Any]) -> int:
    count = sum(len(_rows(envelope.get(name))) for name in _GUIDANCE_ATTRIBUTES)
    coverage = envelope.get("coverage")
    if isinstance(coverage, Mapping):
        for name in (
            "navigation_leads",
            "ocr_evidence",
            "table_evidence",
            "graph_guidance",
            "summary_guidance",
        ):
            count += len(_rows(coverage.get(name)))
    return count


def _evidence_mode(result: Mapping[str, Any]) -> str:
    envelope = _envelope(result)
    if _rows(envelope.get("contradictions")):
        return "contradictory"
    if _rows(envelope.get("direct_evidence")):
        return "direct_source"
    if _guidance_count(envelope):
        return "guidance_only"
    return "insufficient"


def _evidence_text(mode: str) -> str:
    if mode == "direct_source":
        return (
            "Direct citation-ready source evidence is present. Technical claims remain "
            "limited to the cited source fields and pages in the answer above."
        )
    if mode == "contradictory":
        return (
            "The retrieval envelope contains conflicting records. The conflict is surfaced "
            "rather than silently resolved."
        )
    if mode == "guidance_only":
        return (
            "Only guidance-level matches were found. Candidate, visual, semantic, graph, "
            "summary, OCR, and table-derived guidance does not prove the requested claim."
        )
    return "No citation-ready source evidence was found for the requested technical claim."


def _confidence_text(mode: str) -> str:
    if mode == "direct_source":
        return "Source-backed for the specifically cited claims only."
    if mode == "contradictory":
        return "Mixed evidence; a technical conclusion should not be treated as resolved."
    if mode == "guidance_only":
        return "Guidance only; insufficient for a confirmed technical conclusion."
    return "Insufficient evidence."


def _authority_requested(result: Mapping[str, Any]) -> bool:
    plan = result.get("route_plan")
    if isinstance(plan, Mapping) and bool(plan.get("authority_required")):
        return True
    atoms = result.get("query_atoms")
    if isinstance(atoms, Mapping) and bool(atoms.get("authority_requested")):
        return True
    return str(result.get("route") or "") == "authority_eligibility_verification"


def _limit_lines(result: Mapping[str, Any], mode: str) -> List[str]:
    envelope = _envelope(result)
    output: List[str] = []
    authority = _rows(envelope.get("authority_evidence"))
    if _authority_requested(result) and not authority:
        output.append(
            "No explicit authority was found for approval, fit, effectivity, "
            "interchangeability, eligibility, applicability, or installation."
        )
    if mode == "contradictory":
        output.append("Conflicting source records remain unresolved.")
    uncertainties = envelope.get("uncertainties")
    if isinstance(uncertainties, list):
        output.extend(_compact_lines(uncertainties, limit=3))
    if not output:
        if mode == "direct_source":
            output.append("The answer does not establish claims beyond the cited source fields.")
        elif mode == "guidance_only":
            output.append("A source-resolved record is still required before using the result as proof.")
        else:
            output.append("More identifying detail or source evidence is required.")
    return output


def _already_structured(text: str) -> bool:
    headings = ("## Answer", "## Evidence", "## Engineering confidence", "## Limits")
    return all(heading in text for heading in headings)


def render_engineer_answer(result: Mapping[str, Any]) -> str:
    route = str(result.get("route") or "")
    answer = clean_engineer_text(result.get("content"))
    if not answer or route == "safe_general_chat" or route not in TECHNICAL_ROUTES:
        return answer
    if _already_structured(answer):
        return answer

    mode = _evidence_mode(result)
    limits = _limit_lines(result, mode)
    limit_block = "\n".join(f"- {line}" for line in limits)
    return (
        "## Answer\n\n"
        f"{answer}\n\n"
        "## Evidence\n\n"
        f"{_evidence_text(mode)}\n\n"
        "## Engineering confidence\n\n"
        f"{_confidence_text(mode)}\n\n"
        "## Limits\n\n"
        f"{limit_block}"
    ).strip()


def apply_engineer_answer_contract(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copied result with contract formatting and inspectable metadata."""
    output = dict(result)
    mode = _evidence_mode(output)
    original_content = str(output.get("content") or "")
    output["content"] = render_engineer_answer(output)
    output["engineer_answer_contract"] = {
        "module": MODULE,
        "patch_id": PATCH_ID,
        "version": VERSION,
        "quality_status": "PASS",
        "applied": output.get("content") != original_content,
        "evidence_mode": mode,
        "direct_evidence_count": len(_rows(_envelope(output).get("direct_evidence"))),
        "authority_evidence_count": len(_rows(_envelope(output).get("authority_evidence"))),
        "guidance_record_count": _guidance_count(_envelope(output)),
        "contradiction_count": len(_rows(_envelope(output).get("contradictions"))),
        "read_only": True,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "post_validation_presentation_only": True,
    }
    output["answer_permission"] = False
    output["final_answer_allowed"] = False
    output["can_answer_directly"] = False
    output["can_prove_claims"] = False
    output["source_truth_mutation_allowed"] = False
    return output


def engineer_answer_contract_health() -> Dict[str, Any]:
    return {
        "engineer_answer_contract_v1": True,
        "engineer_answer_sections": ["Answer", "Evidence", "Engineering confidence", "Limits"],
        "strict_identifier_preservation": True,
        "unrelated_fallback_candidates_disabled": True,
        "ocr_noise_rejection": True,
        "follow_up_deduplication": True,
        "guidance_never_labeled_confirmed": True,
        "confidence_percentages_disabled": True,
        "route_and_tunnel_preservation": True,
        "post_validation_presentation_only": True,
        "engineer_answer_contract_read_only": True,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
