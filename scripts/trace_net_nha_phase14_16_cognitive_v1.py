#!/usr/bin/env python3
"""TRACE-Net NHA N14-N16 Engram-guided constrained Gemma integration.

N14 connects the reviewed N13 query atoms and skill cards to the real NHA
relationship engine. N15 gives Gemma one constrained answer-only call after
real evidence is assembled. N16 validates the public Answer/Evidence/Limits
contract and falls back to the already-valid deterministic answer on any model
or validation failure.

The Engram remains behavior guidance, never proof. Source evidence comes only
from the promoted real N4 relationship bundle. This module is read-only and
performs no database writes or source mutation.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from scripts.trace_net_nha_phase7_8_runtime_v1 import (
    ELIGIBLE_BEHAVIORS,
    public_contract_valid,
    render_gated_answer,
)
from tiff.trace_net_nha_engram_v1 import (
    NHA_SKILL_IDS,
    extract_nha_query_atoms,
    select_nha_skills,
)

MODULE = "trace_net_nha_phase14_16_cognitive_v1"
STATUS = "TRACE_NET_NHA_PHASE14_16_COGNITIVE_V1"
SCHEMA_VERSION = "trace_net_nha_phase14_16_cognitive_v1"
ROUTE_ID = "assembly_relationship_reasoning"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_GEMMA_MODEL = "gemma4:26b"

PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?|\d{4,6}-\d{1,4}|[A-Z]{2,}\d{3,}[A-Z0-9-]*)\b",
    re.I,
)
CITATION_RE = re.compile(r"\[\d{1,3}\]")
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)

ENGRAM_FILES = {
    "memory_atoms": "trace_net_nha_engram_memory_atoms_v1.json",
    "skill_cards": "trace_net_nha_engram_skill_cards_v1.json",
    "quality": "trace_net_nha_engram_quality_v1.json",
}

INTENT_METHODS = {
    "direct_nha": "direct_nha",
    "ancestor_chain": "ancestor_chain",
    "direct_children": "direct_children",
    "direct_vs_descendants": "descendants",
    "relationship_evidence": "page_evidence",
    "scope_conflict_resolution": "direct_nha",
}

INTENT_SKILL = {
    "direct_nha": "nha_direct_parent_lookup",
    "ancestor_chain": "nha_ancestor_chain_reasoning",
    "direct_children": "nha_children_descendants_reasoning",
    "direct_vs_descendants": "nha_children_descendants_reasoning",
    "relationship_evidence": "nha_relationship_evidence",
    "scope_conflict_resolution": "nha_scope_conflict_resolution",
}

INTENT_ATOM_IDS = {
    "direct_nha": (
        "policy_nha_direct_parent_one_hop_v1",
        "policy_nha_source_page_required_v1",
        "semantic_nha_synonyms_v1",
        "critic_nha_no_grandparent_as_direct_v1",
        "style_nha_answer_shape_v1",
    ),
    "ancestor_chain": (
        "policy_nha_ordered_chain_no_skip_v1",
        "policy_nha_source_page_required_v1",
        "route_nha_assembly_relationship_reasoning_v1",
        "critic_nha_no_grandparent_as_direct_v1",
        "style_nha_answer_shape_v1",
    ),
    "direct_children": (
        "policy_nha_children_not_descendants_v1",
        "policy_nha_source_page_required_v1",
        "route_nha_assembly_relationship_reasoning_v1",
        "style_nha_answer_shape_v1",
    ),
    "direct_vs_descendants": (
        "policy_nha_children_not_descendants_v1",
        "policy_nha_source_page_required_v1",
        "route_nha_assembly_relationship_reasoning_v1",
        "style_nha_answer_shape_v1",
    ),
    "relationship_evidence": (
        "policy_nha_source_page_required_v1",
        "policy_nha_guidance_not_proof_v1",
        "route_nha_assembly_relationship_reasoning_v1",
        "style_nha_answer_shape_v1",
    ),
    "scope_conflict_resolution": (
        "policy_nha_scope_before_candidate_choice_v1",
        "semantic_nha_scope_vocabulary_v1",
        "critic_nha_no_candidate_collapse_v1",
        "repair_nha_request_scope_v1",
        "style_nha_answer_shape_v1",
    ),
}

SAFETY_CONTRACT = {
    "engram_guidance_only": True,
    "real_source_relationships_only": True,
    "single_gemma_call_maximum": True,
    "deterministic_fallback_preserved": True,
    "phase4_evidence_owns_claim_support": True,
    "gemma_cannot_select_route": True,
    "gemma_cannot_retrieve": True,
    "gemma_cannot_select_evidence": True,
    "synthetic_artifacts_loaded": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "skill_cards", "items", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _dedupe(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def load_nha_engram_bundle(engram_dir: str | Path) -> dict[str, Any]:
    root = Path(engram_dir).resolve()
    payloads: dict[str, Any] = {}
    failures: list[str] = []
    for key, filename in ENGRAM_FILES.items():
        path = root / filename
        if not path.exists():
            failures.append(f"missing_engram_file:{filename}")
            payloads[key] = {}
            continue
        payloads[key] = _read_json(path)

    atoms = _records(payloads.get("memory_atoms"))
    cards = _records(payloads.get("skill_cards"))
    quality = payloads.get("quality") if isinstance(payloads.get("quality"), Mapping) else {}
    atom_ids = {str(row.get("engram_id") or "") for row in atoms}
    skill_ids = {str(row.get("skill_id") or "") for row in cards}

    if str(quality.get("quality_status") or "") != "PASS":
        failures.append("nha_engram_quality_not_pass")
    if len(atoms) < 15:
        failures.append(f"nha_memory_atom_count:{len(atoms)}<15")
    if len(cards) < 5:
        failures.append(f"nha_skill_card_count:{len(cards)}<5")
    missing_skills = sorted(set(NHA_SKILL_IDS) - skill_ids)
    if missing_skills:
        failures.append("missing_nha_skills:" + ",".join(missing_skills))

    return {
        "schema_version": SCHEMA_VERSION,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "root": str(root),
        "memory_atoms": atoms,
        "skill_cards": cards,
        "memory_atom_ids": sorted(atom_ids),
        "skill_ids": sorted(skill_ids),
        "nha_memory_atom_count": len(atoms),
        "nha_skill_card_count": len(cards),
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def _card_by_id(bundle: Mapping[str, Any], skill_id: str) -> dict[str, Any]:
    for row in bundle.get("skill_cards") or []:
        if isinstance(row, Mapping) and str(row.get("skill_id") or "") == skill_id:
            return dict(row)
    return {}


def select_memory_atoms(
    query: str,
    atom_payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    max_atoms: int = 5,
) -> list[dict[str, Any]]:
    intent = str(atom_payload.get("intent") or "")
    preferred = list(INTENT_ATOM_IDS.get(intent, ()))
    records_by_id = {
        str(row.get("engram_id") or ""): dict(row)
        for row in bundle.get("memory_atoms") or []
        if isinstance(row, Mapping)
    }
    selected: list[dict[str, Any]] = []
    for atom_id in preferred:
        row = records_by_id.get(atom_id)
        if row:
            selected.append(row)
    if len(selected) < max_atoms:
        lower = str(query or "").casefold()
        extras: list[tuple[int, str, dict[str, Any]]] = []
        selected_ids = {str(row.get("engram_id") or "") for row in selected}
        for atom_id, row in records_by_id.items():
            if atom_id in selected_ids:
                continue
            score = sum(
                1
                for trigger in row.get("triggers") or []
                if str(trigger).casefold() in lower
            )
            if score:
                extras.append((-score, atom_id, row))
        extras.sort(key=lambda item: (item[0], item[1]))
        selected.extend(row for _, _, row in extras[: max_atoms - len(selected)])
    return selected[:max_atoms]


def _result_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "behavior": str(result.get("behavior") or ""),
        "child": str(result.get("child") or ""),
        "parent": str(result.get("parent") or ""),
        "direct_nha": str(result.get("direct_nha") or ""),
        "parent_candidates": _dedupe(result.get("parent_candidates") or []),
        "chain": _dedupe(result.get("chain") or []),
        "direct_children": _dedupe(result.get("direct_children") or []),
        "descendants": _dedupe(result.get("descendants") or []),
        "pages": _dedupe(result.get("pages") or []),
        "limits": _dedupe(result.get("limits") or []),
        "comparison_parent": str(result.get("comparison_parent") or ""),
        "comparison_relation": str(result.get("comparison_relation") or ""),
        "comparison_chain": _dedupe(result.get("comparison_chain") or []),
    }


def build_nha_writer_packet(
    *,
    query: str,
    engine: Any,
    engram_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    atoms = extract_nha_query_atoms(query)
    skills = select_nha_skills(query)
    selected_skill_ids = _dedupe(skills.get("selected_skill_ids") or [])
    intent = str(atoms.get("intent") or "")
    part_numbers = _dedupe(atoms.get("part_numbers") or [])
    part = str(atoms.get("target_part_number") or (part_numbers[0] if part_numbers else ""))
    comparison_parent = str(atoms.get("comparison_parent_part") or "")

    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "query": str(query or ""),
        "query_sha256": _sha256_text(query),
        "route_id": str(atoms.get("route_hint") or ""),
        "intent": intent,
        "part_number": part,
        "part_numbers": part_numbers,
        "comparison_parent_part": comparison_parent,
        "parent_comparison": bool(atoms.get("parent_comparison")),
        "recognized": bool(atoms.get("nha_candidate")),
        "synthetic_blocked": bool(atoms.get("synthetic_blocked")),
        "query_atoms": list(atoms.get("query_atom_tokens") or []),
        "selected_skill_ids": selected_skill_ids,
        "selected_memory_atom_ids": [],
        "selected_memory_rules": [],
        "skill_guidance": {},
        "evidence": {},
        "eligible": False,
        "llm_call_count": 0,
        "production_graph_write_count": 0,
        "source_artifact_mutation_count": 0,
        "synthetic_artifact_access_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }
    if packet["synthetic_blocked"] or not packet["recognized"]:
        return packet

    required_skill = INTENT_SKILL.get(intent, "")
    if required_skill and selected_skill_ids != [required_skill]:
        packet["recognition_failure"] = (
            f"reviewed_skill_mismatch expected={required_skill} actual={selected_skill_ids}"
        )
        return packet

    memory_atoms = select_memory_atoms(query, atoms, engram_bundle)
    packet["selected_memory_atom_ids"] = [
        str(row.get("engram_id") or "") for row in memory_atoms
    ]
    packet["selected_memory_rules"] = [
        str(row.get("rule") or "") for row in memory_atoms if str(row.get("rule") or "")
    ]
    card = _card_by_id(engram_bundle, required_skill)
    packet["skill_guidance"] = {
        "skill_id": required_skill,
        "title": str(card.get("title") or ""),
        "reasoning_goal": str(card.get("reasoning_goal") or ""),
        "ranking_policy": _dedupe(card.get("ranking_policy") or []),
        "answer_requirements": _dedupe(card.get("answer_requirements") or []),
        "follow_up_policy": _dedupe(card.get("follow_up_policy") or []),
    }

    method_name = INTENT_METHODS.get(intent, "")
    method = getattr(engine, method_name, None) if method_name else None
    if not callable(method):
        packet["recognition_failure"] = f"missing_engine_method:{method_name or intent}"
        return packet
    result = method(part)
    evidence = _result_summary(result)
    if packet.get("parent_comparison") and comparison_parent:
        relation = "not_supported_parent_or_ancestor"
        direct_parent = str(evidence.get("direct_nha") or "")
        comparison_chain = []
        if comparison_parent == direct_parent and direct_parent:
            relation = "direct_parent"
        else:
            chain_method = getattr(engine, "ancestor_chain", None)
            if callable(chain_method):
                chain_result = chain_method(part)
                comparison_chain = _dedupe(chain_result.get("chain") or [])
                if comparison_parent in comparison_chain[2:]:
                    relation = "higher_ancestor"
            if comparison_parent in (evidence.get("parent_candidates") or []):
                relation = "candidate_parent"
        evidence["comparison_parent"] = comparison_parent
        evidence["comparison_relation"] = relation
        evidence["comparison_chain"] = comparison_chain
    packet["evidence"] = evidence
    packet["eligible"] = bool(
        evidence["behavior"] in ELIGIBLE_BEHAVIORS and evidence["pages"]
    )
    return packet


def deterministic_answer_text(evidence: Mapping[str, Any]) -> str:
    comparison_parent = str(evidence.get("comparison_parent") or "")
    comparison_relation = str(evidence.get("comparison_relation") or "")
    child = str(evidence.get("child") or "")
    direct_parent = str(evidence.get("direct_nha") or "")
    if comparison_parent and comparison_relation == "direct_parent":
        return f"{comparison_parent} is the immediate direct NHA of {child}"
    if comparison_parent and comparison_relation == "higher_ancestor":
        return f"{comparison_parent} is a supported higher ancestor of {child}, not its direct NHA; the direct NHA is {direct_parent}"
    if comparison_parent and comparison_relation == "not_supported_parent_or_ancestor":
        return f"{comparison_parent} is not supported as the direct parent or a higher ancestor of {child}; the supported direct NHA is {direct_parent}"
    rendered = render_gated_answer(evidence)
    before_evidence = rendered.split("## Evidence", 1)[0]
    answer = before_evidence.replace("## Answer", "", 1).strip()
    return CITATION_RE.sub("", answer).replace("  ", " ").strip()


def build_gemma_messages(packet: Mapping[str, Any]) -> list[dict[str, str]]:
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), Mapping) else {}
    compact = {
        "intent": packet.get("intent"),
        "question": packet.get("query"),
        "part_number": packet.get("part_number"),
        "part_numbers": packet.get("part_numbers") or [],
        "parent_comparison": bool(packet.get("parent_comparison")),
        "comparison_parent": evidence.get("comparison_parent"),
        "comparison_relation": evidence.get("comparison_relation"),
        "comparison_chain": evidence.get("comparison_chain") or [],
        "behavior": evidence.get("behavior"),
        "child": evidence.get("child"),
        "parent": evidence.get("parent"),
        "direct_nha": evidence.get("direct_nha"),
        "parent_candidates": evidence.get("parent_candidates") or [],
        "chain": evidence.get("chain") or [],
        "direct_children": evidence.get("direct_children") or [],
        "descendants": evidence.get("descendants") or [],
        "limits": evidence.get("limits") or [],
        "selected_skill": packet.get("skill_guidance") or {},
        "engram_behavior_rules": packet.get("selected_memory_rules") or [],
    }
    system = """You are the constrained TRACE-Net NHA answer writer.
