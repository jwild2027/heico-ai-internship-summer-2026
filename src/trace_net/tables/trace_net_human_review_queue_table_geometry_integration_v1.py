"""TRACE-Net Human Review Queue Table Geometry Integration v1.

This module merges the Table Geometry Review Bridge v1 task artifact into the
main TRACE-Net Human Review Queue artifact. It is intentionally read-only with
respect to source truth and retrieval systems: it only writes queue artifacts.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_human_review_queue_table_geometry_integration_v1"
QUEUE_SCHEMA_VERSION = "trace_net_human_review_queue_v1"
AUTHORITY = "human_review_advisory_only"
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if path is None:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def stable_id(prefix: str, *parts: Any) -> str:
    text = "||".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def string_list(value: Any) -> list[str]:
    return [str(item) for item in as_list(value) if item is not None and str(item) != ""]


def normalize_priority(value: Any, default: str = "medium") -> str:
    text = str(value or default).strip().lower()
    if text in {"critical", "crit"}:
        return "critical"
    if text in {"high", "hi"}:
        return "high"
    if text in {"medium", "med", "review", "warning"}:
        return "medium"
    if text in {"low", "info"}:
        return "low"
    return default


def sanitize_text(value: Any, max_chars: int = 1200) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()[:max_chars]


def extract_domain_validation(task: dict[str, Any]) -> dict[str, Any]:
    value = task.get("domain_validation")
    if isinstance(value, dict):
        return value
    value = task.get("domain_table_validation")
    if isinstance(value, dict):
        return value
    return {}


def extract_part_numbers(task: dict[str, Any]) -> list[str]:
    values: list[str] = []
    values.extend(string_list(task.get("part_numbers")))
    domain = extract_domain_validation(task)
    values.extend(string_list(domain.get("part_numbers_sample")))
    values.extend(string_list(task.get("part_numbers_sample")))
    # Keep deterministic, compact records. The review bridge keeps counts, not always every part.
    return sorted(set(values))[:50]


def task_has_answer_permission(task: dict[str, Any]) -> bool:
    return bool(
        task.get("answer_permission")
        or task.get("final_answer_allowed")
        or task.get("can_answer_directly")
        or task.get("can_prove_claims")
        or task.get("retrieval_only_answer_allowed")
    )


def task_mutates_source_truth(task: dict[str, Any]) -> bool:
    return bool(
        task.get("source_truth_mutation_allowed")
        or task.get("can_mutate_source_truth")
        or int(task.get("source_truth_mutations_performed") or 0) > 0
    )


def convert_table_geometry_review_task(
    source_task: dict[str, Any],
    *,
    artifact_path: str | None,
) -> dict[str, Any]:
    source_task_id = str(source_task.get("review_task_id") or stable_id("table_geometry_source", source_task))
    page_id = source_task.get("page_id") or source_task.get("source_page_id")
    if page_id is not None:
        page_id = str(page_id)
    table_id = source_task.get("table_id") or source_task.get("target_id") or source_task_id
    table_type = str(source_task.get("table_type") or "unknown_table")
    issue_type = str(source_task.get("issue_type") or "table_geometry_review_required")
    review_flags = string_list(source_task.get("review_flags"))
    recommended_actions = string_list(source_task.get("recommended_actions"))
    part_numbers = extract_part_numbers(source_task)
    priority = normalize_priority(source_task.get("priority"), default="medium")

    if table_type == "parts_list_table" or int(source_task.get("part_number_count") or 0) > 0 or part_numbers:
        # Part-number tables are high leverage in TRACE-Net; do not down-prioritize them.
        if priority not in {"critical", "high"}:
            priority = "high"

    reason = (
        f"Table geometry review bridge routed table '{table_id}' on page '{page_id or 'UNKNOWN'}' "
        f"for issue '{issue_type}'."
    )
    if review_flags:
        reason += f" Review flags: {', '.join(review_flags[:8])}."

    action = "Review table geometry against the source page."
    if recommended_actions:
        action = "; ".join(recommended_actions[:10])

    task_id = stable_id(
        "review",
        "table_geometry_review_required",
        source_task_id,
        page_id,
        table_id,
        issue_type,
    )

    issue_value = {
        "source_review_task_id": source_task_id,
        "table_type": table_type,
        "geometry_confidence": source_task.get("geometry_confidence"),
        "image_line_detection_available": bool(source_task.get("image_line_detection_available")),
        "cell_record_count": int(source_task.get("cell_record_count") or 0),
        "row_record_count": int(source_task.get("row_record_count") or 0),
        "part_number_count": int(source_task.get("part_number_count") or 0),
        "merged_cell_candidate_count": int(source_task.get("merged_cell_candidate_count") or 0),
        "review_flags": review_flags,
        "recommended_actions": recommended_actions,
    }

    return {
        "review_task_id": task_id,
        "schema_version": QUEUE_SCHEMA_VERSION,
        "task_type": "review_table_geometry_line_detection",
        "priority": priority,
        "origin_category": "table_geometry",
        "source_stage": "table_geometry_review_bridge",
        "page_id": page_id,
        "requires_page_id": True,
        "missing_page_id": not bool(page_id),
        "target_type": "table_geometry_review_task",
        "target_id": str(table_id),
        "artifact_path": artifact_path,
        "issue_key": issue_type,
        "issue_value": issue_value,
        "reason": sanitize_text(reason),
        "recommended_action": sanitize_text(action),
        "review_status": "open",
        "review_queue_authority": AUTHORITY,
        "citation_ids": string_list(source_task.get("citation_ids")),
        "community_ids": string_list(source_task.get("community_ids")),
        "part_numbers": part_numbers,
        "tags": sorted(
            set(
                [
                    "table_geometry",
                    "table_line_detection",
                    "table_cell_assignment",
                    table_type,
                    issue_type,
                ]
                + review_flags
            )
        ),
        "table_geometry_review_bridge_task": True,
        "source_table_geometry_review_task_id": source_task_id,
        "table_id": str(table_id),
        "table_type": table_type,
        "geometry_confidence": source_task.get("geometry_confidence"),
        "image_line_detection_available": bool(source_task.get("image_line_detection_available")),
        "cell_record_count": int(source_task.get("cell_record_count") or 0),
        "row_record_count": int(source_task.get("row_record_count") or 0),
        "part_number_count": int(source_task.get("part_number_count") or 0),
        "merged_cell_candidate_count": int(source_task.get("merged_cell_candidate_count") or 0),
        "requires_human_review": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "final_answer_allowed": False,
        "answer_permission": False,
        "retrieval_only_answer_allowed": False,
        "can_override_citation": False,
        "can_override_trust_authority": False,
        "source_truth_mutations_performed": 0,
        "unsafe_review_task": False,
    }


def load_base_tasks(base_queue: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = base_queue.get("review_tasks")
    if isinstance(tasks, list):
        return [dict(task) for task in tasks if isinstance(task, dict)]
    return []


def extract_table_geometry_tasks(bridge_report: dict[str, Any], *, artifact_path: str | None) -> list[dict[str, Any]]:
    source_tasks = bridge_report.get("review_tasks") or bridge_report.get("tasks") or []
    converted: list[dict[str, Any]] = []
    for task in source_tasks:
        if not isinstance(task, dict):
            continue
        if not (task.get("requires_human_review") or task.get("review_required") or task.get("review_flags")):
            continue
        converted.append(convert_table_geometry_review_task(task, artifact_path=artifact_path))
    return converted


def sort_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        tasks,
        key=lambda task: (
            PRIORITY_ORDER.get(normalize_priority(task.get("priority")), 9),
            str(task.get("origin_category") or ""),
            str(task.get("page_id") or ""),
            str(task.get("task_type") or ""),
            str(task.get("review_task_id") or ""),
        ),
    )


def merge_tasks(base_tasks: list[dict[str, Any]], new_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for task in base_tasks + new_tasks:
        task_id = str(task.get("review_task_id") or stable_id("review", task))
        if task_id in seen:
            continue
        task["review_task_id"] = task_id
        task["priority"] = normalize_priority(task.get("priority"))
        seen.add(task_id)
        merged.append(task)
    return sort_tasks(merged)


def compute_summary(
    *,
    tasks: list[dict[str, Any]],
    base_queue: dict[str, Any],
    bridge_report: dict[str, Any],
    table_geometry_task_count: int,
) -> dict[str, Any]:
    priority_counts = Counter(normalize_priority(t.get("priority")) for t in tasks)
    task_type_counts = Counter(str(t.get("task_type") or "") for t in tasks)
    origin_counts = Counter(str(t.get("origin_category") or "") for t in tasks)
    table_geometry_tasks = [t for t in tasks if t.get("table_geometry_review_bridge_task")]
    page_ids = sorted({str(t.get("page_id")) for t in tasks if t.get("page_id")})

    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "integration_schema_version": SCHEMA_VERSION,
        "status": "HUMAN_REVIEW_QUEUE_TABLE_GEOMETRY_INTEGRATED",
        "base_queue_quality_status": base_queue.get("quality_status") or base_queue.get("summary", {}).get("quality_status") or base_queue.get("status"),
        "table_geometry_review_bridge_quality_status": bridge_report.get("quality_status") or bridge_report.get("summary", {}).get("quality_status") or bridge_report.get("status"),
        "base_review_task_count": len(load_base_tasks(base_queue)),
        "table_geometry_review_task_count": len(table_geometry_tasks),
        "table_geometry_review_tasks_added_count": table_geometry_task_count,
        "review_task_count": len(tasks),
        "open_review_task_count": len([t for t in tasks if t.get("review_status", "open") == "open"]),
        "critical_priority_review_task_count": priority_counts.get("critical", 0),
        "high_priority_review_task_count": priority_counts.get("critical", 0) + priority_counts.get("high", 0),
        "medium_priority_review_task_count": priority_counts.get("medium", 0),
        "low_priority_review_task_count": priority_counts.get("low", 0),
        "page_scoped_review_task_count": len([t for t in tasks if t.get("page_id")]),
        "review_page_count": len(page_ids),
        "missing_page_id_count": len([t for t in tasks if t.get("missing_page_id")]),
        "unsafe_review_task_count": len([t for t in tasks if t.get("unsafe_review_task")]),
        "review_task_can_answer_directly_count": len([t for t in tasks if t.get("can_answer_directly")]),
        "review_task_can_prove_claims_count": len([t for t in tasks if t.get("can_prove_claims")]),
        "answer_permission_count": len([t for t in tasks if task_has_answer_permission(t)]),
        "source_truth_mutation_allowed_count": len([t for t in tasks if task_mutates_source_truth(t)]),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "table_geometry_high_priority_task_count": len([t for t in table_geometry_tasks if normalize_priority(t.get("priority")) in {"critical", "high"}]),
        "table_geometry_missing_image_line_detection_task_count": len(
            [t for t in table_geometry_tasks if not t.get("image_line_detection_available")]
        ),
        "table_geometry_part_number_table_task_count": len(
            [t for t in table_geometry_tasks if int(t.get("part_number_count") or 0) > 0 or t.get("part_numbers")]
        ),
        "table_geometry_merged_cell_review_task_count": len(
            [t for t in table_geometry_tasks if int(t.get("merged_cell_candidate_count") or 0) > 0]
        ),
        "task_type_counts": dict(sorted(task_type_counts.items())),
        "origin_category_counts": dict(sorted(origin_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "source_quality_statuses": {
            "human_review_queue_base": base_queue.get("quality_status") or base_queue.get("summary", {}).get("quality_status") or base_queue.get("status"),
            "table_geometry_review_bridge": bridge_report.get("quality_status") or bridge_report.get("summary", {}).get("quality_status") or bridge_report.get("status"),
        },
        "quality_status": "UNKNOWN",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutations_performed": 0,
    }


def compute_quality(
    report: dict[str, Any],
    *,
    min_review_tasks: int,
    min_table_geometry_review_tasks: int,
    require_table_geometry_bridge_quality_pass: bool,
    require_no_answer_permission: bool,
) -> dict[str, Any]:
    summary = report.get("summary", {}) or {}
    checks: dict[str, bool] = {
        "min_review_tasks_met": int(summary.get("review_task_count") or 0) >= min_review_tasks,
        "min_table_geometry_review_tasks_met": int(summary.get("table_geometry_review_task_count") or 0) >= min_table_geometry_review_tasks,
        "unsafe_review_task_count_zero": int(summary.get("unsafe_review_task_count") or 0) == 0,
        "review_task_can_answer_directly_zero": int(summary.get("review_task_can_answer_directly_count") or 0) == 0,
        "review_task_can_prove_claims_zero": int(summary.get("review_task_can_prove_claims_count") or 0) == 0,
        "source_truth_mutation_allowed_zero": int(summary.get("source_truth_mutation_allowed_count") or 0) == 0,
        "write_attempts_zero": int(summary.get("postgres_write_attempt_count") or 0) == 0
        and int(summary.get("qdrant_write_attempt_count") or 0) == 0
        and int(summary.get("opensearch_write_attempt_count") or 0) == 0,
    }
    if require_table_geometry_bridge_quality_pass:
        checks["table_geometry_bridge_quality_pass"] = (
            str(summary.get("table_geometry_review_bridge_quality_status") or "").upper() == "PASS"
        )
    if require_no_answer_permission:
        checks["answer_permission_zero"] = int(summary.get("answer_permission_count") or 0) == 0
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "quality_status": status,
        "checks": checks,
        "summary": summary,
        "generated_at": utc_now(),
    }


def build_human_review_queue_table_geometry_integration(
    *,
    human_review_queue_path: str | Path | None,
    table_geometry_review_bridge_path: str | Path,
    output_dir: str | Path,
    min_review_tasks: int = 1,
    min_table_geometry_review_tasks: int = 1,
    require_table_geometry_bridge_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    base_queue = read_json(human_review_queue_path, {}) if human_review_queue_path else {}
    bridge_report = read_json(table_geometry_review_bridge_path, {})
    if not isinstance(base_queue, dict):
        base_queue = {}
    if not isinstance(bridge_report, dict):
        bridge_report = {}

    base_tasks = load_base_tasks(base_queue)
    table_geometry_tasks = extract_table_geometry_tasks(
        bridge_report,
        artifact_path=str(table_geometry_review_bridge_path),
    )
    tasks = merge_tasks(base_tasks, table_geometry_tasks)

    summary = compute_summary(
        tasks=tasks,
        base_queue=base_queue,
        bridge_report=bridge_report,
        table_geometry_task_count=len(table_geometry_tasks),
    )

    report = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "integration_schema_version": SCHEMA_VERSION,
        "status": "HUMAN_REVIEW_QUEUE_TABLE_GEOMETRY_INTEGRATED",
        "quality_status": "UNKNOWN",
        "generated_at": utc_now(),
        "summary": summary,
        "review_tasks": tasks,
        "review_pages": sorted({str(t.get("page_id")) for t in tasks if t.get("page_id")}),
        "table_geometry_review_bridge_path": str(table_geometry_review_bridge_path),
        "base_human_review_queue_path": str(human_review_queue_path) if human_review_queue_path else None,
        "safety_contract": {
            "read_only_integration": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
        },
    }

    quality = compute_quality(
        report,
        min_review_tasks=min_review_tasks,
        min_table_geometry_review_tasks=min_table_geometry_review_tasks,
        require_table_geometry_bridge_quality_pass=require_table_geometry_bridge_quality_pass,
        require_no_answer_permission=require_no_answer_permission,
    )
    report["quality_status"] = quality["quality_status"]
    report["summary"]["quality_status"] = quality["quality_status"]
    report["summary"]["quality_fail_reasons"] = [key for key, passed in quality["checks"].items() if not passed]
    quality["summary"] = report["summary"]

    report_path = out / "trace_net_human_review_queue_v1.json"
    tasks_path = out / "trace_net_human_review_queue_v1_tasks.jsonl"
    summary_path = out / "trace_net_human_review_queue_v1_summary.json"
    quality_path = out / "trace_net_human_review_queue_v1_quality.json"
    integration_quality_path = out / "trace_net_human_review_queue_table_geometry_integration_v1_quality.json"
    manifest_path = out / "trace_net_human_review_queue_table_geometry_integration_v1_manifest.json"

    report["report_path"] = str(report_path)
    report["tasks_path"] = str(tasks_path)
    report["quality_path"] = str(quality_path)

    write_json(report_path, report)
    write_jsonl(tasks_path, tasks)
    write_json(summary_path, report["summary"])
    write_json(quality_path, quality)
    write_json(integration_quality_path, quality)
    write_json(
        manifest_path,
        {
            "schema_version": f"{SCHEMA_VERSION}_manifest",
            "generated_at": utc_now(),
            "inputs": {
                "human_review_queue": str(human_review_queue_path) if human_review_queue_path else None,
                "table_geometry_review_bridge": str(table_geometry_review_bridge_path),
            },
            "outputs": {
                "report": str(report_path),
                "tasks": str(tasks_path),
                "summary": str(summary_path),
                "quality": str(quality_path),
                "integration_quality": str(integration_quality_path),
            },
        },
    )
    return report


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "min_review_tasks": args.min_review_tasks,
        "min_table_geometry_review_tasks": args.min_table_geometry_review_tasks,
        "require_table_geometry_bridge_quality_pass": args.require_table_geometry_bridge_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Integrate table geometry review tasks into TRACE-Net Human Review Queue.")
    parser.add_argument("--human-review-queue", default=None)
    parser.add_argument("--table-geometry-review-bridge", required=True)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/human_review_queue")
    parser.add_argument("--min-review-tasks", type=int, default=1)
    parser.add_argument("--min-table-geometry-review-tasks", type=int, default=1)
    parser.add_argument("--require-table-geometry-bridge-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_human_review_queue_table_geometry_integration(
        human_review_queue_path=args.human_review_queue,
        table_geometry_review_bridge_path=args.table_geometry_review_bridge,
        output_dir=args.output_dir,
        write_quality=args.quality,
        **thresholds_from_args(args),
    )
    summary = report["summary"]
    print("TRACE-Net Human Review Queue Table Geometry Integration v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "review_task_count",
        "base_review_task_count",
        "table_geometry_review_task_count",
        "table_geometry_high_priority_task_count",
        "table_geometry_missing_image_line_detection_task_count",
        "unsafe_review_task_count",
        "answer_permission_count",
        "review_task_can_answer_directly_count",
        "review_task_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
