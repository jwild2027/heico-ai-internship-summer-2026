"""TRACE-Net Engineering Engram Memory Layers v1.

Artifact-only taxonomy builder for TRACE-Net Engram records.

The layer taxonomy is deliberately behavior guidance, not source truth.  It can
shape answer style, route interpretation, critique, and repair behavior, but it
must never prove manual facts, mutate source truth, or grant answer permission.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_engram_memory_layers_v1"
VERSION = "v1"
STATUS_BUILT = "TRACE_NET_ENGINEERING_ENGRAM_MEMORY_LAYERS_BUILT"
STATUS_CHECKED = "TRACE_NET_ENGINEERING_ENGRAM_MEMORY_LAYERS_CHECKED"
SAFETY_CONTRACT = "no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission"

MEMORY_LAYERS: Tuple[str, ...] = (
    "working_memory",
    "semantic_memory",
    "procedural_memory",
    "episodic_memory",
    "trait_memory",
    "critic_memory",
)

LAYER_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "working_memory": {
        "description": "Current question, current context pack, and current proof citations used only at answer time.",
        "runtime_role": "temporary_answer_state",
        "proof_role": "current_proof_context_only",
        "allowed_sources": ["current_question", "context_pack", "proof_context", "answer_citations"],
        "must_not_persist_source_truth": True,
    },
    "semantic_memory": {
        "description": "Stable route and evidence-meaning knowledge, such as what visual, OCR, table, and summary records can and cannot prove.",
        "runtime_role": "route_meaning_guidance",
        "proof_role": "guidance_only",
        "allowed_sources": ["reviewed_policy", "route_contract", "eval_lesson", "engram_core"],
        "must_not_persist_source_truth": True,
    },
    "procedural_memory": {
        "description": "If/then behavior rules that control boundaries such as interchangeability, replacement approval, fit, effectivity, and unknown-part responses.",
        "runtime_role": "answer_boundary_control",
        "proof_role": "guidance_only",
        "allowed_sources": ["reviewed_policy", "safety_rule", "eval_lesson", "engram_core"],
        "must_not_persist_source_truth": True,
    },
    "episodic_memory": {
        "description": "Past runs, smoke-test outcomes, failures, repairs, and regression lessons.",
        "runtime_role": "failure_recall_and_regression_prevention",
        "proof_role": "guidance_only",
        "allowed_sources": ["eval_result", "smoke_test", "repair_note", "engram_core"],
        "must_not_persist_source_truth": True,
    },
    "trait_memory": {
        "description": "Stable engineering behavior profile: cautious, source-trace-first, useful, calm, and not overclaiming.",
        "runtime_role": "consistent_engineering_style",
        "proof_role": "guidance_only",
        "allowed_sources": ["reviewed_trait", "style_rule", "answer_shape", "engram_core"],
        "must_not_persist_source_truth": True,
    },
    "critic_memory": {
        "description": "Self-RAG and CRAG critique/repair lessons, including safe-but-too-generic drafts, retry patterns, and repair examples.",
        "runtime_role": "draft_critique_and_repair",
        "proof_role": "guidance_only",
        "allowed_sources": ["critic_lesson", "repair_lesson", "eval_failure", "engram_core"],
        "must_not_persist_source_truth": True,
    },
}

DEFAULT_LAYER_SEED_ATOMS: List[Dict[str, Any]] = [
    {
        "atom_id": "working_current_question_context_pack_citations_v1",
        "memory_layer": "working_memory",
        "memory_type": "working_memory",
        "title": "Current answer working set",
        "trigger": ["every answer"],
        "rule": "Use the current user question, current context pack, and current proof citations as the only answer-time factual working set.",
        "allowed_behavior": "Ground the draft in current proof_context and citation labels.",
        "forbidden_behavior": "Do not import proof from old Engram memories or summaries.",
        "proof_role": "current_proof_context_only",
        "activation_status": "active",
        "source": "h17_seed_taxonomy",
    },
    {
        "atom_id": "semantic_visual_link_vs_ocr_nomenclature_v1",
        "memory_layer": "semantic_memory",
        "memory_type": "semantic_memory",
        "title": "Visual link versus OCR nomenclature",
        "trigger": ["visual route", "OCR nomenclature", "figure-to-part identity"],
        "rule": "visual_figure_link establishes figure-to-part identity; OCR nomenclature provides source-trace line-text proof for the part name.",
        "allowed_behavior": "Explain the route distinction when answering pipeline or evidence questions.",
        "forbidden_behavior": "Do not treat visual observations alone as clean nomenclature proof unless source-trace-ready text supports it.",
        "proof_role": "guidance_only",
        "activation_status": "active",
        "source": "h17_seed_taxonomy",
    },
    {
        "atom_id": "procedural_no_interchangeability_without_authority_v1",
        "memory_layer": "procedural_memory",
        "memory_type": "procedural_memory",
        "title": "No interchangeability without explicit authority",
        "trigger": ["interchangeable", "replacement", "substitute", "compatible", "approved replacement"],
        "rule": "Require explicit source authority before saying parts are interchangeable or approved replacements.",
        "allowed_behavior": "Say what TRACE-Net can prove, then state the unproven approval boundary.",
        "forbidden_behavior": "Do not infer approval from shared nomenclature, nearby figures, graph proximity, or part-family similarity.",
        "proof_role": "guidance_only",
        "activation_status": "active",
        "source": "h17_seed_taxonomy",
    },
    {
        "atom_id": "episodic_h13_generic_not_proven_repair_v1",
        "memory_layer": "episodic_memory",
        "memory_type": "episodic_memory",
        "title": "Repair generic not-proven answers",
        "trigger": ["not proven", "pipeline recovery", "known eval failure"],
        "rule": "H13 overused generic not-proven wording; repairs should still explain what evidence is proven and why the requested claim is out of scope.",
        "allowed_behavior": "Use can-prove / cannot-prove / evidence / limits shape.",
        "forbidden_behavior": "Do not answer with a generic refusal when proof_context supports a useful limited explanation.",
        "proof_role": "guidance_only",
        "activation_status": "active",
        "source": "h17_seed_taxonomy",
    },
    {
        "atom_id": "trait_cautious_source_trace_helpful_v1",
        "memory_layer": "trait_memory",
        "memory_type": "trait_memory",
        "title": "Cautious source-trace helpfulness",
        "trigger": ["every answer", "engineering answer style"],
        "rule": "Behave as a cautious, source-trace-first engineering analyst who is helpful without overclaiming.",
        "allowed_behavior": "Use calm engineering confidence, explicit evidence, and explicit limits.",
        "forbidden_behavior": "Do not become a generic disclaimer machine or invent approvals.",
        "proof_role": "guidance_only",
        "activation_status": "active",
        "source": "h17_seed_taxonomy",
    },
    {
        "atom_id": "critic_safe_but_too_generic_repair_v1",
        "memory_layer": "critic_memory",
        "memory_type": "critic_memory",
        "title": "Safe but too generic repair",
        "trigger": ["Self-RAG", "CRAG", "draft critique", "safe but too generic"],
        "rule": "If an answer is safe but too generic, retrieve a repair pattern before regenerating and add the specific route/evidence explanation.",
        "allowed_behavior": "Critique for missing proof explanation, missing limits, or missing route distinction.",
        "forbidden_behavior": "Do not repair by adding unsupported claims or treating Engram memory as proof.",
        "proof_role": "guidance_only",
        "activation_status": "active",
        "source": "h17_seed_taxonomy",
    },
]

UNSAFE_CLAIM_PATTERNS: Tuple[str, ...] = (
    r"\banswer_permission\s*[:=]\s*true\b",
    r"\bsource_truth_mutation_allowed\s*[:=]\s*true\b",
    r"\bpostgres_write_attempt\s*[:=]\s*[1-9]",
    r"\bqdrant_write_attempt\s*[:=]\s*[1-9]",
    r"\bopensearch_write_attempt\s*[:=]\s*[1-9]",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path | str, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _lower_text(*values: Any) -> str:
    parts: List[str] = []
    for value in values:
        if isinstance(value, Mapping):
            parts.append(json.dumps(value, sort_keys=True, ensure_ascii=False))
        elif isinstance(value, (list, tuple)):
            parts.extend(str(v) for v in value)
        elif value is not None:
            parts.append(str(value))
    return "\n".join(parts).lower()


def extract_engram_atoms(core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return likely Engram atom records from a flexible H15-style core JSON."""
    candidate_keys = (
        "engram_atoms",
        "atoms",
        "records",
        "memory_atoms",
        "policy_traits",
        "style_traits",
        "failure_memories",
        "critic_traits",
        "repair_traits",
    )
    atoms: List[Dict[str, Any]] = []
    for key in candidate_keys:
        value = core.get(key)
        if isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, Mapping):
                    rec = dict(item)
                else:
                    rec = {"value": item}
                rec.setdefault("source_key", key)
                rec.setdefault("source_index", idx)
                atoms.append(rec)

    # Some cores may put the list under summary/details wrappers.
    for wrapper_key in ("engram_core", "data", "manifest"):
        wrapper = core.get(wrapper_key)
        if isinstance(wrapper, Mapping):
            for atom in extract_engram_atoms(wrapper):
                atom.setdefault("source_wrapper", wrapper_key)
                atoms.append(atom)

    # De-duplicate by atom_id or stable content hash.
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for atom in atoms:
        key = str(atom.get("atom_id") or atom.get("id") or stable_hash(atom))
        if key in seen:
            continue
        seen.add(key)
        out.append(atom)
    return out


