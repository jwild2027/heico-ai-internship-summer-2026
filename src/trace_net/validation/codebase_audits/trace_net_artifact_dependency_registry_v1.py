"""TRACE-Net Artifact Dependency Registry v1.

This module builds a read-only dependency registry for TRACE-Net artifacts.
It scans a TRACE-Net artifact root, finds primary report JSON files, hashes
those artifacts, records quality/status/schema metadata, and attaches a curated
stage dependency map.

It is intentionally dry-run only: it does not execute jobs, write to Postgres,
write to Qdrant, write to OpenSearch, or mutate source truth.  The registry is
meant to support dynamic-pipeline planning by answering:

* Which artifacts exist?
* What quality/status did each artifact report?
* What inputs/dependencies does each artifact have?
* Which downstream artifacts would be affected by a change?
* Are there dependency cycles or unsafe registry records?
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_artifact_dependency_registry_v1"
ALGORITHM = "trace_net_artifact_dependency_scanner_v1"

SKIP_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    "artifact_dependency_registry",
}

DEFAULT_EXCLUDED_RELATIVE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("it_issue_origin_test_matrix", "synthetic_trace_net_root"),
    ("it_issue_origin_test_matrix", "synthetic_console_report"),
    ("artifact_dependency_registry",),
)

PRIMARY_EXCLUDED_SUFFIXES = (
    "_quality.json",
    "_summary.json",
    "_manifest.json",
    "_schema.json",
    "_mapping.json",
    "_field_map.json",
)

PRIMARY_EXCLUDED_STEM_CONTAINS = (
    "_records",
    "_rows",
    "_cells",
    "_edges",
    "_nodes",
    "_claims",
    "_groups",
    "_results",
    "_documents",
    "_bulk",
    "_events",
    "_cards",
    "_tasks",
    "_plans",
    "_checks",
    "_origins",
    "_scenarios",
    "_part_candidates",
    "_membership",
    "_mapping",
)

# Helper/report artifacts are useful to humans but should not be treated as
# primary pipeline artifacts.  The registry should track the canonical stage
# report, not supplemental matrices or generated config files.
PRIMARY_EXCLUDED_EXACT_NAMES = {
    "trace_net_core_algorithm_matrix_v1.json",
}

# Older stages predate the newer trace_net_*_v1 report naming convention.
# These files are still canonical stage reports and should be normalized into
# the dependency graph instead of being excluded as *_summary or *_quality files.
LEGACY_PRIMARY_FILE_STAGE_IDS = {
    "evidence_consensus_summary.json": "evidence_consensus",
    "page_image_recognition_quality.json": "image_recognition_quality",
    "trace_net_qdrant_loader_v1_summary.json": "qdrant_loader",
    "trace_net_qdrant_loader_v1_quality.json": "qdrant_loader",
    "trace_net_evidence_snippet_claims_v1_summary.json": "evidence_snippet_claims",
    "trace_net_evidence_snippet_claims_v1_quality.json": "evidence_snippet_claims",
}

# These dependencies can be absent in a local checkout while still leaving the
# registry useful.  If present they are resolved normally; if absent they are
# tracked separately as optional-missing references and do not make the primary
# missing dependency count noisy.
OPTIONAL_DEPENDENCY_STAGE_IDS = {
    "qdrant_loader",
    "evidence_snippet_claims",
}

# Stage id -> upstream stage ids.  Missing dependencies are reported as
# warnings because not every local clone has every optional artifact.
DEFAULT_DEPENDENCY_MAP: dict[str, list[str]] = {
    "context_retrieval_helpers": ["graph_context_v2_nomenclature_v1"],
    # Page retrieval profiles are an upstream route/search artifact used by
    # Page Element Registry.  Do not depend on page_element_registry here;
    # that would create an artificial cycle.
    "page_retrieval_profiles": ["context_retrieval_helpers"],
    "embedding_candidates": ["evidence_consensus", "context_retrieval_helpers"],
    "qdrant_loader": ["embedding_candidates", "page_retrieval_profiles"],
    "vector_search_smoke": ["qdrant_loader", "embedding_candidates", "page_retrieval_profiles"],
    "hybrid_retrieval_sim": ["vector_search_smoke", "embedding_candidates", "page_retrieval_profiles"],
    "regression_eval": ["hybrid_retrieval_sim"],
    "ask_hybrid_flag": ["hybrid_retrieval_sim", "regression_eval", "vector_search_smoke"],
    "answer_context_pack": ["ask_hybrid_flag", "hybrid_retrieval_sim", "embedding_candidates", "page_retrieval_profiles"],
    "citation_answer_draft": ["answer_context_pack"],
    "evidence_snippet_claims": ["citation_answer_draft", "answer_context_pack"],
    "evidence_snippet_cleaner": ["evidence_snippet_claims"],
    "final_answer_gate": ["evidence_snippet_cleaner"],
    "ask_api": ["final_answer_gate", "hybrid_retrieval_sim", "community_aware_retrieval_sim"],
    "page_element_registry": ["page_retrieval_profiles", "embedding_candidates", "evidence_consensus"],
    "table_understanding": ["page_element_registry"],
    "table_cell_normalizer": ["table_understanding", "embedding_candidates", "page_element_registry"],
    "figure_chart_understanding": ["page_element_registry", "table_cell_normalizer"],
    "visual_ink_layout_calibrator": ["figure_chart_understanding", "page_element_registry"],
    "vision_model_pilot_plan": ["figure_chart_understanding", "visual_ink_layout_calibrator"],
    "callout_visual_part_verifier": ["figure_chart_understanding", "table_cell_normalizer", "graph_overlay_part_property_normalizer", "embedding_candidates"],
    "fishnet_retry_engine": ["page_element_registry", "table_cell_normalizer", "figure_chart_understanding", "visual_ink_layout_calibrator", "evidence_consensus"],
    "fishnet_retry_refined": ["fishnet_retry_engine"],
    "element_graph_attachment": ["page_element_registry", "table_understanding", "table_cell_normalizer", "figure_chart_understanding", "fishnet_retry_refined", "embedding_candidates"],
    "graph_writeback_overlay": ["element_graph_attachment"],
    "graph_overlay_part_lineage": ["graph_writeback_overlay"],
    "graph_overlay_part_property_normalizer": ["graph_overlay_part_lineage"],
    "leiden_graph_communities": ["graph_overlay_part_property_normalizer"],
    "feedback_memory": ["final_answer_gate", "leiden_graph_communities"],
    "community_aware_retrieval_sim": ["hybrid_retrieval_sim", "leiden_graph_communities", "feedback_memory"],
    "graph_ui_community_overlay": ["graph_overlay_part_property_normalizer", "leiden_graph_communities", "feedback_memory", "community_aware_retrieval_sim"],
    "dublin_core_crosswalk": ["page_element_registry", "table_cell_normalizer", "figure_chart_understanding", "visual_ink_layout_calibrator", "element_graph_attachment", "leiden_graph_communities", "opensearch_adapter", "feedback_memory", "human_review_triage"],
    "dublin_core_crosswalk_refined": ["dublin_core_crosswalk"],
    "element_category_taxonomy": ["dublin_core_crosswalk_refined", "element_graph_attachment", "table_cell_normalizer", "figure_chart_understanding", "callout_visual_part_verifier", "human_review_triage", "opensearch_adapter", "leiden_graph_communities"],
    "category_aware_leiden_overlay": ["leiden_graph_communities", "element_category_taxonomy", "dublin_core_crosswalk_refined", "graph_ui_community_overlay"],
    "category_aware_graph_ui_overlay": ["graph_ui_community_overlay", "category_aware_leiden_overlay", "element_category_taxonomy", "dublin_core_crosswalk_refined"],
    "opensearch_adapter": ["embedding_candidates", "page_retrieval_profiles", "table_cell_normalizer", "evidence_snippet_cleaner", "context_retrieval_helpers", "leiden_graph_communities", "graph_overlay_part_property_normalizer"],
    "incremental_corpus_manifest": ["page_element_registry", "embedding_candidates", "element_graph_attachment", "leiden_graph_communities", "feedback_memory"],
    "incremental_orchestrator": ["incremental_corpus_manifest"],
    "incremental_processing_runner": ["incremental_orchestrator"],
    "incremental_state_commit_gate": ["incremental_processing_runner"],
    "it_operations_console": [],
    "it_issue_origin_test_matrix": ["it_operations_console"],
    "human_review_queue": ["it_operations_console", "fishnet_retry_refined", "figure_chart_understanding", "visual_ink_layout_calibrator", "callout_visual_part_verifier", "table_cell_normalizer", "feedback_memory", "leiden_graph_communities", "community_aware_retrieval_sim", "final_answer_gate"],
    "human_review_triage": ["human_review_queue"],
    "human_review_decisions": ["human_review_triage"],
    "human_review_promotion_gate": ["human_review_decisions", "human_review_triage", "table_cell_normalizer", "embedding_candidates", "graph_overlay_part_property_normalizer"],
    "promotion_writeback_dry_run": ["human_review_promotion_gate", "human_review_decisions", "human_review_triage"],
    "synthetic_incident_console": [],
    "synthetic_incident_console_postgres_smoke": ["synthetic_incident_console"],
    "incident_review_bridge": ["synthetic_incident_console"],
}

RECORD_LIST_KEYS = (
    "records",
    "page_records",
    "documents",
    "node_plans",
    "edge_plans",
    "claims",
    "review_tasks",
    "triage_cards",
    "decision_records",
    "promotion_records",
    "writeback_plans",
    "processing_steps",
    "planned_jobs",
    "artifact_records",
)

COUNT_KEYS = (
    "record_count",
    "page_count",
    "page_record_count",
    "document_count",
    "node_plan_count",
    "edge_plan_count",
    "opensearch_document_count",
    "review_task_count",
    "triage_card_count",
    "community_count",
    "claim_count",
    "feedback_event_count",
    "memory_record_count",
    "processing_step_count",
    "planned_job_count",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}__{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalize_status(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    text = str(value).strip()
    return text.upper() if text else "UNKNOWN"


def relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        rel = path
    return tuple(rel.parts)


def is_excluded_by_prefix(path: Path, root: Path, prefixes: Iterable[tuple[str, ...]]) -> bool:
    parts = relative_parts(path, root)
    for prefix in prefixes:
        if len(parts) >= len(prefix) and tuple(parts[: len(prefix)]) == prefix:
            return True
    return False


def is_primary_artifact(path: Path, root: Path, prefixes: Iterable[tuple[str, ...]]) -> bool:
    if path.suffix.lower() != ".json":
        return False
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return False
    if is_excluded_by_prefix(path, root, prefixes):
        return False
    name = path.name
    stem = path.stem
    if name in PRIMARY_EXCLUDED_EXACT_NAMES:
        return False
    if name in LEGACY_PRIMARY_FILE_STAGE_IDS:
        return True
    if name.endswith(PRIMARY_EXCLUDED_SUFFIXES):
        return False
    if any(token in stem for token in PRIMARY_EXCLUDED_STEM_CONTAINS):
        return False
    if name.startswith("trace_net_") and name.endswith("_v1.json"):
        return True
    return False


def stage_id_from_path(path: Path, root: Path) -> str:
    if path.name in LEGACY_PRIMARY_FILE_STAGE_IDS:
        return LEGACY_PRIMARY_FILE_STAGE_IDS[path.name]
    parts = relative_parts(path, root)
    if len(parts) >= 2:
        return parts[-2]
    stem = path.stem
    if stem.startswith("trace_net_"):
        stem = stem[len("trace_net_") :]
    if stem.endswith("_v1"):
        stem = stem[:-3]
    return stem


def find_quality_path(artifact_path: Path, payload: dict[str, Any]) -> Path | None:
    quality_path = payload.get("quality_path")
    candidates: list[Path] = []
    if isinstance(quality_path, str) and quality_path:
        q = Path(quality_path)
        candidates.append(q)
        candidates.append(artifact_path.parent / q.name)
    stem = artifact_path.stem
    if stem.endswith("_v1"):
        candidates.append(artifact_path.with_name(f"{stem}_quality.json"))
    candidates.extend(sorted(artifact_path.parent.glob("*quality*.json")))
    for c in candidates:
        try:
            if c.exists() and c.is_file():
                return c
        except OSError:
            continue
    return None


def get_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def infer_schema_version(payload: dict[str, Any], artifact_path: Path) -> str:
    summary = get_summary(payload)
    for source in [payload, summary]:
        value = source.get("schema_version")
        if value:
            return str(value)
    stem = artifact_path.stem
    return stem


def infer_record_count(payload: dict[str, Any], summary: dict[str, Any]) -> int:
    for key in COUNT_KEYS:
        value = summary.get(key)
        if isinstance(value, int):
            return int(value)
    for key in RECORD_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 1


def infer_page_count(payload: dict[str, Any], summary: dict[str, Any]) -> int:
    for key in ["page_count", "page_record_count", "source_page_count", "page_registry_record_count"]:
        value = summary.get(key)
        if isinstance(value, int):
            return int(value)
    pages: set[str] = set()
    for key in RECORD_LIST_KEYS:
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for row in value[:10000]:
            if isinstance(row, dict) and row.get("page_id"):
                pages.add(str(row["page_id"]))
    return len(pages)


def count_summary_flags(summary: dict[str, Any], suffix: str) -> int:
    total = 0
    for key, value in summary.items():
        if not key.endswith(suffix):
            continue
        if isinstance(value, bool):
            total += int(value)
        elif isinstance(value, (int, float)):
            total += int(value)
    return total


def build_artifact_record(path: Path, root: Path, dependency_map: dict[str, list[str]], prefixes: Iterable[tuple[str, ...]]) -> dict[str, Any]:
    payload = read_json(path)
    summary = get_summary(payload)
    stage_id = stage_id_from_path(path, root)
    artifact_id = stable_id("artifact", stage_id, relative_parts(path, root))
    qpath = find_quality_path(path, payload)
    quality_payload: dict[str, Any] = {}
    if qpath is not None:
        try:
            quality_payload = read_json(qpath)
        except Exception:
            quality_payload = {}
    status = payload.get("status") or summary.get("status") or quality_payload.get("status")
    quality_status = (
        payload.get("quality_status")
        or summary.get("quality_status")
        or quality_payload.get("quality_status")
        or quality_payload.get("status")
        or (status if normalize_status(status) in {"PASS", "OK"} else None)
    )
    schema_version = infer_schema_version(payload, path)
    file_hash = sha256_file(path)
    input_stage_ids = dependency_map.get(stage_id, [])
    source_truth_count = count_summary_flags(summary, "source_truth_mutation_allowed_count") + count_summary_flags(summary, "source_truth_mutations_performed")
    write_attempt_count = (
        count_summary_flags(summary, "postgres_write_attempt_count")
        + count_summary_flags(summary, "qdrant_write_attempt_count")
        + count_summary_flags(summary, "opensearch_write_attempt_count")
    )
    record = {
        "artifact_id": artifact_id,
        "stage_id": stage_id,
        "artifact_path": path.as_posix(),
        "relative_path": "/".join(relative_parts(path, root)),
        "quality_path": qpath.as_posix() if qpath else "",
        "quality_status": normalize_status(quality_status),
        "status": normalize_status(status),
        "schema_version": schema_version,
        "artifact_type": "trace_net_primary_report",
        "file_sha256": file_hash,
        "file_size_bytes": path.stat().st_size,
        "modified_time_ns": path.stat().st_mtime_ns,
        "record_count": infer_record_count(payload, summary),
        "page_count": infer_page_count(payload, summary),
        "input_stage_ids": input_stage_ids,
        "resolved_input_artifact_ids": [],
        "missing_input_stage_ids": [],
        "optional_missing_input_stage_ids": [],
        "downstream_stage_ids": [],
        "downstream_artifact_ids": [],
        "source_truth_mutation_allowed_count": source_truth_count,
        "write_attempt_count": write_attempt_count,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "registry_state": "clean" if normalize_status(quality_status) in {"PASS", "OK"} else "needs_review",
        "dirty_reason_codes": [] if normalize_status(quality_status) in {"PASS", "OK"} else ["quality_status_not_pass"],
    }
    return record


def discover_artifacts(root: str | Path, dependency_map: dict[str, list[str]], prefixes: Iterable[tuple[str, ...]]) -> list[dict[str, Any]]:
    root_path = Path(root)
    records: list[dict[str, Any]] = []
    for path in sorted(root_path.rglob("*.json")):
        if not is_primary_artifact(path, root_path, prefixes):
            continue
        try:
            records.append(build_artifact_record(path, root_path, dependency_map, prefixes))
        except Exception as exc:
            records.append(
                {
                    "artifact_id": stable_id("artifact_error", path.as_posix()),
                    "stage_id": stage_id_from_path(path, root_path),
                    "artifact_path": path.as_posix(),
                    "relative_path": "/".join(relative_parts(path, root_path)),
                    "quality_path": "",
                    "quality_status": "ERROR",
                    "status": "ERROR",
                    "schema_version": "unknown",
                    "artifact_type": "trace_net_primary_report_error",
                    "file_sha256": "",
                    "file_size_bytes": path.stat().st_size if path.exists() else 0,
                    "modified_time_ns": path.stat().st_mtime_ns if path.exists() else 0,
                    "record_count": 0,
                    "page_count": 0,
                    "input_stage_ids": dependency_map.get(stage_id_from_path(path, root_path), []),
                    "resolved_input_artifact_ids": [],
                    "missing_input_stage_ids": [],
                    "optional_missing_input_stage_ids": [],
                    "downstream_stage_ids": [],
                    "downstream_artifact_ids": [],
                    "source_truth_mutation_allowed_count": 0,
                    "write_attempt_count": 0,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "can_mutate_source_truth": False,
                    "source_truth_mutation_allowed": False,
                    "registry_state": "scan_error",
                    "dirty_reason_codes": ["artifact_scan_error"],
                    "scan_error": repr(exc),
                }
            )
    return records


def resolve_dependencies(records: list[dict[str, Any]], dependency_map: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_stage.setdefault(str(rec.get("stage_id")), []).append(rec)

    # Prefer the largest/latest record when a stage has several primary reports.
    stage_to_artifact: dict[str, str] = {}
    for stage, group in by_stage.items():
        chosen = sorted(group, key=lambda r: (int(r.get("record_count") or 0), int(r.get("modified_time_ns") or 0)), reverse=True)[0]
        stage_to_artifact[stage] = str(chosen["artifact_id"])

    edges: list[dict[str, Any]] = []
    downstream: dict[str, set[str]] = {str(r["artifact_id"]): set() for r in records}
    downstream_stages: dict[str, set[str]] = {str(r["artifact_id"]): set() for r in records}

    for rec in records:
        stage = str(rec.get("stage_id"))
        wanted = list(dependency_map.get(stage, rec.get("input_stage_ids") or []))
        resolved: list[str] = []
        missing: list[str] = []
        optional_missing: list[str] = []
        for input_stage in wanted:
            if input_stage == stage:
                missing.append(input_stage)
                continue
            target_artifact_id = stage_to_artifact.get(input_stage)
            if target_artifact_id:
                resolved.append(target_artifact_id)
                edge = {
                    "dependency_edge_id": stable_id("artifact_dep_edge", rec["artifact_id"], target_artifact_id),
                    "source_artifact_id": target_artifact_id,
                    "target_artifact_id": rec["artifact_id"],
                    "source_stage_id": input_stage,
                    "target_stage_id": stage,
                    "edge_type": "ARTIFACT_DEPENDS_ON_INPUT",
                    "weight": 1.0,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "source_truth_mutation_allowed": False,
                }
                edges.append(edge)
                downstream.setdefault(target_artifact_id, set()).add(str(rec["artifact_id"]))
                downstream_stages.setdefault(target_artifact_id, set()).add(stage)
            else:
                if input_stage in OPTIONAL_DEPENDENCY_STAGE_IDS:
                    optional_missing.append(input_stage)
                else:
                    missing.append(input_stage)
        rec["input_stage_ids"] = wanted
        rec["resolved_input_artifact_ids"] = sorted(set(resolved))
        rec["missing_input_stage_ids"] = sorted(set(missing))
        rec["optional_missing_input_stage_ids"] = sorted(set(optional_missing))
        if missing:
            rec.setdefault("dirty_reason_codes", []).append("missing_required_dependency_reference")
        if optional_missing:
            rec.setdefault("dirty_reason_codes", []).append("missing_optional_dependency_reference")

    for rec in records:
        artifact_id = str(rec["artifact_id"])
        rec["downstream_artifact_ids"] = sorted(downstream.get(artifact_id, set()))
        rec["downstream_stage_ids"] = sorted(downstream_stages.get(artifact_id, set()))
    return records, edges


def detect_cycles(edges: list[dict[str, Any]]) -> list[list[str]]:
    graph: dict[str, list[str]] = {}
    for edge in edges:
        source = str(edge["source_artifact_id"])
        target = str(edge["target_artifact_id"])
        graph.setdefault(source, []).append(target)
        graph.setdefault(target, [])

    visited: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for nxt in graph.get(node, []):
            if nxt not in visited:
                dfs(nxt)
            elif nxt in stack:
                try:
                    idx = path.index(nxt)
                    cycles.append(path[idx:] + [nxt])
                except ValueError:
                    cycles.append([node, nxt])
        stack.discard(node)
        path.pop()

    for node in list(graph):
        if node not in visited:
            dfs(node)
    # Deduplicate by string form.
    unique: dict[str, list[str]] = {}
    for c in cycles:
        unique["->".join(c)] = c
    return list(unique.values())


def combine_dependency_hashes(record: dict[str, Any], records_by_id: dict[str, dict[str, Any]]) -> str:
    parts = [str(record.get("file_sha256") or "")]
    for dep_id in record.get("resolved_input_artifact_ids") or []:
        dep = records_by_id.get(dep_id)
        if dep:
            parts.append(str(dep.get("file_sha256") or ""))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def finalize_cache_keys(records: list[dict[str, Any]]) -> None:
    by_id = {str(r["artifact_id"]): r for r in records}
    for rec in records:
        rec["artifact_cache_key"] = combine_dependency_hashes(rec, by_id)
        rec["input_artifact_count"] = len(rec.get("resolved_input_artifact_ids") or [])
        rec["missing_input_stage_count"] = len(rec.get("missing_input_stage_ids") or [])
        rec["optional_missing_input_stage_count"] = len(rec.get("optional_missing_input_stage_ids") or [])
        rec["downstream_artifact_count"] = len(rec.get("downstream_artifact_ids") or [])


def count_by(rows: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def summarize(records: list[dict[str, Any]], edges: list[dict[str, Any]], cycles: list[list[str]], root: str | Path) -> dict[str, Any]:
    missing_quality = [r for r in records if r.get("quality_status") in {"UNKNOWN", "ERROR", ""}]
    failed_quality = [r for r in records if r.get("quality_status") not in {"PASS", "OK", "UNKNOWN"}]
    missing_deps = sum(int(r.get("missing_input_stage_count") or 0) for r in records)
    optional_missing_deps = sum(int(r.get("optional_missing_input_stage_count") or 0) for r in records)
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "trace_net_root": Path(root).as_posix(),
        "artifact_record_count": len(records),
        "dependency_edge_count": len(edges),
        "dependency_cycle_count": len(cycles),
        "stage_count": len({str(r.get("stage_id")) for r in records}),
        "quality_status_counts": count_by(records, "quality_status"),
        "registry_state_counts": count_by(records, "registry_state"),
        "stage_record_counts": count_by(records, "stage_id"),
        "missing_quality_status_count": len(missing_quality),
        "quality_not_pass_count": len(failed_quality),
        "missing_dependency_reference_count": missing_deps,
        "optional_missing_dependency_reference_count": optional_missing_deps,
        "artifacts_with_missing_dependency_reference_count": sum(1 for r in records if int(r.get("missing_input_stage_count") or 0) > 0),
        "artifacts_with_optional_missing_dependency_reference_count": sum(1 for r in records if int(r.get("optional_missing_input_stage_count") or 0) > 0),
        "artifacts_with_downstream_count": sum(1 for r in records if int(r.get("downstream_artifact_count") or 0) > 0),
        "missing_artifact_path_count": sum(1 for r in records if not Path(str(r.get("artifact_path") or "")).exists()),
        "duplicate_artifact_id_count": len(records) - len({str(r.get("artifact_id")) for r in records}),
        "self_dependency_count": sum(1 for e in edges if e.get("source_artifact_id") == e.get("target_artifact_id")),
        "source_truth_mutation_allowed_count": sum(int(r.get("source_truth_mutation_allowed_count") or 0) for r in records),
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "can_mutate_source_truth_count": 0,
        "read_only_registry": True,
    }


def quality_report(
    report: dict[str, Any],
    *,
    min_artifacts: int = 1,
    min_dependency_edges: int = 0,
    require_no_cycles: bool = True,
    require_quality_status: bool = False,
) -> dict[str, Any]:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else report
    issues: list[str] = []

    def fail_if(condition: bool, message: str) -> None:
        if condition:
            issues.append(message)

    fail_if(int(summary.get("artifact_record_count") or 0) < min_artifacts, f"artifact_record_count below minimum {min_artifacts}")
    fail_if(int(summary.get("dependency_edge_count") or 0) < min_dependency_edges, f"dependency_edge_count below minimum {min_dependency_edges}")
    if require_no_cycles:
        fail_if(int(summary.get("dependency_cycle_count") or 0) != 0, "dependency_cycle_count must be zero")
    if require_quality_status:
        fail_if(int(summary.get("missing_quality_status_count") or 0) != 0, "missing_quality_status_count must be zero")
    for key in [
        "missing_artifact_path_count",
        "duplicate_artifact_id_count",
        "self_dependency_count",
        "source_truth_mutation_allowed_count",
        "source_truth_mutations_performed",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "can_mutate_source_truth_count",
    ]:
        fail_if(int(summary.get(key) or 0) != 0, f"{key} must be zero")
    fail_if(not bool(summary.get("read_only_registry", True)), "registry must be read-only")
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "issue_count": len(issues),
        "checks": {
            "min_artifacts": min_artifacts,
            "min_dependency_edges": min_dependency_edges,
            "require_no_cycles": require_no_cycles,
            "require_quality_status": require_quality_status,
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRACE-Net Artifact Dependency Registry v1",
        "",
        f"**Status:** {report['status']}",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "artifact_record_count",
        "stage_count",
        "dependency_edge_count",
        "dependency_cycle_count",
        "missing_dependency_reference_count",
        "optional_missing_dependency_reference_count",
        "missing_quality_status_count",
        "quality_not_pass_count",
        "source_truth_mutation_allowed_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Top Artifacts", "", "| Stage | Quality | Records | Dependencies | Downstream |", "|---|---|---:|---:|---:|"])
    for rec in report["artifact_records"][:25]:
        lines.append(
            f"| {rec.get('stage_id')} | {rec.get('quality_status')} | {rec.get('record_count')} | {rec.get('input_artifact_count')} | {rec.get('downstream_artifact_count')} |"
        )
    return "\n".join(lines) + "\n"


def html_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in summary.items() if isinstance(v, (str, int, float, bool)) or v is None)
    artifact_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            rec.get("stage_id"), rec.get("quality_status"), rec.get("record_count"), rec.get("input_artifact_count"), rec.get("downstream_artifact_count")
        )
        for rec in report["artifact_records"][:100]
    )
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Artifact Dependency Registry v1</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:6px}}th{{background:#f5f5f5;text-align:left}}</style></head>
<body>
<h1>TRACE-Net Artifact Dependency Registry v1</h1>
<p><b>Status:</b> {report['status']} &nbsp; <b>Quality:</b> {report['quality_status']}</p>
<h2>Summary</h2><table>{rows}</table>
<h2>Artifacts</h2><table><tr><th>Stage</th><th>Quality</th><th>Records</th><th>Inputs</th><th>Downstream</th></tr>{artifact_rows}</table>
</body></html>"""


