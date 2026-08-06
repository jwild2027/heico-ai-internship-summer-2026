"""TRACE-Net Incremental Processing Runner v1.

This module converts a TRACE-Net incremental orchestrator plan into a
server-ready dry-run processing plan.  It intentionally does not run OCR,
write to Postgres, write to Qdrant, or write to OpenSearch.  The goal is to
prove that a clean manifest produces no work and that a dirty manifest is
translated into changed-page jobs only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_incremental_processing_runner_v1"
ALGORITHM = "trace_net_incremental_processing_dry_run_runner_v1"

ALLOWED_EXECUTION_MODES = {"dry-run", "plan-only"}

JOB_COMMAND_HINTS: dict[str, str] = {
    "ocr_changed_pages": "run OCR only for affected pages from changed source list",
    "page_element_registry_changed_pages": "rebuild page element registry records only for affected pages",
    "table_understanding_changed_pages": "rebuild table understanding only for affected pages with table routes",
    "table_cell_normalizer_changed_pages": "normalize changed table rows/cells only for affected pages",
    "figure_chart_understanding_changed_pages": "rebuild visual/figure records only for affected pages",
    "visual_ink_layout_changed_pages": "recompute ink/layout calibration only for affected pages",
    "evidence_consensus_changed_pages": "rerun evidence consensus only for affected pages",
    "fishnet_retry_changed_pages": "rebuild fishnet retry/refinement only for affected pages",
    "trust_authority_changed_pages": "recalculate trust/authority only for affected records",
    "safe_candidates_changed_pages": "rebuild safe RAG/search candidates only for affected pages",
    "embedding_changed_candidates": "embed only changed safe candidates",
    "qdrant_upsert_changed_points": "upsert/delete only changed Qdrant points",
    "opensearch_upsert_changed_docs": "upsert/delete only changed OpenSearch documents",
    "graph_attachment_changed_pages": "rebuild graph attachment plan only for affected pages",
    "graph_writeback_changed_nodes": "write or dry-run only affected graph nodes/edges",
    "leiden_refresh_required": "mark Leiden/community refresh after graph changes",
    "retrieval_regression_smoke_changed_corpus": "run small retrieval smoke over changed corpus slice",
    "source_removed_review": "review removed source before destructive delete/tombstone",
    "qdrant_delete_removed_points": "delete Qdrant points for removed sources only after review",
    "opensearch_delete_removed_docs": "delete OpenSearch docs for removed sources only after review",
    "graph_tombstone_removed_source_nodes": "tombstone graph source nodes for removed files only after review",
    "leiden_refresh_after_source_removal": "refresh communities after approved source removal",
}

DESTRUCTIVE_JOB_TYPES = {
    "source_removed_review",
    "qdrant_delete_removed_points",
    "opensearch_delete_removed_docs",
    "graph_tombstone_removed_source_nodes",
    "leiden_refresh_after_source_removal",
}

WRITE_JOB_FAMILIES = {"qdrant", "opensearch", "graph", "postgres"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}__{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


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


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass"}
    return bool(value)


def get_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def extract_page_ids(job: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    for key in [
        "affected_page_ids",
        "page_ids",
        "dirty_page_ids",
        "target_page_ids",
        "source_page_ids",
    ]:
        candidates.extend(as_list(job.get(key)))
    clean = sorted({str(v) for v in candidates if v not in (None, "")})
    return clean


def normalize_job(job: dict[str, Any], index: int) -> dict[str, Any]:
    job_type = str(job.get("job_type") or job.get("type") or "unknown_job")
    job_family = str(job.get("job_family") or job.get("family") or infer_job_family(job_type))
    page_ids = extract_page_ids(job)
    affected_page_count = int(job.get("affected_page_count") or len(page_ids) or 0)
    job_id = str(job.get("job_id") or stable_id("job", index, job_type, affected_page_count))
    priority = str(job.get("priority") or infer_priority(job_type, job_family)).lower()
    runner_hint = str(job.get("runner_hint") or JOB_COMMAND_HINTS.get(job_type) or f"review runner for {job_type}")
    return {
        **job,
        "job_id": job_id,
        "job_type": job_type,
        "job_family": job_family,
        "affected_page_ids": page_ids,
        "affected_page_count": affected_page_count,
        "priority": priority,
        "runner_hint": runner_hint,
    }


def infer_job_family(job_type: str) -> str:
    prefixes = [
        ("ocr", "ocr"),
        ("page_element", "page_registry"),
        ("table", "table"),
        ("figure", "visual"),
        ("visual", "visual"),
        ("evidence", "evidence"),
        ("fishnet", "fishnet"),
        ("trust", "trust"),
        ("safe_candidates", "candidates"),
        ("embedding", "embedding"),
        ("qdrant", "qdrant"),
        ("opensearch", "opensearch"),
        ("graph", "graph"),
        ("leiden", "community"),
        ("retrieval", "retrieval"),
        ("source_removed", "source_removal"),
    ]
    for prefix, family in prefixes:
        if job_type.startswith(prefix):
            return family
    return "general"


def infer_priority(job_type: str, job_family: str) -> str:
    if job_type in DESTRUCTIVE_JOB_TYPES:
        return "critical"
    if job_family in {"qdrant", "opensearch", "graph", "trust"}:
        return "high"
    if job_family in {"ocr", "table", "visual", "evidence", "fishnet"}:
        return "medium"
    return "low"


def build_execution_step(
    job: dict[str, Any],
    *,
    execution_mode: str,
    batch_size: int,
    order: int,
) -> dict[str, Any]:
    page_ids = extract_page_ids(job)
    affected_page_count = int(job.get("affected_page_count") or len(page_ids) or 0)
    batch_count = max(1, math.ceil(max(affected_page_count, 1) / max(batch_size, 1))) if affected_page_count else 0
    job_type = str(job["job_type"])
    job_family = str(job["job_family"])
    destructive = job_type in DESTRUCTIVE_JOB_TYPES
    write_family = job_family in WRITE_JOB_FAMILIES
    return {
        "processing_step_id": stable_id("incproc_step", job.get("job_id"), order),
        "job_id": job.get("job_id"),
        "job_type": job_type,
        "job_family": job_family,
        "priority": job.get("priority", "low"),
        "execution_order": order,
        "execution_mode": execution_mode,
        "execution_status": "planned_only" if execution_mode in {"dry-run", "plan-only"} else "blocked_unknown_mode",
        "affected_page_count": affected_page_count,
        "affected_page_ids": page_ids,
        "batch_size": batch_size,
        "batch_count": batch_count,
        "runner_hint": job.get("runner_hint", JOB_COMMAND_HINTS.get(job_type, "manual review required")),
        "requires_success_before_state_commit": True,
        "requires_quality_check": True,
        "requires_dry_run_before_write": destructive or write_family,
        "destructive_job": destructive,
        "write_family_job": write_family,
        "external_command_executed": False,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "unsafe_processing_step": False,
    }


def build_batches(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for step in steps:
        count = int(step.get("batch_count") or 0)
        page_ids = step.get("affected_page_ids") or []
        batch_size = int(step.get("batch_size") or max(len(page_ids), 1))
        for idx in range(count):
            start = idx * batch_size
            end = start + batch_size
            batches.append(
                {
                    "processing_batch_id": stable_id("incproc_batch", step["processing_step_id"], idx + 1),
                    "processing_step_id": step["processing_step_id"],
                    "job_id": step["job_id"],
                    "job_type": step["job_type"],
                    "job_family": step["job_family"],
                    "batch_number": idx + 1,
                    "batch_count": count,
                    "page_ids": page_ids[start:end] if page_ids else [],
                    "page_count": len(page_ids[start:end]) if page_ids else 0,
                    "execution_status": "planned_only",
                    "external_command_executed": False,
                    "source_truth_mutation_allowed": False,
                }
            )
    return batches


def count_by(rows: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def summarize(
    *,
    orchestrator: dict[str, Any],
    jobs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    batches: list[dict[str, Any]],
    execution_mode: str,
    batch_size: int,
) -> dict[str, Any]:
    osum = get_summary(orchestrator)
    unsafe_steps = [s for s in steps if s.get("unsafe_processing_step")]
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "execution_mode": execution_mode,
        "writeback_mode": "dry_run_processing_plan",
        "batch_size": batch_size,
        "orchestrator_quality_status": orchestrator.get("quality_status") or osum.get("status"),
        "orchestrator_status": orchestrator.get("status") or osum.get("status"),
        "page_count": int(osum.get("page_count") or orchestrator.get("page_count") or 0),
        "source_record_count": int(osum.get("source_record_count") or 0),
        "dirty_page_count": int(osum.get("dirty_page_count") or 0),
        "affected_page_count": int(osum.get("affected_page_count") or 0),
        "changed_source_count": int(osum.get("changed_source_count") or 0),
        "new_source_count": int(osum.get("new_source_count") or 0),
        "removed_source_count": int(osum.get("removed_source_count") or 0),
        "planned_job_count": len(jobs),
        "processing_step_count": len(steps),
        "processing_batch_count": len(batches),
        "would_execute_job_count": len(jobs) if execution_mode == "dry-run" else 0,
        "executed_job_count": 0,
        "no_op_processed": len(jobs) == 0,
        "full_rescan_required": bool(osum.get("full_rescan_required") or False),
        "full_rescan_required_count": int(osum.get("full_rescan_required_count") or 0),
        "unchanged_page_reprocess_count": int(osum.get("unchanged_page_reprocess_count") or 0),
        "job_type_counts": count_by(jobs, "job_type"),
        "job_family_counts": count_by(jobs, "job_family"),
        "priority_counts": count_by(jobs, "priority"),
        "destructive_job_count_requiring_dry_run": sum(1 for s in steps if s.get("destructive_job")),
        "write_family_job_count": sum(1 for s in steps if s.get("write_family_job")),
        "unsafe_processing_step_count": len(unsafe_steps),
        "external_command_execution_count": sum(1 for s in steps if s.get("external_command_executed")),
        "postgres_write_attempt_count": sum(1 for s in steps if s.get("postgres_write_attempted")),
        "qdrant_write_attempt_count": sum(1 for s in steps if s.get("qdrant_write_attempted")),
        "opensearch_write_attempt_count": sum(1 for s in steps if s.get("opensearch_write_attempted")),
        "source_truth_mutation_allowed_count": sum(1 for s in steps if s.get("source_truth_mutation_allowed")),
        "source_truth_mutations_performed": sum(int(s.get("source_truth_mutations_performed") or 0) for s in steps),
        "direct_answer_allowed_count": sum(1 for s in steps if s.get("can_answer_directly")),
        "claim_proof_allowed_count": sum(1 for s in steps if s.get("can_prove_claims")),
        "state_commit_after_success_only": True,
    }


def evaluate_quality(
    summary: dict[str, Any],
    *,
    require_page_count: int | None = None,
    min_processing_steps: int = 0,
    require_no_full_rescan: bool = False,
    max_unchanged_page_reprocess: int | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, actual: Any = None, expected: Any = None, severity: str = "critical") -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "actual": actual,
                "expected": expected,
                "severity": severity,
            }
        )

    if require_page_count is not None:
        add_check("page_count_matches_required", summary.get("page_count") == require_page_count, summary.get("page_count"), require_page_count)
    add_check("processing_step_count_min", int(summary.get("processing_step_count") or 0) >= min_processing_steps, summary.get("processing_step_count"), f">={min_processing_steps}")
    if require_no_full_rescan:
        add_check("full_rescan_required_false", not summary.get("full_rescan_required"), summary.get("full_rescan_required"), False)
    if max_unchanged_page_reprocess is not None:
        add_check(
            "unchanged_page_reprocess_count_max",
            int(summary.get("unchanged_page_reprocess_count") or 0) <= max_unchanged_page_reprocess,
            summary.get("unchanged_page_reprocess_count"),
            f"<={max_unchanged_page_reprocess}",
        )
    for key in [
        "unsafe_processing_step_count",
        "external_command_execution_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "source_truth_mutation_allowed_count",
        "source_truth_mutations_performed",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
    ]:
        add_check(f"{key}_zero", int(summary.get(key) or 0) == 0, summary.get(key), 0)
    add_check("state_commit_after_success_only_true", bool(summary.get("state_commit_after_success_only")), summary.get("state_commit_after_success_only"), True)
    add_check("dry_run_or_plan_only_mode", summary.get("execution_mode") in ALLOWED_EXECUTION_MODES, summary.get("execution_mode"), sorted(ALLOWED_EXECUTION_MODES))

    blocking = [c for c in checks if not c["passed"] and c["severity"] == "critical"]
    return {
        "status": "PASS" if not blocking else "FAIL",
        "checks": checks,
        "failed_check_count": len([c for c in checks if not c["passed"]]),
        "blocking_failed_check_count": len(blocking),
    }


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRACE-Net Incremental Processing Runner v1",
        "",
        f"**Status:** {report['status']}",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "execution_mode",
        "page_count",
        "dirty_page_count",
        "affected_page_count",
        "planned_job_count",
        "processing_step_count",
        "processing_batch_count",
        "no_op_processed",
        "full_rescan_required",
        "unchanged_page_reprocess_count",
        "external_command_execution_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Processing Steps", ""])
    if not report["processing_steps"]:
        lines.append("No processing steps were planned. The manifest/orchestrator was clean.")
    else:
        lines.append("| Order | Job Type | Family | Priority | Pages | Status |")
        lines.append("|---:|---|---|---|---:|---|")
        for step in report["processing_steps"]:
            lines.append(
                "| {order} | {job_type} | {family} | {priority} | {pages} | {status} |".format(
                    order=step.get("execution_order"),
                    job_type=step.get("job_type"),
                    family=step.get("job_family"),
                    priority=step.get("priority"),
                    pages=step.get("affected_page_count"),
                    status=step.get("execution_status"),
                )
            )
    return "\n".join(lines) + "\n"


def html_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in summary.items() if isinstance(v, (str, int, float, bool)) or v is None)
    step_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            s.get("execution_order"), s.get("job_type"), s.get("job_family"), s.get("priority"), s.get("affected_page_count")
        )
        for s in report["processing_steps"]
    )
    if not step_rows:
        step_rows = "<tr><td colspan='5'>No processing steps planned.</td></tr>"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Incremental Processing Runner v1</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:6px}}th{{background:#f5f5f5;text-align:left}}</style></head>
<body>
<h1>TRACE-Net Incremental Processing Runner v1</h1>
<p><b>Status:</b> {report['status']} &nbsp; <b>Quality:</b> {report['quality_status']}</p>
<h2>Summary</h2><table>{rows}</table>
<h2>Processing Steps</h2><table><tr><th>Order</th><th>Job Type</th><th>Family</th><th>Priority</th><th>Pages</th></tr>{step_rows}</table>
</body></html>"""


