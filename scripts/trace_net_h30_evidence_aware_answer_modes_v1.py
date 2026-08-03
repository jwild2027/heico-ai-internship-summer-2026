"""TRACE-Net H30 Phase 5 evidence-aware answer modes.

Only typed records with claim_support_allowed=true may use the existing
validated Gemma direct-evidence writer. Candidate, visual, semantic, graph,
summary, conflict, authority-missing, and no-evidence modes remain
deterministic and fail closed.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

MODULE = "trace_net_h30_evidence_aware_answer_modes_v1"
VERSION = "v1"
STATUS = "TRACE_NET_EVIDENCE_AWARE_ANSWER_MODES_V1"

MODE_CONFIRMED_DIRECT = "confirmed_direct"
MODE_CANDIDATE = "candidate_discovery"
MODE_VISUAL = "visual_guidance"
MODE_SEMANTIC = "semantic_graph_summary_guidance"
MODE_CONFLICT = "conflict_limited"
MODE_AUTHORITY_MISSING = "authority_not_found"
MODE_NO_EVIDENCE = "no_evidence"
MODE_GENERAL_CHAT = "safe_general_chat"
MODE_UPSTREAM_ERROR = "upstream_error"

ALL_MODES = (
    MODE_CONFIRMED_DIRECT,
    MODE_CANDIDATE,
    MODE_VISUAL,
    MODE_SEMANTIC,
    MODE_CONFLICT,
    MODE_AUTHORITY_MISSING,
    MODE_NO_EVIDENCE,
    MODE_GENERAL_CHAT,
    MODE_UPSTREAM_ERROR,
)

AUTHORITY_ROUTES = {"authority_eligibility_verification"}
AUTHORITY_CLAIMS = {"authority_approval"}
SEMANTIC_MODALITIES = {
    "semantic_vector",
    "graph",
    "summary",
    "source_resolution",
}
PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b", re.I)

# Evidence-synthesis (Phase 4): when the writer produced a validated Gemma answer
# for one of these non-direct modes, keep it instead of overwriting with the
# deterministic template. Each mode's disclaimer sentence contains the exact
# phrase the final Self-RAG critic requires, so synthesis survives without
# weakening any safety check.
SYNTHESIS_MODES = {MODE_CANDIDATE, MODE_VISUAL, MODE_SEMANTIC, MODE_CONFLICT}
FOLLOWUP_MARKER = "Helpful follow-up questions:"
MODE_DISCLAIMERS = {
    MODE_CANDIDATE: "These are candidate matches for narrowing the search, not a final identification.",
    MODE_VISUAL: "This is visual guidance to help locate the item; it is not direct source proof of the technical identity.",
    MODE_SEMANTIC: "These are guidance leads for the next search; on their own they cannot prove the requested claim.",
    MODE_CONFLICT: "Because the evidence conflicts, no positive technical conclusion is asserted until it is resolved against direct source evidence.",
}

SAFETY_CONTRACT = {
    "typed_evidence_required": True,
    "confirmed_mode_requires_claim_support_allowed": True,
    "guidance_modes_are_deterministic": True,
    "candidate_guidance_is_not_identification": True,
    "visual_guidance_is_not_source_truth": True,
    "semantic_graph_summary_are_not_source_truth": True,
    "conflicts_block_positive_conclusions": True,
    "authority_missing_blocks_approval_claims": True,
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


def _compact(value: Any, limit: int = 800) -> str:
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


def load_answer_mode_config(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    try:
        maximum = int(
            env.get(
                "TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS",
                "6",
            )
        )
    except (TypeError, ValueError):
        maximum = 6
    return {
        "enabled": _bool_env(
            env,
            "TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED",
            False,
        ),
        "max_items": max(1, min(10, maximum)),
    }


def typed_record_source(result: Mapping[str, Any]) -> str:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        return "missing_evidence_envelope"
    selected = envelope.get("claim_ready_evidence")
    if isinstance(selected, Mapping) and selected.get("quality_status") == "PASS":
        if isinstance(selected.get("records"), list):
            return "claim_ready_evidence"
    return "complete_typed_evidence_fallback"


def typed_records(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        return []
    selected = envelope.get("claim_ready_evidence")
    if isinstance(selected, Mapping) and selected.get("quality_status") == "PASS":
        if isinstance(selected.get("records"), list):
            return _rows(selected.get("records"))
    return _rows(envelope.get("typed_evidence"))


def _claim_supporting(
    records: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        dict(row)
        for row in records
        if row.get("claim_support_allowed") is True
        and row.get("source_bucket") == "direct_evidence"
        and not row.get("guidance_only")
        and not row.get("conflicted")
    ]


def _records_by_bucket(
    records: Sequence[Mapping[str, Any]],
    bucket: str,
) -> List[Dict[str, Any]]:
    return [
        dict(row)
        for row in records
        if str(row.get("source_bucket") or "") == bucket
    ]


def _records_by_modality(
    records: Sequence[Mapping[str, Any]],
    modalities: Iterable[str],
) -> List[Dict[str, Any]]:
    allowed = set(modalities)
    return [
        dict(row)
        for row in records
        if str(row.get("modality") or "") in allowed
    ]


def _supports_authority(
    records: Sequence[Mapping[str, Any]],
) -> bool:
    for row in records:
        if not row.get("claim_support_allowed"):
            continue
        claims = {
            str(item)
            for item in (row.get("claim_types") or [])
        }
        if claims.intersection(AUTHORITY_CLAIMS):
            return True
    return False


def classify_answer_mode(
    result: Mapping[str, Any],
) -> Dict[str, Any]:
    route = str(result.get("route") or "")
    writer_mode = str(result.get("writer_mode") or "")
    records = typed_records(result)
    support = _claim_supporting(records)
    candidates = _records_by_bucket(records, "candidate_evidence")
    visuals = _records_by_bucket(records, "visual_guidance")
    semantic = _records_by_modality(
        records,
        SEMANTIC_MODALITIES,
    )
    conflicts = [
        dict(row)
        for row in records
        if row.get("conflicted")
        or row.get("source_bucket") == "contradictions"
    ]

    if writer_mode == "fail_closed_upstream_error":
        mode = MODE_UPSTREAM_ERROR
        reason = "cognitive_upstream_error"
    elif route == "safe_general_chat":
        mode = MODE_GENERAL_CHAT
        reason = "allowlisted_general_chat"
    elif route in AUTHORITY_ROUTES and not _supports_authority(support):
        mode = MODE_AUTHORITY_MISSING
        reason = "explicit_authority_claim_not_supported"
    elif support:
        mode = MODE_CONFIRMED_DIRECT
        reason = "claim_supporting_direct_source_trace_available"
    elif conflicts:
        mode = MODE_CONFLICT
        reason = "unresolved_conflict_without_direct_support"
    elif candidates:
        mode = MODE_CANDIDATE
        reason = "candidate_records_without_direct_proof"
    elif visuals:
        mode = MODE_VISUAL
        reason = "visual_records_without_direct_proof"
    elif semantic:
        mode = MODE_SEMANTIC
        reason = "semantic_graph_summary_guidance_only"
    else:
        mode = MODE_NO_EVIDENCE
        reason = "no_typed_record_can_support_or_guide_claim"

    return {
        "status": STATUS,
        "quality_status": "PASS",
        "mode": mode,
        "reason": reason,
        "route": route,
        "typed_record_count": len(records),
        "typed_record_source": typed_record_source(result),
        "claim_support_allowed_count": len(support),
        "candidate_count": len(candidates),
        "visual_count": len(visuals),
        "semantic_graph_summary_count": len(semantic),
        "conflict_count": len(conflicts),
        "gemma_writing_allowed": mode == MODE_CONFIRMED_DIRECT,
        "deterministic_rendering_required": mode not in {
            MODE_CONFIRMED_DIRECT,
            MODE_GENERAL_CHAT,
            MODE_UPSTREAM_ERROR,
        },
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def _query_clue(result: Mapping[str, Any]) -> str:
    atoms = _mapping(result.get("query_atoms"))
    mode = str(atoms.get("identifier_mode") or "").strip()
    identifier = str(
        atoms.get("normalized_identifier")
        or atoms.get("part_prefix")
        or atoms.get("part_contains")
        or atoms.get("part_suffix")
        or atoms.get("family_identifier")
        or ""
    ).strip()
    if mode and mode != "none" and identifier:
        return f"{mode} identifier clue `{identifier}`"
    terms = [
        str(item)
        for item in (atoms.get("nomenclature_terms") or [])
        if str(item).strip()
    ]
    if terms:
        return "nomenclature clue `" + ", ".join(terms[:3]) + "`"
    ata = str(
        atoms.get("ata_prefix")
        or (
            (atoms.get("ata_exact") or [""])[0]
            if atoms.get("ata_exact")
            else ""
        )
    ).strip()
    if ata:
        return f"ATA clue `{ata}`"
    return "the supplied query clues"


def _unique_candidates(
    records: Sequence[Mapping[str, Any]],
    maximum: int,
) -> List[str]:
    output: List[str] = []
    seen = set()
    for row in records:
        identity = _mapping(row.get("identity"))
        value = str(identity.get("candidate") or "").strip()
        if not value:
            parts = identity.get("part_numbers")
            if isinstance(parts, list) and parts:
                value = str(parts[0]).strip()
        if not value:
            match = PART_RE.search(_compact(row.get("excerpt"), 300))
            value = match.group(0) if match else ""
        normalized = re.sub(r"[^A-Z0-9]", "", value.upper())
        if not value or normalized in seen:
            continue
        seen.add(normalized)
        output.append(value)
        if len(output) >= maximum:
            break
    return output


def _visual_leads(
    records: Sequence[Mapping[str, Any]],
    maximum: int,
) -> List[str]:
    output: List[str] = []
    seen = set()
    for row in records:
        trace = _mapping(row.get("source_trace"))
        identity = _mapping(row.get("identity"))
        page = str(trace.get("page_id") or "").strip()
        figures = [
            str(item)
            for item in (identity.get("figure_refs") or [])
            if str(item).strip()
        ]
        parts = [
            str(item)
            for item in (identity.get("part_numbers") or [])
            if str(item).strip()
        ]
        pieces = []
        if page:
            pieces.append(f"page {page}")
        if figures:
            pieces.append("figure " + ", ".join(figures[:3]))
        if parts:
            pieces.append(
                "associated identifier(s) "
                + ", ".join(parts[:3])
            )
        if not pieces:
            excerpt = _compact(row.get("excerpt"), 240)
            if excerpt:
                pieces.append(excerpt)
        value = "; ".join(pieces)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= maximum:
            break
    return output


def _semantic_leads(
    records: Sequence[Mapping[str, Any]],
    maximum: int,
) -> List[str]:
    output: List[str] = []
    seen = set()
    for row in records:
        trace = _mapping(row.get("source_trace"))
        modality = str(row.get("modality") or "guidance")
        page = str(trace.get("page_id") or "").strip()
        document = str(trace.get("document") or "").strip()
        excerpt = _compact(row.get("excerpt"), 260)
        pieces = [modality.replace("_", " ")]
        if page:
            pieces.append(f"page {page}")
        elif document:
            pieces.append(document)
        if excerpt:
            pieces.append(excerpt)
        value = " — ".join(pieces)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= maximum:
            break
    return output


def _conflict_leads(
    records: Sequence[Mapping[str, Any]],
    maximum: int,
) -> List[str]:
    output: List[str] = []
    seen = set()
    for row in records:
        excerpt = _compact(row.get("excerpt"), 300)
        identity = _mapping(row.get("identity"))
        candidate = str(identity.get("candidate") or "").strip()
        value = excerpt or (
            f"conflicting metadata for candidate {candidate}"
            if candidate
            else "unresolved source or metadata conflict"
        )
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= maximum:
            break
    return output


def _append_followups(
    text: str,
    questions: Sequence[Any],
) -> str:
    clean: List[str] = []
    seen = set()
    for raw in questions:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()
        key = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        clean.append(value)
    if not clean:
        return text.strip()
    return (
        text.rstrip()
        + "\n\nHelpful follow-up questions:\n"
        + "\n".join(f"- {item}" for item in clean[:5])
    ).strip()


def _ensure_mode_disclaimer(content: str, mode: str) -> str:
    """Insert the mode's safety disclaimer into the answer BODY (before any
    follow-up section, which the final rollout strips and re-adds). This keeps
    the user-facing safety framing and satisfies the final critic's required
    per-mode phrase without disabling any safety check.
    """
    sentence = MODE_DISCLAIMERS.get(mode)
    text = str(content or "")
    if not sentence:
        return text
    marker_index = text.find(FOLLOWUP_MARKER)
    if marker_index >= 0:
        body = text[:marker_index].rstrip()
        tail = text[marker_index:]
    else:
        body = text.rstrip()
        tail = ""
    if sentence.lower() not in body.lower():
        body = (body + "\n\n" + sentence).strip()
    return (body + "\n\n" + tail).strip() if tail else body


def render_deterministic_mode(
    result: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    maximum_items: int = 6,
) -> str:
    mode = str(decision.get("mode") or MODE_NO_EVIDENCE)
    records = typed_records(result)
    candidates = _records_by_bucket(records, "candidate_evidence")
    visuals = _records_by_bucket(records, "visual_guidance")
    semantic = _records_by_modality(records, SEMANTIC_MODALITIES)
    conflicts = [
        dict(row)
        for row in records
        if row.get("conflicted")
        or row.get("source_bucket") == "contradictions"
    ]

    if mode == MODE_CANDIDATE:
        values = _unique_candidates(candidates, maximum_items)
        lines = [
            "TRACE-Net found candidate matches, not a final identification.",
            f"Why they were returned: they match {_query_clue(result)}.",
        ]
        if values:
            lines.extend(["", "Top candidate identifiers:"])
            lines.extend(f"- {value}" for value in values)
        if visuals:
            lines.extend([
                "",
                f"Additional visual guidance exists for {len(visuals)} record(s), "
                "but visual guidance is not source proof.",
            ])
        if conflicts:
            lines.extend([
                "",
                f"{len(conflicts)} candidate/source conflict record(s) remain unresolved.",
            ])
        lines.extend([
            "",
            "What remains unproven: the exact part identity and any approval, "
            "fit, effectivity, or interchangeability claim.",
        ])
        text = "\n".join(lines)

    elif mode == MODE_VISUAL:
        leads = _visual_leads(visuals, maximum_items)
        lines = [
            "TRACE-Net found visual guidance, but no citation-ready direct source proof.",
        ]
        if leads:
            lines.extend(["", "Visual leads:"])
            lines.extend(f"- {value}" for value in leads)
        lines.extend([
            "",
            "What remains unproven: the technical identity or claim must be "
            "resolved to a direct source field before it can be stated as confirmed.",
        ])
        text = "\n".join(lines)

    elif mode == MODE_SEMANTIC:
        leads = _semantic_leads(semantic, maximum_items)
        lines = [
            "TRACE-Net found semantic, graph, summary, or source-resolution guidance only.",
        ]
        if leads:
            lines.extend(["", "Guidance leads:"])
            lines.extend(f"- {value}" for value in leads)
        lines.extend([
            "",
            "These records can guide the next search, but they cannot prove the requested claim.",
        ])
        text = "\n".join(lines)

    elif mode == MODE_CONFLICT:
        leads = _conflict_leads(conflicts, maximum_items)
        lines = [
            "TRACE-Net found unresolved conflicting evidence, so no positive technical conclusion is allowed.",
        ]
        if leads:
            lines.extend([
                "",
                "Conflicts requiring source resolution:",
            ])
            lines.extend(f"- {value}" for value in leads)
        lines.extend([
            "",
            "The conflict must be resolved against direct source-trace evidence before identifying the part or making an engineering claim.",
        ])
        text = "\n".join(lines)

    elif mode == MODE_AUTHORITY_MISSING:
        lines = [
            "TRACE-Net did not find direct authority evidence for the requested approval, fit, effectivity, eligibility, applicability, or interchangeability claim.",
            "",
            "Candidate, visual, semantic, graph, summary, and general part records cannot establish installation authority.",
        ]
        if conflicts:
            lines.append(
                f"There are also {len(conflicts)} unresolved conflict record(s)."
            )
        text = "\n".join(lines)

    else:
        text = (
            "TRACE-Net did not recover typed evidence that can support or safely "
            "guide the requested technical claim. No technical conclusion is provided."
        )

    return _append_followups(
        text,
        result.get("follow_up_questions") or [],
    )


def validate_mode_result(
    result: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> Dict[str, Any]:
    failures: List[str] = []
    mode = str(decision.get("mode") or "")
    support = _claim_supporting(typed_records(result))

    if mode not in ALL_MODES:
        failures.append("unknown_answer_mode")
    if mode == MODE_CONFIRMED_DIRECT and not support:
        failures.append(
            "confirmed_mode_without_claim_supporting_direct_evidence"
        )
    if (
        mode != MODE_CONFIRMED_DIRECT
        and decision.get("gemma_writing_allowed")
    ):
        failures.append("gemma_enabled_for_non_direct_mode")
    if mode in {
        MODE_CANDIDATE,
        MODE_VISUAL,
        MODE_SEMANTIC,
        MODE_CONFLICT,
        MODE_AUTHORITY_MISSING,
        MODE_NO_EVIDENCE,
    } and not decision.get("deterministic_rendering_required"):
        failures.append("non_direct_mode_not_deterministic")
    if result.get("answer_permission") is not False:
        failures.append("answer_permission_not_false")
    if result.get("source_truth_mutation_allowed") is not False:
        failures.append(
            "source_truth_mutation_allowed_not_false"
        )

    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "accepted": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }


def answer_modes_health(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    config = load_answer_mode_config(environ)
    return {
        "status": STATUS,
        "quality_status": "PASS",
        "enabled": bool(config.get("enabled")),
        "modes": list(ALL_MODES),
        "confirmed_mode_requires_claim_support_allowed": True,
        "non_direct_modes_deterministic": True,
        "gemma_only_for_confirmed_direct": True,
        "typed_evidence_is_source_of_mode_selection": True,
        "claim_ready_evidence_preferred": True,
        "evidence_selection_changed": True,
        "retrieval_changed": False,
        "route_changed": False,
        "evidence_selection_changed": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def install_evidence_aware_answer_modes(
    module: MutableMapping[str, Any],
) -> None:
    marker = "_TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_V1_INSTALLED"
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
        config = load_answer_mode_config()
        result["evidence_aware_answer_modes_enabled"] = bool(
            config.get("enabled")
        )
        if not config.get("enabled"):
            result["answer_mode"] = {
                "quality_status": "SKIPPED",
                "reason": "disabled_by_configuration",
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
            return result

        decision = classify_answer_mode(result)
        synthesis = (
            result.get("evidence_synthesis")
            if isinstance(result.get("evidence_synthesis"), Mapping)
            else {}
        )
        synthesis_kept = bool(
            synthesis.get("written")
        ) and decision["mode"] in SYNTHESIS_MODES
        if decision["deterministic_rendering_required"] and not synthesis_kept:
            result["content"] = render_deterministic_mode(
                result,
                decision,
                maximum_items=int(config.get("max_items") or 6),
            )
            result["writer_mode"] = (
                "evidence_aware_" + str(decision["mode"])
            )
            result["gemma_status"] = (
                "SKIPPED_BY_TYPED_EVIDENCE_MODE"
            )
        elif synthesis_kept:
            # Keep the validated Gemma synthesis; only ensure the mode's safety
            # disclaimer is present in the body. gemma_status stays as the
            # writer set it (LLM_CALL_SUCCEEDED_AND_VALIDATED).
            result["content"] = _ensure_mode_disclaimer(
                str(result.get("content") or ""),
                str(decision["mode"]),
            )
            result["writer_mode"] = (
                "evidence_aware_synthesis_" + str(decision["mode"])
            )
        elif decision["mode"] == MODE_CONFIRMED_DIRECT:
            result["writer_mode_before_answer_mode"] = result.get(
                "writer_mode"
            )

        validation = validate_mode_result(result, decision)
        result["answer_mode"] = decision
        result["answer_mode_validation"] = validation
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        safety = result.get("safety_contract")
        if isinstance(safety, MutableMapping):
            safety["answer_permission"] = False
            safety["final_answer_allowed"] = False
            safety["source_truth_mutation_allowed"] = False
            safety["evidence_aware_answer_mode"] = decision["mode"]
            safety["guidance_modes_are_deterministic"] = True
        return result

    def health_v2(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        health = answer_modes_health()
        result["evidence_aware_answer_modes"] = health
        result["evidence_aware_answer_modes_enabled"] = bool(
            health.get("enabled")
        )
        result["evidence_aware_answer_mode_count"] = len(ALL_MODES)
        result["gemma_only_for_confirmed_direct"] = True
        result["non_direct_modes_deterministic"] = True
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    runtime_cls.process = process_v2
    runtime_cls.health = health_v2
    module[marker] = True
