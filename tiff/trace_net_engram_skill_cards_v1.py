"""TRACE-Net Engram Skill Cards v1.

Phase 1 introduces a validated, inspectable library of reusable reasoning
skills.  Skill cards are behavior guidance only.  They can guide planning,
ranking, follow-up selection, answer shape, criticism, and future repair, but
they cannot prove manual facts, grant answer permission, mutate source truth,
or execute retrieval.

This module intentionally does not wire skill cards into the live cognitive
runtime.  Runtime injection belongs to the next rollout phase after the
library and deterministic selector pass their regression gates.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

MODULE = "trace_net_engram_skill_cards_v1"
VERSION = "v1"
STATUS_CHECKED = "TRACE_NET_ENGRAM_SKILL_CARDS_V1_CHECKED"
STATUS_SELECTED = "TRACE_NET_ENGRAM_SKILL_CARDS_V1_SELECTED"

SAFETY_CONTRACT = {
    "engram_guidance_only": True,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "can_be_used_as_proof": False,
    "retrieval_execution_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}

REQUIRED_CARD_FIELDS: Tuple[str, ...] = (
    "skill_id",
    "version",
    "title",
    "description",
    "memory_layers",
    "applies_when",
    "does_not_apply_when",
    "selection",
    "reasoning_goal",
    "required_first_searches",
    "allowed_tunnels",
    "forbidden_tunnels",
    "ranking_policy",
    "evidence_sufficiency",
    "answer_mode_rules",
    "answer_requirements",
    "follow_up_policy",
    "positive_examples",
    "negative_examples",
    "known_failure_lessons",
    "safety_contract",
)

PERSISTED_MEMORY_LAYERS: Set[str] = {
    "semantic_memory",
    "procedural_memory",
    "episodic_memory",
    "trait_memory",
    "critic_memory",
}

_IDENTIFIER_RE = re.compile(
    r"\b(?=[A-Z0-9-]{5,}\b)(?=[A-Z0-9-]*\d)"
    r"[A-Z0-9]+(?:-[A-Z0-9]+)+\b",
    re.IGNORECASE,
)
_ATA_RE = re.compile(r"\b\d{2}(?:-\d{2}){1,2}\b")
_SIMPLE_ATA_RE = re.compile(r"\bATA\s+\d{2}\b", re.IGNORECASE)
_PREFIX_RE = re.compile(
    r"\b(?:starts?|begins?)\s+with\b|\bprefix\b|\bfirst\s+(?:few\s+)?(?:digits|characters)\b",
    re.IGNORECASE,
)
_CONTAINS_RE = re.compile(r"\bcontains?\b|\bsomewhere\b", re.IGNORECASE)
_EXACT_CUE_RE = re.compile(
    r"\b(?:find|locate|search\s+for|where\s+(?:is|does)|listed|appear)\b",
    re.IGNORECASE,
)
_FUNCTION_RE = re.compile(
    r"\b(?:part|component|item|piece|something)\s+that\b|\bused\s+to\b|"
    r"\bthat\s+(?:lets|supports|locks|connects|slides|releases|retains|adjusts|guides|secures|stops)\b",
    re.IGNORECASE,
)

MANUFACTURER_TERMS: Set[str] = {
    "honeywell", "embraer", "collins", "safran", "boeing", "airbus",
    "recaro", "parker", "rockwell", "be aerospace", "goodrich",
}

NOMENCLATURE_TERMS: Set[str] = {
    "hinge", "bracket", "latch", "locking ring", "ring", "seat leg",
    "armrest", "ashtray", "panel", "cover", "pin", "bolt", "fastener",
    "spring", "washer", "bearing", "support rail", "rail", "buckle",
    "actuator", "switch", "valve", "hose", "connector", "clamp", "lever",
    "fitting", "tray", "protector",
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_atom_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _flatten_query_atoms(value: Any, *, prefix: str = "") -> Set[str]:
    """Flatten only populated router/query-atom values.

    Dataclass payloads contain many fields whose keys are always present even
    when their values are None, False, an empty string, or an empty list.
    Those empty keys must not become positive Engram-selection atoms.
    """
    output: Set[str] = set()
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _normalize_atom_name(raw_key)
            child_tokens = _flatten_query_atoms(
                child,
                prefix=key or prefix,
            )
            if not child_tokens:
                continue
            if key:
                output.add(key)
                if prefix:
                    output.add(
                        _normalize_atom_name(prefix + "_" + key)
                    )
            output.update(child_tokens)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            output.update(
                _flatten_query_atoms(child, prefix=prefix)
            )
    elif isinstance(value, bool):
        if value and prefix:
            output.add(_normalize_atom_name(prefix))
    elif value not in (None, ""):
        text = str(value).strip().lower()
        if not text:
            return output
        if prefix:
            output.add(_normalize_atom_name(prefix))
        output.add(_normalize_atom_name(text))
        for part in re.split(r"[^a-z0-9]+", text):
            if part:
                output.add(_normalize_atom_name(part))
    return {item for item in output if item}


def infer_query_atoms(
    query: str,
    *,
    route: str = "",
    query_atoms: Optional[Mapping[str, Any]] = None,
) -> Set[str]:
    """Infer only broad skill-selection atoms; this is not source extraction."""
    text = str(query or "").strip()
    lower = text.lower()
    atoms = _flatten_query_atoms(query_atoms or {})

    route_atom = _normalize_atom_name(route)
    if route_atom:
        atoms.add(route_atom)
        atoms.add("route_" + route_atom)

    has_identifier = bool(_IDENTIFIER_RE.search(text))
    has_prefix = bool(_PREFIX_RE.search(text))
    has_contains = bool(_CONTAINS_RE.search(text))
    has_ata = bool(_ATA_RE.search(text) or _SIMPLE_ATA_RE.search(text))
    explicit_ata_context = bool(
        has_ata
        and re.search(r"\b(?:ata|manual|chapter|system)\b", lower)
    )
    has_manufacturer = any(term in lower for term in MANUFACTURER_TERMS)
    has_nomenclature = any(term in lower for term in NOMENCLATURE_TERMS)
    has_function = bool(_FUNCTION_RE.search(text))

    if has_prefix:
        atoms.update({"partial_identifier", "partial_identifier_prefix"})
    if has_contains:
        atoms.update({"partial_identifier", "partial_identifier_contains"})
    if has_identifier:
        atoms.add("identifier")
        if not has_prefix and not has_contains and not explicit_ata_context:
            atoms.add("exact_identifier")
    if has_ata:
        atoms.update({"ata", "ata_constraint"})
    if has_manufacturer:
        atoms.update({"manufacturer", "manufacturer_constraint"})
    if has_nomenclature:
        atoms.update({"nomenclature", "component_description"})
    if has_function:
        atoms.update({"function", "functional_description"})

    if (
        _EXACT_CUE_RE.search(text)
        and has_identifier
        and not has_prefix
        and not has_contains
        and not explicit_ata_context
    ):
        atoms.add("exact_lookup_intent")
    if re.search(r"\bwhere\b|\blisted\b|\bappear\b|\bpage\b|\bmanual\b", lower):
        atoms.add("location_intent")
    if re.search(r"\bonly know\b|\bonly remember\b|\bdo not know\b|\bcannot remember\b|\bnot sure\b", lower):
        atoms.add("low_context")
    return atoms


def _validate_string_list(
    errors: List[str],
    card: Mapping[str, Any],
    field: str,
    *,
    minimum: int = 1,
) -> None:
    values = _as_string_list(card.get(field))
    if len(values) < minimum:
        errors.append(f"{field}_count:{len(values)}<{minimum}")


def validate_skill_card(card: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    skill_id = str(card.get("skill_id") or "unknown")

    for field in REQUIRED_CARD_FIELDS:
        if field not in card:
            errors.append(f"missing_field:{field}")

    if not re.fullmatch(r"[a-z][a-z0-9_]{2,80}", skill_id):
        errors.append("invalid_skill_id")

    layers = set(_as_string_list(card.get("memory_layers")))
    if not layers:
        errors.append("memory_layers_empty")
    bad_layers = sorted(layers - PERSISTED_MEMORY_LAYERS)
    if bad_layers:
        errors.append("invalid_memory_layers:" + ",".join(bad_layers))
    if "working_memory" in layers:
        errors.append("persisted_working_memory_forbidden")

    for field in (
        "applies_when",
        "does_not_apply_when",
        "required_first_searches",
        "allowed_tunnels",
        "forbidden_tunnels",
        "ranking_policy",
        "answer_requirements",
        "follow_up_policy",
    ):
        _validate_string_list(errors, card, field)

    _validate_string_list(errors, card, "positive_examples", minimum=5)
    _validate_string_list(errors, card, "negative_examples", minimum=3)
    _validate_string_list(errors, card, "known_failure_lessons", minimum=3)

    selection = card.get("selection")
    if not isinstance(selection, Mapping):
        errors.append("selection_not_object")
    else:
        routes = _as_string_list(selection.get("primary_routes"))
        required_any = _as_string_list(selection.get("required_any_atoms"))
        trigger_terms = _as_string_list(selection.get("trigger_terms"))
        if not (routes or required_any or trigger_terms):
            errors.append("selection_has_no_trigger")
        priority = selection.get("priority", 0)
        if not isinstance(priority, int):
            errors.append("selection_priority_not_int")

    for field in ("evidence_sufficiency", "answer_mode_rules"):
        if not isinstance(card.get(field), Mapping):
            errors.append(f"{field}_not_object")

    safety = card.get("safety_contract")
    if not isinstance(safety, Mapping):
        errors.append("safety_contract_not_object")
    else:
        if safety.get("engram_guidance_only") is not True:
            errors.append("engram_guidance_only_not_true")
        for field in (
            "answer_permission",
            "source_truth_mutation_allowed",
            "can_be_used_as_proof",
            "retrieval_execution_allowed",
            "postgres_write_attempt",
            "qdrant_write_attempt",
            "opensearch_write_attempt",
        ):
            if safety.get(field) is not False:
                errors.append(f"unsafe_safety_field:{field}")

    if not str(card.get("reasoning_goal") or "").strip():
        errors.append("reasoning_goal_empty")
    return [f"{skill_id}:{error}" for error in errors]


def validate_skill_library(
    library: Mapping[str, Any],
    *,
    min_cards: int = 5,
    max_cards: int = 40,
) -> Dict[str, Any]:
    cards = library.get("skill_cards")
    if not isinstance(cards, list):
        cards = []

    errors: List[str] = []
    if str(library.get("module") or "") != MODULE:
        errors.append("library_module_mismatch")
    if str(library.get("version") or "") != VERSION:
        errors.append("library_version_mismatch")
    if len(cards) < min_cards:
        errors.append(f"skill_card_count:{len(cards)}<{min_cards}")
    if len(cards) > max_cards:
        errors.append(f"skill_card_count:{len(cards)}>{max_cards}")

    seen: Set[str] = set()
    for raw in cards:
        if not isinstance(raw, Mapping):
            errors.append("skill_card_not_object")
            continue
        skill_id = str(raw.get("skill_id") or "")
        if skill_id in seen:
            errors.append(f"duplicate_skill_id:{skill_id}")
        seen.add(skill_id)
        errors.extend(validate_skill_card(raw))

    library_safety = library.get("safety_contract")
    if not isinstance(library_safety, Mapping):
        errors.append("library_safety_contract_missing")
    else:
        for key, expected in SAFETY_CONTRACT.items():
            if library_safety.get(key) is not expected:
                errors.append(f"library_safety_mismatch:{key}")

    errors = list(dict.fromkeys(errors))
    return {
        "status": STATUS_CHECKED,
        "quality_status": "PASS" if not errors else "FAIL",
        "module": MODULE,
        "version": VERSION,
        "skill_card_count": len(cards),
        "skill_ids": sorted(seen),
        "error_count": len(errors),
        "errors": errors,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "can_be_used_as_proof": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def _selection_score(
    card: Mapping[str, Any],
    *,
    query: str,
    route: str,
    atoms: Set[str],
) -> Tuple[int, List[str]]:
    selection = card.get("selection") if isinstance(card.get("selection"), Mapping) else {}
    primary_routes = {_normalize_atom_name(v) for v in _as_string_list(selection.get("primary_routes"))}
    required_all = {_normalize_atom_name(v) for v in _as_string_list(selection.get("required_all_atoms"))}
    required_any = {_normalize_atom_name(v) for v in _as_string_list(selection.get("required_any_atoms"))}
    optional = {_normalize_atom_name(v) for v in _as_string_list(selection.get("optional_atoms"))}
    exclude = {_normalize_atom_name(v) for v in _as_string_list(selection.get("exclude_atoms"))}
    trigger_terms = [v.lower() for v in _as_string_list(selection.get("trigger_terms"))]
    priority = int(selection.get("priority") or 0)

    if exclude & atoms:
        return -1, ["excluded_by_atom:" + ",".join(sorted(exclude & atoms))]
    if required_all and not required_all.issubset(atoms):
        return -1, ["missing_required_all:" + ",".join(sorted(required_all - atoms))]
    if required_any and not (required_any & atoms):
        return -1, ["missing_required_any:" + ",".join(sorted(required_any))]

    normalized_route = _normalize_atom_name(route)
    score = priority
    reasons: List[str] = [f"priority:{priority}"]

    if normalized_route and normalized_route in primary_routes:
        score += 100
        reasons.append("route_match")
    matched_required = sorted(required_any & atoms)
    if matched_required:
        score += 50 + 5 * len(matched_required)
        reasons.append("required_atoms:" + ",".join(matched_required))
    matched_optional = sorted(optional & atoms)
    if matched_optional:
        score += 10 * len(matched_optional)
        reasons.append("optional_atoms:" + ",".join(matched_optional))

    lower = str(query or "").lower()
    matched_terms = sorted({term for term in trigger_terms if term and term in lower})
    if matched_terms:
        score += min(30, 5 * len(matched_terms))
        reasons.append("trigger_terms:" + ",".join(matched_terms[:6]))

    if score <= priority and not (matched_required or matched_optional or matched_terms):
        return -1, ["no_positive_match"]
    return score, reasons


def select_engram_skills(
    library: Mapping[str, Any],
    *,
    query: str,
    route: str = "",
    query_atoms: Optional[Mapping[str, Any]] = None,
    max_skills: int = 5,
    min_score: int = 1,
) -> Dict[str, Any]:
    validation = validate_skill_library(library)
    if validation.get("quality_status") != "PASS":
        return {
            "status": STATUS_SELECTED,
            "quality_status": "FAIL",
            "selection_error": "skill_library_failed_validation",
            "library_validation": validation,
            "selected_skill_count": 0,
            "selected_skill_ids": [],
            "selected_skills": [],
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "can_be_used_as_proof": False,
            "write_attempt_count": 0,
            "safety_contract": dict(SAFETY_CONTRACT),
        }

    limit = max(1, min(5, int(max_skills or 5)))
    atoms = infer_query_atoms(query, route=route, query_atoms=query_atoms)
    ranked: List[Dict[str, Any]] = []

    for raw in library.get("skill_cards", []):
        if not isinstance(raw, Mapping):
            continue
        score, reasons = _selection_score(raw, query=query, route=route, atoms=atoms)
        if score < min_score:
            continue
        ranked.append(
            {
                "skill_id": str(raw.get("skill_id")),
                "title": str(raw.get("title")),
                "score": score,
                "score_reasons": reasons,
                "memory_layers": _as_string_list(raw.get("memory_layers")),
                "reasoning_goal": str(raw.get("reasoning_goal") or ""),
                "answer_mode_rules": dict(raw.get("answer_mode_rules") or {}),
                "safety_contract": dict(raw.get("safety_contract") or {}),
            }
        )

    ranked.sort(key=lambda item: (-int(item["score"]), str(item["skill_id"])))
    selected = ranked[:limit]
    return {
        "status": STATUS_SELECTED,
        "quality_status": "PASS",
        "module": MODULE,
        "version": VERSION,
        "query": str(query or ""),
        "route": str(route or ""),
        "inferred_query_atoms": sorted(atoms),
        "max_skills": limit,
        "candidate_skill_count": len(ranked),
        "selected_skill_count": len(selected),
        "selected_skill_ids": [item["skill_id"] for item in selected],
        "selected_skills": selected,
        "engram_guidance_only": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "can_be_used_as_proof": False,
        "retrieval_execution_allowed": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def load_and_validate_skill_library(path: str | Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    library = load_json(path)
    if not isinstance(library, Mapping):
        library = {}
    manifest = dict(library)
    return manifest, validate_skill_library(manifest)