def infer_memory_layer(atom: Mapping[str, Any]) -> str:
    text = _lower_text(
        atom.get("memory_layer"),
        atom.get("memory_type"),
        atom.get("atom_id"),
        atom.get("id"),
        atom.get("title"),
        atom.get("trait"),
        atom.get("traits"),
        atom.get("tags"),
        atom.get("category"),
        atom.get("source_key"),
        atom.get("rule"),
        atom.get("description"),
        atom.get("failure_pattern"),
        atom.get("repair_pattern"),
    )
    explicit = str(atom.get("memory_layer") or atom.get("memory_type") or "").strip().lower()
    explicit = explicit.replace("-", "_").replace(" ", "_")
    if explicit in MEMORY_LAYERS:
        return explicit

    if any(k in text for k in ("working_memory", "working memory", "current question", "context pack", "proof_context")):
        return "working_memory"
    if any(k in text for k in ("critic", "self-rag", "self_rag", "crag", "repair", "fallback", "retry", "too generic")):
        return "critic_memory"
    if any(k in text for k in ("episodic", "episode", "h13", "h14", "h16", "eval", "smoke", "failure", "regression")):
        return "episodic_memory"
    if any(k in text for k in ("procedural", "policy", "rule", "if user", "interchange", "replacement", "effectivity", "fit", "installation")):
        return "procedural_memory"
    if any(k in text for k in ("trait", "style", "tone", "answer shape", "cautious", "helpful", "confidence")):
        return "trait_memory"
    if any(k in text for k in ("semantic", "route", "visual", "ocr", "table", "nomenclature", "summary", "graph", "leiden")):
        return "semantic_memory"
    return "semantic_memory"