def build_artifact_dependency_registry(
    trace_net_root: str | Path,
    output_dir: str | Path,
    *,
    min_artifacts: int = 1,
    min_dependency_edges: int = 0,
    require_no_cycles: bool = True,
    require_quality_status: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    root = Path(trace_net_root)
    if not root.exists():
        raise FileNotFoundError(f"trace_net_root does not exist: {root}")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    prefixes = DEFAULT_EXCLUDED_RELATIVE_PREFIXES
    dependency_map = dict(DEFAULT_DEPENDENCY_MAP)
    records = discover_artifacts(root, dependency_map, prefixes)
    records, edges = resolve_dependencies(records, dependency_map)
    finalize_cache_keys(records)
    cycles = detect_cycles(edges)
    summary = summarize(records, edges, cycles, root)
    quality = quality_report(
        {"summary": summary},
        min_artifacts=min_artifacts,
        min_dependency_edges=min_dependency_edges,
        require_no_cycles=require_no_cycles,
        require_quality_status=require_quality_status,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "ARTIFACT_DEPENDENCY_REGISTRY_BUILT",
        "quality_status": quality["status"],
        "generated_at": utc_now(),
        "trace_net_root": root.as_posix(),
        "summary": {**summary, "quality_status": quality["status"]},
        "quality": quality,
        "artifact_records": records,
        "dependency_edges": edges,
        "dependency_cycles": cycles,
    }
    report["report_path"] = (output / "trace_net_artifact_dependency_registry_v1.json").as_posix()
    report["records_path"] = (output / "trace_net_artifact_dependency_registry_v1_records.jsonl").as_posix()
    report["edges_path"] = (output / "trace_net_artifact_dependency_registry_v1_edges.jsonl").as_posix()
    report["summary_path"] = (output / "trace_net_artifact_dependency_registry_v1_summary.json").as_posix()
    report["quality_path"] = (output / "trace_net_artifact_dependency_registry_v1_quality.json").as_posix()

    write_json(output / "trace_net_artifact_dependency_registry_v1.json", report)
    write_json(output / "trace_net_artifact_dependency_registry_v1_summary.json", report["summary"])
    write_json(output / "trace_net_artifact_dependency_registry_v1_quality.json", quality)
    write_jsonl(output / "trace_net_artifact_dependency_registry_v1_records.jsonl", records)
    write_jsonl(output / "trace_net_artifact_dependency_registry_v1_edges.jsonl", edges)
    write_json(
        output / "trace_net_artifact_dependency_registry_v1_manifest.json",
        {
            "schema_version": f"{SCHEMA_VERSION}_manifest",
            "generated_at": report["generated_at"],
            "report_path": report["report_path"],
            "trace_net_root": root.as_posix(),
            "quality_status": report["quality_status"],
            "artifact_record_count": summary["artifact_record_count"],
            "dependency_edge_count": summary["dependency_edge_count"],
        },
    )
    (output / "trace_net_artifact_dependency_registry_v1.md").write_text(markdown_report(report), encoding="utf-8")
    (output / "trace_net_artifact_dependency_registry_v1.html").write_text(html_report(report), encoding="utf-8")
    return report


def check_artifact_dependency_registry_quality(
    report_path: str | Path,
    *,
    min_artifacts: int = 1,
    min_dependency_edges: int = 0,
    require_no_cycles: bool = True,
    require_quality_status: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path)
    quality = quality_report(
        report,
        min_artifacts=min_artifacts,
        min_dependency_edges=min_dependency_edges,
        require_no_cycles=require_no_cycles,
        require_quality_status=require_quality_status,
    )
    if write_json_report:
        qpath = Path(report_path).with_name("trace_net_artifact_dependency_registry_v1_quality.json")
        write_json(qpath, quality)
    return quality


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Artifact Dependency Registry v1")
    parser.add_argument("--trace-net-root", required=False, default="local_data/organization/trace_net")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-artifacts", type=int, default=1)
    parser.add_argument("--min-dependency-edges", type=int, default=0)
    parser.add_argument("--allow-cycles", action="store_true")
    parser.add_argument("--require-quality-status", action="store_true")
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--check", action="store_true", help="Check an existing report instead of building")
    parser.add_argument("--report-path", help="Existing report path for --check")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        if not args.report_path:
            parser.error("--report-path is required with --check")
        q = check_artifact_dependency_registry_quality(
            args.report_path,
            min_artifacts=args.min_artifacts,
            min_dependency_edges=args.min_dependency_edges,
            require_no_cycles=not args.allow_cycles,
            require_quality_status=args.require_quality_status,
            write_json_report=args.write_json,
        )
        print("TRACE-Net artifact dependency registry v1 quality")
        print(f" Status: {q['status']}")
        print(f" issue_count: {q['issue_count']}")
        return 0 if q["status"] == "PASS" else 1

    report = build_artifact_dependency_registry(
        args.trace_net_root,
        args.output_dir,
        min_artifacts=args.min_artifacts,
        min_dependency_edges=args.min_dependency_edges,
        require_no_cycles=not args.allow_cycles,
        require_quality_status=args.require_quality_status,
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net artifact dependency registry v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "artifact_record_count",
        "stage_count",
        "dependency_edge_count",
        "dependency_cycle_count",
        "missing_dependency_reference_count",
        "missing_quality_status_count",
        "quality_not_pass_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
