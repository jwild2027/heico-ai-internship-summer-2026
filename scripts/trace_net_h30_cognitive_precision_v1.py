#!/usr/bin/env python3
"""Precision and behavior-memory helpers for TRACE-Net H30 cognitive routing.

This module is read-only. Engram atoms are behavior guidance only and never
source-truth evidence, answer permission, or authority.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from scripts.trace_net_h30_engram_canonical_registry_v1 import (
    load_canonical_registry,
    resolve_atom_inheritance,
)

PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b", re.I)
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*")
DEFAULT_ENGRAM_PATHS = (
    Path(
        "local_data/organization/trace_net/engineering_engram_memory_layers_v1/"
        "trace_net_engineering_engram_memory_layers_v1.json"
    ),
    Path(
        "local_data/organization/trace_net/cognitive_openwebui_regression_engram_v1/"
        "trace_net_cognitive_openwebui_regression_engram_v1.json"
    ),
    Path(
        "local_data/organization/trace_net/cognitive_openwebui_regression_engram_v2/"
        "trace_net_cognitive_openwebui_regression_engram_v2.json"
    ),
)
PART_FRAGMENT_STOPWORDS = {
    "A", "AN", "AND", "ARE", "AS", "AT", "BE", "BY", "CONTAIN", "CONTAINS",
    "DOCUMENT", "EVIDENCE", "FOR", "FROM", "IN", "IS", "IT", "MANUAL", "OF",
    "ON", "OR", "PAGE", "PART", "SOURCE", "STRONGEST", "THE", "THIS", "TO",
    "VALUE", "WHAT", "WHERE", "WHICH", "WITH",
}
KNOWN_ALPHA_PART_PREFIXES = {"NAS", "BAC", "MIL", "MS", "AN"}


def _phrase_regex(phrase: str) -> re.Pattern[str]:
    pieces = [re.escape(piece) for piece in str(phrase or "").strip().split() if piece]
    if not pieces:
        return re.compile(r"(?!x)x")
    return re.compile(
        r"(?<![A-Za-z0-9])" + r"\s+".join(pieces) + r"(?![A-Za-z0-9])",
        re.I,
    )


def has_phrase(text: str, phrase: str) -> bool:
    return bool(_phrase_regex(phrase).search(str(text or "")))


def has_any_phrase(text: str, phrases: Iterable[str]) -> bool:
    return any(has_phrase(text, phrase) for phrase in phrases)


def valid_identifier_fragment(value: str) -> bool:
    raw = str(value or "").strip(".,;:()[]{} ").upper()
    normalized = re.sub(r"[^A-Z0-9]", "", raw)
    if not (2 <= len(normalized) <= 16):
        return False
    if normalized in KNOWN_ALPHA_PART_PREFIXES:
        return True
    if normalized in PART_FRAGMENT_STOPWORDS:
        return False
    # Most partial aviation identifiers contain a digit. A small explicit
    # allow-list supports standard-family prefixes such as NAS without
    # accepting arbitrary prose words as part-number clues.
    return any(character.isdigit() for character in normalized)


def explicit_semantic_intent(text: str) -> bool:
    phrases = (
        "find pages about",
        "pages about",
        "documents about",
        "manual sections about",
        "pages on",
        "documents related to",
        "even when the exact phrase is not used",
        "semantic search",
        "conceptually related",
        "topic about",
        "topic related to",
    )
    return has_any_phrase(text, phrases)


def row_part_numbers(row: Mapping[str, Any]) -> set[str]:
    try:
        blob = json.dumps(dict(row), ensure_ascii=False, sort_keys=True)
    except Exception:
        blob = str(row)
    return {value.upper() for value in PART_RE.findall(blob)}


def filter_entity_consistent(
    rows: Sequence[Mapping[str, Any]],
    requested_parts: Sequence[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    requested = {value.upper() for value in requested_parts if value}
    if not requested:
        return [dict(row) for row in rows], []
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        observed = row_part_numbers(row)
        # Rows with no explicit identifier can still be useful context. Rows that
        # explicitly name only different identifiers are irrelevant and removed.
        if observed and not observed.intersection(requested):
            row["entity_gate_reason"] = "explicit_part_number_mismatch"
            row["requested_part_numbers"] = sorted(requested)
            row["observed_part_numbers"] = sorted(observed)
            dropped.append(row)
        else:
            kept.append(row)
    return kept, dropped


def _atom_value(atoms: Any, name: str, default: Any) -> Any:
    if isinstance(atoms, Mapping):
        return atoms.get(name, default)
    return getattr(atoms, name, default)


def decompose_claim_queries(query: str, atoms: Any, maximum: int = 6) -> List[str]:
    exact_parts = list(_atom_value(atoms, "exact_part_numbers", []) or [])
    items = list(_atom_value(atoms, "items", []) or [])
    requested_claims = set(_atom_value(atoms, "requested_claims", []) or [])
    primary = exact_parts[0] if exact_parts else "the requested component"
    parts_text = " and ".join(exact_parts[:2]) if exact_parts else primary
    queries: List[str] = []

    if "exact_identifier" in requested_claims:
        queries.append(f"Find exact citation-ready source evidence for part {primary}")
    if "nomenclature" in requested_claims:
        queries.append(f"Find citation-ready nomenclature or component-name evidence for part {primary}")
    if "table_value" in requested_claims:
        target = f"item {items[0]}" if items else f"part {primary}"
        queries.append(f"Search the illustrated parts list table for {target}")
    if "visual_identity" in requested_claims:
        queries.append(f"Find the figure, drawing, diagram, or callout for part {primary}")
    if "relationship" in requested_claims:
        queries.append(f"Find the parent assembly and typed relationships for part {primary}")
    if "procedure" in requested_claims:
        queries.append(f"Find the documented procedure requested for {primary}")
    if "warning" in requested_claims:
        queries.append(f"Find warnings, cautions, and notes connected to {primary}")
    if "comparison" in requested_claims:
        queries.append(f"Compare source-backed records for {parts_text}")
    if "authority" in requested_claims:
        queries.append(
            f"Find only explicit approval, effectivity, applicability, eligibility, "
            f"interchangeability, or installation-authority evidence for {parts_text}"
        )

    if not queries:
        queries.append(str(query or "").strip())
    deduped: List[str] = []
    seen = set()
    for item in queries:
        key = re.sub(r"\s+", " ", item).strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[: max(1, maximum)]


def specialized_route_queries(route: str, query: str, atoms: Any, maximum: int = 3) -> List[str]:
    exact_parts = list(_atom_value(atoms, "exact_part_numbers", []) or [])
    items = list(_atom_value(atoms, "items", []) or [])
    primary = exact_parts[0] if exact_parts else "the requested component"
    original = str(query or "").strip()
    targets: Dict[str, List[str]] = {
        "exact_table_ipl_lookup": [
            original,
            f"Search table rows and cells in the illustrated parts list for "
            + (f"item {items[0]}" if items else f"part {primary}"),
            f"Resolve the IPL row for {primary} to citation-ready source fields",
        ],
        "procedure_task_lookup": [
            original,
            f"Find the source procedure section and ordered removal or installation steps for {primary}",
        ],
        "warning_caution_note_lookup": [
            original,
            f"Find source warning, caution, note, precaution, and task-context blocks for {primary}",
        ],
        "contradiction_resolution": [
            original,
            "Find each conflicting source value with revision, page, field, and effectivity context",
        ],
        "ocr_scan_recovery": [
            original,
            f"Run source OCR recovery and visual cross-check for {primary}, preserving uncertainty",
        ],
        "high_degree_entity_aggregation": [
            original,
            f"Aggregate every source-backed page and document reference for {primary} with coverage metadata",
        ],
        "cross_source_comparison": [
            original,
            f"Compare source-backed records for {primary} while keeping documents and revisions separate",
        ],
    }
    values = targets.get(route, [original])
    output: List[str] = []
    seen = set()
    for value in values:
        key = re.sub(r"\s+", " ", value).strip().lower()
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output[: max(1, maximum)]


@lru_cache(maxsize=8)
def load_engram(path_text: str) -> Dict[str, Any]:
    path = Path(path_text)
    if not path.is_file():
        return {
            "quality_status": "WARN",
            "path": str(path),
            "memory_atoms": [],
            "error": "engram_file_not_found",
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "quality_status": "WARN",
            "path": str(path),
            "memory_atoms": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    atoms = value.get("memory_atoms") if isinstance(value, Mapping) else []
    return {
        "quality_status": "PASS" if isinstance(atoms, list) else "WARN",
        "path": str(path),
        "memory_atoms": atoms if isinstance(atoms, list) else [],
        "version": value.get("version") if isinstance(value, Mapping) else None,
    }


def select_engram_memory(
    query: str,
    route: str,
    requested_claims: Sequence[str],
    *,
    path: str | None = None,
    registry_path: str | None = None,
    maximum_atoms: int = 6,
) -> Dict[str, Any]:
    configured = (
        path
        or os.environ.get("TRACE_NET_COGNITIVE_ENGRAM_PATHS")
        or os.environ.get("TRACE_NET_COGNITIVE_ENGRAM_PATH")
    )
    path_values = (
        [
            value
            for value in str(configured).split(os.pathsep)
            if value
        ]
        if configured
        else [str(value) for value in DEFAULT_ENGRAM_PATHS]
    )
    loaded_packs = [load_engram(value) for value in path_values]
    registry = load_canonical_registry(registry_path)

    all_atoms: List[Any] = []
    load_errors: List[str] = []
    for pack in loaded_packs:
        all_atoms.extend(pack.get("memory_atoms", []))
        if pack.get("error"):
            load_errors.append(
                f"{pack.get('path')}: {pack.get('error')}"
            )

    query_text = str(query or "")
    query_tokens = {
        token.lower()
        for token in TOKEN_RE.findall(query_text)
    }
    claim_set = {str(value) for value in requested_claims}
    scored: List[Tuple[int, str, Dict[str, Any]]] = []
    unresolved_inheritance: List[Dict[str, Any]] = []

    for raw in all_atoms:
        if (
            not isinstance(raw, Mapping)
            or raw.get("activation_status", "active") != "active"
        ):
            continue
        atom = dict(raw)
        declared = [
            str(value)
            for value in atom.get("inherits", [])
            if value
        ] if isinstance(atom.get("inherits"), list) else []
        if declared:
            resolved = resolve_atom_inheritance(atom, registry)
            missing = resolved.get("unresolved_inheritance", [])
            if missing:
                for rule_id in missing:
                    unresolved_inheritance.append({
                        "atom_id": atom.get("atom_id"),
                        "canonical_rule_id": rule_id,
                    })
                # Fail closed: an incomplete inherited policy does not
                # participate in route or answer behavior.
                continue

        score = 0
        routes = {
            str(value)
            for value in atom.get("routes", [])
            if value
        }
        claims = {
            str(value)
            for value in atom.get("claims", [])
            if value
        }
        trigger_values = atom.get("triggers")
        if not isinstance(trigger_values, list):
            trigger_values = atom.get("trigger", [])
        triggers = [
            str(value)
            for value in trigger_values
            if value
        ]
        if route in routes:
            score += 8
        score += 4 * len(claim_set.intersection(claims))
        for trigger in triggers:
            if has_phrase(query_text, trigger):
                score += 5
            elif trigger.lower() in query_tokens:
                score += 2
        if atom.get("universal"):
            score += 1
        if score > 0:
            scored.append((
                score,
                str(atom.get("atom_id") or ""),
                atom,
            ))

    scored.sort(key=lambda item: (-item[0], item[1]))

    deduplicated: List[Tuple[int, str, Dict[str, Any]]] = []
    seen_rule_ids = set()
    duplicate_atom_count = 0
    duplicate_rule_reference_count = 0

    for score, atom_id, atom in scored:
        declared = [
            str(value)
            for value in atom.get("inherits", [])
            if value
        ] if isinstance(atom.get("inherits"), list) else []

        if declared:
            new_rule_ids = [
                rule_id
                for rule_id in declared
                if rule_id not in seen_rule_ids
            ]
            duplicate_rule_reference_count += (
                len(declared) - len(new_rule_ids)
            )
            if not new_rule_ids and not atom.get("policy_effects"):
                duplicate_atom_count += 1
                continue
            resolved = resolve_atom_inheritance(
                atom,
                registry,
                include_rule_ids=new_rule_ids,
            )
            if resolved.get("unresolved_inheritance"):
                duplicate_atom_count += 1
                continue
            seen_rule_ids.update(new_rule_ids)
        else:
            canonical_rule_id = str(
                atom.get("canonical_rule_id")
                or atom.get("atom_id")
                or atom_id
            )
            if canonical_rule_id in seen_rule_ids:
                duplicate_atom_count += 1
                duplicate_rule_reference_count += 1
                continue
            seen_rule_ids.add(canonical_rule_id)
            resolved = resolve_atom_inheritance(atom, registry)

        deduplicated.append((score, atom_id, resolved))

    selected = [
        item[2]
        for item in deduplicated[: max(1, maximum_atoms)]
    ]

    compact_atoms = []
    # This metric tracks only rules actually resolved through the canonical
    # registry. Selected legacy/local atoms remain visible in atom_ids but do
    # not inflate resolved_rule_count.
    selected_rule_ids: List[str] = []
    for atom in selected:
        inherited_rule_ids = list(
            atom.get("inherited_rule_ids", [])
        )
        if inherited_rule_ids:
            selected_rule_ids.extend(inherited_rule_ids)

        compact_atoms.append({
            "atom_id": atom.get("atom_id"),
            "canonical_rule_id": (
                atom.get("canonical_rule_id")
                or atom.get("atom_id")
            ),
            "declared_inherits": atom.get(
                "declared_inherits", []
            ),
            "inherited_rule_ids": inherited_rule_ids,
            "resolved_rules": atom.get("resolved_rules", []),
            "memory_layer": atom.get("memory_layer"),
            "title": atom.get("title"),
            "route_context": atom.get("route_context"),
            "rule": atom.get("rule"),
            "examples": (
                atom.get("examples", [])[:2]
                if isinstance(atom.get("examples"), list)
                else []
            ),
            "policy_effects": atom.get("policy_effects", {}),
            "proof_role": "guidance_only",
            "source": atom.get("source"),
        })

    registry_ok = registry.get("quality_status") == "PASS"
    quality_status = (
        "PASS"
        if all_atoms
        and registry_ok
        and not unresolved_inheritance
        else "WARN"
    )

    return {
        "quality_status": quality_status,
        "paths": path_values,
        "loaded_atom_count": len(all_atoms),
        "load_errors": load_errors,
        "registry_path": registry.get("path"),
        "registry_quality_status": registry.get(
            "quality_status"
        ),
        "canonical_registry_rule_count": registry.get(
            "canonical_rule_count", 0
        ),
        "registry_duplicate_rule_id_count": registry.get(
            "duplicate_rule_id_count", 0
        ),
        "registry_duplicate_meaning_count": registry.get(
            "duplicate_normalized_meaning_count", 0
        ),
        "unresolved_inheritance": unresolved_inheritance,
        "unresolved_inheritance_count": len(
            unresolved_inheritance
        ),
        "scored_atom_count": len(scored),
        "deduplicated_rule_count": len(seen_rule_ids),
        "duplicate_atom_count": duplicate_atom_count,
        "duplicate_rule_reference_count": (
            duplicate_rule_reference_count
        ),
        "resolved_rule_count": len(
            set(selected_rule_ids)
        ),
        "resolved_rule_ids": list(
            dict.fromkeys(selected_rule_ids)
        ),
        "atom_count": len(compact_atoms),
        "atom_ids": [
            atom.get("atom_id")
            for atom in compact_atoms
        ],
        "memory_layers": list(dict.fromkeys(
            atom.get("memory_layer")
            for atom in compact_atoms
        )),
        "atoms": compact_atoms,
        "proof_role": "guidance_only",
        "citable": False,
        "answer_permission": False,
        "source_truth": False,
    }