def build_incremental_processing_runner(
    orchestrator_report_path: str | Path,
    output_dir: str | Path,
    *,
    execution_mode: str = "dry-run",
    batch_size: int = 100,
    require_page_count: int | None = None,
    min_processing_steps: int = 0,
    require_no_full_rescan: bool = False,
    max_unchanged_page_reprocess: int | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    if execution_mode not in ALLOWED_EXECUTION_MODES:
        raise ValueError(f"execution_mode must be one of {sorted(ALLOWED_EXECUTION_MODES)}")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    orchestrator_path = Path(orchestrator_report_path)
    orchestrator = read_json(orchestrator_path)
    raw_jobs = orchestrator.get("planned_jobs") or []
    if not isinstance(raw_jobs, list):
        raise ValueError("orchestrator report planned_jobs must be a list")
    jobs = [normalize_job(job, idx) for idx, job in enumerate(raw_jobs, start=1) if isinstance(job, dict)]
    steps = [build_execution_step(job, execution_mode=execution_mode, batch_size=batch_size, order=idx) for idx, job in enumerate(jobs, start=1)]
    batches = build_batches(steps)
    summary = summarize(orchestrator=orchestrator, jobs=jobs, steps=steps, batches=batches, execution_mode=execution_mode, batch_size=batch_size)
    quality = evaluate_quality(
        summary,
        require_page_count=require_page_count,
        min_processing_steps=min_processing_steps,
        require_no_full_rescan=require_no_full_rescan,
        max_unchanged_page_reprocess=max_unchanged_page_reprocess,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "INCREMENTAL_PROCESSING_RUNNER_BUILT",
        "quality_status": quality["status"],
        "generated_at": utc_now(),
        "source_orchestrator_report": orchestrator_path.as_posix(),
        "execution_mode": execution_mode,
        "summary": {**summary, "quality_status": quality["status"]},
        "quality": quality,
        "planned_jobs": jobs,
        "processing_steps": steps,
        "processing_batches": batches,
    }
    report["summary_path"] = (output / "trace_net_incremental_processing_runner_v1_summary.json").as_posix()
    report["quality_path"] = (output / "trace_net_incremental_processing_runner_v1_quality.json").as_posix()
    report["steps_path"] = (output / "trace_net_incremental_processing_runner_v1_steps.jsonl").as_posix()
    report["batches_path"] = (output / "trace_net_incremental_processing_runner_v1_batches.jsonl").as_posix()
    report["report_path"] = (output / "trace_net_incremental_processing_runner_v1.json").as_posix()

    write_json(output / "trace_net_incremental_processing_runner_v1.json", report)
    write_json(output / "trace_net_incremental_processing_runner_v1_summary.json", report["summary"])
    write_json(output / "trace_net_incremental_processing_runner_v1_quality.json", quality)
    write_jsonl(output / "trace_net_incremental_processing_runner_v1_steps.jsonl", steps)
    write_jsonl(output / "trace_net_incremental_processing_runner_v1_batches.jsonl", batches)
    write_json(
        output / "trace_net_incremental_processing_runner_v1_manifest.json",
        {
            "schema_version": f"{SCHEMA_VERSION}_manifest",
            "generated_at": report["generated_at"],
            "report_path": report["report_path"],
            "source_orchestrator_report": report["source_orchestrator_report"],
            "execution_mode": execution_mode,
            "quality_status": report["quality_status"],
        },
    )
    (output / "trace_net_incremental_processing_runner_v1.md").write_text(markdown_report(report), encoding="utf-8")
    (output / "trace_net_incremental_processing_runner_v1.html").write_text(html_report(report), encoding="utf-8")
    return report


def quality_report(
    report_path: str | Path,
    *,
    require_page_count: int | None = None,
    min_processing_steps: int = 0,
    require_no_full_rescan: bool = False,
    max_unchanged_page_reprocess: int | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path)
    summary = get_summary(report)
    quality = evaluate_quality(
        summary,
        require_page_count=require_page_count,
        min_processing_steps=min_processing_steps,
        require_no_full_rescan=require_no_full_rescan,
        max_unchanged_page_reprocess=max_unchanged_page_reprocess,
    )
    result = {
        "schema_version": f"{SCHEMA_VERSION}_quality_check",
        "status": quality["status"],
        "report_path": Path(report_path).as_posix(),
        **{k: summary.get(k) for k in [
            "execution_mode",
            "page_count",
            "dirty_page_count",
            "affected_page_count",
            "planned_job_count",
            "processing_step_count",
            "processing_batch_count",
            "no_op_processed",
            "full_rescan_required",
            "unchanged_page_reprocess_count",
            "external_command_execution_count",
            "postgres_write_attempt_count",
            "qdrant_write_attempt_count",
            "opensearch_write_attempt_count",
            "source_truth_mutation_allowed_count",
            "direct_answer_allowed_count",
            "claim_proof_allowed_count",
        ]},
        "quality": quality,
    }
    if write_json_report:
        out = Path(report_path).parent / "trace_net_incremental_processing_runner_v1_quality.json"
        write_json(out, result)
        result["quality_path"] = out.as_posix()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net incremental processing runner v1 dry-run plan.")
    parser.add_argument("--orchestrator-report", required=True)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/incremental_processing_runner")
    parser.add_argument("--execution-mode", default="dry-run", choices=sorted(ALLOWED_EXECUTION_MODES))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-processing-steps", type=int, default=0)
    parser.add_argument("--require-no-full-rescan", action="store_true")
    parser.add_argument("--max-unchanged-page-reprocess", type=int)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_incremental_processing_runner(
            args.orchestrator_report,
            args.output_dir,
            execution_mode=args.execution_mode,
            batch_size=args.batch_size,
            require_page_count=args.require_page_count,
            min_processing_steps=args.min_processing_steps,
            require_no_full_rescan=args.require_no_full_rescan,
            max_unchanged_page_reprocess=args.max_unchanged_page_reprocess,
            write_quality=args.quality,
        )
    except Exception as exc:  # pragma: no cover - command line guard
        print(f"TRACE-Net incremental processing runner failed: {exc}")
        return 1

    summary = report["summary"]
    print("TRACE-Net incremental processing runner v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "execution_mode",
        "page_count",
        "dirty_page_count",
        "affected_page_count",
        "planned_job_count",
        "processing_step_count",
        "processing_batch_count",
        "no_op_processed",
        "full_rescan_required",
        "unchanged_page_reprocess_count",
        "external_command_execution_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
