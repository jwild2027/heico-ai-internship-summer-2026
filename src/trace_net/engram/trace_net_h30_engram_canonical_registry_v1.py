#!/usr/bin/env python3
"""Canonical Engram rule registry and inheritance resolver.

The registry stores each reusable behavior lesson once. Route and episodic
Engram atoms may inherit one or more canonical rules. Resolution is read-only
and produces behavior policy only; it never executes retrieval, grants answer
permission, or becomes source evidence.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

MODULE = "trace_net_h30_engram_canonical_registry_v1"
DEFAULT_REGISTRY_PATH = Path(
    "local_data/organization/trace_net/"
    "engram_canonical_rule_registry_v1/"
    "trace_net_engram_canonical_rule_registry_v1.json"
)


def _normalized_meaning(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        str(value or "").lower(),
    ).strip()


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _merge_unique(left: Sequence[Any], right: Sequence[Any]) -> List[Any]:
    output: List[Any] = []
    seen = set()
    for value in list(left) + list(right):
        marker = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if marker in seen:
            continue
        seen.add(marker)
        output.append(value)
    return output


def merge_policy_effects(
    base: Mapping[str, Any] | None,
    addition: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    """Merge allowlisted-policy-shaped data without executing it."""
    output: Dict[str, Any] = dict(base or {})
    for key, value in dict(addition or {}).items():
        current = output.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            output[key] = merge_policy_effects(current, value)
        elif isinstance(current, list) and isinstance(value, list):
            output[key] = _merge_unique(current, value)
        elif isinstance(current, bool) and isinstance(value, bool):
            output[key] = current or value
        elif current in (None, "", [], {}):
            output[key] = value
        elif current == value:
            output[key] = current
        else:
            # Inheritance order is deterministic. The first rule owns scalar
            # strategy choices; later rules may add lists and true flags.
            output[key] = current
    return output


def validate_registry(
    value: Mapping[str, Any],
) -> Dict[str, Any]:
    errors: List[str] = []
    rules = value.get("canonical_rules", [])
    if not isinstance(rules, list):
        errors.append("canonical_rules must be a list")
        rules = []

    rules_by_id: Dict[str, Dict[str, Any]] = {}
    duplicate_rule_ids: List[str] = []
    meaning_to_ids: Dict[str, List[str]] = {}

    for index, raw in enumerate(rules):
        if not isinstance(raw, Mapping):
            errors.append(f"canonical rule {index} is not an object")
            continue
        rule = dict(raw)
        rule_id = str(rule.get("canonical_rule_id") or "").strip()
        if not rule_id:
            errors.append(f"canonical rule {index} missing canonical_rule_id")
            continue
        if rule_id in rules_by_id:
            duplicate_rule_ids.append(rule_id)
            continue
        rules_by_id[rule_id] = rule

        for field in (
            "title",
            "memory_layer",
            "rule",
            "allowed_behavior",
            "forbidden_behavior",
        ):
            if not str(rule.get(field) or "").strip():
                errors.append(f"canonical rule {rule_id} missing {field}")

        if rule.get("proof_role") != "guidance_only":
            errors.append(
                f"canonical rule {rule_id} must be guidance_only"
            )
        if rule.get("answer_permission") is True:
            errors.append(
                f"canonical rule {rule_id} grants answer permission"
            )
        if rule.get("source_truth") is True:
            errors.append(
                f"canonical rule {rule_id} claims source truth"
            )
        if rule.get("source_truth_mutation_allowed") is True:
            errors.append(
                f"canonical rule {rule_id} permits source mutation"
            )
        if not isinstance(rule.get("policy_effects", {}), Mapping):
            errors.append(
                f"canonical rule {rule_id} policy_effects is not an object"
            )

        meaning = _normalized_meaning(rule.get("rule"))
        if meaning:
            meaning_to_ids.setdefault(meaning, []).append(rule_id)

    duplicate_meaning_groups = [
        ids
        for ids in meaning_to_ids.values()
        if len(ids) > 1
    ]
    if duplicate_rule_ids:
        errors.append(
            "duplicate canonical_rule_id values: "
            + ", ".join(sorted(set(duplicate_rule_ids)))
        )
    if duplicate_meaning_groups:
        errors.append(
            "duplicate normalized rule meanings: "
            + "; ".join(",".join(ids) for ids in duplicate_meaning_groups)
        )

    return {
        "quality_status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "canonical_rule_count": len(rules_by_id),
        "rules_by_id": rules_by_id,
        "duplicate_rule_ids": sorted(set(duplicate_rule_ids)),
        "duplicate_meaning_groups": duplicate_meaning_groups,
        "duplicate_rule_id_count": len(set(duplicate_rule_ids)),
        "duplicate_normalized_meaning_count": len(
            duplicate_meaning_groups
        ),
        "answer_permission": False,
        "source_truth": False,
        "source_truth_mutation_allowed": False,
    }


@lru_cache(maxsize=8)
def load_canonical_registry(
    path_text: str | None = None,
) -> Dict[str, Any]:
    configured = (
        path_text
        or os.environ.get(
            "TRACE_NET_COGNITIVE_ENGRAM_RULE_REGISTRY_PATH"
        )
        or str(DEFAULT_REGISTRY_PATH)
    )
    path = Path(configured)
    if not path.is_file():
        return {
            "quality_status": "WARN",
            "path": str(path),
            "errors": ["canonical_registry_file_not_found"],
            "canonical_rule_count": 0,
            "rules_by_id": {},
            "duplicate_rule_id_count": 0,
            "duplicate_normalized_meaning_count": 0,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "quality_status": "WARN",
            "path": str(path),
            "errors": [f"{type(exc).__name__}: {exc}"],
            "canonical_rule_count": 0,
            "rules_by_id": {},
            "duplicate_rule_id_count": 0,
            "duplicate_normalized_meaning_count": 0,
        }
    if not isinstance(value, Mapping):
        return {
            "quality_status": "FAIL",
            "path": str(path),
            "errors": ["canonical registry root must be an object"],
            "canonical_rule_count": 0,
            "rules_by_id": {},
            "duplicate_rule_id_count": 0,
            "duplicate_normalized_meaning_count": 0,
        }
    result = validate_registry(value)
    result.update({
        "path": str(path),
        "module": value.get("module"),
        "version": value.get("version"),
    })
    return result


def resolve_atom_inheritance(
    atom: Mapping[str, Any],
    registry_result: Mapping[str, Any],
    *,
    include_rule_ids: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Resolve one atom's inherited rules into a runtime memory record."""
    output = dict(atom)
    rules_by_id = (
        registry_result.get("rules_by_id", {})
        if isinstance(registry_result.get("rules_by_id"), Mapping)
        else {}
    )
    declared = [
        str(value)
        for value in _as_list(atom.get("inherits"))
        if value
    ]
    include = (
        {str(value) for value in include_rule_ids if value}
        if include_rule_ids is not None
        else None
    )
    target_ids = [
        rule_id
        for rule_id in declared
        if include is None or rule_id in include
    ]

    unresolved: List[str] = []
    resolved_rules: List[Dict[str, Any]] = []
    effects: Dict[str, Any] = {}

    for rule_id in target_ids:
        raw_rule = rules_by_id.get(rule_id)
        if not isinstance(raw_rule, Mapping):
            unresolved.append(rule_id)
            continue
        rule = dict(raw_rule)
        resolved_rules.append({
            "canonical_rule_id": rule_id,
            "title": rule.get("title"),
            "memory_layer": rule.get("memory_layer"),
            "rule": rule.get("rule"),
            "allowed_behavior": rule.get("allowed_behavior"),
            "forbidden_behavior": rule.get("forbidden_behavior"),
            "proof_role": "guidance_only",
        })
        effects = merge_policy_effects(
            effects,
            rule.get("policy_effects", {}),
        )

    local_effects = atom.get("policy_effects", {})
    if isinstance(local_effects, Mapping):
        effects = merge_policy_effects(effects, local_effects)

    if declared:
        combined_rule = " ".join(
            str(rule.get("rule") or "").strip()
            for rule in resolved_rules
            if str(rule.get("rule") or "").strip()
        )
        output["rule"] = combined_rule
        output["canonical_rule_id"] = (
            target_ids[0]
            if target_ids
            else declared[0]
        )
    else:
        output["canonical_rule_id"] = str(
            atom.get("canonical_rule_id")
            or atom.get("atom_id")
            or ""
        )

    output["declared_inherits"] = declared
    output["inherited_rule_ids"] = [
        str(rule.get("canonical_rule_id"))
        for rule in resolved_rules
    ]
    output["resolved_rules"] = resolved_rules
    output["unresolved_inheritance"] = unresolved
    output["policy_effects"] = effects
    output["proof_role"] = "guidance_only"
    output["citable"] = False
    output["answer_permission"] = False
    output["source_truth"] = False
    return output


