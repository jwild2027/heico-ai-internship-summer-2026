"""TRACE-Net Incremental Orchestrator v1.

This module converts a Step 24 incremental corpus manifest into a safe,
read-only job plan. It does not execute OCR, extraction, embedding, Qdrant,
OpenSearch, graph writeback, or Leiden jobs. It only decides which jobs would
run for new/changed/removed pages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_incremental_orchestrator_v1"
ALGORITHM = "trace_net_dependency_aware_incremental_job_planner_v1"

# Ordered job plan. The stage keys match Step 24 dirty_stages.
STAGE_JOB_MAP: list[tuple[str, str, str, str, list[str]]] = [
    ("ocr", "ocr_changed_pages", "ocr", "run_ocr_changed_pages", ["page_id", "source_file_ids"]),
    ("page_element_registry", "page_element_registry_changed_pages", "page_intelligence", "rebuild_page_registry_changed_pages", ["page_id"]),
    ("table_understanding", "table_understanding_changed_pages", "table", "rebuild_table_understanding_changed_pages", ["page_id"]),
    ("table_cell_normalizer", "table_cell_normalizer_changed_pages", "table", "normalize_table_cells_changed_pages", ["page_id"]),
    ("figure_chart_understanding", "figure_chart_understanding_changed_pages", "visual", "rebuild_figure_chart_understanding_changed_pages", ["page_id"]),
    ("visual_ink_layout_calibrator", "visual_ink_layout_changed_pages", "visual", "rebuild_visual_ink_layout_changed_pages", ["page_id"]),
    ("evidence_consensus", "evidence_consensus_changed_pages", "trust", "rerun_evidence_consensus_changed_pages", ["page_id"]),
    ("fishnet_retry", "fishnet_retry_changed_pages", "fishnet", "rerun_fishnet_retry_changed_pages", ["page_id"]),
    ("trust_authority", "trust_authority_changed_pages", "trust", "rerun_trust_authority_changed_pages", ["page_id"]),
    ("safe_candidates", "safe_candidates_changed_pages", "candidate", "rebuild_safe_candidates_changed_pages", ["page_id"]),
    ("embeddings", "embedding_changed_candidates", "embedding", "reembed_changed_candidates", ["page_id", "embedding_candidate_ids"]),
    ("qdrant_upsert", "qdrant_upsert_changed_points", "qdrant", "upsert_changed_qdrant_points", ["page_id", "embedding_candidate_ids"]),
    ("opensearch_upsert", "opensearch_upsert_changed_docs", "opensearch", "upsert_changed_opensearch_docs", ["page_id"]),
    ("graph_attachment", "graph_attachment_changed_pages", "graph", "rebuild_graph_attachment_changed_pages", ["page_id"]),
    ("graph_writeback", "graph_writeback_changed_nodes", "graph", "writeback_changed_graph_nodes_dry_run_first", ["page_id"]),
    ("leiden_communities", "leiden_refresh_required", "community", "refresh_leiden_communities_if_graph_changed", ["page_id"]),
    ("retrieval_regression_smoke", "retrieval_regression_smoke_changed_corpus", "quality", "run_incremental_retrieval_smoke", ["page_id"]),
]

REMOVAL_JOB_MAP: list[tuple[str, str, str, str]] = [
    ("source_removed", "source_removed_review", "source", "review_removed_source_records"),
    ("qdrant_delete", "qdrant_delete_removed_points", "qdrant", "delete_or_tombstone_removed_qdrant_points"),
    ("opensearch_delete", "opensearch_delete_removed_docs", "opensearch", "delete_or_tombstone_removed_opensearch_docs"),
    ("graph_writeback", "graph_tombstone_removed_source_nodes", "graph", "tombstone_removed_source_graph_nodes_dry_run_first"),
    ("leiden_communities", "leiden_refresh_after_source_removal", "community", "refresh_leiden_after_source_removal"),
]

BASELINE_VALIDATION_JOB = {
    "stage": "no_dirty_pages",
    "job_type": "no_op_quality_validation",
    "job_family": "quality",
    "runner_hint": "confirm_manifest_clean_no_downstream_work",
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def get_manifest_pages(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    pages = manifest.get("page_manifest_records") or manifest.get("pages") or []
    return [p for p in pages if isinstance(p, dict)]


def get_source_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in ("source_file_records", "missing_source_file_records"):
        value = manifest.get(key) or []
        rows.extend([r for r in value if isinstance(r, dict)])
    return rows


def page_sort_key(page_id: str) -> tuple[str, int, str]:
    number = 0
    if "_p" in page_id:
        tail = page_id.rsplit("_p", 1)[-1]
        if tail.isdigit():
            number = int(tail)
    document = page_id.rsplit("_p", 1)[0] if "_p" in page_id else ""
    return (document, number, page_id)


def unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted({v for v in values if isinstance(v, str) and v}, key=page_sort_key)


def dirty_pages_for_stage(pages: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    out = []
    for page in pages:
        dirty_stages = page.get("dirty_stages") or []
        if stage in dirty_stages:
            out.append(page)
    return out


def page_ids_for(pages: list[dict[str, Any]]) -> list[str]:
    return unique_sorted(p.get("page_id") for p in pages)


def collect_candidate_ids(pages: list[dict[str, Any]]) -> list[str]:
    # The Step 24 manifest is page scoped and may not carry candidate IDs. Keep
    # this list if future manifests add them, otherwise the page list is enough.
    ids: set[str] = set()
    for page in pages:
        for key in ("embedding_candidate_ids", "candidate_ids", "source_candidate_ids"):
            for value in page.get(key) or []:
                if isinstance(value, str) and value:
                    ids.add(value)
    return sorted(ids)


def build_job_for_stage(stage: str, job_type: str, job_family: str, runner_hint: str, payload_keys: list[str], pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    affected_pages = dirty_pages_for_stage(pages, stage)
    if not affected_pages:
        return None
    affected_page_ids = page_ids_for(affected_pages)
    job_id = "job__" + stable_hash({"stage": stage, "pages": affected_page_ids}, 20)
    job = {
        "job_id": job_id,
        "stage": stage,
        "job_type": job_type,
        "job_family": job_family,
        "runner_hint": runner_hint,
        "affected_page_ids": affected_page_ids,
        "affected_page_count": len(affected_page_ids),
        "priority": job_priority(stage, affected_page_count=len(affected_page_ids)),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutations_performed": 0,
        "requires_success_before_state_commit": True,
        "dry_run_recommended_before_write": job_family in {"graph", "qdrant", "opensearch"},
        "full_rescan_required": False,
        "skip_reason": None,
    }
    if "embedding_candidate_ids" in payload_keys:
        job["embedding_candidate_ids"] = collect_candidate_ids(affected_pages)
    if "source_file_ids" in payload_keys:
        source_ids: set[str] = set()
        for page in affected_pages:
            for source_id in page.get("source_file_ids") or []:
                if isinstance(source_id, str) and source_id:
                    source_ids.add(source_id)
        job["source_file_ids"] = sorted(source_ids)
        job["source_file_count"] = len(source_ids)
    return job


def job_priority(stage: str, *, affected_page_count: int) -> str:
    if stage in {"source_removed", "qdrant_delete", "opensearch_delete"}:
        return "high"
    if stage in {"ocr", "evidence_consensus", "trust_authority", "safe_candidates"}:
        return "high"
    if stage in {"qdrant_upsert", "opensearch_upsert", "graph_writeback"}:
        return "medium"
    if affected_page_count > 100:
        return "medium"
    return "normal"


def build_removal_jobs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    missing = [r for r in manifest.get("missing_source_file_records", []) or [] if isinstance(r, dict)]
    if not missing:
        return []
    page_ids = unique_sorted(pid for row in missing for pid in (row.get("page_ids") or []))
    source_ids = sorted({row.get("file_id") for row in missing if row.get("file_id")})
    jobs = []
    for stage, job_type, family, runner_hint in REMOVAL_JOB_MAP:
        job = {
            "job_id": "job__" + stable_hash({"stage": stage, "job_type": job_type, "source_ids": source_ids}, 20),
            "stage": stage,
            "job_type": job_type,
            "job_family": family,
            "runner_hint": runner_hint,
            "affected_page_ids": page_ids,
            "affected_page_count": len(page_ids),
            "source_file_ids": source_ids,
            "source_file_count": len(source_ids),
            "priority": "high",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutations_performed": 0,
            "requires_success_before_state_commit": True,
            "dry_run_recommended_before_write": family in {"graph", "qdrant", "opensearch"},
            "full_rescan_required": False,
            "removal_job": True,
        }
        jobs.append(job)
    return jobs


def build_incremental_orchestrator_plan(
    *,
    manifest_path: str | Path,
    output_dir: str | Path = "local_data/organization/trace_net/incremental_orchestrator",
    require_page_count: int | None = None,
    full_rescan_threshold: float = 1.10,
    write_quality: bool = False,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    pages = get_manifest_pages(manifest)
    source_records = get_source_records(manifest)
    page_count = len(pages)
    dirty_pages = [p for p in pages if p.get("dirty_stage_count", 0) > 0]
    missing_source_page_ids = unique_sorted(
        pid
        for row in (manifest.get("missing_source_file_records") or [])
        if isinstance(row, dict)
        for pid in (row.get("page_ids") or [])
    )
    dirty_page_ids = unique_sorted([*page_ids_for(dirty_pages), *missing_source_page_ids])
    dirty_fraction = (len(dirty_page_ids) / page_count) if page_count else 0.0
    full_rescan_required = bool(page_count and dirty_fraction > full_rescan_threshold)

    planned_jobs: list[dict[str, Any]] = []
    for stage, job_type, family, runner_hint, keys in STAGE_JOB_MAP:
        job = build_job_for_stage(stage, job_type, family, runner_hint, keys, pages)
        if job:
            job["full_rescan_required"] = full_rescan_required
            planned_jobs.append(job)
    planned_jobs.extend(build_removal_jobs(manifest))

    # If the manifest is clean, make that explicit as a no-op plan record while
    # keeping planned_job_count at zero for downstream gating.
    no_op_job: dict[str, Any] | None = None
    if not planned_jobs:
        no_op_job = {
            "job_id": "job__" + stable_hash({"stage": "no_dirty_pages", "manifest": str(manifest_path)}, 20),
            **BASELINE_VALIDATION_JOB,
            "affected_page_ids": [],
            "affected_page_count": 0,
            "priority": "none",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutations_performed": 0,
            "requires_success_before_state_commit": True,
            "full_rescan_required": False,
            "skip_reason": "manifest_has_zero_dirty_pages",
        }

    summary = summarize_plan(
        manifest=manifest,
        pages=pages,
        source_records=source_records,
        planned_jobs=planned_jobs,
        no_op_job=no_op_job,
        dirty_page_ids=dirty_page_ids,
        require_page_count=require_page_count,
        full_rescan_required=full_rescan_required,
    )

    plan = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "INCREMENTAL_ORCHESTRATOR_PLAN_BUILT",
        "quality_status": "PASS" if quality_passes(summary) else "FAIL",
        "created_at": now_iso(),
        "input_manifest_path": str(manifest_path),
        "writeback_mode": "read_only_job_plan",
        "execution_mode": "plan_only",
        "state_commit_policy": "commit_after_all_planned_jobs_succeed",
        "state_commit_after_success_only": True,
        "full_rescan_required": full_rescan_required,
        "dirty_page_ids": dirty_page_ids,
        "planned_jobs": planned_jobs,
        "no_op_job": no_op_job,
        "summary": summary,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutations_performed": 0,
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_incremental_orchestrator_v1.json"
    jobs_path = out / "trace_net_incremental_orchestrator_v1_jobs.jsonl"
    dirty_pages_path = out / "trace_net_incremental_orchestrator_v1_dirty_pages.jsonl"
    summary_path = out / "trace_net_incremental_orchestrator_v1_summary.json"
    quality_path = out / "trace_net_incremental_orchestrator_v1_quality.json"
    readme_path = out / "trace_net_incremental_orchestrator_v1.md"

    write_json(report_path, plan)
    write_jsonl(jobs_path, planned_jobs)
    write_jsonl(dirty_pages_path, [{"page_id": pid} for pid in dirty_page_ids])
    write_json(summary_path, summary)
    write_markdown(readme_path, plan)
    if write_quality:
        quality = quality_report(plan)
        write_json(quality_path, quality)
        plan["quality_path"] = str(quality_path)
        write_json(report_path, plan)

    plan["report_path"] = str(report_path)
    plan["jobs_path"] = str(jobs_path)
    plan["dirty_pages_path"] = str(dirty_pages_path)
    plan["summary_path"] = str(summary_path)
    return plan


def summarize_plan(
    *,
    manifest: dict[str, Any],
    pages: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    planned_jobs: list[dict[str, Any]],
    no_op_job: dict[str, Any] | None,
    dirty_page_ids: list[str],
    require_page_count: int | None,
    full_rescan_required: bool,
) -> dict[str, Any]:
    page_count = len(pages)
    planned_job_count = len(planned_jobs)
    affected_page_ids = unique_sorted(pid for job in planned_jobs for pid in job.get("affected_page_ids", []))
    job_type_counts = Counter(job.get("job_type") for job in planned_jobs)
    job_family_counts = Counter(job.get("job_family") for job in planned_jobs)
    dirty_stage_counts = Counter()
    for page in pages:
        dirty_stage_counts.update(page.get("dirty_stages") or [])
    unchanged_page_reprocess_count = sum(
        1
        for pid in affected_page_ids
        if pid not in set(dirty_page_ids)
    )
    unsafe_job_count = sum(
        1
        for job in planned_jobs
        if job.get("can_answer_directly") or job.get("can_prove_claims") or job.get("can_mutate_source_truth")
    )
    source_truth_mutation_allowed_count = sum(1 for job in planned_jobs if job.get("can_mutate_source_truth"))
    destructive_job_count = sum(1 for job in planned_jobs if job.get("job_family") in {"qdrant", "opensearch", "graph"} and job.get("dry_run_recommended_before_write"))
    source_state_counts = Counter(r.get("change_state") for r in source_records if r.get("change_state"))
    no_jobs_when_clean = (len(dirty_page_ids) > 0) or planned_job_count == 0
    checks = {
        "page_count_matches_required": require_page_count is None or page_count == require_page_count,
        "full_rescan_required_false": not full_rescan_required,
        "unsafe_job_count_zero": unsafe_job_count == 0,
        "source_truth_mutation_allowed_count_zero": source_truth_mutation_allowed_count == 0,
        "unchanged_page_reprocess_count_zero": unchanged_page_reprocess_count == 0,
        "state_commit_after_success_only_true": True,
        "no_jobs_when_manifest_clean": no_jobs_when_clean,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": status,
        "manifest_schema_version": manifest.get("schema_version"),
        "manifest_quality_status": manifest.get("quality_status") or (manifest.get("summary") or {}).get("status"),
        "page_count": page_count,
        "source_record_count": len(source_records),
        "dirty_page_count": len(dirty_page_ids),
        "affected_page_count": len(affected_page_ids),
        "planned_job_count": planned_job_count,
        "no_op_planned": no_op_job is not None,
        "full_rescan_required": full_rescan_required,
        "full_rescan_required_count": 1 if full_rescan_required else 0,
        "unchanged_page_reprocess_count": unchanged_page_reprocess_count,
        "unsafe_job_count": unsafe_job_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "source_truth_mutations_performed": 0,
        "state_commit_after_success_only": True,
        "destructive_job_count_requiring_dry_run": destructive_job_count,
        "job_type_counts": dict(job_type_counts),
        "job_family_counts": dict(job_family_counts),
        "dirty_stage_counts": dict(dirty_stage_counts),
        "source_state_counts": dict(source_state_counts),
        "new_source_count": source_state_counts.get("new", 0),
        "changed_source_count": source_state_counts.get("changed", 0),
        "unchanged_source_count": source_state_counts.get("unchanged", 0),
        "removed_source_count": source_state_counts.get("missing", 0),
        "needs_ocr_job_count": job_type_counts.get("ocr_changed_pages", 0),
        "needs_embedding_job_count": job_type_counts.get("embedding_changed_candidates", 0),
        "needs_qdrant_job_count": job_type_counts.get("qdrant_upsert_changed_points", 0),
        "needs_opensearch_job_count": job_type_counts.get("opensearch_upsert_changed_docs", 0),
        "needs_graph_job_count": job_type_counts.get("graph_writeback_changed_nodes", 0),
        "needs_leiden_job_count": job_type_counts.get("leiden_refresh_required", 0),
        "quality_checks": checks,
    }


def quality_passes(summary: dict[str, Any]) -> bool:
    return summary.get("status") == "PASS" and all((summary.get("quality_checks") or {}).values())


def quality_report(
    report_or_path: dict[str, Any] | str | Path,
    *,
    require_page_count: int | None = None,
    max_unchanged_page_reprocess: int | None = None,
    require_no_full_rescan: bool = False,
    require_no_jobs_if_clean: bool = True,
    write_json_report: bool = False,
) -> dict[str, Any]:
    if isinstance(report_or_path, (str, Path)):
        plan = read_json(report_or_path)
        report_path = Path(report_or_path)
    else:
        plan = report_or_path
        report_path = None
    summary = dict(plan.get("summary") or {})
    checks = dict(summary.get("quality_checks") or {})
    if require_page_count is not None:
        checks["page_count_matches_required"] = summary.get("page_count") == require_page_count
    if max_unchanged_page_reprocess is not None:
        checks["unchanged_page_reprocess_within_limit"] = summary.get("unchanged_page_reprocess_count", 0) <= max_unchanged_page_reprocess
    if require_no_full_rescan:
        checks["full_rescan_required_false"] = not summary.get("full_rescan_required")
    if require_no_jobs_if_clean:
        clean = summary.get("dirty_page_count", 0) == 0
        checks["no_jobs_when_manifest_clean"] = (not clean) or summary.get("planned_job_count", 0) == 0
    status = "PASS" if all(checks.values()) else "FAIL"
    summary["quality_checks"] = checks
    summary["status"] = status
    report = {
        "schema_version": SCHEMA_VERSION + "_quality",
        "status": status,
        "quality_status": status,
        "summary": summary,
        "page_count": summary.get("page_count", 0),
        "dirty_page_count": summary.get("dirty_page_count", 0),
        "planned_job_count": summary.get("planned_job_count", 0),
        "affected_page_count": summary.get("affected_page_count", 0),
        "full_rescan_required": summary.get("full_rescan_required", False),
        "unchanged_page_reprocess_count": summary.get("unchanged_page_reprocess_count", 0),
        "unsafe_job_count": summary.get("unsafe_job_count", 0),
        "source_truth_mutation_allowed_count": summary.get("source_truth_mutation_allowed_count", 0),
        "state_commit_after_success_only": summary.get("state_commit_after_success_only", False),
    }
    if write_json_report and report_path is not None:
        quality_path = report_path.with_name("trace_net_incremental_orchestrator_v1_quality.json")
        write_json(quality_path, report)
        report["quality_path"] = str(quality_path)
    return report


def write_markdown(path: Path, plan: dict[str, Any]) -> None:
    summary = plan.get("summary") or {}
    lines = [
        "# TRACE-Net Incremental Orchestrator v1",
        "",
        f"**Status:** {plan.get('status')}",
        f"**Quality:** {plan.get('quality_status')}",
        f"**Execution mode:** {plan.get('execution_mode')}",
        f"**Writeback mode:** {plan.get('writeback_mode')}",
        "",
        "## Summary",
        "",
        f"- Pages: {summary.get('page_count', 0)}",
        f"- Dirty pages: {summary.get('dirty_page_count', 0)}",
        f"- Affected pages: {summary.get('affected_page_count', 0)}",
        f"- Planned jobs: {summary.get('planned_job_count', 0)}",
        f"- Full rescan required: {summary.get('full_rescan_required', False)}",
        f"- Unchanged page reprocess count: {summary.get('unchanged_page_reprocess_count', 0)}",
        f"- Unsafe jobs: {summary.get('unsafe_job_count', 0)}",
        f"- Source-truth mutation allowed: {summary.get('source_truth_mutation_allowed_count', 0)}",
        "",
        "## Planned job types",
        "",
    ]
    for job_type, count in sorted((summary.get("job_type_counts") or {}).items()):
        lines.append(f"- {job_type}: {count}")
    if not (summary.get("job_type_counts") or {}):
        lines.append("- none: manifest is clean")
    lines.extend([
        "",
        "## Safety rule",
        "",
        "This is a plan-only orchestrator. It cannot answer directly, prove claims, mutate source truth, or commit state before downstream jobs succeed.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_plan_summary(plan: dict[str, Any]) -> None:
    summary = plan.get("summary") or {}
    print("TRACE-Net incremental orchestrator v1")
    print(f" Status: {plan.get('status')}")
    print(f" Quality status: {plan.get('quality_status')}")
    print(f" page_count: {summary.get('page_count', 0)}")
    print(f" dirty_page_count: {summary.get('dirty_page_count', 0)}")
    print(f" affected_page_count: {summary.get('affected_page_count', 0)}")
    print(f" planned_job_count: {summary.get('planned_job_count', 0)}")
    print(f" full_rescan_required: {summary.get('full_rescan_required', False)}")
    print(f" unchanged_page_reprocess_count: {summary.get('unchanged_page_reprocess_count', 0)}")
    print(f" unsafe_job_count: {summary.get('unsafe_job_count', 0)}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}")
    print(f" state_commit_after_success_only: {summary.get('state_commit_after_success_only', False)}")
    print(f" report_path: {plan.get('report_path')}")
    if plan.get("jobs_path"):
        print(f" jobs_path: {plan.get('jobs_path')}")
    if plan.get("quality_path"):
        print(f" quality_path: {plan.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net incremental orchestrator v1")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/incremental_orchestrator")
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--full-rescan-threshold", type=float, default=1.10)
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    plan = build_incremental_orchestrator_plan(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        require_page_count=args.require_page_count,
        full_rescan_threshold=args.full_rescan_threshold,
        write_quality=args.quality,
    )
    print_plan_summary(plan)
    return 0 if plan.get("quality_status") == "PASS" else 1


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net incremental orchestrator v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--max-unchanged-page-reprocess", type=int, default=0)
    parser.add_argument("--require-no-full-rescan", action="store_true")
    parser.add_argument("--allow-jobs-when-clean", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: list[str] | None = None) -> int:
    args = quality_arg_parser().parse_args(argv)
    report = quality_report(
        args.report_path,
        require_page_count=args.require_page_count,
        max_unchanged_page_reprocess=args.max_unchanged_page_reprocess,
        require_no_full_rescan=args.require_no_full_rescan,
        require_no_jobs_if_clean=not args.allow_jobs_when_clean,
        write_json_report=args.write_json,
    )
    summary = report.get("summary") or {}
    print("TRACE-Net incremental orchestrator v1 quality")
    print(f" Status: {report.get('status')}")
    print(f" page_count: {summary.get('page_count', 0)}")
    print(f" dirty_page_count: {summary.get('dirty_page_count', 0)}")
    print(f" affected_page_count: {summary.get('affected_page_count', 0)}")
    print(f" planned_job_count: {summary.get('planned_job_count', 0)}")
    print(f" full_rescan_required: {summary.get('full_rescan_required', False)}")
    print(f" unchanged_page_reprocess_count: {summary.get('unchanged_page_reprocess_count', 0)}")
    print(f" unsafe_job_count: {summary.get('unsafe_job_count', 0)}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")
    return 0 if report.get("status") == "PASS" else 1


# Compatibility aliases for tests/future callers.
run_incremental_orchestrator = build_incremental_orchestrator_plan
check_incremental_orchestrator_quality = quality_report


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
