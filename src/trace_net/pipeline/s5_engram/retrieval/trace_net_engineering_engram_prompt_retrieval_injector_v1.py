"""TRACE-Net Engineering Engram Prompt Retrieval Injector v1.

Artifact-only prompt guidance builder for H19 Engram retrieval records.

H20 does not call an LLM, Qdrant, Postgres, OpenSearch, or any live service.
It converts H19 local retrieval results into compact prompt guidance blocks that
can later be injected into the engineering LLM prompt.  The generated guidance is
explicitly behavior guidance only; it is never proof and never grants answer
permission.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

MODULE = "trace_net_engineering_engram_prompt_retrieval_injector_v1"
VERSION = "v1"

SAFETY_CONTRACT = {
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_read_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
    "opensearch_upload_attempt": False,
    "live_qdrant_read_attempted": False,
    "live_qdrant_write_attempted": False,
    "engram_guidance_only": True,
}

REQUIRED_LAYERS = [
    "working_memory",
    "semantic_memory",
    "procedural_memory",
    "episodic_memory",
    "trait_memory",
    "critic_memory",
]

ALLOWED_PROOF_ROLES = {"guidance_only", "current_proof_context_only"}

_LAYER_PRIORITY = {
    "procedural_memory": 0,
    "semantic_memory": 1,
    "trait_memory": 2,
    "critic_memory": 3,
    "episodic_memory": 4,
    "working_memory": 5,
}

_WHITESPACE_RE = re.compile(r"\s+")


def _clean_text(text: Any, limit: int = 520) -> str:
    raw = _WHITESPACE_RE.sub(" ", str(text or "")).strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 3)].rstrip() + "..."


def _counter(values: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for value in values:
        if not value:
            continue
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


def _write_json(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")


def load_vector_retriever(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _result_rule_text(item: Mapping[str, Any]) -> str:
    # H19 only guarantees text_preview.  Keep extraction conservative and compact.
    for key in ("rule", "text_preview", "text_for_embedding", "title"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_text(value, 650)
    return _clean_text(item.get("atom_id"), 200)


def normalize_retrieved_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    proof_role = str(item.get("proof_role") or "guidance_only")
    memory_layer = str(item.get("memory_layer") or "unknown")
    return {
        "atom_id": str(item.get("atom_id") or "unknown_atom"),
        "point_id": str(item.get("point_id") or ""),
        "rank": int(item.get("rank") or 0),
        "memory_layer": memory_layer,
        "proof_role": proof_role,
        "title": str(item.get("title") or item.get("atom_id") or ""),
        "retrieval_score": float(item.get("retrieval_score") or 0.0),
        "similarity_score": float(item.get("similarity_score") or 0.0),
        "keyword_overlap_score": float(item.get("keyword_overlap_score") or 0.0),
        "text_preview": _result_rule_text(item),
        "answer_permission": bool(item.get("answer_permission") or False),
        "source_truth_mutation_allowed": bool(item.get("source_truth_mutation_allowed") or False),
        "qdrant_write_attempt": bool(item.get("qdrant_write_attempt") or False),
    }


def select_prompt_atoms(
    retrieved_items: Sequence[Mapping[str, Any]],
    *,
    max_atoms: int = 4,
    require_guidance_only: bool = True,
) -> List[Dict[str, Any]]:
    """Select compact prompt atoms from H19 retrieved items.

    Selection preserves retrieval quality while preventing unsafe or proof-confused
    atoms from entering prompt guidance.  The final list is sorted by retrieval
    score/rank, not by memory layer, so H19 retrieval remains the source of order.
    """
    normalized = [normalize_retrieved_item(item) for item in retrieved_items if isinstance(item, Mapping)]
    candidates: List[Dict[str, Any]] = []
    for item in normalized:
        if item.get("answer_permission"):
            continue
        if item.get("source_truth_mutation_allowed"):
            continue
        if item.get("qdrant_write_attempt"):
            continue
        if require_guidance_only and item.get("proof_role") not in ALLOWED_PROOF_ROLES:
            continue
        candidates.append(item)

    candidates.sort(key=lambda x: (x.get("retrieval_score", 0.0), -_LAYER_PRIORITY.get(str(x.get("memory_layer")), 99), -int(x.get("rank") or 0)), reverse=True)
    selected: List[Dict[str, Any]] = []
    seen_atoms = set()
    for item in candidates:
        atom_id = item.get("atom_id")
        if atom_id in seen_atoms:
            continue
        seen_atoms.add(atom_id)
        selected.append(item)
        if len(selected) >= max(1, int(max_atoms or 4)):
            break
    return selected


def build_prompt_guidance_block(
    *,
    query_id: str,
    task_type: str,
    query_text: str,
    selected_atoms: Sequence[Mapping[str, Any]],
    max_prompt_chars: int = 1800,
) -> str:
    lines = [
        "TRACE-NET ENGRAM RETRIEVAL GUIDANCE — BEHAVIOR ONLY, NOT PROOF",
        f"query_id: {query_id}",
        f"task_type: {task_type or 'unknown'}",
        f"query: {_clean_text(query_text, 260)}",
        "",
        "Use these retrieved Engram atoms to shape answer behavior only. Do not use Engram memory as manual evidence.",
        "Manual/source claims still require current proof_context citations from TRACE-Net.",
        "",
        "Retrieved behavior atoms:",
    ]
    for atom in selected_atoms:
        rule = _clean_text(atom.get("text_preview"), 420)
        lines.append(
            f"- [{atom.get('atom_id')}] layer={atom.get('memory_layer')} proof_role={atom.get('proof_role')} score={atom.get('retrieval_score'):.6f}: {rule}"
        )
    lines.extend([
        "",
        "Required boundary: if proof_context is missing or insufficient, answer not found / not source-trace-ready and explain the limitation.",
        "Forbidden: do not infer interchangeability, fit, installation safety, effectivity, or replacement approval from Engram memory.",
    ])
    text = "\n".join(lines).strip() + "\n"
    max_chars = max(600, int(max_prompt_chars or 1800))
    if len(text) <= max_chars:
        return text
    # Truncate atom text first while preserving boundary lines.
    compact_lines = lines[:8]
    for atom in selected_atoms:
        rule = _clean_text(atom.get("text_preview"), 180)
        compact_lines.append(
            f"- [{atom.get('atom_id')}] layer={atom.get('memory_layer')} proof_role={atom.get('proof_role')}: {rule}"
        )
    compact_lines.extend(lines[-2:])
    text = "\n".join(compact_lines).strip() + "\n"
    if len(text) > max_chars:
        text = text[: max_chars - 80].rstrip() + "\n[TRUNCATED: prompt guidance compacted; still guidance only, not proof.]\n"
    return text


def build_prompt_bundle_for_record(
    rr: Mapping[str, Any],
    *,
    max_atoms_per_query: int = 4,
    max_prompt_chars: int = 1800,
    require_guidance_only: bool = True,
) -> Dict[str, Any]:
    results = rr.get("results") if isinstance(rr.get("results"), list) else []
    selected = select_prompt_atoms(results, max_atoms=max_atoms_per_query, require_guidance_only=require_guidance_only)
    query_id = str(rr.get("query_id") or "unknown_query")
    task_type = str(rr.get("task_type") or "engram_prompt_guidance")
    query_text = str(rr.get("query_text") or "")
    prompt = build_prompt_guidance_block(
        query_id=query_id,
        task_type=task_type,
        query_text=query_text,
        selected_atoms=selected,
        max_prompt_chars=max_prompt_chars,
    )
    return {
        "query_id": query_id,
        "task_type": task_type,
        "query_text": query_text,
        "selected_atom_count": len(selected),
        "selected_atoms": selected,
        "selected_layers": sorted({str(x.get("memory_layer")) for x in selected if x.get("memory_layer")}),
        "selected_proof_roles": sorted({str(x.get("proof_role")) for x in selected if x.get("proof_role")}),
        "prompt_guidance_text": prompt,
        "prompt_guidance_char_count": len(prompt),
        "engram_guidance_only": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }


def build_prompt_retrieval_injector_manifest(
    *,
    vector_retriever_path: str | Path,
    output_dir: str | Path,
    max_atoms_per_query: int = 4,
    max_prompt_chars: int = 1800,
    min_queries: int = 1,
    min_injected_atoms: int = 1,
    require_guidance_only: bool = True,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    retriever = load_vector_retriever(vector_retriever_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    retrieval_records = retriever.get("retrieval_records") if isinstance(retriever.get("retrieval_records"), list) else []
    prompt_bundles = [
        build_prompt_bundle_for_record(
            rr,
            max_atoms_per_query=max_atoms_per_query,
            max_prompt_chars=max_prompt_chars,
            require_guidance_only=require_guidance_only,
        )
        for rr in retrieval_records
        if isinstance(rr, Mapping)
    ]
    selected_atoms = [atom for bundle in prompt_bundles for atom in bundle.get("selected_atoms", [])]
    layer_counts = _counter(str(atom.get("memory_layer")) for atom in selected_atoms)
    proof_role_counts = _counter(str(atom.get("proof_role")) for atom in selected_atoms)
    missing_selected_layers = [layer for layer in REQUIRED_LAYERS if layer_counts.get(layer, 0) <= 0]

    answer_permission_count = sum(1 for atom in selected_atoms if atom.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for atom in selected_atoms if atom.get("source_truth_mutation_allowed"))
    qdrant_write_attempt_count = sum(1 for atom in selected_atoms if atom.get("qdrant_write_attempt"))
    write_attempt_count = qdrant_write_attempt_count
    max_observed_prompt_chars = max([int(b.get("prompt_guidance_char_count") or 0) for b in prompt_bundles] or [0])

    unsafe_findings: List[str] = []
    if len(prompt_bundles) < min_queries:
        unsafe_findings.append(f"query_count_below_min:{len(prompt_bundles)}<{min_queries}")
    for bundle in prompt_bundles:
        if int(bundle.get("selected_atom_count") or 0) < min_injected_atoms:
            unsafe_findings.append(f"selected_atom_count_below_min:{bundle.get('query_id')}:{bundle.get('selected_atom_count')}<{min_injected_atoms}")
        if "BEHAVIOR ONLY, NOT PROOF" not in str(bundle.get("prompt_guidance_text") or ""):
            unsafe_findings.append(f"missing_not_proof_banner:{bundle.get('query_id')}")
        if int(bundle.get("prompt_guidance_char_count") or 0) > max_prompt_chars:
            unsafe_findings.append(f"prompt_chars_above_max:{bundle.get('query_id')}")
    if require_guidance_only:
        bad_roles = sorted(set(proof_role_counts) - ALLOWED_PROOF_ROLES)
        if bad_roles:
            unsafe_findings.append("non_guidance_proof_roles:" + ",".join(bad_roles))
    if require_no_answer_permission and answer_permission_count:
        unsafe_findings.append(f"answer_permission_count:{answer_permission_count}")
    if source_truth_mutation_allowed_count:
        unsafe_findings.append(f"source_truth_mutation_allowed_count:{source_truth_mutation_allowed_count}")
    if write_attempt_count > max_write_attempts:
        unsafe_findings.append(f"write_attempt_count:{write_attempt_count}>{max_write_attempts}")

    unsafe_finding_count = len(unsafe_findings)
    quality_status = "PASS" if unsafe_finding_count <= max_unsafe else "FAIL"

    manifest = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_PROMPT_RETRIEVAL_INJECTOR_BUILT",
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "source_vector_retriever_path": str(vector_retriever_path),
        "injection_policy": {
            "max_atoms_per_query": max_atoms_per_query,
            "max_prompt_chars": max_prompt_chars,
            "require_guidance_only": require_guidance_only,
            "proof_boundary": "Engram retrieval guidance shapes behavior only; factual manual claims require current proof_context citations.",
            "forbidden": [
                "answer_permission_from_engram",
                "source_truth_mutation_from_engram",
                "interchangeability_or_approval_from_engram",
                "summary_or_engram_used_as_proof",
            ],
        },
        "prompt_bundles": prompt_bundles,
        "summary": {
            "module": MODULE,
            "version": VERSION,
            "query_count": len(prompt_bundles),
            "prompt_bundle_count": len(prompt_bundles),
            "selected_atom_count": len(selected_atoms),
            "max_atoms_per_query": max_atoms_per_query,
            "max_prompt_chars": max_prompt_chars,
            "max_observed_prompt_chars": max_observed_prompt_chars,
            "selected_memory_layer_counts": layer_counts,
            "selected_proof_role_counts": proof_role_counts,
            "missing_selected_layers": missing_selected_layers,
            "engram_guidance_only_count": len(selected_atoms),
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "postgres_write_attempt_count": 0,
            "qdrant_read_attempt_count": 0,
            "qdrant_write_attempt_count": qdrant_write_attempt_count,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": write_attempt_count,
            "unsafe_finding_count": unsafe_finding_count,
            "unsafe_findings": unsafe_findings,
            "ready_for_llm_prompt_integration": quality_status == "PASS",
        },
        "safety_contract": dict(SAFETY_CONTRACT),
    }

    manifest_path = output / f"{MODULE}.json"
    bundles_path = output / f"{MODULE}_prompt_bundles.jsonl"
    check_path = output / f"{MODULE}_quality_check.json"
    _write_json(manifest_path, manifest)
    _write_jsonl(bundles_path, prompt_bundles)
    _write_json(check_path, {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_PROMPT_RETRIEVAL_INJECTOR_CHECKED",
        "quality_status": quality_status,
        "summary": manifest["summary"],
        "safety_contract": manifest["safety_contract"],
    })
    manifest["output_path"] = str(manifest_path)
    manifest["prompt_bundles_path"] = str(bundles_path)
    manifest["quality_check_path"] = str(check_path)
    _write_json(manifest_path, manifest)
    return manifest


def check_prompt_retrieval_injector_manifest(
    *,
    prompt_injector_path: str | Path,
    min_queries: int = 1,
    min_injected_atoms: int = 1,
    require_quality_pass: bool = False,
    require_guidance_only: bool = True,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = json.loads(Path(prompt_injector_path).read_text(encoding="utf-8"))
    summary = data.get("summary") if isinstance(data.get("summary"), Mapping) else {}
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_status_not_pass")
    if int(summary.get("query_count") or 0) < min_queries:
        failures.append("query_count_below_min")
    if int(summary.get("selected_atom_count") or 0) < min_injected_atoms:
        failures.append("selected_atom_count_below_min")
    if require_guidance_only:
        proof_roles = set((summary.get("selected_proof_role_counts") or {}).keys())
        bad_roles = sorted(proof_roles - ALLOWED_PROOF_ROLES)
        if bad_roles:
            failures.append("non_guidance_proof_roles:" + ",".join(bad_roles))
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count_nonzero")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_exceeds_max")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        failures.append("unsafe_finding_count_exceeds_max")
    for bundle in data.get("prompt_bundles", []) or []:
        text = str(bundle.get("prompt_guidance_text") or "")
        if "BEHAVIOR ONLY, NOT PROOF" not in text:
            failures.append(f"missing_not_proof_banner:{bundle.get('query_id')}")
        if "proof_context" not in text:
            failures.append(f"missing_proof_context_boundary:{bundle.get('query_id')}")

    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_PROMPT_RETRIEVAL_INJECTOR_CHECKED",
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "query_count": int(summary.get("query_count") or 0),
        "prompt_bundle_count": int(summary.get("prompt_bundle_count") or 0),
        "selected_atom_count": int(summary.get("selected_atom_count") or 0),
        "selected_memory_layer_counts": summary.get("selected_memory_layer_counts") or {},
        "selected_proof_role_counts": summary.get("selected_proof_role_counts") or {},
        "unsafe_finding_count": int(summary.get("unsafe_finding_count") or 0),
        "answer_permission_count": int(summary.get("answer_permission_count") or 0),
        "write_attempt_count": int(summary.get("write_attempt_count") or 0),
        "ready_for_llm_prompt_integration": quality_status == "PASS",
        "failures": failures,
    }
    out = Path(prompt_injector_path).with_name(f"{MODULE}_external_quality_check.json")
    _write_json(out, result)
    result["output_path"] = str(out)
    return result
