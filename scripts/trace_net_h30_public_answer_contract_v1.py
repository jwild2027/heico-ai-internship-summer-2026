#!/usr/bin/env python3
"""Authoritative TRACE-Net H30 public answer contract (Phase 1).

The route-specific answer layers decide *what* evidence and wording to expose. This
module is the final deterministic public boundary and owns one shared parser,
canonical renderer, structural validator, and runtime integration for all
technical routes.

Public technical answers use exactly:

    ## Answer
    ## Evidence
    ## Limits        # omitted when there is no material limitation

The module is presentation-only. It performs no retrieval, no LLM call, no route
selection, no evidence promotion, and no source/database mutation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

MODULE = "trace_net_h30_public_answer_contract_v1"
STATUS = "TRACE_NET_H30_PUBLIC_ANSWER_CONTRACT_V1"
PATCH_ID = "trace_net_h30_phase1_public_answer_contract_v1"

CANONICAL_SECTIONS = ("Answer", "Evidence", "Limits")
HEADING_RE = re.compile(r"^\s*#{2,3}\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+")
CITATION_RE = re.compile(r"\[(\d{1,3})\]")
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?|"
    r"[A-Z]{2,}\d{4,}(?:[-./][A-Z0-9]+)*)\b",
    re.I,
)
FIGURE_RE = re.compile(r"\bfigure\s+\d+(?:\s+sheet\s+\d+)?\b", re.I)

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
}

FORBIDDEN_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.I))
    for name, pattern in (
        ("raw_json", r"(?:^|\n)\s*[\[{]\s*[\"']?[A-Za-z0-9_]+[\"']?\s*[:=]"),
        ("route_name", r"\b(?:expected_route|actual_route|route\s*[:=])\b"),
        ("retrieval_tunnel", r"\bretrieval_tunnels?\b"),
        ("entity_gate", r"\bentity_gate\b"),
        ("policy_id", r"\bpolicy[_ -]?id\b"),
        ("writer_mode", r"\bwriter_mode\b"),
        ("gemma_status", r"\bgemma_status\b"),
        ("quality_status", r"\bquality_status\b"),
        ("embedding_candidate", r"\bembedding_candidate\b"),
        ("recommended_route", r"\brecommended route\b"),
        ("ocr_status", r"\bocr status\b"),
        ("identifier_blob", r"\bidentifier_blob\b"),
        ("source_trace_ready", r"\bsource_trace_ready\b"),
        ("engineering_confidence", r"\bengineering confidence\b"),
        ("generic_followup", r"\bhelpful follow-up questions?\b"),
        ("confidence_percentage", r"\bconfidence\s*[:=]?\s*\d+(?:\.\d+)?\s*%"),
        ("trace_internal_symbol", r"\btrace_net_[a-z0-9_]+\b"),
    )
)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean(value: Any) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "").strip())


def _dedupe(lines: Iterable[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for raw in lines:
        line = _clean(raw)
        key = re.sub(r"\s+", " ", line).casefold()
        if not line or key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def _canonical_heading(raw: str) -> str:
    normalized = re.sub(r"\s+", " ", str(raw or "")).strip().casefold()
    return {
        "answer": "Answer",
        "evidence": "Evidence",
        "limits": "Limits",
        "limit": "Limits",
        "limitations": "Limits",
    }.get(normalized, "")


def parse_public_answer(text: str) -> Dict[str, Any]:
    """Parse public answer text with one shared heading/section interpretation."""
    sections: Dict[str, List[str]] = {name: [] for name in CANONICAL_SECTIONS}
    heading_order: List[str] = []
    duplicate_headings: List[str] = []
    unknown_headings: List[str] = []
    preamble: List[str] = []
    current = ""

    for raw in str(text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        match = HEADING_RE.match(stripped)
        if match:
            heading = _canonical_heading(match.group(1))
            if not heading:
                unknown_headings.append(_clean(match.group(1)))
                current = ""
                continue
            if heading in heading_order:
                duplicate_headings.append(heading)
            else:
                heading_order.append(heading)
            current = heading
            continue

        if not current:
            preamble.append(_clean(stripped))
            continue

        line = stripped
        if current in {"Evidence", "Limits"}:
            line = BULLET_RE.sub("", line)
        sections[current].append(_clean(line))

    return {
        "sections": sections,
        "heading_order": heading_order,
        "duplicate_headings": duplicate_headings,
        "unknown_headings": unknown_headings,
        "preamble": preamble,
    }


def render_public_answer(
    answer: str | Sequence[str],
    evidence: Sequence[str],
    limits: Sequence[str],
) -> str:
    """Render the canonical Answer / Evidence / optional Limits shape."""
    if isinstance(answer, str):
        answer_lines = [_clean(line) for line in answer.splitlines() if _clean(line)]
    else:
        answer_lines = [_clean(line) for line in answer if _clean(line)]
    evidence_lines = _dedupe(evidence)
    limit_lines = _dedupe(limits)

    lines = ["## Answer", "", "\n\n".join(answer_lines) or "No usable answer was produced."]
    if evidence_lines:
        lines.extend(["", "## Evidence", ""])
        lines.extend(f"- {line}" for line in evidence_lines)
    if limit_lines:
        lines.extend(["", "## Limits", ""])
        lines.extend(f"- {line}" for line in limit_lines)
    return "\n".join(lines).strip()


def canonicalize_public_answer(text: str) -> Dict[str, Any]:
    """Canonicalize an already-rendered technical answer without adding facts."""
    parsed = parse_public_answer(text)
    sections = parsed["sections"]
    answer_lines = list(sections["Answer"])
    if not answer_lines and parsed["preamble"]:
        answer_lines = list(parsed["preamble"])
    canonical = render_public_answer(
        answer_lines,
        sections["Evidence"],
        sections["Limits"],
    )
    return {
        "content": canonical,
        "parsed": parsed,
        "changed": canonical.strip() != str(text or "").strip(),
    }


def _protected_tokens(text: str) -> Dict[str, List[str]]:
    return {
        "citations": sorted(set(CITATION_RE.findall(str(text or ""))), key=int),
        "pages": sorted(set(value.casefold() for value in PAGE_RE.findall(str(text or "")))),
        "atas": sorted(set(ATA_RE.findall(str(text or "")))),
        "parts": sorted(set(value.upper() for value in PART_RE.findall(str(text or "")))),
        "figures": sorted(set(value.casefold() for value in FIGURE_RE.findall(str(text or "")))),
    }


def validate_public_answer_contract(text: str, *, route: str = "") -> Dict[str, Any]:
    """Validate only the public structural/leak contract, not claim authority."""
    if route and route not in TECHNICAL_ROUTES:
        return {
            "accepted": True,
            "quality_status": "PASS",
            "failures": [],
            "applied": False,
            "reason": "non_technical_route",
        }

    parsed = parse_public_answer(text)
    sections = parsed["sections"]
    failures: List[str] = []
    order = parsed["heading_order"]

    if parsed["preamble"]:
        failures.append("text_before_answer_heading")
    if parsed["unknown_headings"]:
        failures.extend(f"unexpected_heading:{value}" for value in parsed["unknown_headings"])
    if parsed["duplicate_headings"]:
        failures.extend(f"duplicate_heading:{value}" for value in parsed["duplicate_headings"])
    if not order or order[0] != "Answer":
        failures.append("answer_heading_must_be_first")
    if not sections["Answer"]:
        failures.append("answer_section_empty")
    if "Evidence" not in order or not sections["Evidence"]:
        failures.append("evidence_section_required")
    if "Limits" in order and not sections["Limits"]:
        failures.append("empty_limits_section")

    expected_order = [name for name in CANONICAL_SECTIONS if name in order]
    if order != expected_order:
        failures.append("section_order_invalid")

    raw_headings = [line.strip() for line in str(text or "").splitlines() if HEADING_RE.match(line.strip())]
    for heading in raw_headings:
        if not heading.startswith("## ") or heading.startswith("### "):
            failures.append("noncanonical_heading_level")
            break

    evidence_normalized = [re.sub(r"\s+", " ", line).casefold() for line in sections["Evidence"]]
    if len(evidence_normalized) != len(set(evidence_normalized)):
        failures.append("duplicate_evidence_line")

    for name, pattern in FORBIDDEN_PATTERNS:
        if pattern.search(str(text or "")):
            failures.append(f"public_leak:{name}")

    return {
        "accepted": not failures,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": list(dict.fromkeys(failures)),
        "applied": True,
        "headings": order,
        "answer_line_count": len(sections["Answer"]),
        "evidence_line_count": len(sections["Evidence"]),
        "limit_line_count": len(sections["Limits"]),
    }


def install_public_answer_contract(module: MutableMapping[str, Any]) -> None:
    """Install the final canonical public boundary after all route renderers."""
    marker = "_TRACE_NET_H30_PUBLIC_ANSWER_CONTRACT_V1_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health

    def process_public_answer_contract(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        route = str(result.get("route") or "")
        if route not in TECHNICAL_ROUTES:
            result["public_answer_contract"] = {
                "status": STATUS,
                "patch_id": PATCH_ID,
                "applied": False,
                "reason": "non_technical_route",
                "gemma_call_count_added": 0,
                "retrieval_changed": False,
                "route_changed": False,
                "source_truth_mutation_allowed": False,
                "write_attempt_count": 0,
            }
            return result

        original = str(result.get("content") or "")
        prior_validation = _mapping(result.get("post_answer_validation"))
        canonicalized = canonicalize_public_answer(original)
        rendered = str(canonicalized["content"])
        contract_validation = validate_public_answer_contract(rendered, route=route)

        before_tokens = _protected_tokens(original)
        after_tokens = _protected_tokens(rendered)
        token_failures: List[str] = []
        for token_type in before_tokens:
            if before_tokens[token_type] != after_tokens[token_type]:
                token_failures.append(f"canonicalization_changed_{token_type}")

        failures = list(prior_validation.get("failures") or [])
        failures.extend(contract_validation.get("failures") or [])
        failures.extend(token_failures)
        failures = list(dict.fromkeys(str(value) for value in failures if str(value)))
        accepted = bool(prior_validation.get("accepted")) and not failures

        result["content"] = rendered
        result["post_answer_validation"] = {
            **prior_validation,
            "accepted": accepted,
            "quality_status": "PASS" if accepted else "FAIL",
            "failures": failures,
            "public_answer_contract": contract_validation,
        }
        result["writer_mode_before_public_answer_contract"] = result.get("writer_mode")
        result["writer_mode"] = "public_answer_contract_v1"
        result["public_answer_contract"] = {
            "status": STATUS,
            "patch_id": PATCH_ID,
            "quality_status": "PASS" if accepted else "FAIL",
            "applied": True,
            "canonical_sections": list(CANONICAL_SECTIONS),
            "limits_optional": True,
            "canonicalization_changed": bool(canonicalized["changed"]),
            "source_unknown_headings": list(canonicalized["parsed"]["unknown_headings"]),
            "source_duplicate_headings": list(canonicalized["parsed"]["duplicate_headings"]),
            "protected_tokens_preserved": not token_failures,
            "contract_validation": contract_validation,
            "prior_validation_accepted": bool(prior_validation.get("accepted")),
            "final_validation_accepted": accepted,
            "final_validation_failures": failures,
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

    def health_public_answer_contract(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result.update({
            "public_answer_contract_enabled": True,
            "public_answer_contract_status": STATUS,
            "public_answer_contract_sections": list(CANONICAL_SECTIONS),
            "public_answer_limits_optional": True,
            "public_answer_shared_parser": True,
            "public_answer_shared_validator": True,
            "public_answer_contract_adds_gemma_call": False,
            "public_answer_contract_changes_retrieval": False,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.process = process_public_answer_contract
    runtime_cls.health = health_public_answer_contract
    module[marker] = True


__all__ = [
    "MODULE",
    "STATUS",
    "PATCH_ID",
    "CANONICAL_SECTIONS",
    "TECHNICAL_ROUTES",
    "parse_public_answer",
    "render_public_answer",
    "canonicalize_public_answer",
    "validate_public_answer_contract",
    "install_public_answer_contract",
]