def infer_proof_role(atom: Mapping[str, Any], layer: str) -> str:
    proof_role = str(atom.get("proof_role") or "").strip().lower()
    if proof_role:
        return proof_role
    if layer == "working_memory":
        return "current_proof_context_only"
    return "guidance_only"


def normalize_atom(atom: Mapping[str, Any], *, source_core_path: str = "") -> Dict[str, Any]:
    layer = infer_memory_layer(atom)
    atom_id = str(atom.get("atom_id") or atom.get("id") or f"h17_imported_{stable_hash(atom)}")
    proof_role = infer_proof_role(atom, layer)
    normalized: Dict[str, Any] = {
        "atom_id": atom_id,
        "memory_layer": layer,
        "memory_type": str(atom.get("memory_type") or layer),
        "title": str(atom.get("title") or atom.get("name") or atom_id),
        "trigger": _as_list(atom.get("trigger") or atom.get("triggers") or atom.get("intent_triggers") or atom.get("tags")),
        "rule": str(atom.get("rule") or atom.get("description") or atom.get("guidance") or atom.get("content") or atom.get("value") or "").strip(),
        "allowed_behavior": str(atom.get("allowed_behavior") or atom.get("positive_behavior") or atom.get("do") or "").strip(),
        "forbidden_behavior": str(atom.get("forbidden_behavior") or atom.get("negative_behavior") or atom.get("do_not") or "").strip(),
        "proof_role": proof_role,
        "activation_status": str(atom.get("activation_status") or atom.get("status") or "active"),
        "source": str(atom.get("source") or atom.get("source_key") or "engram_core"),
        "source_core_path": source_core_path,
        "source_hash": stable_hash(atom),
    }
    # Preserve compact provenance/debug metadata without trusting it as proof.
    for key in ("category", "traits", "trait", "memory_id", "eval_id", "question_id", "grade", "repair_pattern", "failure_pattern"):
        if key in atom and atom.get(key) not in (None, ""):
            normalized[key] = atom.get(key)
    return normalized


