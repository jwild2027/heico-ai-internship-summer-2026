#!/usr/bin/env python3
"""TRACE-Net H30 Phase 4.3 part intent and source-resolution overlay.

This module is read-only. It improves exact/partial/prefix/suffix/family part
intent, rejects malformed or unrelated candidates, performs bounded attempts to
resolve guidance to citation-ready source evidence, and adds claim-specific
support metadata. It does not write PostgreSQL, Qdrant, OpenSearch, or source
truth and never grants answer permission.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


from scripts.trace_net_h30_phase4_3_1_exact_identifier_v1 import (
    build_planner_seed,
    enforce_final_identifier_filter,
    explicit_part_partial_wording,
    general_source_overview_requested,
    infer_exact_identifier_candidate,
    normalize_identifier as normalize_identifier_v431,
    part_fragment_is_explicit,
    phase4_3_1_health,
)

MODULE = "trace_net_h30_part_intent_source_resolution_v1"
PATCH_ID = "trace_net_h30_phase4_3_part_intent_source_resolution_v1"
VERSION = "v1"

PART_CONTEXT_RE = re.compile(
    r"\b(?:p/?n|part(?:\s+number)?|component(?:\s+number)?)\b"
    r"\s*(?:is|=|:|#)?\s*([A-Za-z0-9][A-Za-z0-9./-]{2,31})",
    re.I,
)
HYPHENATED_IDENTIFIER_RE = re.compile(r"\b[A-Za-z0-9]{2,10}(?:-[A-Za-z0-9]{2,12}){1,4}\b", re.I)
PREFIX_RE = re.compile(
    r"\b(?:starts?|begins?|prefix(?:ed)?)\b\s*(?:with|is|=|:)?\s*([A-Za-z0-9-]{2,24})",
    re.I,
)
CONTAINS_RE = re.compile(
    r"\b(?:contains?|includes?|has)\b\s*(?:the\s+characters?|digits?|text|fragment)?\s*"
    r"(?:is|=|:)?\s*([A-Za-z0-9-]{2,24})",
    re.I,
)
SUFFIX_RE = re.compile(
    r"\b(?:ends?|suffix(?:ed)?)\b\s*(?:with|is|=|:)?\s*([A-Za-z0-9-]{2,24})",
    re.I,
)
FAMILY_BEFORE_RE = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9-]{3,30})\s+(?:family|series|base(?:\s+number)?)\b", re.I)
FAMILY_AFTER_RE = re.compile(r"\b(?:family|series|base(?:\s+number)?)\b\s*(?:is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9-]{3,30})", re.I)

PARTIAL_WORDS = (
    "partial", "fragment", "contains", "contain", "starts with", "start with",
    "begins with", "begin with", "ends with", "end with", "prefix", "suffix",
    "only know", "only remember", "do not know", "don't know", "cannot remember",
    "can't remember", "family", "series", "base number",
)

AUTHORITY_FIELD_HINTS = (
    "approval", "approved", "interchange", "effectivity", "eligibility",
    "installation_authority", "applicability", "fitment",
)


def compact(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            import json
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def normalize_identifier(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def clean_identifier(value: Any) -> str:
    text = str(value or "").strip().strip(".,;:()[]{}<>\"'")
    return text.upper()


def identifier_is_well_formed(value: Any) -> bool:
    """Conservative candidate validity check; never repairs uncertain OCR."""
    text = clean_identifier(value)
    if not text or len(text) > 40:
        return False
    if "/" in text or "\\" in text:
        return False
    if re.search(r"\s", text):
        return False
    if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", text):
        return False
    normalized = normalize_identifier(text)
    if len(normalized) < 4 or not any(ch.isdigit() for ch in normalized):
        return False
    if re.search(r"(?:--|\.\.|__)", text):
        return False
    # Reject common OCR/symbol artifacts masquerading as identifiers.
    if re.fullmatch(r"[0O1ILSZB]{4,}", normalized):
        return False
    return True


def _first_identifier(query: str) -> Optional[str]:
    for pattern in (PART_CONTEXT_RE, HYPHENATED_IDENTIFIER_RE):
        match = pattern.search(query)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            value = clean_identifier(value)
            if identifier_is_well_formed(value):
                return value
    return None


def _match_value(pattern: re.Pattern[str], query: str) -> Optional[str]:
    match = pattern.search(query)
    if not match:
        return None
    value = clean_identifier(match.group(1))
    if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", value):
        return None
    normalized = normalize_identifier(value)
    if len(normalized) < 2 or not any(ch.isdigit() for ch in normalized):
        return None
    return value


def _ata_identifier_values(atoms: Optional[Any]) -> set[str]:
    values: set[str] = set()
    if atoms is None:
        return values
    prefix = normalize_identifier(getattr(atoms, "ata_prefix", ""))
    if prefix:
        values.add(prefix)
    for value in list(getattr(atoms, "ata_exact", []) or []):
        normalized = normalize_identifier(value)
        if normalized:
            values.add(normalized)
    return values


def _ata_bound_fragments(query: str) -> set[str]:
    """Extract only values grammatically bound to ATA/chapter/system wording."""
    output: set[str] = set()
    patterns = (
        r"\b(?:ata|chapter|system)(?:\s+(?:number|code))?\s*"
        r"(?:(?:starts?|begins?|prefix(?:ed)?|contains?|ends?)\s*(?:with\s+)?)?"
        r"(?:is|=|:)?\s*([A-Za-z0-9-]{2,24})",
        r"\b(?:starts?|begins?)\s+with\s+([A-Za-z0-9-]{2,24})"
        r".{0,20}\b(?:ata|chapter|system)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, query, re.I):
            normalized = normalize_identifier(match.group(1))
            if normalized:
                output.add(normalized)
    return output


def _is_ata_bound_fragment(query: str, value: Optional[str], atoms: Optional[Any]) -> bool:
    """Prevent ATA chapter/code clues from becoming part-number intent."""
    normalized = normalize_identifier(value)
    if not normalized:
        return False
    return normalized in (_ata_identifier_values(atoms) | _ata_bound_fragments(query))


def derive_part_intent(query: str, atoms: Optional[Any] = None) -> Dict[str, Any]:
    """Return an inspectable intent contract without performing retrieval."""
    text = str(query or "").strip()
    low = re.sub(r"\s+", " ", text.lower()).strip()

    prefix = _match_value(PREFIX_RE, text)
    contains = _match_value(CONTAINS_RE, text)
    suffix = _match_value(SUFFIX_RE, text)
    family = _match_value(FAMILY_BEFORE_RE, text) or _match_value(FAMILY_AFTER_RE, text)

    atom_prefix = clean_identifier(getattr(atoms, "part_prefix", "")) if atoms is not None else ""
    atom_contains = clean_identifier(getattr(atoms, "part_contains", "")) if atoms is not None else ""
    atom_suffix = clean_identifier(getattr(atoms, "part_suffix", "")) if atoms is not None else ""
    if atoms is not None:
        prefix = prefix or atom_prefix or None
        contains = contains or atom_contains or None
        suffix = suffix or atom_suffix or None

    # Generic words such as "table contains" must not become partial part intent.
    if prefix and not (
        part_fragment_is_explicit(text, prefix, "prefix")
        or normalize_identifier_v431(prefix) == normalize_identifier_v431(atom_prefix)
    ):
        prefix = None
    if contains and not (
        part_fragment_is_explicit(text, contains, "contains")
        or normalize_identifier_v431(contains) == normalize_identifier_v431(atom_contains)
    ):
        contains = None
    if suffix and not (
        part_fragment_is_explicit(text, suffix, "suffix")
        or normalize_identifier_v431(suffix) == normalize_identifier_v431(atom_suffix)
    ):
        suffix = None

    ata_fragment_suppressed = False
    if _is_ata_bound_fragment(text, prefix, atoms):
        prefix = None
        ata_fragment_suppressed = True
    if _is_ata_bound_fragment(text, contains, atoms):
        contains = None
        ata_fragment_suppressed = True
    if _is_ata_bound_fragment(text, suffix, atoms):
        suffix = None
        ata_fragment_suppressed = True
    if _is_ata_bound_fragment(text, family, atoms):
        family = None
        ata_fragment_suppressed = True

    legacy_identifier = _first_identifier(text)
    if _is_ata_bound_fragment(text, legacy_identifier, atoms):
        # Record that an ATA-shaped token was intentionally suppressed even
        # though the exact-identifier classifier will also reject it.
        legacy_identifier = None
        ata_fragment_suppressed = True

    explicit_partial = explicit_part_partial_wording(text) or bool(family)
    if explicit_partial:
        # A complete-looking token can still be an uncertain/partial clue when
        # the user explicitly says it is partial or only remembered.
        fallback_identifier = legacy_identifier
    else:
        fallback_identifier = infer_exact_identifier_candidate(
            text,
            atoms,
            legacy_identifier=legacy_identifier,
        )
    token = family or prefix or contains or suffix or fallback_identifier

    mode = "none"
    requested = token
    if family:
        mode = "family"
    elif prefix:
        mode = "prefix"
    elif suffix:
        mode = "suffix"
    elif contains:
        mode = "contains"
    elif token and explicit_partial:
        mode = "partial"
    elif token:
        mode = "exact"

    return {
        "identifier_mode": mode,
        "requested_identifier": requested,
        "normalized_identifier": normalize_identifier(requested),
        "family_identifier": family,
        "allow_family_expansion": mode == "family",
        "allow_partial_candidates": mode in {"prefix", "contains", "suffix", "partial", "family"},
        "explicit_partial_wording": explicit_partial,
        "ata_fragment_suppressed": ata_fragment_suppressed,
        "strict_exact_equality": mode == "exact",
        "auto_ocr_correction_allowed": False,
    }


def apply_intent_to_atoms(atoms: Any, intent: Mapping[str, Any]) -> Any:
    mode = str(intent.get("identifier_mode") or "none")
    requested = clean_identifier(intent.get("requested_identifier"))

    atoms.identifier_mode = mode
    atoms.normalized_identifier = str(intent.get("normalized_identifier") or "")
    atoms.family_identifier = clean_identifier(intent.get("family_identifier")) or None
    atoms.allow_family_expansion = bool(intent.get("allow_family_expansion"))
    atoms.allow_partial_candidates = bool(intent.get("allow_partial_candidates"))
    atoms.explicit_partial_wording = bool(intent.get("explicit_partial_wording"))
    atoms.ata_fragment_suppressed = bool(intent.get("ata_fragment_suppressed"))

    if mode == "none" and atoms.ata_fragment_suppressed:
        ata_values = _ata_identifier_values(atoms)
        for field_name in ("part_prefix", "part_contains", "part_suffix"):
            current = getattr(atoms, field_name, None)
            if normalize_identifier(current) in ata_values:
                setattr(atoms, field_name, None)

    if mode == "exact":
        atoms.exact_part_numbers = [requested] if requested else list(getattr(atoms, "exact_part_numbers", []) or [])
        atoms.part_prefix = None
        atoms.part_contains = None
        atoms.part_suffix = None
    elif mode == "prefix":
        atoms.exact_part_numbers = []
        atoms.part_prefix = requested
        atoms.part_contains = None
        atoms.part_suffix = None
    elif mode in {"contains", "partial"}:
        atoms.exact_part_numbers = []
        atoms.part_prefix = None
        atoms.part_contains = requested
        atoms.part_suffix = None
    elif mode == "suffix":
        atoms.exact_part_numbers = []
        atoms.part_prefix = None
        atoms.part_contains = None
        atoms.part_suffix = requested
    elif mode == "family":
        atoms.exact_part_numbers = []
        atoms.part_prefix = requested
        atoms.part_contains = None
        atoms.part_suffix = None
    return atoms


def candidate_matches_intent(value: Any, intent: Mapping[str, Any]) -> bool:
    if not identifier_is_well_formed(value):
        return False
    candidate = normalize_identifier(value)
    requested = str(intent.get("normalized_identifier") or "")
    mode = str(intent.get("identifier_mode") or "none")
    if not requested or mode == "none":
        return True
    if mode == "exact":
        return candidate == requested
    if mode in {"prefix", "family"}:
        return candidate.startswith(requested)
    if mode in {"contains", "partial"}:
        return requested in candidate
    if mode == "suffix":
        return candidate.endswith(requested)
    return False


def candidate_value(row: Mapping[str, Any]) -> str:
    for key in ("candidate_part_number", "candidate_value", "part_number", "value", "matched_token"):
        value = compact(row.get(key), 300)
        if value:
            return value
    return ""


def row_supports_identifier(row: Mapping[str, Any], identifier: str) -> bool:
    requested = normalize_identifier(identifier)
    if not requested:
        return False
    blob = normalize_identifier(compact(row, 12000))
    return requested in blob


def _claim_type(row: Mapping[str, Any]) -> str:
    field = " ".join(
        compact(row.get(name), 500).lower()
        for name in ("field_name", "field", "claim_type", "source_type", "nomenclature")
    )
    if any(token in field for token in AUTHORITY_FIELD_HINTS):
        return "authority"
    if any(token in field for token in ("warning", "caution", "note", "hazard")):
        return "warning_or_caution"
    if any(token in field for token in ("procedure", "task", "step", "removal", "installation")):
        return "procedure_step"
    if any(token in field for token in ("nomenclature", "description", "part_name", "name")):
        return "nomenclature"
    if any(token in field for token in ("figure", "callout", "illustration")):
        return "figure_callout"
    if any(token in field for token in ("item", "table", "ipl", "row", "cell")):
        return "table_item"
    if any(token in field for token in ("assembly", "parent", "relationship", "contains")):
        return "assembly_relationship"
    if any(token in field for token in ("part", "identifier", "part_number", "pn")):
        return "part_identity"
    return "source_field"


def build_claim_evidence(direct_rows: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    output: Dict[str, List[Dict[str, Any]]] = {}
    for raw in direct_rows:
        row = dict(raw)
        output.setdefault(_claim_type(row), []).append(row)
    return output


def _resolution_record(
    *,
    lead_type: str,
    lead_value: str,
    page_id: str,
    direct_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    matches = []
    for row in direct_rows:
        same_page = bool(page_id and compact(row.get("page_id"), 300) == page_id)
        same_identifier = bool(lead_value and row_supports_identifier(row, lead_value))
        if same_page or same_identifier:
            matches.append(dict(row))
    return {
        "lead_type": lead_type,
        "lead_value": lead_value,
        "page_id": page_id,
        "resolution_status": "resolved" if matches else "unresolved",
        "matching_direct_evidence_count": len(matches),
        "resolved_claim_types": sorted({_claim_type(row) for row in matches}),
        "guidance_only": not bool(matches),
        "source_truth_mutation_allowed": False,
    }


def build_source_resolution(envelope: Any, atoms: Any) -> List[Dict[str, Any]]:
    direct = [dict(row) for row in getattr(envelope, "direct_evidence", []) if isinstance(row, Mapping)]
    records: List[Dict[str, Any]] = []
    seen = set()

    requested = clean_identifier(getattr(atoms, "family_identifier", None) or getattr(atoms, "normalized_identifier", ""))
    if requested:
        record = _resolution_record(
            lead_type="requested_identifier",
            lead_value=requested,
            page_id="",
            direct_rows=direct,
        )
        records.append(record)
        seen.add((record["lead_type"], normalize_identifier(requested), ""))

    for attr, lead_type in (
        ("candidate_evidence", "candidate"),
        ("visual_guidance", "visual"),
        ("semantic_guidance", "semantic"),
    ):
        for raw in getattr(envelope, attr, [])[:8]:
            if not isinstance(raw, Mapping):
                continue
            value = candidate_value(raw)
            if not value:
                parts = raw.get("part_numbers")
                if isinstance(parts, list) and parts:
                    value = compact(parts[0], 300)
            page = compact(raw.get("page_id"), 300)
            key = (lead_type, normalize_identifier(value), page)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                _resolution_record(
                    lead_type=lead_type,
                    lead_value=value,
                    page_id=page,
                    direct_rows=direct,
                )
            )
    return records


def part_intent_source_resolution_health() -> Dict[str, Any]:
    return {
        "part_intent_source_resolution_v1": True,
        "identifier_modes": ["exact", "prefix", "contains", "suffix", "partial", "family", "none"],
        "explicit_partial_overrides_exact": True,
        "strict_exact_candidate_equality": True,
        "unrelated_fallback_candidates_disabled": True,
        "ocr_candidate_auto_correction": False,
        "bounded_source_resolution": True,
        "claim_specific_evidence_buckets": True,
        "candidate_discovery_is_guidance_only": True,
        "read_only": True,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }


def install_part_intent_source_resolution(module: MutableMapping[str, Any]) -> None:
    """Install the Phase 4.3 overlay into the cognitive router module globals."""
    marker = "_TRACE_NET_H30_PART_INTENT_SOURCE_RESOLUTION_V1_INSTALLED"
    if module.get(marker):
        return

    original_extract = module["extract_query_atoms"]
    original_plan = module["plan_route"]
    original_matches = module["candidate_matches_atoms"]
    original_extract_candidates = module["extract_candidates"]
    runtime_cls = module["CognitiveRuntime"]
    original_gather = runtime_cls.gather_initial
    original_critic = runtime_cls.critic
    original_repair = getattr(runtime_cls, "repair", None)
    original_health = runtime_cls.health
    unique_dicts = module["unique_dicts"]
    apply_exact_entity_gate = module["apply_exact_entity_gate"]

    def atoms_intent(atoms: Any) -> Dict[str, Any]:
        return {
            "identifier_mode": getattr(atoms, "identifier_mode", "none"),
            "requested_identifier": (
                getattr(atoms, "family_identifier", None)
                or (getattr(atoms, "exact_part_numbers", []) or [None])[0]
                or getattr(atoms, "part_prefix", None)
                or getattr(atoms, "part_contains", None)
                or getattr(atoms, "part_suffix", None)
            ),
            "normalized_identifier": getattr(atoms, "normalized_identifier", ""),
            "family_identifier": getattr(atoms, "family_identifier", None),
            "allow_family_expansion": bool(getattr(atoms, "allow_family_expansion", False)),
            "allow_partial_candidates": bool(getattr(atoms, "allow_partial_candidates", False)),
            "explicit_partial_wording": bool(getattr(atoms, "explicit_partial_wording", False)),
        }

    def extract_query_atoms_v1(query: str) -> Any:
        atoms = original_extract(query)
        intent = derive_part_intent(query, atoms)
        return apply_intent_to_atoms(atoms, intent)

    def plan_route_v1(atoms: Any) -> Any:
        plan = original_plan(atoms)
        mode = str(getattr(atoms, "identifier_mode", "none"))
        if (
            general_source_overview_requested(getattr(atoms, "latest_query", ""))
            and plan.primary_route in {
                "clarification_no_evidence", "semantic_discovery",
                "nomenclature_function_search",
            }
        ):
            plan.primary_route = "semantic_discovery"
            plan.secondary_routes = ["document_page_navigation"]
            plan.retrieval_tunnels = [
                "qdrant_guidance", "v2_v3_summary_guidance",
                "graph_leiden_guidance", "normal_source_resolution",
            ]
            plan.rationale = ["Phase 4.3.1 general manual/source overview intent"]
            return plan
        protected = {
            "safe_general_chat", "multi_question_research", "authority_eligibility_verification",
            "contradiction_resolution", "cross_source_comparison", "ocr_scan_recovery",
            "warning_caution_note_lookup", "procedure_task_lookup", "exact_table_ipl_lookup",
            "visual_figure_callout_lookup", "high_degree_entity_aggregation",
            "graph_relationship_reasoning", "document_page_navigation",
        }
        if plan.primary_route not in protected:
            if mode == "exact":
                plan.primary_route = "exact_identifier_lookup"
                plan.secondary_routes = ["guided_part_discovery", "visual_figure_callout_lookup"]
                plan.retrieval_tunnels = [
                    "normal_source_truth", "guided_exact_candidate", "confirmed_visual",
                    "phase4_3_exact_source_resolution", "qdrant_guidance",
                ]
                plan.rationale = ["Phase 4.3 strict exact identifier intent"]
            elif mode in {"prefix", "contains", "suffix", "partial", "family"}:
                plan.primary_route = "guided_part_discovery"
                plan.secondary_routes = ["exact_identifier_lookup", "document_page_navigation"]
                plan.retrieval_tunnels = [
                    "guided_candidate_discovery", "normal_source_resolution",
                    "phase4_3_candidate_source_resolution", "qdrant_guidance",
                ]
                plan.rationale = [f"Phase 4.3 {mode} identifier discovery intent"]
        return plan

    def candidate_matches_atoms_v1(value: str, atoms: Any) -> bool:
        intent = atoms_intent(atoms)
        if str(intent.get("identifier_mode")) != "none":
            return candidate_matches_intent(value, intent)
        return original_matches(value, atoms)

    def extract_candidates_v1(result: Mapping[str, Any], atoms: Any, *, allow_broad: bool = False) -> List[Dict[str, Any]]:
        rows = original_extract_candidates(result, atoms, allow_broad=allow_broad)
        intent = atoms_intent(atoms)
        mode = str(intent.get("identifier_mode") or "none")
        output = []
        for raw in rows:
            row = dict(raw)
            value = candidate_value(row)
            if not identifier_is_well_formed(value):
                continue
            if mode != "none" and not candidate_matches_intent(value, intent):
                continue
            row["candidate_value"] = value
            row["candidate_validity"] = "PASS"
            row["identifier_match_mode"] = mode
            row["requested_identifier"] = intent.get("requested_identifier")
            row["guidance_only"] = True
            row["source_truth"] = False
            row["final_answer_allowed"] = False
            output.append(row)
        return unique_dicts(output, ("candidate_value", "page_id", "document", "ata"))

    def _strict_filter_direct(envelope: Any, atoms: Any) -> None:
        intent = atoms_intent(atoms)
        mode = str(intent.get("identifier_mode") or "none")
        requested = clean_identifier(intent.get("requested_identifier"))
        if mode == "exact" and requested:
            kept = [row for row in envelope.direct_evidence if row_supports_identifier(row, requested)]
            dropped = len(envelope.direct_evidence) - len(kept)
            envelope.direct_evidence = kept
            if dropped:
                envelope.uncertainties.append(
                    f"phase4_3_removed_{dropped}_direct_row(s)_without_exact_identifier_support"
                )
        if mode != "none":
            envelope.candidate_evidence = [
                row for row in envelope.candidate_evidence
                if candidate_matches_intent(candidate_value(row), intent)
            ]

    def _refresh_phase4_3_1_metadata(envelope: Any, atoms: Any, plan: Any) -> Dict[str, Any]:
        intent = atoms_intent(atoms)
        _strict_filter_direct(envelope, atoms)
        apply_exact_entity_gate(envelope, atoms)
        final_filter = enforce_final_identifier_filter(envelope, intent)
        envelope.claim_evidence = build_claim_evidence(envelope.direct_evidence)
        envelope.source_resolution = build_source_resolution(envelope, atoms)
        resolved = sum(
            row.get("resolution_status") == "resolved"
            for row in envelope.source_resolution
        )
        envelope.coverage.update({
            "phase4_3_1_final_filter": final_filter,
            "phase4_3_1_planner_seed": build_planner_seed(
                getattr(atoms, "latest_query", ""),
                intent,
                getattr(plan, "primary_route", ""),
                engram_policy=getattr(plan, "engram_policy", None),
            ),
            "source_resolution_attempt_count": len(envelope.source_resolution),
            "source_resolution_resolved_count": resolved,
            "source_resolution_unresolved_count": len(envelope.source_resolution) - resolved,
            "claim_evidence_bucket_count": len(envelope.claim_evidence),
            "source_truth_mutation_allowed": False,
        })
        envelope.safety_contract.update({
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        })
        return final_filter

    def gather_initial_v1(self: Any, plan: Any, atoms: Any) -> Any:
        envelope = original_gather(self, plan, atoms)
        intent = atoms_intent(atoms)
        mode = str(intent.get("identifier_mode") or "none")
        requested = clean_identifier(intent.get("requested_identifier"))

        _strict_filter_direct(envelope, atoms)

        # Bounded source-resolution attempts. Existing upstreams remain read-only.
        if mode == "exact" and requested and not envelope.direct_evidence:
            self.add_unified(
                envelope,
                f"Search the IPL table and citation-ready source fields for exact part {requested}",
                "phase4_3_exact_source_resolution",
            )
        elif mode in {"prefix", "contains", "suffix", "partial", "family"} and envelope.candidate_evidence:
            for row in envelope.candidate_evidence[:2]:
                value = candidate_value(row)
                if value:
                    self.add_unified(
                        envelope,
                        f"Search citation-ready source fields and IPL rows for exact part {value}",
                        "phase4_3_candidate_source_resolution",
                    )

        envelope.direct_evidence = unique_dicts(
            envelope.direct_evidence,
            ("page_id", "field_name", "normalized_value", "value"),
        )
        envelope.candidate_evidence = unique_dicts(
            envelope.candidate_evidence,
            ("candidate_value", "page_id", "document", "ata"),
        )
        envelope.visual_guidance = unique_dicts(
            envelope.visual_guidance,
            ("page_id", "subject", "figure_refs", "part_numbers"),
        )
        envelope.semantic_guidance = unique_dicts(
            envelope.semantic_guidance,
            ("point_id", "page_id", "candidate_type"),
        )
        _strict_filter_direct(envelope, atoms)
        apply_exact_entity_gate(envelope, atoms)

        envelope.claim_evidence = build_claim_evidence(envelope.direct_evidence)
        envelope.source_resolution = build_source_resolution(envelope, atoms)
        resolved = sum(row.get("resolution_status") == "resolved" for row in envelope.source_resolution)
        unresolved = len(envelope.source_resolution) - resolved
        envelope.coverage.update({
            "part_intent": dict(intent),
            "source_resolution_attempt_count": len(envelope.source_resolution),
            "source_resolution_resolved_count": resolved,
            "source_resolution_unresolved_count": unresolved,
            "claim_evidence_bucket_count": len(envelope.claim_evidence),
            "phase4_3_bounded_resolution_call_count": sum(
                1 for row in envelope.upstream_results
                if str(row.get("tunnel") or "").startswith("phase4_3_")
            ),
            "candidate_discovery_is_guidance_only": True,
            "source_truth_mutation_allowed": False,
        })
        envelope.safety_contract.update({
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "candidate_discovery_is_not_final_identification": True,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        })
        _refresh_phase4_3_1_metadata(envelope, atoms, plan)
        return envelope

    def repair_v1(
        self: Any,
        plan: Any,
        atoms: Any,
        envelope: Any,
        critic: Mapping[str, Any],
    ) -> None:
        if original_repair is not None:
            original_repair(self, plan, atoms, envelope, critic)
        # CRAG and source-resolution calls may add new rows. Reapply exact intent
        # after every repair rather than trusting only the initial extraction pass.
        _refresh_phase4_3_1_metadata(envelope, atoms, plan)

    def critic_v1(self: Any, plan: Any, atoms: Any, envelope: Any) -> Dict[str, Any]:
        result = dict(original_critic(self, plan, atoms, envelope))
        failures = list(result.get("failures") or [])
        warnings = list(result.get("warnings") or [])
        intent = atoms_intent(atoms)
        mode = str(intent.get("identifier_mode") or "none")

        for row in envelope.candidate_evidence:
            value = candidate_value(row)
            if not identifier_is_well_formed(value):
                failures.append("phase4_3_malformed_or_ocr_noise_candidate_exposed")
                break
            if mode != "none" and not candidate_matches_intent(value, intent):
                failures.append("phase4_3_unrelated_fallback_candidate_exposed")
                break

        if mode == "exact" and not envelope.direct_evidence:
            warnings.append("phase4_3_exact_identifier_not_source_resolved")
        if mode == "family" and not bool(intent.get("allow_family_expansion")):
            failures.append("phase4_3_family_expansion_not_explicitly_allowed")

        failures = list(dict.fromkeys(failures))
        warnings = list(dict.fromkeys(warnings))
        result["failures"] = failures
        result["warnings"] = warnings
        result["quality_status"] = "RETRY" if failures else "PASS"
        result["retry_required"] = bool(failures)
        dimensions = dict(result.get("dimensions") or {})
        dimensions.update({
            "identifier_intent": "PASS" if mode in {"exact", "prefix", "contains", "suffix", "partial", "family", "none"} else "FAIL",
            "candidate_validity": "PASS" if not any("candidate" in item for item in failures) else "FAIL",
            "source_resolution": "PASS" if envelope.direct_evidence else ("GUIDANCE_ONLY" if envelope.source_resolution else "INSUFFICIENT"),
            "claim_specific_support": "PASS" if envelope.claim_evidence else "GUIDANCE_ONLY",
        })
        result["dimensions"] = dimensions
        return result

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(original_health(self))
        result.update(part_intent_source_resolution_health())
        result.update(phase4_3_1_health())
        return result

    module["extract_query_atoms"] = extract_query_atoms_v1
    module["plan_route"] = plan_route_v1
    module["candidate_matches_atoms"] = candidate_matches_atoms_v1
    module["extract_candidates"] = extract_candidates_v1
    runtime_cls.gather_initial = gather_initial_v1
    if original_repair is not None:
        runtime_cls.repair = repair_v1
    runtime_cls.critic = critic_v1
    runtime_cls.health = health_v1
    module[marker] = True
