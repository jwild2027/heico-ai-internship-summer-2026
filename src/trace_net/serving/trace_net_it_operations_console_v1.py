"""TRACE-Net IT Operations Console v1.

This module scans TRACE-Net local artifact outputs and builds a backend/IT-facing
health report. It is intentionally read-only: it does not mutate source truth,
Postgres, Qdrant, OpenSearch, or local pipeline artifacts.

The report is meant to answer, in plain operational terms:
- Which stages are present?
- Which stages are passing/failing?
- Where are unsafe counts non-zero?
- Which records need human review?
- Are there source-truth mutation risks?
- Are feedback/community/LLM helpers being treated only as advisory?
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_it_operations_console_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/it_operations_console")
DEFAULT_TRACE_NET_ROOT = Path("local_data/organization/trace_net")

# Synthetic stress-test outputs are useful for validating the IT console, but
# they should not count as real project health problems when scanning the actual
# trace_net root. If the caller scans the synthetic root directly, these prefixes
# are not present and synthetic scenarios are still detected.
DEFAULT_EXCLUDED_RELATIVE_PREFIXES = [
    ("it_issue_origin_test_matrix", "synthetic_trace_net_root"),
    ("it_issue_origin_test_matrix", "synthetic_console_report"),
]

PASS_STATUSES = {"PASS", "OK", "BUILT", "FROZEN", "LOADED", "RAN", "RECORDED"}
FAIL_STATUSES = {"FAIL", "FAILED", "ERROR", "BLOCKED"}

# Count fields that represent hard safety failures if they are > 0.
CRITICAL_COUNT_PATTERNS = [
    re.compile(r"(^|_)unsafe(_|$)"),
    re.compile(r"source_truth_mutation"),
    re.compile(r"direct_answer_allowed"),
    re.compile(r"claim_proof_allowed"),
    re.compile(r"claim_proof_without_authority"),
    re.compile(r"community_as_proof"),
    re.compile(r"feedback_as_proof"),
    re.compile(r"retrieval_only_answer_allowed"),
    re.compile(r"raw_feedback_direct_to_llm"),
    re.compile(r"uncited_.*claim"),
    re.compile(r"claim_without_citation"),
    re.compile(r"answer_capable_without_citation"),
    re.compile(r"local_path_leak"),
    re.compile(r"raw_bytes_repr"),
    re.compile(r"boilerplate_leak"),
    re.compile(r"orphan_edge"),
    re.compile(r"postgres_write_attempt"),
]

# Count fields that usually indicate work for IT/review, not a hard failure.
REVIEW_COUNT_PATTERNS = [
    re.compile(r"human_review"),
    re.compile(r"review_required"),
    re.compile(r"needs_human_review"),
    re.compile(r"pages_with_review"),
    re.compile(r"records_needing_human_review"),
    re.compile(r"prompt_injection_flagged"),
    re.compile(r"block_or_downgrade"),
]

# Count fields that are useful warnings but not necessarily failures.
WARNING_COUNT_PATTERNS = [
    re.compile(r"missing_"),
    re.compile(r"dirty_page_count"),
    re.compile(r"changed_source_count"),
    re.compile(r"new_source_count"),
    re.compile(r"needs_.*_count"),
    re.compile(r"candidate_unverified"),
    re.compile(r"unverified"),
]

# Do not create issues for these operationally expected counts.
BENIGN_COUNT_KEYS = {
    "missing_part_number_count",  # handled by Step 19.2 after lineage; retained for older artifacts.
    "missing_source_page_ids_count",
    "missing_page_id_count",  # can be non-critical for cross-page entity reports if scoped separately.
    "page_scoped_missing_page_id_count",  # when zero quality checks handle it.
}

EXPECTED_STAGE_PATHS = {
    "page_element_registry": "page_element_registry/trace_net_page_element_registry_v1_quality.json",
    "table_understanding": "table_understanding/trace_net_table_understanding_v1_quality.json",
    "table_cell_normalizer": "table_cell_normalizer/trace_net_table_cell_normalizer_v1_quality.json",
    "figure_chart_understanding": "figure_chart_understanding/trace_net_figure_chart_understanding_v1_quality.json",
    "visual_ink_layout_calibrator": "visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1_quality.json",
    "fishnet_retry_engine": "fishnet_retry_engine/trace_net_fishnet_retry_engine_v1_quality.json",
    "fishnet_retry_refined": "fishnet_retry_refined/trace_net_fishnet_retry_refinement_v1_quality.json",
    "element_graph_attachment": "element_graph_attachment/trace_net_element_graph_attachment_plan_v1_quality.json",
    "graph_writeback_overlay": "graph_writeback_overlay/trace_net_graph_writeback_overlay_v1_quality.json",
    "part_lineage": "graph_overlay_part_lineage/trace_net_graph_overlay_part_lineage_v1_quality.json",
    "part_property_normalizer": "graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1_quality.json",
    "leiden_communities": "leiden_graph_communities/trace_net_leiden_graph_communities_v1_quality.json",
    "feedback_memory": "feedback_memory/trace_net_feedback_memory_v1_quality.json",
    "community_aware_retrieval": "community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1_quality.json",
    "incremental_manifest": "incremental_corpus_manifest/trace_net_incremental_corpus_manifest_v1_quality.json",
    "incremental_orchestrator": "incremental_orchestrator/trace_net_incremental_orchestrator_v1_quality.json",
}


@dataclass
class Issue:
    issue_id: str
    severity: str
    category: str
    message: str
    artifact_path: str | None = None
    stage_id: str | None = None
    key: str | None = None
    value: Any | None = None
    recommended_action: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "artifact_path": self.artifact_path,
            "stage_id": self.stage_id,
            "key": self.key,
            "value": self.value,
            "recommended_action": self.recommended_action,
        }


@dataclass
class StageRecord:
    stage_id: str
    artifact_path: str
    exists: bool
    status: str
    quality_status: str
    summary: dict[str, Any] = field(default_factory=dict)
    key_counts: dict[str, Any] = field(default_factory=dict)
    issue_count: int = 0
    critical_issue_count: int = 0
    warning_issue_count: int = 0
    review_issue_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "artifact_path": self.artifact_path,
            "exists": self.exists,
            "status": self.status,
            "quality_status": self.quality_status,
            "summary": self.summary,
            "key_counts": self.key_counts,
            "issue_count": self.issue_count,
            "critical_issue_count": self.critical_issue_count,
            "warning_issue_count": self.warning_issue_count,
            "review_issue_count": self.review_issue_count,
        }


def utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.UTC).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def normalize_status(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    text = str(value).strip()
    if not text:
        return "UNKNOWN"
    upper = text.upper()
    if upper == "QUALITY_STATUS: PASS":
        return "PASS"
    return upper


def find_status(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("quality_status"),
        payload.get("status"),
        payload.get("quality", {}).get("status") if isinstance(payload.get("quality"), dict) else None,
        payload.get("summary", {}).get("status") if isinstance(payload.get("summary"), dict) else None,
    ]
    for value in candidates:
        status = normalize_status(value)
        if status != "UNKNOWN":
            return status
    return "UNKNOWN"


def iter_numeric_counts(payload: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, Any] = {}

    def visit(obj: Any, prefix: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_path = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if key.endswith("_count") or "count" in key or key.endswith("_allowed") or key.endswith("_used"):
                        counts[key_path] = value
                elif isinstance(value, dict):
                    visit(value, key_path)

    visit(payload)
    return counts


def short_stage_id_from_path(trace_net_root: Path, path: Path) -> str:
    try:
        rel = path.relative_to(trace_net_root)
    except ValueError:
        rel = path
    parts = rel.parts
    if len(parts) >= 2:
        return parts[0]
    return path.stem


def matches_any(key: str, patterns: list[re.Pattern[str]]) -> bool:
    key_l = key.lower().replace(".", "_")
    return any(pattern.search(key_l) for pattern in patterns)


def path_starts_with_parts(path_parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    if len(path_parts) < len(prefix):
        return False
    return path_parts[: len(prefix)] == prefix


def is_excluded_quality_path(
    trace_net_root: Path,
    path: Path,
    excluded_relative_prefixes: list[tuple[str, ...]] | None = None,
) -> bool:
    prefixes = excluded_relative_prefixes if excluded_relative_prefixes is not None else DEFAULT_EXCLUDED_RELATIVE_PREFIXES
    try:
        rel_parts = path.relative_to(trace_net_root).parts
    except ValueError:
        return False
    return any(path_starts_with_parts(rel_parts, tuple(prefix)) for prefix in prefixes)


def classify_count_issue(key: str, value: Any) -> tuple[str, str] | None:
    if key.split(".")[-1] in BENIGN_COUNT_KEYS:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    key_l = key.lower()
    if matches_any(key_l, CRITICAL_COUNT_PATTERNS):
        # Review counts with words like unsafe? no, critical wins.
        return "critical", "safety_count_nonzero"
    if matches_any(key_l, REVIEW_COUNT_PATTERNS):
        return "review", "review_backlog"
    if matches_any(key_l, WARNING_COUNT_PATTERNS):
        return "warning", "operational_warning"
    return None


def load_stage_records(
    trace_net_root: Path,
    include_all_quality_files: bool = True,
    excluded_relative_prefixes: list[tuple[str, ...]] | None = None,
) -> tuple[list[StageRecord], list[Issue], int]:
    stage_records: list[StageRecord] = []
    issues: list[Issue] = []
    issue_index = 0
    seen_paths: set[Path] = set()
    excluded_quality_file_count = 0

    def add_issue(**kwargs: Any) -> None:
        nonlocal issue_index
        issue_index += 1
        issues.append(Issue(issue_id=f"itops_issue_{issue_index:06d}", **kwargs))

    # Expected stages first, so missing important stages are visible.
    for stage_id, rel_path in EXPECTED_STAGE_PATHS.items():
        path = trace_net_root / rel_path
        seen_paths.add(path.resolve())
        if not path.exists():
            stage_records.append(
                StageRecord(
                    stage_id=stage_id,
                    artifact_path=path.as_posix(),
                    exists=False,
                    status="MISSING",
                    quality_status="MISSING",
                )
            )
            add_issue(
                severity="warning",
                category="missing_expected_stage",
                message=f"Expected TRACE-Net quality artifact is missing for stage '{stage_id}'.",
                artifact_path=path.as_posix(),
                stage_id=stage_id,
                recommended_action="Run the stage or confirm it is intentionally not part of this environment.",
            )
            continue

        payload = read_json(path)
        status = find_status(payload)
        counts = iter_numeric_counts(payload)
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        record = StageRecord(
            stage_id=stage_id,
            artifact_path=path.as_posix(),
            exists=True,
            status=status,
            quality_status=status,
            summary=summary,
            key_counts=counts,
        )
        stage_records.append(record)

    if include_all_quality_files and trace_net_root.exists():
        for path in sorted(trace_net_root.rglob("*quality*.json")):
            if is_excluded_quality_path(trace_net_root, path, excluded_relative_prefixes):
                excluded_quality_file_count += 1
                continue
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            try:
                payload = read_json(path)
            except Exception:
                continue
            status = find_status(payload)
            counts = iter_numeric_counts(payload)
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            stage_id = short_stage_id_from_path(trace_net_root, path)
            stage_records.append(
                StageRecord(
                    stage_id=stage_id,
                    artifact_path=path.as_posix(),
                    exists=True,
                    status=status,
                    quality_status=status,
                    summary=summary,
                    key_counts=counts,
                )
            )

    # Issue pass across stage records.
    for record in stage_records:
        if not record.exists:
            continue
        status = record.quality_status
        if status in FAIL_STATUSES:
            add_issue(
                severity="critical",
                category="stage_quality_failed",
                message=f"Stage '{record.stage_id}' quality status is {status}.",
                artifact_path=record.artifact_path,
                stage_id=record.stage_id,
                recommended_action="Open the quality artifact, inspect failing checks, and rerun/fix the stage before publishing.",
            )
        elif status not in PASS_STATUSES and status != "UNKNOWN":
            add_issue(
                severity="warning",
                category="stage_quality_nonstandard",
                message=f"Stage '{record.stage_id}' has non-standard status {status}.",
                artifact_path=record.artifact_path,
                stage_id=record.stage_id,
                recommended_action="Confirm whether this status is expected for the artifact type.",
            )

        for key, value in record.key_counts.items():
            classified = classify_count_issue(key, value)
            if classified is None:
                continue
            severity, category = classified
            if severity == "critical":
                action = "Treat as a blocker for answer/search publication until the stage is repaired or the count is justified."
            elif severity == "review":
                action = "Create or inspect human review tasks for this queue/backlog signal."
            else:
                action = "Inspect the operational count; it may indicate changed data, missing artifacts, or work pending."
            add_issue(
                severity=severity,
                category=category,
                message=f"Stage '{record.stage_id}' has {key} = {value}.",
                artifact_path=record.artifact_path,
                stage_id=record.stage_id,
                key=key,
                value=value,
                recommended_action=action,
            )

    # Attach counts to stage records.
    by_stage: dict[str, list[Issue]] = {}
    for issue in issues:
        if issue.stage_id:
            by_stage.setdefault(issue.stage_id, []).append(issue)
    for record in stage_records:
        stage_issues = by_stage.get(record.stage_id, [])
        record.issue_count = len(stage_issues)
        record.critical_issue_count = sum(1 for i in stage_issues if i.severity == "critical")
        record.warning_issue_count = sum(1 for i in stage_issues if i.severity == "warning")
        record.review_issue_count = sum(1 for i in stage_issues if i.severity == "review")

    return stage_records, issues, excluded_quality_file_count


def summarize(stage_records: list[StageRecord], issues: list[Issue]) -> dict[str, Any]:
    present = [s for s in stage_records if s.exists]
    missing = [s for s in stage_records if not s.exists]
    critical = [i for i in issues if i.severity == "critical"]
    warning = [i for i in issues if i.severity == "warning"]
    review = [i for i in issues if i.severity == "review"]

    fail_count = sum(1 for s in present if s.quality_status in FAIL_STATUSES)
    pass_count = sum(1 for s in present if s.quality_status in PASS_STATUSES)
    unknown_count = sum(1 for s in present if s.quality_status == "UNKNOWN")

    source_truth_mutation_issue_count = sum(1 for i in issues if i.key and "source_truth_mutation" in i.key.lower() and float(i.value or 0) > 0)
    raw_feedback_issue_count = sum(1 for i in issues if i.key and "raw_feedback_direct_to_llm" in i.key.lower() and float(i.value or 0) > 0)
    answer_permission_issue_count = sum(
        1
        for i in issues
        if i.key
        and any(term in i.key.lower() for term in ["direct_answer_allowed", "retrieval_only_answer_allowed", "answer_capable_without_citation"])
        and float(i.value or 0) > 0
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not critical and fail_count == 0 else "FAIL",
        "stage_record_count": len(stage_records),
        "present_stage_record_count": len(present),
        "missing_expected_stage_count": len(missing),
        "stage_pass_count": pass_count,
        "stage_fail_count": fail_count,
        "stage_unknown_count": unknown_count,
        "issue_count": len(issues),
        "critical_issue_count": len(critical),
        "warning_issue_count": len(warning),
        "review_issue_count": len(review),
        "source_truth_mutation_issue_count": source_truth_mutation_issue_count,
        "raw_feedback_direct_to_llm_issue_count": raw_feedback_issue_count,
        "answer_permission_issue_count": answer_permission_issue_count,
        "generated_at": utc_now_iso(),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRACE-Net IT Operations Console v1",
        "",
        f"**Status:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "stage_record_count",
        "present_stage_record_count",
        "missing_expected_stage_count",
        "stage_pass_count",
        "stage_fail_count",
        "critical_issue_count",
        "warning_issue_count",
        "review_issue_count",
        "source_truth_mutation_issue_count",
        "raw_feedback_direct_to_llm_issue_count",
        "answer_permission_issue_count",
        "excluded_quality_file_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Top Issues", ""])
    issues = report.get("issues", [])
    if not issues:
        lines.append("No issues detected.")
    else:
        for issue in issues[:50]:
            lines.append(f"- **{issue['severity'].upper()}** `{issue['category']}`: {issue['message']}")
            if issue.get("recommended_action"):
                lines.append(f"  - Action: {issue['recommended_action']}")
    lines.extend(["", "## Stage Health", ""])
    lines.append("| Stage | Exists | Status | Critical | Warning | Review |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for stage in report.get("stages", []):
        lines.append(
            f"| {stage['stage_id']} | {stage['exists']} | {stage['quality_status']} | "
            f"{stage['critical_issue_count']} | {stage['warning_issue_count']} | {stage['review_issue_count']} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_html(report: dict[str, Any]) -> str:
    md = render_markdown(report)
    escaped = html.escape(md)
    # Keep this dependency-free: a simple preformatted report is enough for backend/IT review.
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>TRACE-Net IT Operations Console v1</title>"
        "<style>body{font-family:Arial,sans-serif;margin:32px;}"
        "pre{white-space:pre-wrap;background:#f7f7f7;padding:16px;border:1px solid #ddd;}"
        ".pass{color:#0a7a0a}.fail{color:#b00020}</style></head><body>"
        f"<h1>TRACE-Net IT Operations Console v1</h1><pre>{escaped}</pre></body></html>"
    )




def build_effective_excluded_prefixes(
    trace_net_root: Path,
    output_dir: Path,
    excluded_relative_prefixes: list[tuple[str, ...]] | None = None,
    exclude_output_dir_artifacts: bool = True,
) -> list[tuple[str, ...]]:
    """Return relative prefixes that should be ignored during a real health scan.

    The IT console often writes its own report under the same trace_net root it
    scans. If an older console report failed, scanning that output folder creates
    a self-referential failure: the console reports itself as unhealthy because
    it found yesterday's console quality file. We exclude the selected output
    directory by default so the console reports project health, not its own prior
    diagnostics.
    """
    prefixes = list(excluded_relative_prefixes if excluded_relative_prefixes is not None else DEFAULT_EXCLUDED_RELATIVE_PREFIXES)
    if exclude_output_dir_artifacts:
        try:
            rel_parts = output_dir.resolve().relative_to(trace_net_root.resolve()).parts
        except ValueError:
            rel_parts = ()
        if rel_parts:
            prefix = tuple(str(part) for part in rel_parts)
            if prefix not in prefixes:
                prefixes.append(prefix)
    return prefixes


def build_it_operations_console(
    trace_net_root: Path = DEFAULT_TRACE_NET_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    include_all_quality_files: bool = True,
    max_critical_issues: int = 0,
    allow_missing_expected_stages: bool = True,
    excluded_relative_prefixes: list[tuple[str, ...]] | None = None,
    exclude_output_dir_artifacts: bool = True,
) -> dict[str, Any]:
    effective_excluded_prefixes = build_effective_excluded_prefixes(
        trace_net_root=trace_net_root,
        output_dir=output_dir,
        excluded_relative_prefixes=excluded_relative_prefixes,
        exclude_output_dir_artifacts=exclude_output_dir_artifacts,
    )
    stage_records, issues, excluded_quality_file_count = load_stage_records(
        trace_net_root,
        include_all_quality_files=include_all_quality_files,
        excluded_relative_prefixes=effective_excluded_prefixes,
    )

    if not allow_missing_expected_stages:
        missing = [s for s in stage_records if not s.exists]
        start = len(issues)
        for index, stage in enumerate(missing, start=start + 1):
            issues.append(
                Issue(
                    issue_id=f"itops_issue_{index:06d}",
                    severity="critical",
                    category="missing_required_stage",
                    message=f"Required stage '{stage.stage_id}' is missing.",
                    artifact_path=stage.artifact_path,
                    stage_id=stage.stage_id,
                    recommended_action="Run the missing required stage or adjust the requirement for this environment.",
                )
            )

    summary = summarize(stage_records, issues)
    summary["excluded_quality_file_count"] = excluded_quality_file_count
    summary["excluded_relative_prefixes"] = [list(prefix) for prefix in effective_excluded_prefixes]
    summary["exclude_output_dir_artifacts"] = exclude_output_dir_artifacts
    critical_count = summary["critical_issue_count"]
    quality_status = "PASS" if critical_count <= max_critical_issues and summary["stage_fail_count"] == 0 else "FAIL"

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "IT_OPERATIONS_CONSOLE_BUILT",
        "quality_status": quality_status,
        "generated_at": utc_now_iso(),
        "trace_net_root": trace_net_root.as_posix(),
        "output_dir": output_dir.as_posix(),
        "summary": summary,
        "quality": {
            "status": quality_status,
            "max_critical_issues": max_critical_issues,
            "critical_issue_count": critical_count,
            "stage_fail_count": summary["stage_fail_count"],
            "checks": {
                "critical_issue_count_within_limit": critical_count <= max_critical_issues,
                "stage_fail_count_zero": summary["stage_fail_count"] == 0,
                "source_truth_mutation_issue_count_zero": summary["source_truth_mutation_issue_count"] == 0,
                "raw_feedback_direct_to_llm_issue_count_zero": summary["raw_feedback_direct_to_llm_issue_count"] == 0,
                "answer_permission_issue_count_zero": summary["answer_permission_issue_count"] == 0,
            },
        },
        "stages": [stage.as_dict() for stage in stage_records],
        "issues": [issue.as_dict() for issue in issues],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_it_operations_console_v1.json"
    stages_path = output_dir / "trace_net_it_operations_console_v1_stages.jsonl"
    issues_path = output_dir / "trace_net_it_operations_console_v1_issues.jsonl"
    summary_path = output_dir / "trace_net_it_operations_console_v1_summary.json"
    manifest_path = output_dir / "trace_net_it_operations_console_v1_manifest.json"
    quality_path = output_dir / "trace_net_it_operations_console_v1_quality.json"
    md_path = output_dir / "trace_net_it_operations_console_v1.md"
    html_path = output_dir / "trace_net_it_operations_console_v1.html"

    write_json(report_path, report)
    write_jsonl(stages_path, report["stages"])
    write_jsonl(issues_path, report["issues"])
    write_json(summary_path, summary)
    write_json(quality_path, report["quality"])
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report["generated_at"],
        "report_path": report_path.as_posix(),
        "stages_path": stages_path.as_posix(),
        "issues_path": issues_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "quality_path": quality_path.as_posix(),
        "markdown_path": md_path.as_posix(),
        "html_path": html_path.as_posix(),
    }
    write_json(manifest_path, manifest)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")

    report.update(
        {
            "report_path": report_path.as_posix(),
            "stages_path": stages_path.as_posix(),
            "issues_path": issues_path.as_posix(),
            "summary_path": summary_path.as_posix(),
            "manifest_path": manifest_path.as_posix(),
            "quality_path": quality_path.as_posix(),
            "markdown_path": md_path.as_posix(),
            "html_path": html_path.as_posix(),
        }
    )
    write_json(report_path, report)
    return report


def check_it_operations_console_quality(
    report_path: Path,
    max_critical_issues: int = 0,
    require_no_stage_failures: bool = True,
    write_json_report: bool = False,
) -> dict[str, Any]:
    payload = read_json(report_path)
    summary = payload.get("summary", {})
    critical = int(summary.get("critical_issue_count", 0) or 0)
    stage_failures = int(summary.get("stage_fail_count", 0) or 0)
    checks = {
        "critical_issue_count_within_limit": critical <= max_critical_issues,
        "stage_fail_count_zero_if_required": (stage_failures == 0) if require_no_stage_failures else True,
        "source_truth_mutation_issue_count_zero": int(summary.get("source_truth_mutation_issue_count", 0) or 0) == 0,
        "raw_feedback_direct_to_llm_issue_count_zero": int(summary.get("raw_feedback_direct_to_llm_issue_count", 0) or 0) == 0,
        "answer_permission_issue_count_zero": int(summary.get("answer_permission_issue_count", 0) or 0) == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    quality = {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "report_path": report_path.as_posix(),
        "summary": summary,
        "checks": checks,
        "max_critical_issues": max_critical_issues,
        "critical_issue_count": critical,
        "stage_fail_count": stage_failures,
    }
    if write_json_report:
        quality_path = report_path.with_name("trace_net_it_operations_console_v1_quality.json")
        write_json(quality_path, quality)
        quality["quality_path"] = quality_path.as_posix()
    return quality


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net IT Operations Console v1")
    parser.add_argument("--trace-net-root", type=Path, default=DEFAULT_TRACE_NET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-critical-issues", type=int, default=0)
    parser.add_argument("--require-all-expected-stages", action="store_true")
    parser.add_argument("--expected-only", action="store_true", help="Only scan expected stage quality artifacts.")
    parser.add_argument(
        "--include-synthetic-test-artifacts",
        action="store_true",
        help="Include synthetic IT issue-origin test artifacts in a real trace_net scan.",
    )
    parser.add_argument(
        "--include-output-dir-artifacts",
        action="store_true",
        help="Include the console output directory in the scan. By default, the console ignores its own previous reports.",
    )
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_it_operations_console(
        trace_net_root=args.trace_net_root,
        output_dir=args.output_dir,
        include_all_quality_files=not args.expected_only,
        max_critical_issues=args.max_critical_issues,
        allow_missing_expected_stages=not args.require_all_expected_stages,
        excluded_relative_prefixes=[] if args.include_synthetic_test_artifacts else None,
        exclude_output_dir_artifacts=not args.include_output_dir_artifacts,
    )

    print("TRACE-Net IT operations console v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    summary = report["summary"]
    for key in [
        "stage_record_count",
        "present_stage_record_count",
        "missing_expected_stage_count",
        "stage_pass_count",
        "stage_fail_count",
        "critical_issue_count",
        "warning_issue_count",
        "review_issue_count",
        "source_truth_mutation_issue_count",
        "raw_feedback_direct_to_llm_issue_count",
        "answer_permission_issue_count",
        "excluded_quality_file_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" issues_path: {report['issues_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
