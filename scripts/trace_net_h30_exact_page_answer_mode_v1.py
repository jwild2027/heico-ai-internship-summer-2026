"""Final exact-page answer integration for TRACE-Net H30.

This overlay runs after the existing evidence-aware answer modes and before the
final Engram rollout. It keeps a validated Gemma exact-page answer when safe,
otherwise renders a deterministic fallback from ONLY the requested exact-page
pack. It never retrieves new evidence, adds a model call, or mutates a source
store.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence

MODULE = "trace_net_h30_exact_page_answer_mode_v1"
PATCH_ID = "trace_net_h30_exact_page_answer_integration_v1"
MODE_EXACT_PAGE = "exact_page_content"
FOLLOWUP_MARKER = "Helpful follow-up questions:"


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _page_content(result: Mapping[str, Any]) -> Mapping[str, Any]:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        return {}
    coverage = envelope.get("coverage")
    if not isinstance(coverage, Mapping):
        return {}
    page_content = coverage.get("page_content")
    return page_content if isinstance(page_content, Mapping) else {}


def exact_page_packs(result: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    page_content = _page_content(result)
    pages = page_content.get("pages")
    if not page_content.get("available") or not isinstance(pages, list):
        return []
    return [row for row in pages if isinstance(row, Mapping) and row.get("found") is not False]


def exact_page_content_found(result: Mapping[str, Any]) -> bool:
    packs = exact_page_packs(result)
    if not packs:
        return False
    return any(
        pack.get(section)
        for pack in packs
        for section in (
            "ocr",
            "tables",
            "visuals",
            "v1_context",
            "v2_context",
            "v3_page_intelligence",
        )
    )


def _compact(value: Any, limit: int = 1800) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _citation(record: Mapping[str, Any]) -> str:
    value = record.get("citation_id")
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    return f"[{number}]"


def _record_lines(
    records: Any,
    *,
    label: str,
    wording: str,
    maximum: int = 4,
    text_limit: int = 1800,
) -> List[str]:
    output: List[str] = []
    if not isinstance(records, list):
        return output
    for record in records[:maximum]:
        if not isinstance(record, Mapping):
            continue
        text = _compact(record.get("text"), text_limit)
        citation = _citation(record)
        if not text or not citation:
            continue
        output.append(f"- **{label}:** {wording}{text} {citation}")
    return output


def _first_page_citation(pack: Mapping[str, Any]) -> str:
    for section in (
        "ocr",
        "tables",
        "visuals",
        "v3_page_intelligence",
        "v2_context",
        "v1_context",
    ):
        records = pack.get(section)
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, Mapping):
                citation = _citation(record)
                if citation:
                    return citation
    return ""


def render_exact_page_fallback(result: Mapping[str, Any]) -> str:
    """Render only the exact page pack; never fall back to unrelated typed leads."""
    packs = exact_page_packs(result)
    lines: List[str] = ["## Answer"]

    for pack in packs:
        page_id = str(pack.get("page_id") or "the requested page")
        page_citation = _first_page_citation(pack)
        if page_citation:
            lines.extend(["", f"### Page `{page_id}` {page_citation}"])
        else:
            lines.extend(["", f"### Page `{page_id}`"])

        source_lines: List[str] = []
        source_lines.extend(
            _record_lines(
                pack.get("ocr"),
                label="OCR text",
                wording="The page text reads: ",
                maximum=3,
                text_limit=2400,
            )
        )
        source_lines.extend(
            _record_lines(
                pack.get("tables"),
                label="Table content",
                wording="The exact-page table record contains: ",
                maximum=5,
                text_limit=1400,
            )
        )
        if source_lines:
            lines.extend(["", "The page text supports these literal observations:"])
            lines.extend(source_lines)

        visual_lines = _record_lines(
            pack.get("visuals"),
            label="Diagram guidance",
            wording="The diagram appears to show: ",
            maximum=4,
            text_limit=1800,
        )
        if visual_lines:
            lines.extend(["", "Visual interpretation:"])
            lines.extend(visual_lines)

        context_lines: List[str] = []
        context_lines.extend(
            _record_lines(
                pack.get("v3_page_intelligence"),
                label="V3 page intelligence",
                wording="The page-intelligence summary suggests: ",
                maximum=2,
                text_limit=1200,
            )
        )
        context_lines.extend(
            _record_lines(
                pack.get("v2_context"),
                label="V2 page context",
                wording="The V2 page summary suggests: ",
                maximum=2,
                text_limit=900,
            )
        )
        context_lines.extend(
            _record_lines(
                pack.get("v1_context"),
                label="V1 page context",
                wording="The older page context suggests: ",
                maximum=1,
                text_limit=700,
            )
        )
        if context_lines and not source_lines:
            lines.extend(["", "Page-context guidance:"])
            lines.extend(context_lines)

        conflicts = pack.get("conflicts")
        if isinstance(conflicts, list) and conflicts:
            lines.extend([
                "",
                "The page records contain an unresolved conflict, so the conflicting value is not stated as fact.",
            ])

    lines.extend([
        "",
        "## Evidence limits",
        "OCR and exact table text support statements about what is printed on the requested page. Visual, V1, V2, and V3 records remain guidance. These records describe page content only and do not establish engineering authorization or installation suitability.",
    ])
    return "\n".join(lines).strip()


def _strip_followups(text: str) -> str:
    value = str(text or "").strip()
    index = value.find(FOLLOWUP_MARKER)
    return value[:index].rstrip() if index >= 0 else value


def sanitize_validated_exact_page_answer(text: str, *, has_supporting: bool) -> str:
    """Remove generic guidance boilerplate that contradicts exact OCR/table support."""
    value = _strip_followups(text)
    if not has_supporting:
        return value

    replacements = {
        "Only guidance-level matches were found. Candidate, visual, semantic, graph, summary, OCR, and table-derived guidance does not prove the requested claim.":
            "The OCR or table record supports literal observations about what is printed on the requested page. Visual and summary records remain guidance.",
        "Guidance only; insufficient for a confirmed technical conclusion.":
            "The page text supports literal page-content observations, but it does not establish engineering authorization or installation suitability.",
        "A source-resolved record is still required before using the result as proof.":
            "Additional authority evidence is required before making an engineering authorization or installation-suitability conclusion.",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value.strip()


def _answer_mode(result: Mapping[str, Any], *, fallback_used: bool) -> Dict[str, Any]:
    page_content = _page_content(result)
    telemetry = page_content.get("telemetry") if isinstance(page_content.get("telemetry"), Mapping) else {}
    return {
        "status": "TRACE_NET_H30_EXACT_PAGE_ANSWER_MODE_V1",
        "quality_status": "PASS",
        "mode": MODE_EXACT_PAGE,
        "reason": "exact_canonical_page_content_available",
        "route": str(result.get("route") or ""),
        "gemma_writing_allowed": True,
        "deterministic_rendering_required": bool(fallback_used),
        "exact_page_match": bool(telemetry.get("exact_page_match")),
        "page_content_record_count": int(telemetry.get("page_content_record_count") or 0),
        "page_content_registry_count": int(telemetry.get("page_content_registry_count") or 0),
        "cross_page_record_count": int(telemetry.get("cross_page_record_count") or 0),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def install_exact_page_answer_mode(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_EXACT_PAGE_ANSWER_MODE_V1_INSTALLED"
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

    def process_exact_page(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        if not exact_page_content_found(result):
            return result
        if str(result.get("route") or "") == "authority_eligibility_verification":
            return result

        query = extract_latest_user(payload)
        registry = citation_registry(result)
        old_validation = _mapping(result.get("post_answer_validation"))
        has_supporting = any(
            entry.get("page_content") and entry.get("authority") == "supporting"
            for entry in registry
        )

        fallback_used = not bool(old_validation.get("accepted"))
        if fallback_used:
            candidate = render_exact_page_fallback(result)
        else:
            candidate = sanitize_validated_exact_page_answer(
                str(result.get("content") or ""),
                has_supporting=has_supporting,
            )

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
        )

        if not final_validation.get("accepted") and not fallback_used:
            fallback_used = True
            candidate = render_exact_page_fallback(result)
            final_validation = validate_answer(
                candidate,
                query,
                result,
                extra_allowed=extra_allowed,
                registry=registry,
            )

        result["gemma_draft_validation"] = old_validation
        result["content"] = _strip_followups(candidate)
        result["follow_up_questions"] = []
        result["post_answer_validation"] = final_validation
        result["answer_mode"] = _answer_mode(result, fallback_used=fallback_used)
        result["answer_mode_validation"] = {
            "quality_status": "PASS" if final_validation.get("accepted") else "FAIL",
            "accepted": bool(final_validation.get("accepted")),
            "failures": list(final_validation.get("failures") or []),
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        result["writer_mode"] = (
            "deterministic_exact_page_fallback_after_validation_failure"
            if fallback_used
            else "gemma_validated_exact_page_content"
        )
        if fallback_used:
            result["gemma_status"] = (
                "LLM_OUTPUT_REJECTED_EXACT_PAGE_FALLBACK_ACCEPTED"
                if final_validation.get("accepted")
                else "LLM_OUTPUT_REJECTED_EXACT_PAGE_FALLBACK_REJECTED"
            )
        result["citation_registry"] = registry
        result["citation_registry_size"] = len(registry)
        result["citation_registry_digest"] = citation_registry_digest(registry)
        result["exact_page_answer_mode"] = {
            "module": MODULE,
            "patch_id": PATCH_ID,
            "enabled": True,
            "fallback_used": fallback_used,
            "final_answer_accepted": bool(final_validation.get("accepted")),
            "unrelated_typed_fallback_allowed": False,
            "followups_suppressed": True,
            "gemma_call_count_added": 0,
            "read_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    def health_exact_page(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result.update({
            "exact_page_answer_mode_enabled": True,
            "exact_page_answer_mode": MODE_EXACT_PAGE,
            "exact_page_fallback_uses_requested_page_only": True,
            "exact_page_followups_suppressed": True,
            "exact_page_adds_gemma_call": False,
            "exact_page_read_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.process = process_exact_page
    runtime_cls.health = health_exact_page
    module[marker] = True