def check_pack_inheritance(
    pack: Mapping[str, Any],
    registry_result: Mapping[str, Any],
) -> Dict[str, Any]:
    atoms = pack.get("memory_atoms", [])
    if not isinstance(atoms, list):
        atoms = []
    unresolved: List[Dict[str, Any]] = []
    inherited_reference_count = 0
    local_policy_effect_count = 0
    local_rule_text_count = 0

    for raw in atoms:
        if not isinstance(raw, Mapping):
            continue
        inherits = [
            str(value)
            for value in _as_list(raw.get("inherits"))
            if value
        ]
        inherited_reference_count += len(inherits)
        resolved = resolve_atom_inheritance(raw, registry_result)
        for rule_id in resolved.get("unresolved_inheritance", []):
            unresolved.append({
                "atom_id": raw.get("atom_id"),
                "canonical_rule_id": rule_id,
            })
        if raw.get("policy_effects"):
            local_policy_effect_count += 1
        if str(raw.get("rule") or "").strip():
            local_rule_text_count += 1

    return {
        "quality_status": "PASS" if not unresolved else "FAIL",
        "atom_count": len(atoms),
        "inherited_reference_count": inherited_reference_count,
        "unresolved_inheritance": unresolved,
        "unresolved_inheritance_count": len(unresolved),
        "local_policy_effect_count": local_policy_effect_count,
        "local_rule_text_count": local_rule_text_count,
    }


def write_quality_check(
    registry_path: str | Path,
    output_path: str | Path | None = None,
) -> Dict[str, Any]:
    path = Path(registry_path)
    result = load_canonical_registry(str(path))
    payload = {
        "status": "TRACE_NET_ENGRAM_CANONICAL_RULE_REGISTRY_CHECKED",
        "module": MODULE,
        "version": result.get("version"),
        "quality_status": result.get("quality_status"),
        "checked_path": str(path),
        "summary": {
            "canonical_rule_count": result.get(
                "canonical_rule_count", 0
            ),
            "duplicate_rule_id_count": result.get(
                "duplicate_rule_id_count", 0
            ),
            "duplicate_normalized_meaning_count": result.get(
                "duplicate_normalized_meaning_count", 0
            ),
            "answer_permission_count": 0,
            "source_truth_count": 0,
            "write_attempt_count": 0,
        },
        "quality_errors": list(result.get("errors", [])),
        "safety_contract": (
            "behavior_guidance_only_no_source_truth_"
            "no_answer_permission_no_db_writes"
        ),
    }
    destination = (
        Path(output_path)
        if output_path is not None
        else path.with_name(
            "trace_net_engram_canonical_rule_registry_v1_"
            "quality_check.json"
        )
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload
