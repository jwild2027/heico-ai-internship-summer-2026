"""TRACE-Net Incremental State Commit Gate v1.

This module decides whether an incremental processing run is safe to mark as
processed.  It intentionally does not mutate the manifest, source state,
Postgres, Qdrant, OpenSearch, or graph truth.  It is a dry-run gate that keeps
state commits behind successful job and quality evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_incremental_state_commit_gate_v1"
ALGORITHM = "trace_net_incremental_state_commit_commit_gate_v1"

SUCCESS_STATUSES = {
    "completed_success",
    "complete_success",
    "success",
    "succeeded",
    "pass",
    "passed",
    "quality_pass",
    "executed_success",
}

PENDING_STATUSES = {
    "planned_only",
    "plan_only",
    "planned",
    "dry_run",
    "dry-run",
    "pending",
    "pending_execution",
    "not_started",
}

FAILURE_STATUSES = {
    "fail",
    "failed",
    "failure",
    "error",
    "errored",
    "blocked",
    "blocked_unknown_mode",
    "quality_fail",
}

SAFETY_ZERO_KEYS = [
    "unsafe_processing_step_count",
    "source_truth_mutation_allowed_count",
    "source_truth_mutations_performed",
    "direct_answer_allowed_count",
    "claim_proof_allowed_count",
]

WRITE_ATTEMPT_KEYS = [
    "state_commit_write_attempt_count",
    "state_commit_performed_count",
]


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
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "passed"}
    return bool(value)


def get_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def status_value(row: dict[str, Any]) -> str:
    for key in ["execution_status", "status", "quality_status", "job_status"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip().lower()
    return "unknown"


def page_ids_from_step(step: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ["affected_page_ids", "page_ids", "dirty_page_ids", "source_page_ids"]:
        values.extend(as_list(step.get(key)))
    return sorted({str(v) for v in values if v not in (None, "")})


def step_has_safety_violation(step: dict[str, Any]) -> bool:
    bool_keys = [
        "unsafe_processing_step",
        "source_truth_mutation_allowed",
        "can_answer_directly",
        "can_prove_claims",
        "can_mutate_source_truth",
    ]
    if any(normalize_bool(step.get(key)) for key in bool_keys):
        return True
    if int_value(step.get("source_truth_mutations_performed")) > 0:
        return True
    return False


def evaluate_step_commit_check(step: dict[str, Any], index: int) -> dict[str, Any]:
    status = status_value(step)
    page_ids = page_ids_from_step(step)
    safety_violation = step_has_safety_violation(step)
    check_status = "blocked_missing_success_proof"
    reason = "Step does not contain a recognized successful execution status."
    commit_allowed = False

    if safety_violation:
        check_status = "blocked_safety_violation"
        reason = "Step carries an unsafe, answer-authority, or source-truth mutation flag."
    elif status in SUCCESS_STATUSES:
        check_status = "safe_to_commit"
        reason = "Step has success evidence and no safety violations."
        commit_allowed = True
    elif status in PENDING_STATUSES:
        check_status = "pending_execution"
        reason = "Step is planned/dry-run only; state commit must wait for successful execution."
    elif status in FAILURE_STATUSES:
        check_status = "blocked_failed_execution"
        reason = "Step failed or was blocked; state commit is not allowed."

    return {
        "state_commit_check_id": stable_id("inccommit_check", step.get("processing_step_id") or index, step.get("job_id"), status),
        "processing_step_id": step.get("processing_step_id"),
        "job_id": step.get("job_id"),
        "job_type": step.get("job_type"),
        "job_family": step.get("job_family"),
        "priority": step.get("priority"),
        "execution_status": status,
        "affected_page_count": int_value(step.get("affected_page_count") or len(page_ids)),
        "affected_page_ids": page_ids,
        "safety_violation": safety_violation,
        "commit_check_status": check_status,
        "state_commit_allowed_for_step": commit_allowed,
        "state_commit_block_reason": "" if commit_allowed else reason,
        "requires_success_before_state_commit": True,
        "state_commit_performed": False,
        "state_commit_write_attempted": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
    }


def count_by(rows: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def make_commit_decision(summary: dict[str, Any], checks: list[dict[str, Any]]) -> tuple[str, bool, bool, str]:
    planned_job_count = int_value(summary.get("planned_job_count"))
    full_rescan_required = normalize_bool(summary.get("full_rescan_required"))
    safety_total = sum(int_value(summary.get(key)) for key in SAFETY_ZERO_KEYS)
    if full_rescan_required:
        return "state_commit_blocked_full_rescan", False, planned_job_count > 0, "Full rescan was required; do not commit incremental state."
    if safety_total > 0:
        return "state_commit_blocked_safety", False, planned_job_count > 0, "Processing summary contains safety or source-truth mutation flags."
    if planned_job_count == 0:
        return "no_op_no_state_commit_needed", False, False, "No dirty pages or planned jobs; no state commit is needed."

    blocked = [c for c in checks if str(c.get("commit_check_status", "")).startswith("blocked")]
    pending = [c for c in checks if c.get("commit_check_status") == "pending_execution"]
    safe = [c for c in checks if c.get("state_commit_allowed_for_step")]

    if blocked:
        return "state_commit_blocked_failed_or_unsafe_jobs", False, True, "At least one required job failed, is unsafe, or lacks success proof."
    if pending:
        return "state_commit_pending_execution", False, True, "Required jobs are still planned/dry-run only; wait for successful execution."
    if len(safe) == len(checks) and checks:
        return "state_commit_allowed_after_success", True, True, "Every required job has success evidence and passed safety checks."
    return "state_commit_blocked_missing_checks", False, True, "No successful job checks were available for commit."


def summarize(processing_runner: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    psum = get_summary(processing_runner)
    decision, allowed, required, reason = make_commit_decision(psum, checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "gate_mode": "dry_run_commit_gate",
        "processing_runner_quality_status": processing_runner.get("quality_status") or psum.get("quality_status"),
        "processing_runner_status": processing_runner.get("status") or psum.get("status"),
        "page_count": int_value(psum.get("page_count")),
        "source_record_count": int_value(psum.get("source_record_count")),
        "dirty_page_count": int_value(psum.get("dirty_page_count")),
        "affected_page_count": int_value(psum.get("affected_page_count")),
        "planned_job_count": int_value(psum.get("planned_job_count")),
        "processing_step_count": int_value(psum.get("processing_step_count")),
        "processing_batch_count": int_value(psum.get("processing_batch_count")),
        "no_op_processed": bool(psum.get("no_op_processed")),
        "full_rescan_required": bool(psum.get("full_rescan_required")),
        "unchanged_page_reprocess_count": int_value(psum.get("unchanged_page_reprocess_count")),
        "state_commit_after_success_only": True,
        "state_commit_decision": decision,
        "state_commit_reason": reason,
        "state_commit_required": required,
        "state_commit_allowed": allowed,
        "state_commit_performed": False,
        "state_commit_write_attempt_count": 0,
        "state_commit_performed_count": 0,
        "commit_check_count": len(checks),
        "commit_check_status_counts": count_by(checks, "commit_check_status"),
        "commit_allowed_step_count": sum(1 for c in checks if c.get("state_commit_allowed_for_step")),
        "pending_execution_step_count": sum(1 for c in checks if c.get("commit_check_status") == "pending_execution"),
        "failed_execution_step_count": sum(1 for c in checks if c.get("commit_check_status") == "blocked_failed_execution"),
        "blocked_commit_check_count": sum(1 for c in checks if str(c.get("commit_check_status", "")).startswith("blocked")),
        "safety_violation_commit_check_count": sum(1 for c in checks if c.get("commit_check_status") == "blocked_safety_violation"),
        "unsafe_processing_step_count": int_value(psum.get("unsafe_processing_step_count")),
        "external_command_execution_count": int_value(psum.get("external_command_execution_count")),
        "postgres_write_attempt_count": int_value(psum.get("postgres_write_attempt_count")),
        "qdrant_write_attempt_count": int_value(psum.get("qdrant_write_attempt_count")),
        "opensearch_write_attempt_count": int_value(psum.get("opensearch_write_attempt_count")),
        "source_truth_mutation_allowed_count": int_value(psum.get("source_truth_mutation_allowed_count")),
        "source_truth_mutations_performed": int_value(psum.get("source_truth_mutations_performed")),
        "direct_answer_allowed_count": int_value(psum.get("direct_answer_allowed_count")),
        "claim_proof_allowed_count": int_value(psum.get("claim_proof_allowed_count")),
    }


def evaluate_quality(
    summary: dict[str, Any],
    *,
    require_page_count: int | None = None,
    require_no_full_rescan: bool = False,
    max_unchanged_page_reprocess: int | None = None,
    require_no_state_commit_performed: bool = True,
    require_commit_allowed: bool = False,
    require_commit_blocked_for_pending: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, actual: Any = None, expected: Any = None, severity: str = "critical") -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected, "severity": severity})

    if require_page_count is not None:
        add_check("page_count_matches_required", summary.get("page_count") == require_page_count, summary.get("page_count"), require_page_count)
    if require_no_full_rescan:
        add_check("full_rescan_required_false", not summary.get("full_rescan_required"), summary.get("full_rescan_required"), False)
    if max_unchanged_page_reprocess is not None:
        add_check(
            "unchanged_page_reprocess_count_max",
            int_value(summary.get("unchanged_page_reprocess_count")) <= max_unchanged_page_reprocess,
            summary.get("unchanged_page_reprocess_count"),
            f"<={max_unchanged_page_reprocess}",
        )
    for key in [
        "unsafe_processing_step_count",
        "source_truth_mutation_allowed_count",
        "source_truth_mutations_performed",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "state_commit_write_attempt_count",
    ]:
        add_check(f"{key}_zero", int_value(summary.get(key)) == 0, summary.get(key), 0)
    if require_no_state_commit_performed:
        add_check("state_commit_performed_false", not summary.get("state_commit_performed"), summary.get("state_commit_performed"), False)
        add_check("state_commit_performed_count_zero", int_value(summary.get("state_commit_performed_count")) == 0, summary.get("state_commit_performed_count"), 0)
    add_check("state_commit_after_success_only_true", bool(summary.get("state_commit_after_success_only")), summary.get("state_commit_after_success_only"), True)
    add_check("processing_runner_quality_pass", str(summary.get("processing_runner_quality_status")).upper() == "PASS", summary.get("processing_runner_quality_status"), "PASS")
    if require_commit_allowed:
        add_check("state_commit_allowed_true", bool(summary.get("state_commit_allowed")), summary.get("state_commit_allowed"), True)
    if require_commit_blocked_for_pending:
        pending = int_value(summary.get("pending_execution_step_count"))
        if pending > 0:
            add_check("pending_execution_blocks_commit", not summary.get("state_commit_allowed"), summary.get("state_commit_allowed"), False)
    # Fail on failed or unsafe job evidence. Pending dry-run work is allowed as a PASS state
    # because it correctly blocks commit without making a false failure.
    add_check("failed_execution_step_count_zero", int_value(summary.get("failed_execution_step_count")) == 0, summary.get("failed_execution_step_count"), 0)
    add_check("safety_violation_commit_check_count_zero", int_value(summary.get("safety_violation_commit_check_count")) == 0, summary.get("safety_violation_commit_check_count"), 0)

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
        "# TRACE-Net Incremental State Commit Gate v1",
        "",
        f"**Status:** {report['status']}",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "gate_mode",
        "page_count",
        "dirty_page_count",
        "affected_page_count",
        "planned_job_count",
        "processing_step_count",
        "state_commit_decision",
        "state_commit_required",
        "state_commit_allowed",
        "state_commit_performed",
        "pending_execution_step_count",
        "blocked_commit_check_count",
        "full_rescan_required",
        "unchanged_page_reprocess_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Commit Checks", ""])
    if not report["commit_checks"]:
        lines.append("No commit checks were needed. The incremental run was a clean no-op.")
    else:
        lines.append("| Job Type | Status | Commit Allowed | Pages | Reason |")
        lines.append("|---|---|---:|---:|---|")
        for check in report["commit_checks"]:
            lines.append(
                "| {job_type} | {status} | {allowed} | {pages} | {reason} |".format(
                    job_type=check.get("job_type"),
                    status=check.get("commit_check_status"),
                    allowed=check.get("state_commit_allowed_for_step"),
                    pages=check.get("affected_page_count"),
                    reason=str(check.get("state_commit_block_reason") or "safe")[:120],
                )
            )
    return "\n".join(lines) + "\n"


def html_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in summary.items() if isinstance(v, (str, int, float, bool)) or v is None)
    check_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            c.get("job_type"), c.get("commit_check_status"), c.get("state_commit_allowed_for_step"), c.get("affected_page_count"), c.get("state_commit_block_reason") or "safe"
        )
        for c in report["commit_checks"]
    )
    if not check_rows:
        check_rows = "<tr><td colspan='5'>No commit checks needed.</td></tr>"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Incremental State Commit Gate v1</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:6px}}th{{background:#f5f5f5;text-align:left}}</style></head>
<body>
<h1>TRACE-Net Incremental State Commit Gate v1</h1>
<p><b>Status:</b> {report['status']} &nbsp; <b>Quality:</b> {report['quality_status']}</p>
<h2>Summary</h2><table>{rows}</table>
<h2>Commit Checks</h2><table><tr><th>Job Type</th><th>Status</th><th>Commit Allowed</th><th>Pages</th><th>Reason</th></tr>{check_rows}</table>
</body></html>"""


def build_incremental_state_commit_gate(
    processing_runner_report_path: str | Path,
    output_dir: str | Path,
    *,
    require_page_count: int | None = None,
    require_no_full_rescan: bool = False,
    max_unchanged_page_reprocess: int | None = None,
    require_commit_allowed: bool = False,
    require_commit_blocked_for_pending: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source_path = Path(processing_runner_report_path)
    processing_runner = read_json(source_path)
    steps = processing_runner.get("processing_steps") or []
    if not isinstance(steps, list):
        raise ValueError("processing runner report processing_steps must be a list")
    commit_checks = [evaluate_step_commit_check(step, idx) for idx, step in enumerate(steps, start=1) if isinstance(step, dict)]
    summary = summarize(processing_runner, commit_checks)
    quality = evaluate_quality(
        summary,
        require_page_count=require_page_count,
        require_no_full_rescan=require_no_full_rescan,
        max_unchanged_page_reprocess=max_unchanged_page_reprocess,
        require_commit_allowed=require_commit_allowed,
        require_commit_blocked_for_pending=require_commit_blocked_for_pending,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "INCREMENTAL_STATE_COMMIT_GATE_BUILT",
        "quality_status": quality["status"],
        "generated_at": utc_now(),
        "source_processing_runner_report": source_path.as_posix(),
        "summary": {**summary, "quality_status": quality["status"]},
        "quality": quality,
        "commit_checks": commit_checks,
    }
    report["report_path"] = (output / "trace_net_incremental_state_commit_gate_v1.json").as_posix()
    report["checks_path"] = (output / "trace_net_incremental_state_commit_gate_v1_checks.jsonl").as_posix()
    report["summary_path"] = (output / "trace_net_incremental_state_commit_gate_v1_summary.json").as_posix()
    report["quality_path"] = (output / "trace_net_incremental_state_commit_gate_v1_quality.json").as_posix()

    write_json(output / "trace_net_incremental_state_commit_gate_v1.json", report)
    write_json(output / "trace_net_incremental_state_commit_gate_v1_summary.json", report["summary"])
    write_json(output / "trace_net_incremental_state_commit_gate_v1_quality.json", quality)
    write_jsonl(output / "trace_net_incremental_state_commit_gate_v1_checks.jsonl", commit_checks)
    write_json(
        output / "trace_net_incremental_state_commit_gate_v1_manifest.json",
        {
            "schema_version": f"{SCHEMA_VERSION}_manifest",
            "generated_at": report["generated_at"],
            "report_path": report["report_path"],
            "source_processing_runner_report": report["source_processing_runner_report"],
            "quality_status": report["quality_status"],
            "state_commit_decision": summary["state_commit_decision"],
            "state_commit_allowed": summary["state_commit_allowed"],
        },
    )
    (output / "trace_net_incremental_state_commit_gate_v1.md").write_text(markdown_report(report), encoding="utf-8")
    (output / "trace_net_incremental_state_commit_gate_v1.html").write_text(html_report(report), encoding="utf-8")
    return report


def quality_report(
    report_path: str | Path,
    *,
    require_page_count: int | None = None,
    require_no_full_rescan: bool = False,
    max_unchanged_page_reprocess: int | None = None,
    require_commit_allowed: bool = False,
    require_commit_blocked_for_pending: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path)
    summary = get_summary(report)
    quality = evaluate_quality(
        summary,
        require_page_count=require_page_count,
        require_no_full_rescan=require_no_full_rescan,
        max_unchanged_page_reprocess=max_unchanged_page_reprocess,
        require_commit_allowed=require_commit_allowed,
        require_commit_blocked_for_pending=require_commit_blocked_for_pending,
    )
    result = {
        "schema_version": f"{SCHEMA_VERSION}_quality_check",
        "status": quality["status"],
        "report_path": Path(report_path).as_posix(),
        **{k: summary.get(k) for k in [
            "page_count",
            "dirty_page_count",
            "affected_page_count",
            "planned_job_count",
            "processing_step_count",
            "state_commit_decision",
            "state_commit_required",
            "state_commit_allowed",
            "state_commit_performed",
            "pending_execution_step_count",
            "blocked_commit_check_count",
            "failed_execution_step_count",
            "full_rescan_required",
            "unchanged_page_reprocess_count",
            "state_commit_write_attempt_count",
            "source_truth_mutation_allowed_count",
        ]},
        "quality": quality,
    }
    if write_json_report:
        out = Path(report_path).parent / "trace_net_incremental_state_commit_gate_v1_quality.json"
        write_json(out, result)
        result["quality_path"] = out.as_posix()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net incremental state commit gate v1.")
    parser.add_argument("--processing-runner-report", required=True)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/incremental_state_commit_gate")
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--require-no-full-rescan", action="store_true")
    parser.add_argument("--max-unchanged-page-reprocess", type=int)
    parser.add_argument("--require-commit-allowed", action="store_true")
    parser.add_argument("--require-commit-blocked-for-pending", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_incremental_state_commit_gate(
            args.processing_runner_report,
            args.output_dir,
            require_page_count=args.require_page_count,
            require_no_full_rescan=args.require_no_full_rescan,
            max_unchanged_page_reprocess=args.max_unchanged_page_reprocess,
            require_commit_allowed=args.require_commit_allowed,
            require_commit_blocked_for_pending=args.require_commit_blocked_for_pending,
            write_quality=args.quality,
        )
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net incremental state commit gate failed: {exc}")
        return 1
    summary = report["summary"]
    print("TRACE-Net incremental state commit gate v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "page_count",
        "dirty_page_count",
        "affected_page_count",
        "planned_job_count",
        "processing_step_count",
        "state_commit_decision",
        "state_commit_required",
        "state_commit_allowed",
        "state_commit_performed",
        "pending_execution_step_count",
        "blocked_commit_check_count",
        "full_rescan_required",
        "unchanged_page_reprocess_count",
        "state_commit_write_attempt_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
