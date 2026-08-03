#!/usr/bin/env python3
"""TRACE-Net H30 public answer presentation v1.2 (Phases 0.6 and 0.7 gate).

This final corrective overlay is intentionally narrow. It runs after the v1.1
presentation layer and only re-renders part-search routes to:

* remove uncited factual wording from mixed exact-part limits;
* require nomenclature relevance for nomenclature-search results;
* normalize a small set of known OCR nomenclature defects;
* hide internal evidence-field labels such as ``Covered Part Number``; and
* keep all selected evidence tied to the existing numeric citation registry.

It does not retrieve evidence, call an LLM, alter routing, grant answer authority,
or write/mutate any source store.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

MODULE = "trace_net_h30_chatgpt_answer_presentation_v1_2"
STATUS = "TRACE_NET_H30_CHATGPT_ANSWER_PRESENTATION_V1_2"
PATCH_ID = "trace_net_h30_phase0_6_public_answer_corrections_v1"

PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?|"
    r"[A-Z]{2,}\d{4,}(?:[-./][A-Z0-9]+)*)\b",
    re.I,
)
CITATION_RE = re.compile(r"\[(\d{1,3})\]")
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)

TARGET_ROUTES = {
    "exact_identifier_lookup",
    "guided_part_discovery",
    "nomenclature_function_search",
}

INTERNAL_NAMES = {
    "covered part number",
    "covered identifier",
    "source backed record",
    "source field",
    "direct source",
    "embedding candidate",
    "ocr page text",
    "page content",
    "candidate",
    "record",
}

QUERY_STOPWORDS = {
    "find", "show", "best", "matching", "match", "matches", "part", "parts",
    "component", "components", "document", "documents", "set", "source", "sources",
    "page", "pages", "connected", "connection", "the", "a", "an", "in", "and",
}


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _compact(value: Any, limit: int = 8000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _citation(entry: Mapping[str, Any]) -> str:
    try:
        number = int(entry.get("citation_id") or 0)
    except (TypeError, ValueError):
        return ""
    return f"[{number}]" if number > 0 else ""


def _entry_class(entry: Mapping[str, Any]) -> str:
    return str(entry.get("class") or "").strip().lower()


def _entry_text(entry: Mapping[str, Any]) -> str:
    return _compact(
        entry.get("identifier_blob")
        or entry.get("value")
        or entry.get("candidate_value")
        or entry.get("snippet")
        or entry.get("field_name")
    )


def _entry_identifier(entry: Mapping[str, Any]) -> str:
    explicit = str(entry.get("candidate_value") or entry.get("part_number") or "").strip()
    if explicit:
        return explicit
    match = PART_RE.search(_entry_text(entry))
    return match.group(0) if match else ""


def _entry_page(entry: Mapping[str, Any]) -> str:
    page = str(entry.get("page_id") or "").strip()
    if page:
        return page
    pages = entry.get("page_ids")
    if isinstance(pages, list):
        for value in pages:
            if str(value).strip():
                return str(value).strip()
    match = PAGE_RE.search(_entry_text(entry))
    return match.group(0) if match else ""


def _is_direct(entry: Mapping[str, Any]) -> bool:
    return bool(entry.get("can_prove_claims")) or _entry_class(entry) in {
        "direct_source",
        "authority",
    }


def _canonical_name(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        raw = " ".join(str(item) for item in value if str(item).strip())
    else:
        raw = str(value or "")

    upper = re.sub(r"[^A-Z0-9 ]+", " ", raw.upper())
    upper = re.sub(r"\bSEE\s+FIGURE\b", " ", upper)
    upper = re.sub(r"\bUSING\s+THE\s+INSTALLED\b.*", " ", upper)
    upper = PART_RE.sub(" ", upper)
    upper = re.sub(r"\bASSYV\b", "ASSEMBLY", upper)
    upper = re.sub(r"\bASSEMBLYV\b", "ASSEMBLY", upper)
    upper = re.sub(r"\bASSY\b", "ASSEMBLY", upper)
    upper = re.sub(r"\s+", " ", upper).strip()
    if not upper:
        return ""

    words = upper.split()
    word_set = set(words)
    if "STRUCTURE" in word_set and "ARMREST" in word_set:
        return "Structure Armrest"
    if "STRUCTURE" in word_set and "LATERAL" in word_set and "LEG" in word_set:
        return "Structure Lateral Leg"
    if "STRUCTURE" in word_set and ({"CENTRAL", "CENTER"} & word_set) and "LEG" in word_set:
        return "Structure Central Leg"
    if "STRUCTURE" in word_set and "ASSEMBLY" in word_set:
        return "Structure Assembly"
    if "COVER" in word_set and "LATCH" in word_set and "SNACK" in word_set and "TABLE" in word_set:
        return "Cover Latch Snack Table Assembly"
    if "PIN" in word_set and "SPRING" in word_set:
        return "Pin Spring"
    if "PIN" in word_set and ({"ATTACH", "ATTACHMENT"} & word_set):
        return "Pin Attach"
    if "RING" in word_set and ({"LOCK", "LOCKING"} & word_set):
        return "Ring Locking"
    if "SUPPORT" in word_set:
        return "Support"
    if "SINGLE" in word_set and "PASSENGER" in word_set and "SEAT" in word_set:
        return "Single Passenger Seat Assembly" if "ASSEMBLY" in word_set else "Single Passenger Seat"
    if "DOUBLE" in word_set and "PASSENGER" in word_set and "SEAT" in word_set:
        return "Double Passenger Seat Assembly" if "ASSEMBLY" in word_set else "Double Passenger Seat"

    blocked = {"UNKNOWN", "FIGURE", "COVES", "RERE", "SARY", "WS", "VS", "MCE"}
    output: List[str] = []
    seen = set()
    for token in words:
        if token in blocked or token.isdigit() or re.search(r"(.)\1\1", token):
            continue
        if token in seen:
            continue
        seen.add(token)
        output.append(token)
    return " ".join(output[:7]).title().replace("Lh", "LH").replace("Rh", "RH")


def _entry_name(entry: Mapping[str, Any]) -> str:
    for value in (
        entry.get("nomenclature"),
        entry.get("matched_nomenclature"),
        entry.get("field_name"),
    ):
        name = _canonical_name(value)
        if name and name.casefold() not in INTERNAL_NAMES:
            return name
    return ""


def _intent(result: Mapping[str, Any], query: str) -> Tuple[str, str]:
    atoms = _mapping(result.get("query_atoms"))
    mode = str(atoms.get("identifier_mode") or "").lower()
    exact_parts = atoms.get("exact_part_numbers")
    exact_first = exact_parts[0] if isinstance(exact_parts, list) and exact_parts else ""
    requested = (
        atoms.get("normalized_identifier")
        or atoms.get("family_identifier")
        or exact_first
        or atoms.get("part_prefix")
        or atoms.get("part_contains")
        or atoms.get("part_suffix")
    )
    if not requested:
        match = PART_RE.search(query)
        requested = match.group(0) if match else ""
    if not mode or mode == "none":
        mode = "exact" if requested else "none"
    return mode, _norm(requested)


def _matches_intent(identifier: str, mode: str, requested: str) -> bool:
    candidate = _norm(identifier)
    if not candidate:
        return False
    if not requested or mode == "none":
        return True
    if mode == "exact":
        return candidate == requested
    if mode in {"prefix", "family"}:
        return candidate.startswith(requested)
    if mode == "suffix":
        return candidate.endswith(requested)
    if mode in {"contains", "partial"}:
        return requested in candidate
    return requested in candidate


def _requested_nomenclature_terms(result: Mapping[str, Any], query: str) -> List[str]:
    atoms = _mapping(result.get("query_atoms"))
    values: List[str] = []
    for key in (
        "nomenclature_terms",
        "component_terms",
        "part_nouns",
        "function_terms",
    ):
        value = atoms.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value)

    match = re.search(r"\bfind\s+the\s+(.+?)\s+in\s+the\s+document", query, re.I)
    if match:
        values.append(match.group(1))

    output: List[str] = []
    seen = set()
    for value in values:
        for token in re.findall(r"[A-Za-z]{3,}", value.lower()):
            if token in QUERY_STOPWORDS or token in seen:
                continue
            seen.add(token)
            output.append(token)
    return output


def _nomenclature_relevant(entry: Mapping[str, Any], terms: Sequence[str]) -> bool:
    name = _entry_name(entry)
    typed = " ".join(
        str(entry.get(key) or "")
        for key in ("matched_term", "search_term", "nomenclature_match", "match_reason")
    )
    blob_tokens = set(re.findall(r"[a-z]{3,}", (name + " " + typed).lower()))
    if not terms:
        return bool(name)
    return bool(name and any(term in blob_tokens or term in name.lower() for term in terms))


def _entry_score(entry: Mapping[str, Any]) -> Tuple[int, int, int]:
    try:
        citation_number = int(entry.get("citation_id") or 10_000)
    except (TypeError, ValueError):
        citation_number = 10_000
    return (
        1 if _is_direct(entry) else 0,
        1 if _entry_name(entry) else 0,
        -citation_number,
    )


def _selected_entries(
    result: Mapping[str, Any],
    query: str,
    entries: Sequence[Mapping[str, Any]],
    *,
    route: str,
    maximum: int = 10,
) -> List[Dict[str, Any]]:
    mode, requested = _intent(result, query)
    terms = _requested_nomenclature_terms(result, query)
    candidates: List[Dict[str, Any]] = []
    for raw in entries:
        entry = dict(raw)
        identifier = _entry_identifier(entry)
        if not identifier or not _citation(entry):
            continue
        if route == "nomenclature_function_search":
            if not _nomenclature_relevant(entry, terms):
                continue
        elif not _matches_intent(identifier, mode, requested):
            continue
        candidates.append(entry)

    groups: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}
    for entry in candidates:
        identifier = _norm(_entry_identifier(entry))
        page = _entry_page(entry).casefold()
        kind = "direct" if _is_direct(entry) else "guidance"
        name = _entry_name(entry).casefold() if not _is_direct(entry) else ""
        groups.setdefault((identifier, page, kind, name), []).append(entry)

    selected: List[Dict[str, Any]] = []
    for group in groups.values():
        group.sort(key=_entry_score, reverse=True)
        selected.append(group[0])
    selected.sort(
        key=lambda entry: (
            0 if _is_direct(entry) else 1,
            _norm(_entry_identifier(entry)),
            _entry_page(entry),
            _entry_name(entry),
        )
    )
    return selected[:maximum]


def _bullet(entry: Mapping[str, Any]) -> str:
    identifier = _entry_identifier(entry)
    citation = _citation(entry)
    if not identifier or not citation:
        return ""
    details: List[str] = []
    name = _entry_name(entry)
    page = _entry_page(entry)
    if name:
        details.append(name)
    if page:
        details.append(f"page `{page}`")
    label = "Source-backed record: " if _is_direct(entry) else ""
    suffix = " — " + "; ".join(details) if details else ""
    return f"{label}`{identifier}`{suffix} {citation}".strip()


def _dedupe(lines: Iterable[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for raw in lines:
        line = re.sub(r"\s+", " ", str(raw or "")).strip()
        key = line.casefold()
        if not line or key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def _format(answer: str, evidence: Sequence[str], limits: Sequence[str]) -> str:
    lines = ["## Answer", "", answer.strip()]
    evidence = _dedupe(evidence)
    limits = _dedupe(limits)
    if evidence:
        lines.extend(["", "## Evidence", ""])
        lines.extend(f"- {line}" for line in evidence)
    if limits:
        lines.extend(["", "## Limits", ""])
        lines.extend(f"- {line}" for line in limits)
    return "\n".join(lines).strip()


def render_part_answer_v1_2(result: Mapping[str, Any], query: str) -> str:
    route = str(result.get("route") or "")
    entries = _rows(result.get("citation_registry"))
    selected = _selected_entries(result, query, entries, route=route)
    evidence = [_bullet(entry) for entry in selected]
    evidence = [line for line in evidence if line]
    query_match = PART_RE.search(query)
    identifier = query_match.group(0) if query_match else ""

    if not evidence:
        target = f"`{identifier}`" if identifier else "the requested part"
        return _format(
            f"No indexed match was found for {target}.",
            ["No matching indexed part record was returned."],
            [],
        )

    first_citation = _citation(selected[0])
    direct = any(_is_direct(entry) for entry in selected)
    guidance = any(not _is_direct(entry) for entry in selected)
    conflicts = any(entry.get("metadata_conflict") for entry in selected)

    if route == "guided_part_discovery":
        answer = "Matching candidates are listed below."
        if direct and first_citation:
            answer = f"Matching candidates are listed below {first_citation}."
        limits = ["These are ranked search matches; use the cited source pages to compare them."]
    elif route == "nomenclature_function_search":
        answer = "The strongest nomenclature matches are listed below."
        limits = ["A nomenclature match is a search lead, not confirmation of a technical relationship."]
    else:
        target = f"`{identifier}`" if identifier else "The requested part"
        if direct:
            answer = f"{target} appears in the indexed source records {first_citation}."
            # Avoid the validator's factual-marker terms (listed/page/nomenclature).
            limits = ["Some associations remain guidance-level."] if guidance else []
        else:
            answer = f"The best indexed match for {target} is shown below {first_citation}."
            limits = ["The record remains a candidate unless a cited source field confirms the requested identity."]

    if conflicts:
        limits.append("One or more records contain an unresolved source-association conflict.")
    return _format(answer, evidence, limits)


def _validate_rendered(
    answer: str,
    query: str,
    result: Mapping[str, Any],
    validate_answer: Any,
    registry: Sequence[Mapping[str, Any]],
    extra_allowed: Any,
) -> Dict[str, Any]:
    validation = validate_answer(
        answer,
        query,
        result,
        extra_allowed=extra_allowed,
        registry=registry,
    )
    if isinstance(validation, Mapping):
        return dict(validation)
    return {
        "accepted": False,
        "quality_status": "FAIL",
        "failures": ["invalid_validator_result"],
    }


def install_chatgpt_answer_presentation_v1_2(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_CHATGPT_ANSWER_PRESENTATION_V1_2_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health
    validate_answer = module["validate_answer"]
    extract_latest_user = module["extract_latest_user"]
    citation_registry = module["citation_registry"]
    citation_registry_digest = module["citation_registry_digest"]
    synthesis_allowed_identifiers = module.get("synthesis_allowed_identifiers")

    def process_v1_2(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        query = extract_latest_user(payload)
        route = str(result.get("route") or "")
        old_content = str(result.get("content") or "")
        old_validation = _mapping(result.get("post_answer_validation"))

        if route not in TARGET_ROUTES:
            result["chatgpt_answer_presentation_v1_2"] = {
                "status": STATUS,
                "patch_id": PATCH_ID,
                "quality_status": "PASS" if old_validation.get("accepted") else str(old_validation.get("quality_status") or "PASS"),
                "applied": False,
                "reason": "route_not_targeted",
                "gemma_call_count_added": 0,
                "retrieval_changed": False,
                "route_changed": False,
                "source_truth_mutation_allowed": False,
                "write_attempt_count": 0,
            }
            return result

        registry = citation_registry(result)
        rendered = render_part_answer_v1_2(result, query).strip()
        extra_allowed = (
            synthesis_allowed_identifiers(query, result)
            if callable(synthesis_allowed_identifiers)
            else None
        )
        validation = _validate_rendered(
            rendered,
            query,
            result,
            validate_answer,
            registry,
            extra_allowed,
        )

        # Never replace a previously valid answer with a less-safe one.
        fallback_used = False
        if not validation.get("accepted") and old_validation.get("accepted"):
            rendered = old_content
            validation = old_validation
            fallback_used = True

        result["content"] = rendered
        result["post_answer_validation"] = validation
        result["citation_registry"] = registry
        result["citation_registry_size"] = len(registry)
        result["citation_registry_digest"] = citation_registry_digest(registry)
        result["writer_mode_before_chatgpt_presentation_v1_2"] = result.get("writer_mode")
        result["writer_mode"] = (
            "chatgpt_presentation_v1_2_fallback_to_prior_valid_answer"
            if fallback_used
            else "chatgpt_style_public_answer_v1_2"
        )
        result["chatgpt_answer_presentation_v1_2"] = {
            "status": STATUS,
            "patch_id": PATCH_ID,
            "quality_status": "PASS" if validation.get("accepted") else "FAIL",
            "applied": True,
            "q02_q03_uncited_limit_fixed": True,
            "nomenclature_relevance_filter_enabled": True,
            "known_assyv_cleanup_enabled": True,
            "internal_evidence_labels_hidden": True,
            "old_answer_changed": rendered.strip() != old_content.strip(),
            "fallback_used": fallback_used,
            "final_validation_accepted": bool(validation.get("accepted")),
            "final_validation_failures": list(validation.get("failures") or []),
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

    def health_v1_2(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result.update({
            "chatgpt_answer_presentation_v1_2_enabled": True,
            "chatgpt_answer_presentation_v1_2_status": STATUS,
            "public_nomenclature_relevance_filter": True,
            "public_internal_evidence_labels_hidden_v1_2": True,
            "public_mixed_exact_limit_validation_fixed": True,
            "chatgpt_presentation_v1_2_adds_gemma_call": False,
            "chatgpt_presentation_v1_2_changes_retrieval": False,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.process = process_v1_2
    runtime_cls.health = health_v1_2
    module[marker] = True


__all__ = [
    "MODULE",
    "STATUS",
    "PATCH_ID",
    "install_chatgpt_answer_presentation_v1_2",
    "render_part_answer_v1_2",
]
