"""TRACE-Net Engineering Engram Prompt Retrieval Smoke v1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

MODULE = "trace_net_engineering_engram_prompt_retrieval_smoke_v1"
VERSION = "v1"
ALLOWED_PROOF_ROLES = {"guidance_only", "current_proof_context_only"}
REQUIRED_BOUNDARY_PHRASES = (
    "BEHAVIOR ONLY, NOT PROOF",
    "Do not use Engram memory as manual evidence",
    "Manual/source claims still require current proof_context citations",
)


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _summary_value(obj: Mapping[str, Any], key: str, default: int = 0) -> int:
    summary = obj.get("summary", {}) if isinstance(obj.get("summary", {}), Mapping) else {}
    return int(summary.get(key, obj.get(key, default)) or 0)


def _source_safety_counters_zero(obj: Mapping[str, Any]) -> bool:
    for key in (
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_read_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
        "write_attempt_count",
        "unsafe_finding_count",
    ):
        if _summary_value(obj, key, 0) != 0:
            return False
    return True


def _compact_prompt_bundle(bundle: Mapping[str, Any], *, max_prompt_chars: int) -> str:
    guidance = str(bundle.get("prompt_guidance_text") or "").strip()
    header = (
        "TRACE-NET RETRIEVED ENGRAM PROMPT INTEGRATION\n"
        "Use this block as behavior guidance only. It is not proof.\n"
        "Manual/source claims still require current proof_context citations.\n\n"
    )
    prompt = header + guidance
    if len(prompt) > max_prompt_chars:
        marker = "\n[TRUNCATED BY H21 PROMPT SMOKE: guidance remains behavior-only, not proof.]"
        prompt = prompt[: max(0, max_prompt_chars - len(marker))].rstrip() + marker
    return prompt


def build_integration_records(prompt_injector: Mapping[str, Any], *, max_prompt_chars: int = 2200) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for bundle in _as_list(prompt_injector.get("prompt_bundles")):
        if not isinstance(bundle, Mapping):
            continue
        prompt_text = _compact_prompt_bundle(bundle, max_prompt_chars=max_prompt_chars)
        selected_proof_roles = [str(x) for x in _as_list(bundle.get("selected_proof_roles"))]
        selected_layers = [str(x) for x in _as_list(bundle.get("selected_layers"))]
        selected_atom_count = int(bundle.get("selected_atom_count") or 0)
        missing_boundary_phrases = [p for p in REQUIRED_BOUNDARY_PHRASES if p not in prompt_text]
        disallowed_roles = [r for r in selected_proof_roles if r not in ALLOWED_PROOF_ROLES]
        unsafe_findings: List[str] = []
        if missing_boundary_phrases:
            unsafe_findings.append("missing_proof_boundary_phrase")
        if disallowed_roles:
            unsafe_findings.append("disallowed_proof_role")
        if selected_atom_count <= 0:
            unsafe_findings.append("no_selected_atoms")
        if len(prompt_text) > max_prompt_chars:
            unsafe_findings.append("prompt_budget_exceeded")
        lower_prompt = prompt_text.lower()
        if "answer_permission=true" in lower_prompt or "answer_permission: true" in lower_prompt:
            unsafe_findings.append("prompt_mentions_answer_permission_true")
        records.append({
            "query_id": bundle.get("query_id"),
            "task_type": bundle.get("task_type"),
            "integration_mode": "retrieved_engram_prompt_guidance",
            "selected_atom_count": selected_atom_count,
            "selected_layers": selected_layers,
            "selected_proof_roles": selected_proof_roles,
            "prompt_char_count": len(prompt_text),
            "max_prompt_chars": max_prompt_chars,
            "contains_behavior_only_boundary": "BEHAVIOR ONLY, NOT PROOF" in prompt_text,
            "contains_manual_proof_boundary": "Manual/source claims still require current proof_context citations" in prompt_text,
            "missing_boundary_phrases": missing_boundary_phrases,
            "disallowed_proof_roles": disallowed_roles,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_read_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "write_attempt": False,
            "unsafe_findings": unsafe_findings,
            "unsafe": bool(unsafe_findings),
            "integration_prompt_preview": prompt_text[:1200],
        })
    return records


def _count_layers(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in records:
        for layer in _as_list(r.get("selected_layers")):
            layer_s = str(layer)
            counts[layer_s] = counts.get(layer_s, 0) + 1
    return dict(sorted(counts.items()))


def build_prompt_retrieval_smoke_manifest(
    *,
    prompt_injector_path: str | Path,
    output_dir: str | Path,
    max_prompt_chars: int = 2200,
    min_queries: int = 6,
    min_injected_atoms: int = 6,
    require_quality_pass: bool = True,
    require_guidance_only: bool = True,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    prompt_injector = _read_json(prompt_injector_path)
    records = build_integration_records(prompt_injector, max_prompt_chars=max_prompt_chars)
    total_selected_atoms = sum(int(r.get("selected_atom_count") or 0) for r in records)
    unsafe_records = [r for r in records if r.get("unsafe")]
    write_attempt_count = sum(1 for r in records if r.get("write_attempt"))
    answer_permission_count = sum(1 for r in records if r.get("answer_permission"))
    quality_failures: List[str] = []
    if require_quality_pass and prompt_injector.get("quality_status") != "PASS":
        quality_failures.append("source_prompt_injector_not_pass")
    if len(records) < min_queries:
        quality_failures.append("min_queries_not_met")
    if total_selected_atoms < min_injected_atoms:
        quality_failures.append("min_injected_atoms_not_met")
    if require_guidance_only:
        for r in records:
            bad_roles = [role for role in _as_list(r.get("selected_proof_roles")) if role not in ALLOWED_PROOF_ROLES]
            if bad_roles:
                quality_failures.append("non_guidance_proof_role_selected")
                break
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append("answer_permission_detected")
    if len(unsafe_records) > max_unsafe:
        quality_failures.append("unsafe_limit_exceeded")
    if write_attempt_count > max_write_attempts:
        quality_failures.append("write_attempt_limit_exceeded")
    if not _source_safety_counters_zero(prompt_injector):
        quality_failures.append("source_prompt_injector_safety_counter_nonzero")
    quality_status = "PASS" if not quality_failures else "FAIL"
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records_path = out_dir / "trace_net_engineering_engram_prompt_retrieval_smoke_v1_records.jsonl"
    check_path = out_dir / "trace_net_engineering_engram_prompt_retrieval_smoke_v1_quality_check.json"
    manifest_path = out_dir / "trace_net_engineering_engram_prompt_retrieval_smoke_v1.json"
    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_prompt_injector_quality_status": prompt_injector.get("quality_status"),
        "query_count": len(records),
        "prompt_integration_record_count": len(records),
        "selected_atom_count": total_selected_atoms,
        "selected_memory_layer_counts": _count_layers(records),
        "max_observed_prompt_chars": max((int(r.get("prompt_char_count") or 0) for r in records), default=0),
        "max_prompt_chars": max_prompt_chars,
        "ready_for_llm_prompt_retrieval_smoke": quality_status == "PASS",
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_read_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": write_attempt_count,
        "unsafe_finding_count": len(unsafe_records),
        "quality_failures": quality_failures,
    }
    manifest = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_PROMPT_RETRIEVAL_SMOKE_BUILT",
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "source_prompt_injector_path": str(prompt_injector_path),
        "summary": summary,
        "integration_policy": {
            "mode": "artifact_only_prompt_retrieval_smoke",
            "proof_boundary": "Retrieved Engram atoms shape answer behavior only; factual manual claims require current proof_context citations.",
            "allowed_proof_roles": sorted(ALLOWED_PROOF_ROLES),
            "forbidden": [
                "answer_permission_from_engram",
                "source_truth_mutation_from_engram",
                "summary_or_engram_used_as_proof",
                "live_qdrant_io_without_explicit_gate",
            ],
            "max_prompt_chars": max_prompt_chars,
        },
        "records_path": str(records_path),
        "quality_check_path": str(check_path),
        "prompt_integration_records": records,
    }
    quality_check = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_PROMPT_RETRIEVAL_SMOKE_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
        "quality_failures": quality_failures,
    }
    _write_jsonl(records_path, records)
    _write_json(check_path, quality_check)
    _write_json(manifest_path, manifest)
    return manifest


def check_prompt_retrieval_smoke_manifest(
    manifest: Mapping[str, Any],
    *,
    min_queries: int = 6,
    min_injected_atoms: int = 6,
    require_quality_pass: bool = True,
    require_guidance_only: bool = True,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    records = _as_list(manifest.get("prompt_integration_records"))
    selected_atom_count = sum(int(r.get("selected_atom_count") or 0) for r in records if isinstance(r, Mapping))
    unsafe_count = sum(1 for r in records if isinstance(r, Mapping) and r.get("unsafe"))
    summary = manifest.get("summary", {}) if isinstance(manifest.get("summary", {}), Mapping) else {}
    write_attempt_count = int(summary.get("write_attempt_count", 0) or 0)
    answer_permission_count = int(summary.get("answer_permission_count", 0) or 0)
    failures: List[str] = []
    if require_quality_pass and manifest.get("quality_status") != "PASS":
        failures.append("quality_status_not_pass")
    if len(records) < min_queries:
        failures.append("min_queries_not_met")
    if selected_atom_count < min_injected_atoms:
        failures.append("min_injected_atoms_not_met")
    if require_guidance_only:
        for r in records:
            if not isinstance(r, Mapping):
                failures.append("invalid_record")
                continue
            bad_roles = [role for role in _as_list(r.get("selected_proof_roles")) if role not in ALLOWED_PROOF_ROLES]
            if bad_roles:
                failures.append("non_guidance_proof_role_selected")
                break
    if require_no_answer_permission and answer_permission_count:
        failures.append("answer_permission_detected")
    if unsafe_count > max_unsafe:
        failures.append("unsafe_limit_exceeded")
    if write_attempt_count > max_write_attempts:
        failures.append("write_attempt_limit_exceeded")
    return {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_PROMPT_RETRIEVAL_SMOKE_CHECKED",
        "quality_status": "PASS" if not failures else "FAIL",
        "query_count": len(records),
        "selected_atom_count": selected_atom_count,
        "unsafe_finding_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "write_attempt_count": write_attempt_count,
        "quality_failures": failures,
    }