Return exactly one JSON object with one key: {\"answer\": \"...\"}.
Write only the concise user-facing Answer paragraph, not headings, Evidence, Limits, citations, or analysis.
Use only the supplied deterministic facts. Engram rules are behavior guidance, never evidence.
Preserve every part number exactly. Do not invent identifiers, pages, scope, effectivity, approval, safety, fit, or interchangeability.
For a direct NHA, state exactly one immediate supported parent.
For a parent-comparison question, explicitly say whether the proposed parent is the direct parent, only a higher ancestor, only a candidate, or unsupported by the supplied chain.
For an ordered chain, preserve every hop in order.
For direct children or descendants, include every supplied identifier and keep one-hop children separate from lower descendants.
For conflict-limited evidence, do not choose a parent; state that no single direct NHA is confirmed and list every candidate.
For relationship-evidence intent, explain what relationship the source pages support without inventing page content.
Do not use markdown headings or citation markers."""
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "CONSTRAINED_NHA_PACKET\n" + json.dumps(compact, ensure_ascii=False, sort_keys=True),
        },
    ]


def call_ollama_json(
    *,
    ollama_url: str,
    model: str,
    messages: Sequence[Mapping[str, str]],
    timeout: float,
    max_tokens: int = 512,
    keep_alive: str = "1h",
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [dict(row) for row in messages],
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": keep_alive,
        "options": {
            "temperature": 0,
            "num_predict": int(max_tokens),
        },
    }
    request = urllib.request.Request(
        ollama_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as exc:
        return {
            "quality_status": "FAIL",
            "http_status": exc.code,
            "error": exc.read().decode("utf-8", errors="replace"),
            "latency_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "quality_status": "FAIL",
            "http_status": 599,
            "error": f"{type(exc).__name__}: {exc}",
            "latency_seconds": round(time.perf_counter() - started, 3),
        }
    message = body.get("message") if isinstance(body, Mapping) else {}
    content = str(message.get("content") or "") if isinstance(message, Mapping) else ""
    return {
        "quality_status": "PASS" if status == 200 and content.strip() else "FAIL",
        "http_status": status,
        "content": content,
        "prompt_eval_count": int(body.get("prompt_eval_count") or 0) if isinstance(body, Mapping) else 0,
        "eval_count": int(body.get("eval_count") or 0) if isinstance(body, Mapping) else 0,
        "total_duration": int(body.get("total_duration") or 0) if isinstance(body, Mapping) else 0,
        "latency_seconds": round(time.perf_counter() - started, 3),
        "raw": body,
    }


def parse_gemma_answer(content: str) -> str:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, Mapping):
        return ""
    return re.sub(r"\s+", " ", str(payload.get("answer") or "")).strip()


def _allowed_identifiers(evidence: Mapping[str, Any]) -> set[str]:
    values: list[Any] = [
        evidence.get("child"),
        evidence.get("parent"),
        evidence.get("direct_nha"),
        evidence.get("comparison_parent"),
    ]
    for key in ("parent_candidates", "chain", "direct_children", "descendants", "comparison_chain"):
        values.extend(evidence.get(key) or [])
    return {str(value).upper() for value in values if value not in (None, "") and str(value).strip()}


def _required_identifiers(evidence: Mapping[str, Any]) -> set[str]:
    if evidence.get("comparison_parent"):
        return _allowed_identifiers({
            "child": evidence.get("child"),
            "direct_nha": evidence.get("direct_nha"),
            "comparison_parent": evidence.get("comparison_parent"),
        })
    behavior = str(evidence.get("behavior") or "")
    if behavior == "direct_answer":
        return _allowed_identifiers({
            "child": evidence.get("child"),
            "direct_nha": evidence.get("direct_nha"),
        })
    if behavior == "ordered_chain_answer":
        return {str(value).upper() for value in evidence.get("chain") or [] if value not in (None, "") and str(value).strip()}
    if behavior == "direct_children_answer":
        return _allowed_identifiers({
            "parent": evidence.get("parent"),
            "direct_children": evidence.get("direct_children") or [],
        })
    if behavior == "tree_answer":
        return _allowed_identifiers({
            "parent": evidence.get("parent"),
            "direct_children": evidence.get("direct_children") or [],
            "descendants": evidence.get("descendants") or [],
        })
    if behavior in {"conflict_limited", "candidate_or_clarification", "conflict_evidence_answer"}:
        return _allowed_identifiers({
            "child": evidence.get("child"),
            "parent_candidates": evidence.get("parent_candidates") or [],
        })
    if behavior == "page_and_trait_answer":
        return _allowed_identifiers({
            "child": evidence.get("child"),
            "direct_nha": evidence.get("direct_nha"),
            "parent_candidates": evidence.get("parent_candidates") or [],
        })
    return _allowed_identifiers({"child": evidence.get("child")})


def validate_gemma_answer(answer: str, packet: Mapping[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    text = str(answer or "").strip()
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), Mapping) else {}
    if not text:
        failures.append("empty_answer")
        return False, failures
    if len(text) > 5000:
        failures.append("answer_too_long")
    if "## " in text:
        failures.append("model_returned_headings")
    if CITATION_RE.search(text):
        failures.append("model_returned_citation_marker")
    if PAGE_RE.search(text):
        failures.append("model_returned_internal_page_id")
    lower = text.casefold()
    for forbidden in ("approved replacement", "safe to install", "interchangeable", "fit approval"):
        if forbidden in lower:
            failures.append("unsupported_authority_claim:" + forbidden)

    allowed = _allowed_identifiers(evidence)
    found = {match.group(0).upper() for match in PART_RE.finditer(text)}
    unsupported = sorted(found - allowed)
    if unsupported:
        failures.append("unsupported_identifiers:" + ",".join(unsupported))
    missing = sorted(_required_identifiers(evidence) - found)
    if missing:
        failures.append("missing_required_identifiers:" + ",".join(missing))

    relation = str(evidence.get("comparison_relation") or "")
    if relation == "direct_parent" and not any(term in lower for term in ("direct parent", "immediate parent", "direct nha", "next higher assembly")):
        failures.append("direct_parent_comparison_not_expressed")
    elif relation == "higher_ancestor" and not ("higher ancestor" in lower and any(term in lower for term in ("not the direct", "not its direct", "not immediate"))):
        failures.append("higher_ancestor_comparison_not_expressed")
    elif relation == "not_supported_parent_or_ancestor" and not any(term in lower for term in ("not supported", "not shown", "not confirmed")):
        failures.append("unsupported_comparison_not_expressed")
    behavior = str(evidence.get("behavior") or "")
    if behavior in {"conflict_limited", "candidate_or_clarification", "conflict_evidence_answer"}:
        if not any(term in lower for term in ("cannot be confirmed", "no single", "multiple candidate", "ambiguous")):
            failures.append("conflict_not_expressed")
    return not failures, failures


def render_final_answer(answer_text: str, packet: Mapping[str, Any]) -> str:
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), Mapping) else {}
    pages = _dedupe(evidence.get("pages") or [])
    markers = " ".join(f"[{index}]" for index in range(1, len(pages) + 1))
    answer_line = str(answer_text or "").strip().rstrip(".")
    if markers:
        answer_line += " " + markers
    answer_line += "."
    evidence_lines = [
        f"- [{index}] Source page `{page}`."
        for index, page in enumerate(pages, 1)
    ] or ["- No source-backed relationship page was returned."]
    limits = [
        "Only promoted real N4 assembly relationships support this answer.",
        "Engram atoms and skill cards guide behavior but are not evidence.",
        "A higher ancestor is not treated as the direct NHA unless every intermediate hop is supported.",
    ]
    behavior = str(evidence.get("behavior") or "")
    if behavior in {"conflict_limited", "candidate_or_clarification", "conflict_evidence_answer"}:
        limits.append(
            "Project, configuration, effectivity, usage code, revision, or variant context may be required before choosing a parent."
        )
    limits.extend(_dedupe(evidence.get("limits") or []))
    return "\n".join([
        "## Answer",
        "",
        answer_line,
        "",
        "## Evidence",
        "",
        *evidence_lines,
        "",
        "## Limits",
        "",
        *[f"- {value}" for value in _dedupe(limits)],
    ])


@dataclass
class GemmaWriteResult:
    answer: str
    writer_source: str
    gemma_call_count: int
    gemma_writer_accepted: bool
    self_rag_pass: bool
    validation_failures: list[str]
    latency_seconds: float
    prompt_tokens: int
    completion_tokens: int
    raw_model_content: str = ""


def write_nha_answer_with_gemma(
    packet: Mapping[str, Any],
    *,
    model_call: Callable[..., Mapping[str, Any]] | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_GEMMA_MODEL,
    timeout: float = 120.0,
    max_tokens: int = 512,
) -> GemmaWriteResult:
    if not packet.get("eligible"):
        raise ValueError("packet_not_eligible_for_gemma_writer")
    caller = model_call or call_ollama_json
    started = time.perf_counter()
    response = dict(caller(
        ollama_url=ollama_url,
        model=model,
        messages=build_gemma_messages(packet),
        timeout=timeout,
        max_tokens=max_tokens,
        keep_alive="1h",
    ))
    raw_content = str(response.get("content") or "")
    parsed = parse_gemma_answer(raw_content)
    accepted, failures = validate_gemma_answer(parsed, packet)
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), Mapping) else {}
    answer_text = parsed if accepted else deterministic_answer_text(evidence)
    final = render_final_answer(answer_text, packet)
    contract_ok, contract_failures = public_contract_valid(
        final,
        evidence.get("pages") or [],
    )
    failures.extend(contract_failures)
    if not contract_ok:
        fallback_text = deterministic_answer_text(evidence)
        final = render_final_answer(fallback_text, packet)
        contract_ok, second_failures = public_contract_valid(
            final,
            evidence.get("pages") or [],
        )
        failures.extend(second_failures)
    return GemmaWriteResult(
        answer=final,
        writer_source="gemma" if accepted and contract_ok else "deterministic_fallback",
        gemma_call_count=1,
        gemma_writer_accepted=bool(accepted and contract_ok),
        self_rag_pass=bool(contract_ok),
        validation_failures=_dedupe(failures),
        latency_seconds=round(time.perf_counter() - started, 3),
        prompt_tokens=int(response.get("prompt_eval_count") or 0),
        completion_tokens=int(response.get("eval_count") or 0),
        raw_model_content=raw_content,
    )


def packet_diagnostic(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in packet.items()
        if key not in {"selected_memory_rules"}
    }
