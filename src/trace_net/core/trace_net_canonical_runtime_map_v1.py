"""TRACE-Net canonical runtime map v1.

This module creates a small governance layer for the TRACE-Net repo.

It does not move files, delete files, write databases, or mutate source-truth
artifacts. Its job is to make the current runtime decision explicit:

- one selected OpenWebUI answer path;
- active/support/superseded/archive classifications for major modules;
- an integration contract for wiring the selected path to Engram + Self-RAG + CRAG;
- a cleanup hold list so backup/superseded files are not moved before tests pass.

The implementation is intentionally conservative. It inspects the repo, records
whether named modules exist, and writes a JSON + Markdown manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


MODULE = "trace_net_canonical_runtime_map_v1"
VERSION = "1.0.0"

DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/canonical_runtime_map_v1"
DEFAULT_JSON_NAME = "trace_net_canonical_runtime_map_v1.json"
DEFAULT_MD_NAME = "trace_net_canonical_runtime_map_v1.md"
DEFAULT_QUALITY_NAME = "trace_net_canonical_runtime_map_v1_quality.json"


SELECTED_OPENWEBUI_ANSWER_PATH = {
    "selected_path_id": "openwebui_page_context_native_answer_v1",
    "status": "active_current_openwebui_path",
    "model_id": "trace-net-page-context-v3-bridge",
    "default_port": 8023,
    "entrypoint_script": "scripts/operations/serving/serve_trace_net_openwebui_page_context_bridge_v1.py",
    "implementation_module": "tiff/trace_net_openwebui_page_context_bridge_v1.py",
    "page_context_module": "tiff/trace_net_page_context_pack_v3.py",
    "llm_provider": "ollama_native_api_chat",
    "llm_endpoint": "http://127.0.0.1:11434/api/chat",
    "llm_model": "gemma4:26b",
    "why_selected": (
        "This path was recently proven to build page_context_pack_v3, call Gemma4 "
        "through Ollama /api/chat with visible message.content, pass page alignment, "
        "and return without fallback for a page-binder question."
    ),
    "known_limits": [
        "Currently strongest for page-explicit questions.",
        "Needs existing Engram/Self-RAG/CRAG modules wired into its native answer path.",
        "Must keep proof_context separate from guidance_only records.",
    ],
}


MAJOR_MODULES = [
    {
        "module_id": "openwebui_page_context_bridge_v1",
        "path": "tiff/trace_net_openwebui_page_context_bridge_v1.py",
        "kind": "implementation",
        "status": "active_current",
        "role": "Current selected OpenWebUI-compatible page/native Gemma answer path.",
        "cleanup_allowed": False,
        "wire_role": "primary_endpoint",
    },
    {
        "module_id": "page_context_pack_v3",
        "path": "tiff/trace_net_page_context_pack_v3.py",
        "kind": "implementation",
        "status": "active_current",
        "role": "Builds source-bounded page binder used by the selected OpenWebUI path.",
        "cleanup_allowed": False,
        "wire_role": "proof_and_guidance_binder",
    },
    {
        "module_id": "serve_openwebui_page_context_bridge_v1",
        "path": "scripts/operations/serving/serve_trace_net_openwebui_page_context_bridge_v1.py",
        "kind": "script_entrypoint",
        "status": "active_current",
        "role": "Runs the selected 8023 OpenWebUI-compatible bridge.",
        "cleanup_allowed": False,
        "wire_role": "server_entrypoint",
    },
    {
        "module_id": "webui_self_rag_crag_bridge_v1",
        "path": "tiff/trace_net_webui_self_rag_crag_bridge_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing full WebUI/Self-RAG/CRAG bridge. Reuse as integration source, not as primary endpoint until inspected/tested.",
        "cleanup_allowed": False,
        "wire_role": "existing_full_stack_reference",
    },
    {
        "module_id": "e2e_live_self_rag_crag_evaluator_v20",
        "path": "tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing live Self-RAG/CRAG evaluator layer.",
        "cleanup_allowed": False,
        "wire_role": "critic_repair_evaluator",
    },
    {
        "module_id": "engram_core_v1",
        "path": "tiff/trace_net_engineering_engram_core_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Engram policy/style/failure/example core.",
        "cleanup_allowed": False,
        "wire_role": "behavior_memory_core",
    },
    {
        "module_id": "engram_answer_runner_retrieval_bridge_v1",
        "path": "tiff/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing Engram retrieval bridge for answer runner overlays.",
        "cleanup_allowed": False,
        "wire_role": "engram_retrieval_adapter",
    },
    {
        "module_id": "engram_answer_runner_overlay_llm_smoke_v1",
        "path": "tiff/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing Engram overlay + LLM smoke path.",
        "cleanup_allowed": False,
        "wire_role": "prompt_overlay_reference",
    },
    {
        "module_id": "engram_self_rag_critic_v1",
        "path": "tiff/trace_net_engineering_engram_self_rag_critic_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing Engram-aware Self-RAG critic.",
        "cleanup_allowed": False,
        "wire_role": "self_rag_critic",
    },
    {
        "module_id": "engram_crag_repair_v1",
        "path": "tiff/trace_net_engineering_engram_crag_repair_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing Engram-aware CRAG repair module.",
        "cleanup_allowed": False,
        "wire_role": "crag_repair",
    },
    {
        "module_id": "engram_unified_runtime_gate_v1",
        "path": "tiff/trace_net_engineering_engram_unified_runtime_gate_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing runtime gate for Engram/Self-RAG/CRAG safety counters.",
        "cleanup_allowed": False,
        "wire_role": "runtime_gate",
    },
    {
        "module_id": "engineering_context_pack_blueprint_v1",
        "path": "tiff/trace_net_engineering_context_pack_blueprint_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing engineering query/context blueprint builder.",
        "cleanup_allowed": False,
        "wire_role": "planner_blueprint_reference",
    },
    {
        "module_id": "engineering_context_pack_builder_v1",
        "path": "tiff/trace_net_engineering_context_pack_builder_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing engineering context pack builder.",
        "cleanup_allowed": False,
        "wire_role": "context_pack_reference",
    },
    {
        "module_id": "engineering_context_self_rag_check_v1",
        "path": "tiff/trace_net_engineering_context_self_rag_check_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing context Self-RAG check.",
        "cleanup_allowed": False,
        "wire_role": "context_self_rag_reference",
    },
    {
        "module_id": "engineering_context_crag_retry_plan_v1",
        "path": "tiff/trace_net_engineering_context_crag_retry_plan_v1.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing context CRAG retry planner.",
        "cleanup_allowed": False,
        "wire_role": "context_crag_reference",
    },
    {
        "module_id": "e2e_live_llm_final_gate_v23",
        "path": "tiff/trace_net_e2e_live_llm_final_gate_v23.py",
        "kind": "implementation",
        "status": "active_support",
        "role": "Existing live LLM final gate implementation.",
        "cleanup_allowed": False,
        "wire_role": "final_gate_reference",
    },
    {
        "module_id": "engineering_webui_answer_server_v1",
        "path": "tiff/trace_net_engineering_webui_answer_server_v1.py",
        "kind": "implementation",
        "status": "superseded_not_primary",
        "role": "Older WebUI answer server. Keep for reference until current path is fully integrated.",
        "cleanup_allowed": False,
        "wire_role": "reference_only",
    },
    {
        "module_id": "engineering_webui_answer_server_v1_3_bridge_v1",
        "path": "tiff/trace_net_engineering_webui_answer_server_v1_3_bridge_v1.py",
        "kind": "implementation",
        "status": "superseded_not_primary",
        "role": "Older bridge with useful behavior/reference patterns. Not selected as current endpoint.",
        "cleanup_allowed": False,
        "wire_role": "reference_only",
    },
    {
        "module_id": "e2e_local_endpoint_v1",
        "path": "tiff/trace_net_e2e_local_endpoint_v1.py",
        "kind": "implementation",
        "status": "superseded_do_not_use_as_current_openwebui",
        "role": "Old smoke/artifact endpoint; not current full-stack OpenWebUI model.",
        "cleanup_allowed": False,
        "wire_role": "do_not_use_current_endpoint",
    },
    {
        "module_id": "e2e_live_orchestrator_stage_timing_fastpath_v27",
        "path": "tiff/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.py",
        "kind": "implementation",
        "status": "support_only_fastpath_or_legacy",
        "role": "Useful fastpath/orchestrator reference, but not selected for page-binder native answers.",
        "cleanup_allowed": False,
        "wire_role": "support_reference",
    },
]


PIPELINE_STAGES = [
    {
        "stage": 1,
        "name": "OpenWebUI request",
        "active_module": "scripts/operations/serving/serve_trace_net_openwebui_page_context_bridge_v1.py",
        "status": "active_current",
        "contract": "Expose /health, /v1/models, /v1/chat/completions compatible response.",
    },
    {
        "stage": 2,
        "name": "Question/page detection",
        "active_module": "tiff/trace_net_openwebui_page_context_bridge_v1.py",
        "status": "active_current",
        "contract": "Detect page-explicit questions and route them to page_context_pack_v3.",
    },
    {
        "stage": 3,
        "name": "Proof/guidance binder",
        "active_module": "tiff/trace_net_page_context_pack_v3.py",
        "status": "active_current",
        "contract": "Build source-bounded binder with proof records, guidance records, route metadata, and safety counters.",
    },
    {
        "stage": 4,
        "name": "Engram behavior overlay",
        "active_module": "tiff/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py",
        "status": "active_support_to_wire",
        "contract": "Retrieve policy/style/failure/example behavior memory. Engram is guidance only, not factual proof.",
    },
    {
        "stage": 5,
        "name": "Native Gemma answer draft",
        "active_module": "tiff/trace_net_openwebui_page_context_bridge_v1.py",
        "status": "active_current",
        "contract": "Call Ollama /api/chat with Gemma4, think:false, bounded context, and visible message.content.",
    },
    {
        "stage": 6,
        "name": "Self-RAG critic",
        "active_module": "tiff/trace_net_engineering_engram_self_rag_critic_v1.py",
        "status": "active_support_to_wire",
        "contract": "Check proof-vs-guidance discipline, citation/page alignment, forbidden overclaims, and limits.",
    },
    {
        "stage": 7,
        "name": "CRAG repair",
        "active_module": "tiff/trace_net_engineering_engram_crag_repair_v1.py",
        "status": "active_support_to_wire",
        "contract": "Repair only when critic requires repair; never invent proof or promote guidance to proof.",
    },
    {
        "stage": 8,
        "name": "Final runtime gate",
        "active_module": "tiff/trace_net_engineering_engram_unified_runtime_gate_v1.py",
        "status": "active_support_to_wire",
        "contract": "Enforce zero source-truth mutation, no DB writes, no answer permission, and no unsupported claims.",
    },
    {
        "stage": 9,
        "name": "OpenWebUI response",
        "active_module": "tiff/trace_net_openwebui_page_context_bridge_v1.py",
        "status": "active_current",
        "contract": "Return answer, trace_net metadata, safety counters, and fallback when alignment/critic/gate fails.",
    },
]


STATUS_DEFINITIONS = {
    "active_current": "Selected or directly required by the current 8023 OpenWebUI page-native answer path.",
    "active_current_openwebui_path": "The selected current OpenWebUI answer path.",
    "active_support": "Actively kept and intended for reuse/wiring, but not the selected endpoint itself.",
    "active_support_to_wire": "Known support module that must be wired into the selected endpoint in the next integration patch.",
    "support_only_fastpath_or_legacy": "May remain useful for deterministic/fast tasks or reference, but is not the primary current endpoint.",
    "superseded_not_primary": "Older answer/runtime path. Do not use as the current endpoint. Keep until current path passes integration/eval.",
    "superseded_do_not_use_as_current_openwebui": "Known old endpoint that should not be pointed at OpenWebUI for current testing.",
    "backup_snapshot": "Patch/edit backup file. Never import. Candidate for quarantine only after integration tests and git safety checks.",
    "archived_reference": "Historical/reference material under docs/archive or old patch folders.",
    "script_wrapper": "Thin CLI entrypoint. Keep if it is used for running/checking an active module.",
}


def _as_path(repo_root: Path, rel: str) -> Path:
    return repo_root / rel.replace("\\", "/")


def _read_text(path: Path, limit: int = 500_000) -> str:
    try:
        return path.read_bytes()[:limit].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _sha1(path: Path) -> Optional[str]:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except Exception:
        return None


def scan_backup_candidates(repo_root: Path) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for root_name in ("scripts", "tiff"):
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and (".bak" in path.name or ".pre_" in path.name or path.suffix.endswith(".bak")):
                rel = path.relative_to(repo_root).as_posix()
                candidates.append(
                    {
                        "path": rel,
                        "status": "backup_snapshot",
                        "cleanup_allowed_now": False,
                        "recommended_action": "quarantine_after_current_endpoint_integration_passes",
                        "size_bytes": path.stat().st_size,
                        "sha1": _sha1(path),
                    }
                )
    return sorted(candidates, key=lambda r: r["path"])


def detect_script_wrappers(repo_root: Path, max_records: int = 250) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    root = repo_root / "scripts"
    if not root.exists():
        return records
    rx = re.compile(r"from\s+tiff\.([A-Za-z0-9_]+)\s+import\s+([A-Za-z0-9_,\s]+)")
    for path in sorted(root.rglob("*.py")):
        text = _read_text(path)
        m = rx.search(text)
        if not m:
            continue
        rel = path.relative_to(repo_root).as_posix()
        target_module = m.group(1)
        records.append(
            {
                "path": rel,
                "status": "script_wrapper",
                "target_module": f"tiff/{target_module}.py",
                "cleanup_allowed_now": False,
            }
        )
        if len(records) >= max_records:
            break
    return records


def detect_exact_duplicate_groups(repo_root: Path, max_groups: int = 50) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[str]] = defaultdict(list)
    for root_name in ("scripts", "tiff"):
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            digest = _sha1(path)
            if digest:
                buckets[digest].append(path.relative_to(repo_root).as_posix())
    groups = []
    for digest, paths in buckets.items():
        if len(paths) > 1:
            groups.append(
                {
                    "sha1": digest,
                    "paths": sorted(paths),
                    "cleanup_allowed_now": False,
                    "recommended_action": "review_after_current_endpoint_integration_passes",
                }
            )
    groups.sort(key=lambda g: (-len(g["paths"]), g["paths"]))
    return groups[:max_groups]


def annotate_major_modules(repo_root: Path) -> List[Dict[str, Any]]:
    annotated = []
    for record in MAJOR_MODULES:
        item = dict(record)
        path = _as_path(repo_root, item["path"])
        item["exists"] = path.exists()
        item["size_bytes"] = path.stat().st_size if path.exists() else None
        item["sha1"] = _sha1(path) if path.exists() else None
        annotated.append(item)
    return annotated


def build_runtime_map(repo_root: str | Path = ".", output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    modules = annotate_major_modules(repo_root)
    backup_candidates = scan_backup_candidates(repo_root)
    script_wrappers = detect_script_wrappers(repo_root)
    duplicate_groups = detect_exact_duplicate_groups(repo_root)

    active_current_count = sum(1 for m in modules if m["status"] == "active_current" and m["exists"])
    active_support_count = sum(1 for m in modules if str(m["status"]).startswith("active_support") and m["exists"])
    superseded_count = sum(1 for m in modules if str(m["status"]).startswith("superseded") and m["exists"])
    missing_major_modules = [m for m in modules if not m["exists"]]

    primary_exists = _as_path(repo_root, SELECTED_OPENWEBUI_ANSWER_PATH["implementation_module"]).exists()
    page_context_exists = _as_path(repo_root, SELECTED_OPENWEBUI_ANSWER_PATH["page_context_module"]).exists()
    entrypoint_exists = _as_path(repo_root, SELECTED_OPENWEBUI_ANSWER_PATH["entrypoint_script"]).exists()

    cleanup_policy = {
        "cleanup_allowed_now": False,
        "reason": (
            "No backup/superseded moves until the selected OpenWebUI path is integrated with "
            "Engram + Self-RAG + CRAG and the smoke/eval gate passes."
        ),
        "preconditions_before_move": [
            "Canonical runtime map quality PASS.",
            "Selected 8023 OpenWebUI path smoke PASS.",
            "Engram overlay injection PASS.",
            "Self-RAG critic PASS or safe repair recommendation.",
            "CRAG repair PASS when invoked.",
            "Unified runtime gate PASS.",
            "Git working tree reviewed; no generated cache files staged.",
        ],
    }

    integration_contract = {
        "status": "integration_contract_ready_not_yet_code_wired_by_this_map",
        "selected_path": SELECTED_OPENWEBUI_ANSWER_PATH["selected_path_id"],
        "must_wire_next": [
            "Engram retrieval overlay into native page answer prompt.",
            "Self-RAG critic after native Gemma answer.",
            "CRAG repair only when critic requires repair.",
            "Unified runtime gate before final OpenWebUI response.",
        ],
        "must_not_do": [
            "Do not treat Engram/vector/graph/page summaries as factual proof.",
            "Do not move backup/superseded files before integration/eval pass.",
            "Do not point OpenWebUI to old 8014/8020/8021 endpoints for current testing.",
            "Do not write Postgres/Qdrant/OpenSearch in this governance step.",
        ],
    }

    summary = {
        "primary_openwebui_module_exists": primary_exists,
        "page_context_module_exists": page_context_exists,
        "entrypoint_script_exists": entrypoint_exists,
        "active_current_existing_count": active_current_count,
        "active_support_existing_count": active_support_count,
        "superseded_existing_count": superseded_count,
        "missing_major_module_count": len(missing_major_modules),
        "backup_candidate_count": len(backup_candidates),
        "script_wrapper_sample_count": len(script_wrappers),
        "exact_duplicate_group_count": len(duplicate_groups),
        "cleanup_allowed_now": False,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "answer_permission_count": 0,
    }

    quality_status = "PASS" if primary_exists and page_context_exists and entrypoint_exists and active_support_count >= 5 else "REVIEW"
    failure_reasons = []
    if not primary_exists:
        failure_reasons.append("missing_selected_openwebui_implementation_module")
    if not page_context_exists:
        failure_reasons.append("missing_page_context_pack_v3_module")
    if not entrypoint_exists:
        failure_reasons.append("missing_selected_openwebui_entrypoint_script")
    if active_support_count < 5:
        failure_reasons.append("active_support_existing_count_lt_5")

    manifest: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": "CANONICAL_RUNTIME_MAP_BUILT",
        "quality_status": quality_status,
        "failure_reasons": failure_reasons,
        "repo_root": str(repo_root),
        "selected_openwebui_answer_path": SELECTED_OPENWEBUI_ANSWER_PATH,
        "status_definitions": STATUS_DEFINITIONS,
        "pipeline_stages": PIPELINE_STAGES,
        "major_modules": modules,
        "integration_contract": integration_contract,
        "cleanup_policy": cleanup_policy,
        "backup_candidates": backup_candidates,
        "exact_duplicate_groups": duplicate_groups,
        "script_wrapper_samples": script_wrappers,
        "missing_major_modules": missing_major_modules,
        "summary": summary,
    }

    json_path = output_dir / DEFAULT_JSON_NAME
    md_path = output_dir / DEFAULT_MD_NAME
    json_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(manifest), encoding="utf-8")
    manifest["output_paths"] = {
        "json": json_path.as_posix(),
        "markdown": md_path.as_posix(),
    }
    json_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def render_markdown(manifest: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# TRACE-Net canonical runtime map v1")
    lines.append("")
    lines.append(f"Quality status: **{manifest.get('quality_status')}**")
    if manifest.get("failure_reasons"):
        lines.append("")
        lines.append("Failure reasons:")
        for r in manifest["failure_reasons"]:
            lines.append(f"- `{r}`")
    lines.append("")
    lines.append("## Selected current OpenWebUI answer path")
    selected = manifest["selected_openwebui_answer_path"]
    for key in [
        "selected_path_id",
        "status",
        "model_id",
        "default_port",
        "entrypoint_script",
        "implementation_module",
        "page_context_module",
        "llm_provider",
        "llm_model",
    ]:
        lines.append(f"- **{key}**: `{selected.get(key)}`")
    lines.append("")
    lines.append(selected["why_selected"])
    lines.append("")
    lines.append("## Pipeline stages")
    for stage in manifest["pipeline_stages"]:
        lines.append("")
        lines.append(f"### {stage['stage']}. {stage['name']}")
        lines.append(f"- Status: `{stage['status']}`")
        lines.append(f"- Module: `{stage['active_module']}`")
        lines.append(f"- Contract: {stage['contract']}")
    lines.append("")
    lines.append("## Major module classification")
    for status in [
        "active_current",
        "active_support",
        "superseded_not_primary",
        "superseded_do_not_use_as_current_openwebui",
        "support_only_fastpath_or_legacy",
    ]:
        rows = [m for m in manifest["major_modules"] if m["status"] == status]
        if not rows:
            continue
        lines.append("")
        lines.append(f"### {status}")
        for m in rows:
            exists = "exists" if m.get("exists") else "MISSING"
            lines.append(f"- `{m['path']}` — {exists}; role={m['wire_role']}; {m['role']}")
    lines.append("")
    lines.append("## Integration contract")
    contract = manifest["integration_contract"]
    lines.append(f"- Status: `{contract['status']}`")
    lines.append("- Must wire next:")
    for item in contract["must_wire_next"]:
        lines.append(f"  - {item}")
    lines.append("- Must not do:")
    for item in contract["must_not_do"]:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("## Cleanup policy")
    policy = manifest["cleanup_policy"]
    lines.append(f"- cleanup_allowed_now: `{policy['cleanup_allowed_now']}`")
    lines.append(f"- Reason: {policy['reason']}")
    lines.append("- Preconditions before moving backups/superseded files:")
    for item in policy["preconditions_before_move"]:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("## Summary")
    for key, value in manifest["summary"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Backup candidates")
    lines.append("These are candidates only. This module does not move them.")
    for b in manifest["backup_candidates"][:80]:
        lines.append(f"- `{b['path']}`")
    if len(manifest["backup_candidates"]) > 80:
        lines.append(f"- ... {len(manifest['backup_candidates']) - 80} more")
    return "\n".join(lines) + "\n"


def check_runtime_map(
    manifest_path: str | Path,
    output_path: str | Path = "",
    min_active_support: int = 5,
    require_primary_openwebui_path: bool = True,
    require_no_cleanup_allowed: bool = True,
) -> Dict[str, Any]:
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    summary = data.get("summary", {})
    failure_reasons: List[str] = []

    if require_primary_openwebui_path:
        if not summary.get("primary_openwebui_module_exists"):
            failure_reasons.append("primary_openwebui_module_missing")
        if not summary.get("page_context_module_exists"):
            failure_reasons.append("page_context_module_missing")
        if not summary.get("entrypoint_script_exists"):
            failure_reasons.append("entrypoint_script_missing")

    if int(summary.get("active_support_existing_count") or 0) < min_active_support:
        failure_reasons.append("active_support_existing_count_lt_min")

    if require_no_cleanup_allowed and bool(summary.get("cleanup_allowed_now")):
        failure_reasons.append("cleanup_allowed_before_integration_gate")

    safety_keys = [
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "answer_permission_count",
    ]
    for key in safety_keys:
        if int(summary.get(key) or 0) != 0:
            failure_reasons.append(f"{key}_nonzero")

    status = "PASS" if not failure_reasons else "FAIL"
    quality = {
        "module": MODULE,
        "version": VERSION,
        "status": "CANONICAL_RUNTIME_MAP_QUALITY_CHECKED",
        "quality_status": status,
        "failure_reasons": failure_reasons,
        "summary": summary,
        "source_manifest_path": manifest_path.as_posix(),
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(quality, indent=2), encoding="utf-8")
    return quality


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net canonical runtime map v1.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    manifest = build_runtime_map(repo_root=args.repo_root, output_dir=args.output_dir)
    print(f"Wrote: {manifest['output_paths']['json']}")
    print(f"Wrote: {manifest['output_paths']['markdown']}")
    print(f"quality_status: {manifest['quality_status']}")
    print(f"summary: {json.dumps(manifest['summary'], sort_keys=True)}")
    return 0 if manifest["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