def seed_layer_atoms() -> List[Dict[str, Any]]:
    return [dict(a) for a in DEFAULT_LAYER_SEED_ATOMS]



def _collect_query_planner_records(planner: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = planner.get("records")
    if isinstance(records, list):
        return [dict(r) for r in records if isinstance(r, Mapping)]
    record = planner.get("record")
    if isinstance(record, Mapping):
        return [dict(record)]
    return []


def _profile_triggers(profile: Mapping[str, Any]) -> List[str]:
    clues = profile.get("extracted_engineer_clues") if isinstance(profile.get("extracted_engineer_clues"), Mapping) else {}
    filters = profile.get("facet_filters") if isinstance(profile.get("facet_filters"), Mapping) else {}

    values: List[str] = [
        "engineer query clarification",
        "part number",
        "partial identifier",
        "NHA",
        "ATA",
        "fleet",
        "IPC",
        "CMM",
        "SB",
        "eligibility",
        "applicability",
        "effectivity",
    ]

    for key in (
        "part_number_candidates",
        "partial_identifier_candidates",
        "nha_candidates",
        "requested_doc_types",
        "engine_candidates",
        "fleet_candidates",
        "ata_candidates",
        "part_description_candidates",
    ):
        for value in _as_list(clues.get(key)):
            if value:
                values.append(str(value))

    for key in ("document_type", "evidence_language", "fleet_or_aircraft", "ata"):
        for value in _as_list(filters.get(key)):
            if value:
                values.append(str(value))

    seen = set()
    out: List[str] = []
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out[:40]


def engineer_query_clarification_profile_to_atom(
    *,
    profile: Mapping[str, Any],
    question: str = "",
    source_query_planner_path: str = "",
    source_record_index: int = 0,
) -> Dict[str, Any]:
    """Convert a planner clarification profile into a guidance-only Engram atom."""
    stable_payload = {
        "question": question,
        "profile_type": profile.get("profile_type"),
        "extracted_engineer_clues": profile.get("extracted_engineer_clues"),
        "facet_filters": profile.get("facet_filters"),
        "risk_flags": profile.get("risk_flags"),
    }
    atom_id = "working_engineer_query_clarification_" + stable_hash(stable_payload)[:16]

    payload = {
        "question": question,
        "profile_type": profile.get("profile_type") or "engineer_query_clarification_profile_v1",
        "extracted_engineer_clues": profile.get("extracted_engineer_clues") or {},
        "facet_filters": profile.get("facet_filters") or {},
        "clarifying_questions": profile.get("clarifying_questions") or [],
        "risk_flags": profile.get("risk_flags") or [],
        "recommended_first_pass": profile.get("recommended_first_pass") or [],
    }

    return {
        "atom_id": atom_id,
        "memory_layer": "working_memory",
        "memory_type": "engineer_query_clarification",
        "proof_role": "guidance_only",
        "title": "Engineer query clarification profile",
        "rule": (
            "Use extracted engineer clues, facet filters, clarifying questions, "
            "and risk flags to narrow retrieval before answering. This is not "
            "source proof; manual/source claims still require current proof_context citations."
        ),
        "triggers": _profile_triggers(profile),
        "payload": payload,
        "source_module": "trace_net_engineering_query_planner_v1",
        "source_query_planner_path": source_query_planner_path,
        "source_record_index": source_record_index,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "can_be_used_as_proof": False,
        "safety": {
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "can_be_used_as_proof": False,
        },
    }


def extract_engineer_query_clarification_atoms(
    query_planner_manifests: Optional[Sequence[Mapping[str, Any]]] = None,
    *,
    source_paths: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    atoms: List[Dict[str, Any]] = []
    manifests = list(query_planner_manifests or [])
    paths = list(source_paths or [])

    for manifest_index, planner in enumerate(manifests):
        source_path = paths[manifest_index] if manifest_index < len(paths) else ""
        for record_index, record in enumerate(_collect_query_planner_records(planner)):
            profile = record.get("engineer_clarification_profile")
            if not isinstance(profile, Mapping):
                continue
            if profile.get("profile_type") != "engineer_query_clarification_profile_v1":
                continue
            atoms.append(engineer_query_clarification_profile_to_atom(
                profile=profile,
                question=str(record.get("question") or planner.get("question") or ""),
                source_query_planner_path=source_path,
                source_record_index=record_index,
            ))

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for atom in atoms:
        atom_id = str(atom.get("atom_id") or "")
        if atom_id and atom_id not in seen:
            seen.add(atom_id)
            deduped.append(atom)
    return deduped

def build_layered_atoms(
    core: Mapping[str, Any],
    *,
    source_core_path: str = "",
    include_seed_atoms: bool = True,
    query_planner_manifests: Optional[Sequence[Mapping[str, Any]]] = None,
    query_planner_source_paths: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    atoms = [normalize_atom(a, source_core_path=source_core_path) for a in extract_engram_atoms(core)]
    atoms.extend(extract_engineer_query_clarification_atoms(
        query_planner_manifests,
        source_paths=query_planner_source_paths,
    ))
    if include_seed_atoms:
        existing = {a["atom_id"] for a in atoms}
        for seed in seed_layer_atoms():
            if seed["atom_id"] not in existing:
                atoms.append(seed)
    return atoms


def group_layer_counts(atoms: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts = {layer: 0 for layer in MEMORY_LAYERS}
    for atom in atoms:
        layer = str(atom.get("memory_layer") or "")
        if layer in counts:
            counts[layer] += 1
    return counts


def unsafe_findings(atoms: Sequence[Mapping[str, Any]], manifest: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for atom in atoms:
        text = _lower_text(atom)
        for pattern in UNSAFE_CLAIM_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                findings.append({
                    "atom_id": atom.get("atom_id"),
                    "memory_layer": atom.get("memory_layer"),
                    "pattern": pattern,
                    "finding_type": "unsafe_memory_atom_pattern",
                })
    if manifest:
        summary = manifest.get("summary", {}) if isinstance(manifest.get("summary"), Mapping) else {}
        safety_keys = (
            "answer_permission_count",
            "source_truth_mutation_allowed_count",
            "postgres_write_attempt_count",
            "qdrant_write_attempt_count",
            "opensearch_write_attempt_count",
            "opensearch_upload_attempt_count",
            "write_attempt_count",
            "unsafe_record_count",
        )
        for key in safety_keys:
            try:
                value = int(summary.get(key, manifest.get(key, 0)) or 0)
            except Exception:
                value = 0
            if value:
                findings.append({"finding_type": "unsafe_manifest_counter", "counter": key, "value": value})
    return findings


def validate_layered_manifest(
    manifest: Mapping[str, Any],
    *,
    min_atoms: int = 6,
    require_all_layers: bool = True,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = True,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    errors: List[str] = []
    atoms = manifest.get("memory_atoms") or manifest.get("records") or []
    if not isinstance(atoms, list):
        errors.append("memory_atoms must be a list")
        atoms = []
    if len(atoms) < min_atoms:
        errors.append(f"memory atom count below minimum: {len(atoms)} < {min_atoms}")

    layer_counts = group_layer_counts([a for a in atoms if isinstance(a, Mapping)])
    if require_all_layers:
        missing = [layer for layer, count in layer_counts.items() if count <= 0]
        if missing:
            errors.append("missing required memory layers: " + ",".join(missing))

    for idx, atom in enumerate(atoms):
        if not isinstance(atom, Mapping):
            errors.append(f"atom {idx} is not an object")
            continue
        layer = str(atom.get("memory_layer") or "")
        if layer not in MEMORY_LAYERS:
            errors.append(f"atom {atom.get('atom_id', idx)} has invalid memory_layer={layer!r}")
        proof_role = str(atom.get("proof_role") or "")
        if not proof_role:
            errors.append(f"atom {atom.get('atom_id', idx)} missing proof_role")
        if layer != "working_memory" and proof_role != "guidance_only":
            errors.append(f"atom {atom.get('atom_id', idx)} non-working memory must be guidance_only, got {proof_role!r}")
        if layer == "working_memory" and proof_role not in ("current_proof_context_only", "guidance_only"):
            errors.append(f"working atom {atom.get('atom_id', idx)} has invalid proof_role={proof_role!r}")
        if atom.get("answer_permission") is True or atom.get("answer_permission_allowed") is True:
            errors.append(f"atom {atom.get('atom_id', idx)} grants answer permission")

    findings = unsafe_findings([a for a in atoms if isinstance(a, Mapping)], manifest)
    if len(findings) > max_unsafe:
        errors.append(f"unsafe finding count above maximum: {len(findings)} > {max_unsafe}")

    summary = manifest.get("summary", {}) if isinstance(manifest.get("summary"), Mapping) else {}
    if require_no_answer_permission:
        answer_permission_count = int(summary.get("answer_permission_count", manifest.get("answer_permission_count", 0)) or 0)
        if answer_permission_count:
            errors.append(f"answer_permission_count must be 0, got {answer_permission_count}")

    metrics = {
        "memory_atom_count": len(atoms),
        "layer_counts": layer_counts,
        "unsafe_finding_count": len(findings),
        "unsafe_findings": findings,
    }
    return not errors, errors, metrics



def load_query_planner_manifests(paths: Optional[Sequence[Any]] = None):
    manifests: List[Dict[str, Any]] = []
    source_paths: List[str] = []
    for raw_path in paths or []:
        p = Path(raw_path)
        data = load_json(p)
        if isinstance(data, Mapping):
            manifests.append(dict(data))
            source_paths.append(str(p))
    return manifests, source_paths

def build_memory_layer_manifest(
    *,
    engram_core_path: Path | str,
    output_dir: Path | str,
    include_seed_atoms: bool = True,
    min_atoms: int = 6,
    require_all_layers: bool = True,
    max_unsafe: int = 0,    query_planner_paths: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    core_path = Path(engram_core_path)
    out_dir = Path(output_dir)
    core = load_json(core_path)
    query_planner_manifests, query_planner_source_paths = load_query_planner_manifests(query_planner_paths)
    atoms = build_layered_atoms(core if isinstance(core, Mapping) else {}, source_core_path=str(core_path), include_seed_atoms=include_seed_atoms)
    atoms.extend(extract_engineer_query_clarification_atoms(
        query_planner_manifests,
        source_paths=query_planner_source_paths,
    ))
    layer_counts = group_layer_counts(atoms)
    generated_at = utc_now_iso()

    manifest: Dict[str, Any] = {
        "status": STATUS_BUILT,
        "module": MODULE,
        "version": VERSION,
        "generated_at": generated_at,
        "quality_status": "UNKNOWN",
        "safety_contract": SAFETY_CONTRACT,
        "source_engram_core_path": str(core_path),
        "taxonomy": {
            "memory_layers": list(MEMORY_LAYERS),
            "layer_definitions": LAYER_DEFINITIONS,
            "proof_boundary": "Engram memory is behavior guidance only. Manual facts must still come from current proof_context citations.",
            "working_memory_note": "Working memory can carry current proof citations at answer time but is not persisted as source truth by this artifact.",
        },
        "memory_atoms": atoms,
        "summary": {
            "module": MODULE,
            "version": VERSION,
            "memory_layer_count": len(MEMORY_LAYERS),
            "memory_atom_count": len(atoms),
            "layer_counts": layer_counts,
            "source_engram_atom_count": len(extract_engram_atoms(core if isinstance(core, Mapping) else {})),
            "seed_atom_count": len(DEFAULT_LAYER_SEED_ATOMS) if include_seed_atoms else 0,
            "engram_memory_guidance_only_count": sum(1 for a in atoms if a.get("proof_role") == "guidance_only"),
            "working_memory_current_proof_context_count": sum(1 for a in atoms if a.get("proof_role") == "current_proof_context_only"),
            "engineer_query_clarification_atom_count": sum(1 for a in atoms if a.get("memory_type") == "engineer_query_clarification"),
            "source_query_planner_count": len(query_planner_manifests),
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": 0,
        },
    }

    passed, errors, metrics = validate_layered_manifest(
        manifest,
        min_atoms=min_atoms,
        require_all_layers=require_all_layers,
        max_unsafe=max_unsafe,
    )
    manifest["quality_status"] = "PASS" if passed else "FAIL"
    manifest["quality_errors"] = errors
    manifest["summary"].update(metrics)

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "trace_net_engineering_engram_memory_layers_v1.json"
    write_json(manifest_path, manifest)
    return manifest


def check_memory_layer_manifest(
    *,
    memory_layers_path: Path | str,
    min_atoms: int = 6,
    require_all_layers: bool = True,
    max_unsafe: int = 0,
    require_quality_pass: bool = False,
) -> Dict[str, Any]:
    path = Path(memory_layers_path)
    manifest = load_json(path)
    passed, errors, metrics = validate_layered_manifest(
        manifest if isinstance(manifest, Mapping) else {},
        min_atoms=min_atoms,
        require_all_layers=require_all_layers,
        max_unsafe=max_unsafe,
    )
    if require_quality_pass and manifest.get("quality_status") != "PASS":
        passed = False
        errors.append(f"input quality_status is not PASS: {manifest.get('quality_status')!r}")
    result = {
        "status": STATUS_CHECKED,
        "module": MODULE,
        "version": VERSION,
        "quality_status": "PASS" if passed else "FAIL",
        "checked_path": str(path),
        "safety_contract": SAFETY_CONTRACT,
        "summary": {
            "module": MODULE,
            "version": VERSION,
            **metrics,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": 0,
        },
        "quality_errors": errors,
    }
    check_path = path.with_name("trace_net_engineering_engram_memory_layers_v1_quality_check.json")
    write_json(check_path, result)
    return result
