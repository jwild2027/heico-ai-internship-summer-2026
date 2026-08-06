"""TRACE-Net H30 final Engram rollout: roadmap Phases 6 through 10.

Phase 6: information-gain follow-up selection.
Phase 7: typed-evidence and answer-mode Self-RAG critic.
Phase 8: one-pass bounded deterministic CRAG-compatible answer repair.
Phase 9: benchmark contract hooks and quality metadata.
Phase 10: broad response-behavior rollout across all five Engram skill cards.

This module wraps only the final Gemma-facing runtime result. It does not choose
routes, execute tools, select evidence, broaden retrieval, grant answer
permission, or mutate source truth.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from src.trace_net.writing.trace_net_h30_evidence_aware_answer_modes_v1 import (
    MODE_AUTHORITY_MISSING,
    MODE_CANDIDATE,
    MODE_CONFIRMED_DIRECT,
    MODE_CONFLICT,
    MODE_GENERAL_CHAT,
    MODE_NO_EVIDENCE,
    MODE_SEMANTIC,
    MODE_UPSTREAM_ERROR,
    MODE_VISUAL,
    render_deterministic_mode,
)

MODULE = "trace_net_h30_final_engram_rollout_v1"
VERSION = "v1"
STATUS = "TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_V1"

SUPPORTED_SKILL_IDS = (
    "partial_identifier_discovery",
    "exact_identifier_lookup",
    "nomenclature_function_discovery",
    "ata_plus_description_discovery",
    "manufacturer_plus_description_discovery",
)

ROUTE_SKILL_FALLBACK = {
    "guided_part_discovery": "partial_identifier_discovery",
    "exact_identifier_lookup": "exact_identifier_lookup",
    "exact_table_ipl_lookup": "exact_identifier_lookup",
    "document_page_navigation": "exact_identifier_lookup",
    "nomenclature_function_search": "nomenclature_function_discovery",
    "ata_system_discovery": "ata_plus_description_discovery",
}

TECHNICAL_NON_DIRECT_MODES = {
    MODE_CANDIDATE,
    MODE_VISUAL,
    MODE_SEMANTIC,
    MODE_CONFLICT,
    MODE_AUTHORITY_MISSING,
    MODE_NO_EVIDENCE,
}

FOLLOWUP_MARKER = "Helpful follow-up questions:"
GENERIC_FOLLOWUP_PATTERNS = (
    r"\banything else\b",
    r"\bmore information\b",
    r"\bmore details\b",
    r"\bcan you clarify\b",
    r"\btell me more\b",
)

UNSAFE_POSITIVE_PATTERNS = (
    r"\bthe part number is\b",
    r"\bis an approved replacement\b",
    r"\bis approved for\b",
    r"\bis interchangeable\b",
    r"\bsafe to install\b",
    r"\bconfirmed (?:as|identity|part)\b",
)

TOPIC_QUESTIONS = {
    "adjacent_identifier_characters": (
        "What characters come immediately before or after the known part-number fragment?"
    ),
    "manufacturer": "Who manufactured the component?",
    "ata_system": "Which ATA chapter or aircraft system is associated with it?",
    "component_function": "What does the component do?",
    "appearance": "What does the component look like?",
    "installation_location": "Where is it installed, or which assembly is it near?",
    "figure_table_item": "Do you remember a figure, table, item, or callout number?",
    "manual_revision": "Which manual and revision produced this value?",
    "exact_source_location": "Which page, figure, table, or item contains the value?",
    "authority_document": (
        "Which IPC, CMM, service bulletin, approval record, or other authority "
        "document should govern this claim?"
    ),
    "effectivity": "What aircraft, assembly, serial number, or effectivity range applies?",
    "installation_context": "What installation or replacement context must be verified?",
    "exact_identifier": "What is the complete part number or identifier?",
    "document_family": "Which manual, aircraft, assembly, or document family should be searched?",
    "requested_claim": "Are you trying to identify it, find its function, or verify approval?",
}

SKILL_TOPIC_ORDER = {
    "partial_identifier_discovery": (
        "adjacent_identifier_characters",
        "manufacturer",
        "ata_system",
        "component_function",
        "appearance",
        "figure_table_item",
    ),
    "exact_identifier_lookup": (
        "document_family",
        "exact_source_location",
        "requested_claim",
    ),
    "nomenclature_function_discovery": (
        "component_function",
        "appearance",
        "installation_location",
        "manufacturer",
        "ata_system",
        "figure_table_item",
    ),
    "ata_plus_description_discovery": (
        "component_function",
        "manufacturer",
        "exact_identifier",
        "figure_table_item",
    ),
    "manufacturer_plus_description_discovery": (
        "manufacturer",
        "component_function",
        "exact_identifier",
        "ata_system",
        "appearance",
    ),
}

MODE_TOPIC_PREFIX = {
    MODE_CONFLICT: ("manual_revision", "exact_source_location"),
    MODE_AUTHORITY_MISSING: (
        "authority_document",
        "effectivity",
        "installation_context",
    ),
    MODE_NO_EVIDENCE: (
        "exact_identifier",
        "manufacturer",
        "ata_system",
        "component_function",
    ),
}

SAFETY_CONTRACT = {
    "engram_behavior_guidance_only": True,
    "engram_is_never_evidence": True,
    "typed_evidence_controls_claim_support": True,
    "answer_mode_controls_writer_access": True,
    "followups_cannot_create_evidence": True,
    "self_rag_critic_read_only": True,
    "maximum_bounded_repairs": 1,
    "repair_can_execute_retrieval": False,
    "repair_can_select_new_evidence": False,
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
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _compact(value: Any, limit: int = 1000) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def _bool_env(
    environ: Mapping[str, str],
    name: str,
    default: bool = False,
) -> bool:
    raw = str(
        environ.get(name, "1" if default else "0")
    ).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _bounded_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def load_final_rollout_config(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    return {
        "enabled": _bool_env(
            env,
            "TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED",
            False,
        ),
        "max_followups": _bounded_int(
            env.get(
                "TRACE_NET_H30_FINAL_ENGRAM_MAX_FOLLOWUPS",
                "3",
            ),
            default=3,
            minimum=1,
            maximum=5,
        ),
        "max_repairs": _bounded_int(
            env.get(
                "TRACE_NET_H30_FINAL_ENGRAM_MAX_REPAIRS",
                "1",
            ),
            default=1,
            minimum=0,
            maximum=1,
        ),
    }


def _iter_skill_ids(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for key in (
            "skill_id",
            "id",
            "selected_skill_id",
            "primary_skill_id",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str):
                yield candidate
        for key in (
            "skills",
            "selected_skills",
            "skill_ids",
            "selected_skill_ids",
            "records",
        ):
            child = value.get(key)
            if isinstance(child, (Mapping, list, tuple)):
                yield from _iter_skill_ids(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_skill_ids(child)


def _manufacturer_known(atoms: Mapping[str, Any]) -> bool:
    for key in (
        "manufacturer",
        "manufacturer_name",
        "manufacturer_terms",
        "manufacturer_clues",
    ):
        value = atoms.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
    return False


def select_primary_skill(
    result: Mapping[str, Any],
) -> Dict[str, Any]:
    # TRACE_NET_H30_ROUTE_CONSISTENT_ENGRAM_SKILL_V1
    # The executed deterministic route owns the behavior skill for partial,
    # exact, ATA, and nomenclature requests. Manufacturer + description is the
    # intentional specialization above a nomenclature/semantic route.
    discovered: List[str] = []
    for key in (
        "engram_skill_shadow",
        "engram_memory",
        "engram_skill_selection",
        "engram_skill_planner_guidance",
    ):
        for candidate in _iter_skill_ids(result.get(key)):
            if candidate in SUPPORTED_SKILL_IDS and candidate not in discovered:
                discovered.append(candidate)

    atoms = _mapping(result.get("query_atoms"))
    route = str(result.get("route") or "")

    if _manufacturer_known(atoms) and route in {
        "nomenclature_function_search",
        "semantic_discovery",
    }:
        return {
            "skill_id": "manufacturer_plus_description_discovery",
            "selection_basis": "deterministic_manufacturer_route_override",
            "candidate_skill_ids": discovered,
        }

    route_skill = ROUTE_SKILL_FALLBACK.get(route, "")
    if route_skill:
        return {
            "skill_id": route_skill,
            "selection_basis": (
                "route_consistent_runtime_selected_engram_skill"
                if route_skill in discovered
                else "deterministic_route_skill_override"
            ),
            "candidate_skill_ids": discovered,
        }

    if discovered:
        return {
            "skill_id": discovered[0],
            "selection_basis": "runtime_selected_engram_skill",
            "candidate_skill_ids": discovered,
        }

    if _manufacturer_known(atoms):
        return {
            "skill_id": "manufacturer_plus_description_discovery",
            "selection_basis": "deterministic_manufacturer_atom_fallback",
            "candidate_skill_ids": [],
        }

    return {
        "skill_id": "",
        "selection_basis": "no_applicable_final_rollout_skill",
        "candidate_skill_ids": [],
    }


def _known_topics(result: Mapping[str, Any]) -> set[str]:
    atoms = _mapping(result.get("query_atoms"))
    known: set[str] = set()

    identifier_mode = str(atoms.get("identifier_mode") or "")
    identifier = _compact(
        atoms.get("normalized_identifier")
        or atoms.get("part_number")
        or atoms.get("part_prefix")
        or atoms.get("part_contains")
        or atoms.get("part_suffix"),
        200,
    )
    if identifier_mode == "exact" and identifier:
        known.update({"exact_identifier", "adjacent_identifier_characters"})
    elif identifier:
        known.add("exact_identifier")

    if _manufacturer_known(atoms):
        known.add("manufacturer")

    if any(
        atoms.get(key)
        for key in ("ata_exact", "ata_prefix", "ata", "ata_clues")
    ):
        known.add("ata_system")

    nomenclature = atoms.get("nomenclature_terms")
    if isinstance(nomenclature, list) and nomenclature:
        known.add("component_function")

    if any(
        atoms.get(key)
        for key in ("figure", "figure_number", "item", "item_number", "page_id")
    ):
        known.update({"figure_table_item", "exact_source_location"})

    if atoms.get("document") or atoms.get("manual"):
        known.add("document_family")

    # If the user already named an exact page (page-content bridge found it), the
    # page/figure/table/document questions are already answered — do not ask them.
    if _page_content_found(result):
        known.update({"exact_source_location", "figure_table_item", "document_family"})

    return known


def _page_content_found(result: Mapping[str, Any]) -> bool:
    envelope = _mapping(result.get("evidence_envelope"))
    coverage = _mapping(envelope.get("coverage"))
    page_content = _mapping(coverage.get("page_content"))
    pages = page_content.get("pages")
    return bool(page_content.get("available") and isinstance(pages, list) and pages)


def _candidate_count(result: Mapping[str, Any]) -> int:
    decision = _mapping(result.get("answer_mode"))
    try:
        return int(decision.get("candidate_count") or 0)
    except (TypeError, ValueError):
        return 0


def _topic_score(
    topic: str,
    *,
    mode: str,
    candidate_count: int,
    position: int,
) -> int:
    score = 100 - position * 5
    if topic == "adjacent_identifier_characters" and candidate_count > 1:
        score += 40
    if topic in {"manual_revision", "exact_source_location"} and mode == MODE_CONFLICT:
        score += 35
    if topic in {
        "authority_document",
        "effectivity",
        "installation_context",
    } and mode == MODE_AUTHORITY_MISSING:
        score += 35
    if topic == "manufacturer" and candidate_count > 1:
        score += 15
    return score


def build_information_gain_followups(
    result: Mapping[str, Any],
    *,
    maximum: int,
) -> Dict[str, Any]:
    decision = _mapping(result.get("answer_mode"))
    mode = str(decision.get("mode") or "")
    selection = select_primary_skill(result)
    skill_id = str(selection.get("skill_id") or "")
    known = _known_topics(result)
    candidate_count = _candidate_count(result)

    if _page_content_found(result):
        return {
            "quality_status": "PASS",
            "selected_skill_id": skill_id,
            "skill_selection_basis": selection["selection_basis"],
            "known_topics": sorted(known),
            "candidate_count": candidate_count,
            "selected_count": 0,
            "questions": [],
            "records": [],
            "generic_question_count": 0,
            "suppression_reason": "exact_page_already_supplied_and_found",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }

    ordered_topics: List[str] = []
    for topic in MODE_TOPIC_PREFIX.get(mode, ()):
        if topic not in ordered_topics:
            ordered_topics.append(topic)
    for topic in SKILL_TOPIC_ORDER.get(skill_id, ()):
        if topic not in ordered_topics:
            ordered_topics.append(topic)
    if not ordered_topics and mode in TECHNICAL_NON_DIRECT_MODES:
        ordered_topics.extend(MODE_TOPIC_PREFIX[MODE_NO_EVIDENCE])

    scored = []
    for position, topic in enumerate(ordered_topics):
        if topic in known:
            continue
        question = TOPIC_QUESTIONS.get(topic)
        if not question:
            continue
        scored.append({
            "topic": topic,
            "question": question,
            "score": _topic_score(
                topic,
                mode=mode,
                candidate_count=candidate_count,
                position=position,
            ),
            "reason": (
                "expected_to_reduce_candidate_ambiguity"
                if candidate_count > 1
                else "fills_missing_query_atom"
            ),
        })

    scored.sort(key=lambda row: (-int(row["score"]), row["topic"]))
    selected = scored[:maximum]
    return {
        "quality_status": "PASS",
        "selected_skill_id": skill_id,
        "skill_selection_basis": selection["selection_basis"],
        "known_topics": sorted(known),
        "candidate_count": candidate_count,
        "selected_count": len(selected),
        "questions": [row["question"] for row in selected],
        "records": selected,
        "generic_question_count": 0,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def strip_followup_section(text: str) -> str:
    value = str(text or "").strip()
    marker_index = value.find(FOLLOWUP_MARKER)
    if marker_index < 0:
        return value
    return value[:marker_index].rstrip()


def apply_followup_section(
    text: str,
    questions: Sequence[str],
) -> str:
    base = strip_followup_section(text)
    clean: List[str] = []
    seen = set()
    for raw in questions:
        question = re.sub(r"\s+", " ", str(raw or "")).strip()
        key = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        clean.append(question)
    if not clean:
        return base
    return (
        base
        + "\n\n"
        + FOLLOWUP_MARKER
        + "\n"
        + "\n".join(f"- {question}" for question in clean)
    ).strip()


def _extract_rendered_followups(text: str) -> List[str]:
    value = str(text or "")
    marker_index = value.find(FOLLOWUP_MARKER)
    if marker_index < 0:
        return []
    tail = value[marker_index + len(FOLLOWUP_MARKER):]
    output = []
    for line in tail.splitlines():
        clean = line.strip()
        if clean.startswith("- "):
            output.append(clean[2:].strip())
    return output


def run_final_self_rag_critic(
    result: Mapping[str, Any],
    *,
    maximum_followups: int,
) -> Dict[str, Any]:
    failures: List[str] = []
    warnings: List[str] = []
    checks: List[Dict[str, Any]] = []

    decision = _mapping(result.get("answer_mode"))
    mode = str(decision.get("mode") or "")
    content = str(result.get("content") or "")
    lower = content.lower()
    envelope = _mapping(result.get("evidence_envelope"))
    typed_validation = _mapping(
        envelope.get("typed_evidence_validation")
    )
    answer_mode_validation = _mapping(
        result.get("answer_mode_validation")
    )
    followups = _extract_rendered_followups(content)

    def check(name: str, passed: bool, failure: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed)})
        if not passed and failure:
            failures.append(failure)

    check(
        "answer_permission_false",
        result.get("answer_permission") is False,
        "answer_permission_not_false",
    )
    check(
        "source_truth_mutation_false",
        result.get("source_truth_mutation_allowed") is False,
        "source_truth_mutation_allowed",
    )
    check(
        "typed_evidence_validation",
        typed_validation.get("quality_status") in {"PASS", None},
        "typed_evidence_validation_failed",
    )
    check(
        "answer_mode_validation",
        answer_mode_validation.get("quality_status") in {"PASS", None},
        "answer_mode_validation_failed",
    )

    support_count = int(
        decision.get("claim_support_allowed_count") or 0
    )
    check(
        "confirmed_requires_direct_support",
        mode != MODE_CONFIRMED_DIRECT or support_count > 0,
        "confirmed_mode_without_direct_support",
    )

    unsafe_positive = [
        pattern
        for pattern in UNSAFE_POSITIVE_PATTERNS
        if re.search(pattern, lower)
    ]
    check(
        "non_direct_has_no_positive_proof_claim",
        mode not in TECHNICAL_NON_DIRECT_MODES or not unsafe_positive,
        "non_direct_positive_proof_claim",
    )

    mode_requirements = {
        MODE_CANDIDATE: "not a final identification",
        MODE_VISUAL: "direct source proof",
        MODE_SEMANTIC: "cannot prove",
        MODE_CONFLICT: "no positive technical conclusion",
        MODE_AUTHORITY_MISSING: "did not find direct authority evidence",
        MODE_NO_EVIDENCE: "no technical conclusion",
    }
    required_phrase = mode_requirements.get(mode)
    check(
        "mode_disclaimer_present",
        not required_phrase or required_phrase in lower,
        "answer_mode_disclaimer_missing",
    )

    normalized_followups = [
        re.sub(r"[^a-z0-9]+", " ", item.lower()).strip()
        for item in followups
    ]
    check(
        "followup_count_bounded",
        len(followups) <= maximum_followups,
        "followup_count_exceeds_limit",
    )
    check(
        "followups_unique",
        len(normalized_followups) == len(set(normalized_followups)),
        "duplicate_followup_question",
    )
    generic = [
        question
        for question in followups
        if any(
            re.search(pattern, question.lower())
            for pattern in GENERIC_FOLLOWUP_PATTERNS
        )
    ]
    check(
        "followups_non_generic",
        not generic,
        "generic_followup_question",
    )

    if mode in TECHNICAL_NON_DIRECT_MODES and not followups:
        warnings.append("no_information_gain_followups_available")

    failures = list(dict.fromkeys(failures))
    warnings = list(dict.fromkeys(warnings))
    return {
        "status": "TRACE_NET_H30_FINAL_SELF_RAG_CRITIC_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "check_count": len(checks),
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
        "answer_mode": mode,
        "followup_count": len(followups),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def run_bounded_final_repair(
    result: MutableMapping[str, Any],
    *,
    followup_plan: Mapping[str, Any],
    maximum_repairs: int,
    maximum_followups: int,
) -> Dict[str, Any]:
    initial = run_final_self_rag_critic(
        result,
        maximum_followups=maximum_followups,
    )
    actions: List[str] = []
    repair_count = 0

    if initial["quality_status"] == "FAIL" and maximum_repairs > 0:
        decision = _mapping(result.get("answer_mode"))
        mode = str(decision.get("mode") or "")
        if mode in TECHNICAL_NON_DIRECT_MODES:
            result["content"] = render_deterministic_mode(
                result,
                decision,
                maximum_items=6,
            )
            actions.append("rerender_non_direct_answer_from_typed_mode")
        result["content"] = apply_followup_section(
            str(result.get("content") or ""),
            [
                str(item)
                for item in (followup_plan.get("questions") or [])
            ][:maximum_followups],
        )
        result["follow_up_questions"] = list(
            followup_plan.get("questions") or []
        )[:maximum_followups]
        actions.append("replace_followups_with_information_gain_questions")
        repair_count = 1

    final = run_final_self_rag_critic(
        result,
        maximum_followups=maximum_followups,
    )
    return {
        "status": "TRACE_NET_H30_BOUNDED_FINAL_CRAG_REPAIR_V1",
        "quality_status": final["quality_status"],
        "repair_count": repair_count,
        "maximum_repairs": maximum_repairs,
        "actions": actions,
        "initial_critic": initial,
        "final_critic": final,
        "retrieval_reexecuted": False,
        "new_evidence_selected": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }


def final_rollout_health(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    config = load_final_rollout_config(environ)
    return {
        "status": STATUS,
        "quality_status": "PASS",
        "enabled": bool(config.get("enabled")),
        "completed_roadmap_phases": [6, 7, 8, 9, 10],
        "phase_6_information_gain_followups": True,
        "phase_7_typed_self_rag_critic": True,
        "phase_8_bounded_final_crag_repair": True,
        "phase_9_benchmark_contract": True,
        "phase_10_all_skill_response_rollout": True,
        "supported_skill_ids": list(SUPPORTED_SKILL_IDS),
        "rollout_scope": "all_five_engram_skills_response_behavior",
        "maximum_followups": config["max_followups"],
        "maximum_repairs": config["max_repairs"],
        "critical_live_route_smoke_required_for_restart": False,
        "routes_changed": False,
        "retrieval_changed": False,
        "evidence_selection_changed": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def install_final_engram_rollout(
    module: MutableMapping[str, Any],
) -> None:
    marker = "_TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_V1_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health

    def process_v2(
        self: Any,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        config = load_final_rollout_config()
        result["final_engram_rollout_enabled"] = bool(
            config.get("enabled")
        )

        if not config.get("enabled"):
            result["final_engram_rollout"] = {
                "quality_status": "SKIPPED",
                "reason": "disabled_by_configuration",
                "completed_roadmap_phases": [6, 7, 8, 9, 10],
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
            return result

        decision = _mapping(result.get("answer_mode"))
        mode = str(decision.get("mode") or "")
        followup_plan = build_information_gain_followups(
            result,
            maximum=int(config["max_followups"]),
        )

        if mode not in {
            MODE_CONFIRMED_DIRECT,
            MODE_GENERAL_CHAT,
            MODE_UPSTREAM_ERROR,
        }:
            result["follow_up_questions"] = list(
                followup_plan["questions"]
            )
            result["content"] = apply_followup_section(
                str(result.get("content") or ""),
                followup_plan["questions"],
            )

        repair = run_bounded_final_repair(
            result,
            followup_plan=followup_plan,
            maximum_repairs=int(config["max_repairs"]),
            maximum_followups=int(config["max_followups"]),
        )
        critic = repair["final_critic"]
        skill = select_primary_skill(result)

        result["information_gain_followups"] = followup_plan
        result["final_engram_critic"] = critic
        result["bounded_crag_repair"] = repair
        result["final_engram_rollout"] = {
            "status": STATUS,
            "quality_status": critic["quality_status"],
            "completed_roadmap_phases": [6, 7, 8, 9, 10],
            "selected_skill_id": skill["skill_id"],
            "skill_selection_basis": skill["selection_basis"],
            "rollout_scope": "all_five_engram_skills_response_behavior",
            "engram_behavior_guidance_only": True,
            "typed_evidence_controls_claim_support": True,
            "answer_mode_controls_writer_access": True,
            "critical_live_route_smoke_required": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "write_attempt_count": 0,
        }
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    def health_v2(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        health = final_rollout_health()
        result["final_engram_rollout"] = health
        result["final_engram_rollout_enabled"] = bool(
            health.get("enabled")
        )
        result["roadmap_phases_6_through_10_complete"] = True
        result["critical_live_route_smoke_default"] = "SKIP"
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    runtime_cls.process = process_v2
    runtime_cls.health = health_v2
    module[marker] = True
