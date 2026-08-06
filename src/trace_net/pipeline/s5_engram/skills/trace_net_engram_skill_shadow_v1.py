"""TRACE-Net Engram Skill Shadow v1.

Phase 2 converts reviewed Phase 1 skill cards into compact runtime guidance
bundles and comparison diagnostics. Shadow output is attached to the trace only.

The shadow layer:
- does not alter the answer;
- does not alter route planning or retrieval;
- does not call an LLM or live service;
- does not execute a retrieval tunnel;
- does not grant answer permission;
- does not mutate source truth or write to any database.

Phase 3 may use reviewed shadow results to influence planner behavior. This
module intentionally has no enforcement path.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from tiff.trace_net_engram_skill_cards_v1 import (
    load_json,
    select_engram_skills,
    validate_skill_library,
)

MODULE = "trace_net_engram_skill_shadow_v1"
VERSION = "v1"
STATUS = "TRACE_NET_ENGRAM_SKILL_SHADOW_V1_BUILT"

DEFAULT_LIBRARY_PATH = (
    Path(__file__).resolve().parents[1]
    / "local_data"
    / "organization"
    / "trace_net"
    / "engram_skill_cards_v1"
    / "trace_net_engram_skill_cards_v1.json"
)

SAFETY_CONTRACT = {
    "shadow_mode": True,
    "applied_to_answer": False,
    "applied_to_route": False,
    "applied_to_retrieval": False,
    "engram_guidance_only": True,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "can_be_used_as_proof": False,
    "retrieval_execution_allowed": False,
    "llm_call_attempt": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}

GENERIC_ANSWER_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    (
        "generic_candidate_boilerplate",
        re.compile(
            r"TRACE-Net found candidate evidence,\s*not a final identification",
            re.IGNORECASE,
        ),
    ),
    (
        "generic_guidance_disclaimer",
        re.compile(
            r"Candidate,\s*visual,\s*graph,\s*summary,\s*and semantic results "
            r"are guidance only",
            re.IGNORECASE,
        ),
    ),
    (
        "generic_engineering_confidence",
        re.compile(
            r"Engineering confidence\s*\n+\s*Guidance only",
            re.IGNORECASE,
        ),
    ),
    (
        "generic_source_resolved_required",
        re.compile(
            r"source-resolved record is still required",
            re.IGNORECASE,
        ),
    ),
)

GENERIC_FOLLOWUP_MARKERS: Tuple[str, ...] = (
    "additional part number characters",
    "manufacturer, vendor, or supplier",
    "component, function, assembly, or installation location",
    "shape, color, size, markings, and nearby hardware",
    "ata chapter, aircraft system, figure, diagram, ipl item, table, manual, or page",
)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()[:20]


def immutable_output_fingerprint(result: Mapping[str, Any]) -> str:
    """Fingerprint current behavior fields before adding shadow-only metadata."""
    payload = {
        "content": result.get("content") or result.get("answer"),
        "route": result.get("route") or result.get("actual_route"),
        "route_plan": result.get("route_plan"),
        "planned_tunnels": result.get("planned_tunnels"),
        "used_tunnels": result.get("used_tunnels"),
        "evidence_envelope": result.get("evidence_envelope"),
        "citation_count": result.get("citation_count"),
        "citations": result.get("citations"),
        "follow_up_questions": result.get("follow_up_questions"),
        "writer_mode": result.get("writer_mode"),
        "writer_status": result.get("writer_status"),
        "gemma_status": result.get("gemma_status"),
        "quality_status": result.get("quality_status"),
        "failures": result.get("failures"),
        "answer_permission": result.get("answer_permission"),
        "source_truth_mutation_allowed": result.get("source_truth_mutation_allowed"),
    }
    return stable_hash(payload)


def _card_map(library: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    cards = library.get("skill_cards")
    if not isinstance(cards, list):
        return {}
    return {
        str(card.get("skill_id")): dict(card)
        for card in cards
        if isinstance(card, Mapping) and card.get("skill_id")
    }


def _compact_list(value: Any, limit: int) -> List[str]:
    return _string_list(value)[: max(0, int(limit))]


def _answer_flags(answer: str) -> List[str]:
    text = str(answer or "")
    flags = [
        name for name, pattern in GENERIC_ANSWER_PATTERNS
        if pattern.search(text)
    ]
    heading_count = len(re.findall(r"(?m)^##\s+", text))
    if heading_count >= 4 and len(text) < 1800:
        flags.append("short_answer_with_many_template_sections")
    return list(dict.fromkeys(flags))


def _followup_assessment(followups: Sequence[str]) -> Dict[str, Any]:
    questions = [str(item).strip() for item in followups if str(item).strip()]
    lower_blob = "\n".join(questions).lower()
    markers = [
        marker for marker in GENERIC_FOLLOWUP_MARKERS
        if marker in lower_blob
    ]
    return {
        "follow_up_count": len(questions),
        "generic_follow_up_marker_count": len(markers),
        "generic_follow_up_markers": markers,
        "all_five_standard_discovery_questions_present": len(markers) >= 5,
        "questions": questions,
    }


def _result_parts(result: Mapping[str, Any]) -> Dict[str, Any]:
    trace = _mapping(result.get("trace_net"))
    route_plan = _mapping(
        result.get("route_plan")
        or trace.get("route_plan")
    )
    envelope = _mapping(
        result.get("evidence_envelope")
        or trace.get("evidence_envelope")
    )
    query_atoms = _mapping(
        result.get("query_atoms")
        or trace.get("query_atoms")
    )
    planned = _string_list(
        result.get("planned_tunnels")
        or route_plan.get("retrieval_tunnels")
    )
    used = _string_list(
        result.get("used_tunnels")
        or envelope.get("retrieval_tunnels_used")
    )
    return {
        "query": str(
            result.get("query")
            or trace.get("query")
            or ""
        ),
        "route": str(
            result.get("route")
            or result.get("actual_route")
            or trace.get("route")
            or ""
        ),
        "query_atoms": query_atoms,
        "route_plan": route_plan,
        "evidence_envelope": envelope,
        "planned_tunnels": planned,
        "used_tunnels": used,
        "answer": str(
            result.get("content")
            or result.get("answer")
            or trace.get("content")
            or ""
        ),
        "followups": _string_list(
            result.get("follow_up_questions")
            or trace.get("follow_up_questions")
        ),
        "writer_mode": str(
            result.get("writer_mode")
            or trace.get("writer_mode")
            or ""
        ),
        "writer_status": str(
            result.get("writer_status")
            or result.get("gemma_status")
            or trace.get("gemma_status")
            or ""
        ),
    }


def build_guidance_text(
    selected_cards: Sequence[Mapping[str, Any]],
    *,
    max_chars: int = 5200,
) -> str:
    lines = [
        "TRACE-NET ENGRAM SKILL SHADOW — BEHAVIOR GUIDANCE ONLY; NOT PROOF",
        "This block is not applied to the current answer, plan, or retrieval.",
        "Current manual claims still require current citation-ready evidence.",
    ]
    for card in selected_cards:
        lines.extend([
            "",
            f"SKILL: {card.get('skill_id')} — {card.get('title')}",
            f"Reasoning goal: {card.get('reasoning_goal')}",
            "Required first searches:",
        ])
        lines.extend(
            f"- {item}"
            for item in _compact_list(card.get("required_first_searches"), 4)
        )
        lines.append("Ranking policy:")
        lines.extend(
            f"- {item}"
            for item in _compact_list(card.get("ranking_policy"), 4)
        )
        answer_modes = _mapping(card.get("answer_mode_rules"))
        if answer_modes:
            lines.append(
                "Expected answer mode: "
                + str(answer_modes.get("default") or "unknown")
            )
        lines.append("Answer requirements:")
        lines.extend(
            f"- {item}"
            for item in _compact_list(card.get("answer_requirements"), 5)
        )
        lines.append("Follow-up policy:")
        lines.extend(
            f"- {item}"
            for item in _compact_list(card.get("follow_up_policy"), 3)
        )
        lessons = _compact_list(card.get("known_failure_lessons"), 3)
        if lessons:
            lines.append("Failure lessons:")
            lines.extend(f"- {item}" for item in lessons)

    lines.extend([
        "",
        "FORBIDDEN: never use this guidance as source evidence, never grant "
        "answer permission, and never execute a tunnel from this block.",
    ])
    text = "\n".join(lines).strip() + "\n"
    limit = max(1200, int(max_chars or 5200))
    if len(text) > limit:
        text = (
            text[: limit - 100].rstrip()
            + "\n[TRUNCATED: shadow guidance compacted; still behavior only, not proof.]\n"
        )
    return text


def build_engram_skill_shadow(
    result: Mapping[str, Any],
    *,
    query: str = "",
    stage: str = "offline_final_record",
    library_path: str | Path = DEFAULT_LIBRARY_PATH,
    max_skills: int = 3,
    max_guidance_chars: int = 5200,
) -> Dict[str, Any]:
    parts = _result_parts(result)
    current_query = str(query or parts["query"])
    before_fingerprint = immutable_output_fingerprint(result)

    try:
        library = load_json(library_path)
        if not isinstance(library, Mapping):
            library = {}
        validation = validate_skill_library(library)
        if validation.get("quality_status") != "PASS":
            raise ValueError(
                "skill library validation failed: "
                + " | ".join(validation.get("errors") or [])
            )

        selection = select_engram_skills(
            library,
            query=current_query,
            route=parts["route"],
            query_atoms=parts["query_atoms"],
            max_skills=max_skills,
        )
        cards_by_id = _card_map(library)
        full_cards = [
            cards_by_id[skill_id]
            for skill_id in selection.get("selected_skill_ids") or []
            if skill_id in cards_by_id
        ]

        allowed_tunnels = sorted({
            tunnel
            for card in full_cards
            for tunnel in _string_list(card.get("allowed_tunnels"))
        })
        planned = parts["planned_tunnels"]
        used = parts["used_tunnels"]
        planned_overlap = sorted(set(planned) & set(allowed_tunnels))
        used_overlap = sorted(set(used) & set(allowed_tunnels))

        expected_modes = [
            str(_mapping(card.get("answer_mode_rules")).get("default") or "")
            for card in full_cards
            if _mapping(card.get("answer_mode_rules")).get("default")
        ]
        answer_flags = _answer_flags(parts["answer"])
        followup = _followup_assessment(parts["followups"])

        recommendations: List[str] = []
        for card in full_cards:
            recommendations.extend(
                _compact_list(card.get("answer_requirements"), 5)
            )
        if followup["all_five_standard_discovery_questions_present"]:
            recommendations.append(
                "Replace the five standard discovery questions with the "
                "smallest set that distinguishes the current candidates."
            )
        if answer_flags:
            recommendations.append(
                "Replace generic TRACE-Net process boilerplate with a direct "
                "explanation of the current candidates, match reasons, and unresolved clue."
            )
        recommendations = list(dict.fromkeys(recommendations))

        guidance = build_guidance_text(
            full_cards,
            max_chars=max_guidance_chars,
        )
        result_bundle = {
            "status": STATUS,
            "quality_status": "PASS",
            "module": MODULE,
            "version": VERSION,
            "stage": stage,
            "query": current_query,
            "route": parts["route"],
            "library_path": str(Path(library_path)),
            "library_quality_status": validation.get("quality_status"),
            "selected_skill_count": len(full_cards),
            "selected_skill_ids": [
                str(card.get("skill_id")) for card in full_cards
            ],
            "selection": selection,
            "skill_card_hashes": {
                str(card.get("skill_id")): stable_hash(card)
                for card in full_cards
            },
            "expected_answer_modes": expected_modes,
            "required_first_searches": list(dict.fromkeys(
                item
                for card in full_cards
                for item in _compact_list(card.get("required_first_searches"), 6)
            )),
            "ranking_policy": list(dict.fromkeys(
                item
                for card in full_cards
                for item in _compact_list(card.get("ranking_policy"), 6)
            )),
            "answer_requirements": list(dict.fromkeys(
                item
                for card in full_cards
                for item in _compact_list(card.get("answer_requirements"), 8)
            )),
            "follow_up_policy": list(dict.fromkeys(
                item
                for card in full_cards
                for item in _compact_list(card.get("follow_up_policy"), 6)
            )),
            "planned_tunnels": planned,
            "used_tunnels": used,
            "skill_allowed_tunnels": allowed_tunnels,
            "planned_tunnel_overlap": planned_overlap,
            "used_tunnel_overlap": used_overlap,
            "current_writer_mode": parts["writer_mode"],
            "current_writer_status": parts["writer_status"],
            "current_answer_flags": answer_flags,
            "follow_up_assessment": followup,
            "shadow_recommendations": recommendations,
            "guidance_text": guidance,
            "guidance_character_count": len(guidance),
            "current_output_fingerprint": before_fingerprint,
            "current_output_unchanged_by_shadow": True,
            "shadow_applied_to_answer": False,
            "shadow_applied_to_route": False,
            "shadow_applied_to_retrieval": False,
            "engram_guidance_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "can_be_used_as_proof": False,
            "retrieval_execution_allowed": False,
            "write_attempt_count": 0,
            "safety_contract": dict(SAFETY_CONTRACT),
        }
        return result_bundle
    except Exception as exc:
        return {
            "status": STATUS,
            "quality_status": "FAIL",
            "module": MODULE,
            "version": VERSION,
            "stage": stage,
            "query": current_query,
            "route": parts["route"],
            "error": f"{type(exc).__name__}: {exc}",
            "selected_skill_count": 0,
            "selected_skill_ids": [],
            "current_output_fingerprint": before_fingerprint,
            "current_output_unchanged_by_shadow": True,
            "shadow_applied_to_answer": False,
            "shadow_applied_to_route": False,
            "shadow_applied_to_retrieval": False,
            "engram_guidance_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "can_be_used_as_proof": False,
            "retrieval_execution_allowed": False,
            "write_attempt_count": 0,
            "safety_contract": dict(SAFETY_CONTRACT),
        }


def attach_engram_skill_shadow(
    result: Mapping[str, Any],
    *,
    query: str = "",
    stage: str,
    library_path: str | Path = DEFAULT_LIBRARY_PATH,
    max_skills: int = 3,
    max_guidance_chars: int = 5200,
) -> Dict[str, Any]:
    """Return a copy with shadow metadata while preserving current behavior."""
    before = immutable_output_fingerprint(result)
    output = dict(result)
    output["engram_skill_shadow"] = build_engram_skill_shadow(
        result,
        query=query,
        stage=stage,
        library_path=library_path,
        max_skills=max_skills,
        max_guidance_chars=max_guidance_chars,
    )
    output["engram_skill_shadow_mode"] = True
    output["engram_skill_shadow_applied_to_answer"] = False
    output["engram_skill_shadow_applied_to_route"] = False
    output["engram_skill_shadow_applied_to_retrieval"] = False
    output["engram_skill_shadow_input_fingerprint"] = before
    output["engram_skill_shadow_output_fingerprint"] = immutable_output_fingerprint(output)
    output["engram_skill_shadow_behavior_preserved"] = (
        output["engram_skill_shadow_input_fingerprint"]
        == output["engram_skill_shadow_output_fingerprint"]
    )
    return output
