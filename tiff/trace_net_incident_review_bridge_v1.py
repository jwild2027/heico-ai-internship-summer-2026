"""TRACE-Net Incident -> Review Task Bridge v1.

This module converts operational incident events into human-review tasks.

Safety contract:
- Incidents are workflow signals only.
- Incidents cannot prove claims.
- Incidents cannot answer directly.
- Incidents cannot mutate source truth.
- The bridge is read-only with respect to source/graph/trust data.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_incident_review_bridge_v1"
DEFAULT_POSTGRES_TABLE = "trace_net_synthetic_incident_events"

SEVERITY_TO_PRIORITY = {
    "critical": "critical",
    "high": "high",
    "review": "high",
    "warning": "medium",
    "medium": "medium",
    "low": "low",
    "info": "low",
}

ORIGIN_TASK_MAP = {
    "source_ingest": ("review_source_ingest_incident", "Verify source package, file traceability, and affected page mapping."),
    "ocr_text": ("review_ocr_text_incident", "Inspect OCR quality and schedule OCR cleanup or region retry if needed."),
    "page_registry": ("review_page_registry_incident", "Inspect page traits, detected elements, and route selection."),
    "table_extraction": ("review_table_extraction_incident", "Inspect table rows/cells, repaired part numbers, and table trust status."),
    "visual_diagram": ("verify_visual_callouts", "Verify visual regions, callout candidates, and part-catalog/graph links."),
    "graph_integrity": ("inspect_graph_integrity_incident", "Inspect graph nodes/edges, orphan risks, and related attachment plans."),
    "semantic_vector": ("inspect_vector_index_incident", "Inspect Qdrant/vector counts, payload safety, and embedding status."),
    "keyword_search": ("inspect_keyword_search_incident", "Inspect OpenSearch/keyword index plans and safe document filters."),
    "retrieval": ("review_retrieval_incident", "Inspect retrieval groups, ranking signals, and citation/trust resolution."),
    "answer_gate": ("review_answer_gate_incident", "Inspect final answer gate artifacts, claim citations, and leakage checks."),
    "feedback_memory": ("review_feedback_memory_incident", "Inspect sanitized feedback memory and prompt-injection handling."),
    "incremental_ops": ("review_incremental_ops_incident", "Inspect incremental manifest/orchestrator dirty-stage and job planning state."),
    "llm_advisory": ("review_llm_advisory_incident", "Inspect LLM advisory output boundaries and ensure no source-truth promotion occurred."),
    "security_leakage": ("review_security_leakage_incident", "Inspect leakage signals and block unsafe data from prompts/search/answers."),
    "trust_authority": ("review_trust_authority_incident", "Inspect trust tier/authority gates and answer-permission boundaries."),
    "graph_community": ("review_graph_community_incident", "Inspect Leiden/community assignment and advisory-only retrieval use."),
    "human_review": ("review_human_review_incident", "Inspect review queue, triage, decisions, and promotion-gate status."),
}

SAFE_DECISION_FLAGS = {
    "can_answer_directly": False,
    "can_prove_claims": False,
    "can_mutate_source_truth": False,
    "source_truth_mutation_allowed": False,
    "raw_feedback_direct_to_llm": False,
    "affects_real_pipeline": False,
}


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(payload: Any, *, length: int = 16) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:length]


def ensure_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped[0:1] in {"[", "{"}:
            try:
                parsed = json.loads(stripped)
            except Exception:
                return [value]
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        return [value]
    return [value]


def ensure_dict(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {"raw": value}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    return {"value": value}


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def normalize_incident(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize incident-like input from JSONL/report/Postgres."""
    payload = ensure_dict(raw.get("payload"))
    incident_id = str(raw.get("incident_id") or raw.get("id") or payload.get("incident_id") or "").strip()
    if not incident_id:
        incident_id = "inc__" + stable_hash(raw)

    page_ids = ensure_list(raw.get("page_ids") or payload.get("page_ids"))
    citation_ids = ensure_list(raw.get("citation_ids") or payload.get("citation_ids"))
    community_ids = ensure_list(raw.get("community_ids") or payload.get("community_ids"))
    related_artifacts = ensure_list(raw.get("related_artifacts") or payload.get("related_artifacts"))

    target_type = str(raw.get("target_type") or payload.get("target_type") or "incident").strip() or "incident"
    target_id = str(raw.get("target_id") or payload.get("target_id") or incident_id).strip() or incident_id
    origin_category = str(raw.get("origin_category") or payload.get("origin_category") or "unknown").strip() or "unknown"
    severity = str(raw.get("severity") or payload.get("severity") or "info").strip().lower() or "info"
    status = str(raw.get("status") or payload.get("status") or "open").strip().lower() or "open"

    normalized = {
        "incident_id": incident_id,
        "created_at": str(raw.get("created_at") or payload.get("created_at") or utc_now_iso()),
        "environment": str(raw.get("environment") or payload.get("environment") or "local"),
        "incident_source": str(raw.get("incident_source") or payload.get("incident_source") or "synthetic_console"),
        "synthetic_only": safe_bool(raw.get("synthetic_only", payload.get("synthetic_only", True))),
        "origin_category": origin_category,
        "severity": severity,
        "status": status,
        "message": str(raw.get("message") or payload.get("message") or "TRACE-Net incident requires review."),
        "recommended_action": str(raw.get("recommended_action") or payload.get("recommended_action") or "Review incident and related TRACE-Net artifacts."),
        "target_type": target_type,
        "target_id": target_id,
        "page_ids": [str(x) for x in page_ids if str(x).strip()],
        "citation_ids": [str(x) for x in citation_ids if str(x).strip()],
        "community_ids": [str(x) for x in community_ids if str(x).strip()],
        "related_artifacts": [str(x) for x in related_artifacts if str(x).strip()],
        "affects_real_pipeline": safe_bool(raw.get("affects_real_pipeline", payload.get("affects_real_pipeline", False))),
        "can_answer_directly": safe_bool(raw.get("can_answer_directly", payload.get("can_answer_directly", False))),
        "can_prove_claims": safe_bool(raw.get("can_prove_claims", payload.get("can_prove_claims", False))),
        "can_mutate_source_truth": safe_bool(raw.get("can_mutate_source_truth", payload.get("can_mutate_source_truth", False))),
        "source_truth_mutation_allowed": safe_bool(raw.get("source_truth_mutation_allowed", payload.get("source_truth_mutation_allowed", False))),
        "raw_feedback_direct_to_llm": safe_bool(raw.get("raw_feedback_direct_to_llm", payload.get("raw_feedback_direct_to_llm", False))),
        "payload": payload,
    }
    return normalized


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            records.append(loaded)
    return records


def load_incidents_from_report(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("incidents", "incident_records", "records", "events"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    # Some reports may only store summary plus paths; not an incident source.
    return []


def load_incidents_from_postgres(database_url: str, *, table_name: str = DEFAULT_POSTGRES_TABLE, limit: int | None = None) -> list[dict[str, Any]]:
    if not database_url:
        raise ValueError("database_url is required for Postgres incident loading")
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("psycopg is required for Postgres incident loading") from exc

    safe_limit = ""
    params: tuple[Any, ...] = ()
    if limit and limit > 0:
        safe_limit = " limit %s"
        params = (limit,)

    # Table name is controlled by CLI; keep strict characters to avoid injection.
    if not table_name.replace("_", "").replace(".", "").isalnum():
        raise ValueError(f"unsafe postgres table name: {table_name!r}")

    query = f"select * from {table_name} order by created_at desc{safe_limit}"
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def load_incidents(
    *,
    database_url: str | None = None,
    postgres_table: str = DEFAULT_POSTGRES_TABLE,
    incidents_jsonl: Path | None = None,
    incident_report: Path | None = None,
    postgres_limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources: list[str] = []
    raw: list[dict[str, Any]] = []
    if database_url:
        raw.extend(load_incidents_from_postgres(database_url, table_name=postgres_table, limit=postgres_limit))
        sources.append(f"postgres:{postgres_table}")
    if incidents_jsonl:
        raw.extend(load_jsonl(incidents_jsonl))
        sources.append(str(incidents_jsonl))
    if incident_report:
        raw.extend(load_incidents_from_report(incident_report))
        sources.append(str(incident_report))

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for incident in raw:
        item = normalize_incident(incident)
        if item["incident_id"] in seen:
            continue
        seen.add(item["incident_id"])
        normalized.append(item)
    normalized.sort(key=lambda x: (x.get("created_at", ""), x.get("incident_id", "")), reverse=True)
    return normalized, {"incident_sources": sources, "raw_incident_count": len(raw), "deduped_incident_count": len(normalized)}


def priority_for_incident(incident: dict[str, Any]) -> str:
    severity = str(incident.get("severity") or "info").lower()
    priority = SEVERITY_TO_PRIORITY.get(severity, "low")
    if incident.get("raw_feedback_direct_to_llm") or incident.get("source_truth_mutation_allowed"):
        return "critical"
    if incident.get("origin_category") in {"security_leakage", "trust_authority", "answer_gate"} and severity in {"critical", "high"}:
        return "critical"
    return priority


def task_type_for_incident(incident: dict[str, Any]) -> tuple[str, str]:
    origin = str(incident.get("origin_category") or "unknown")
    return ORIGIN_TASK_MAP.get(origin, ("review_incident", "Review incident and determine whether a downstream review/promotion action is needed."))


def make_review_task(incident: dict[str, Any]) -> dict[str, Any]:
    task_type, default_action = task_type_for_incident(incident)
    priority = priority_for_incident(incident)
    page_ids = ensure_list(incident.get("page_ids"))
    citation_ids = ensure_list(incident.get("citation_ids"))
    community_ids = ensure_list(incident.get("community_ids"))
    incident_id = incident["incident_id"]
    task_id = "review_incident__" + stable_hash({"incident_id": incident_id, "task_type": task_type})
    recommended_action = str(incident.get("recommended_action") or default_action)
    if recommended_action.strip() in {"", "None"}:
        recommended_action = default_action

    reason = f"Incident {incident_id} from {incident.get('origin_category')} reported {incident.get('severity')} severity: {incident.get('message')}"
    task = {
        "review_task_id": task_id,
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "task_type": task_type,
        "origin_category": incident.get("origin_category"),
        "origin_incident_id": incident_id,
        "incident_source": incident.get("incident_source"),
        "severity": incident.get("severity"),
        "priority": priority,
        "status": "open",
        "target_type": incident.get("target_type") or "incident",
        "target_id": incident.get("target_id") or incident_id,
        "page_id": str(page_ids[0]) if page_ids else "",
        "page_ids": [str(x) for x in page_ids],
        "citation_ids": [str(x) for x in citation_ids],
        "community_ids": [str(x) for x in community_ids],
        "related_artifacts": ensure_list(incident.get("related_artifacts")),
        "reason": reason,
        "message": incident.get("message"),
        "recommended_action": recommended_action,
        "synthetic_only": bool(incident.get("synthetic_only", True)),
        "source_incident": incident,
        "requires_human_review": True,
        "requires_promotion_gate": False,
        "review_decision_allowed": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "raw_feedback_direct_to_llm": False,
        "affects_real_pipeline": False,
        "safety_status": "incident_review_task_only",
        "authority": "incident_review_advisory_only",
    }
    return task


def summarize_tasks(incidents: list[dict[str, Any]], tasks: list[dict[str, Any]], source_meta: dict[str, Any]) -> dict[str, Any]:
    def count_if(key: str, expected: Any = True, records: list[dict[str, Any]] | None = None) -> int:
        rows = records if records is not None else tasks
        return sum(1 for row in rows if row.get(key) == expected)

    priority_counts: dict[str, int] = {}
    task_type_counts: dict[str, int] = {}
    origin_counts: dict[str, int] = {}
    for task in tasks:
        priority_counts[str(task.get("priority") or "unknown")] = priority_counts.get(str(task.get("priority") or "unknown"), 0) + 1
        task_type_counts[str(task.get("task_type") or "unknown")] = task_type_counts.get(str(task.get("task_type") or "unknown"), 0) + 1
        origin_counts[str(task.get("origin_category") or "unknown")] = origin_counts.get(str(task.get("origin_category") or "unknown"), 0) + 1

    unsafe_task_count = sum(
        1
        for task in tasks
        if task.get("can_answer_directly")
        or task.get("can_prove_claims")
        or task.get("can_mutate_source_truth")
        or task.get("source_truth_mutation_allowed")
        or task.get("raw_feedback_direct_to_llm")
    )

    page_scoped_missing_page_id_count = sum(
        1
        for task in tasks
        if task.get("target_type") == "page" and not task.get("page_ids")
    )
    source_truth_mutation_incident_count = sum(1 for incident in incidents if incident.get("source_truth_mutation_allowed") or incident.get("can_mutate_source_truth"))
    raw_feedback_incident_count = sum(1 for incident in incidents if incident.get("raw_feedback_direct_to_llm"))

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PENDING",
        "incident_count": len(incidents),
        "review_task_count": len(tasks),
        "critical_priority_review_task_count": priority_counts.get("critical", 0),
        "high_priority_review_task_count": priority_counts.get("high", 0),
        "medium_priority_review_task_count": priority_counts.get("medium", 0),
        "low_priority_review_task_count": priority_counts.get("low", 0),
        "priority_counts": priority_counts,
        "task_type_counts": task_type_counts,
        "origin_category_counts": origin_counts,
        "page_scoped_missing_page_id_count": page_scoped_missing_page_id_count,
        "missing_target_count": sum(1 for task in tasks if not task.get("target_id")),
        "unsafe_review_task_count": unsafe_task_count,
        "review_task_can_answer_directly_count": count_if("can_answer_directly"),
        "review_task_can_prove_claims_count": count_if("can_prove_claims"),
        "source_truth_mutation_allowed_count": count_if("source_truth_mutation_allowed"),
        "raw_feedback_direct_to_llm_count": count_if("raw_feedback_direct_to_llm"),
        "source_truth_mutation_incident_count": source_truth_mutation_incident_count,
        "raw_feedback_incident_count": raw_feedback_incident_count,
        "synthetic_only_task_count": count_if("synthetic_only"),
        **source_meta,
    }


def evaluate_quality(
    report: dict[str, Any],
    *,
    min_incidents: int = 1,
    min_review_tasks: int = 1,
    min_high_priority_tasks: int = 0,
) -> dict[str, Any]:
    summary = report.get("summary", {})
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected})

    incident_count = int(summary.get("incident_count", 0))
    review_task_count = int(summary.get("review_task_count", 0))
    high_count = int(summary.get("high_priority_review_task_count", 0)) + int(summary.get("critical_priority_review_task_count", 0))
    add("incident_count_min", incident_count >= min_incidents, incident_count, f">= {min_incidents}")
    add("review_task_count_min", review_task_count >= min_review_tasks, review_task_count, f">= {min_review_tasks}")
    add("high_priority_review_task_count_min", high_count >= min_high_priority_tasks, high_count, f">= {min_high_priority_tasks}")
    for key in [
        "unsafe_review_task_count",
        "review_task_can_answer_directly_count",
        "review_task_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
        "missing_target_count",
    ]:
        value = int(summary.get(key, 0))
        add(f"{key}_zero", value == 0, value, 0)

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    quality = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "checks": checks,
        "incident_count": incident_count,
        "review_task_count": review_task_count,
        "critical_priority_review_task_count": int(summary.get("critical_priority_review_task_count", 0)),
        "high_priority_review_task_count": int(summary.get("high_priority_review_task_count", 0)),
        "unsafe_review_task_count": int(summary.get("unsafe_review_task_count", 0)),
        "review_task_can_answer_directly_count": int(summary.get("review_task_can_answer_directly_count", 0)),
        "review_task_can_prove_claims_count": int(summary.get("review_task_can_prove_claims_count", 0)),
        "source_truth_mutation_allowed_count": int(summary.get("source_truth_mutation_allowed_count", 0)),
        "raw_feedback_direct_to_llm_count": int(summary.get("raw_feedback_direct_to_llm_count", 0)),
    }
    return quality


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Incident Review Bridge v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "incident_count",
        "review_task_count",
        "critical_priority_review_task_count",
        "high_priority_review_task_count",
        "medium_priority_review_task_count",
        "low_priority_review_task_count",
        "unsafe_review_task_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Top Review Tasks", ""])
    for task in report.get("review_tasks", [])[:25]:
        lines.append(f"### {task.get('priority', '').upper()} — {task.get('task_type')}")
        lines.append(f"- review_task_id: `{task.get('review_task_id')}`")
        lines.append(f"- origin_incident_id: `{task.get('origin_incident_id')}`")
        lines.append(f"- target: `{task.get('target_type')}` / `{task.get('target_id')}`")
        lines.append(f"- pages: {', '.join(task.get('page_ids') or [])}")
        lines.append(f"- reason: {task.get('reason')}")
        lines.append(f"- action: {task.get('recommended_action')}")
        lines.append("")
    return "\n".join(lines)


def render_html(report: dict[str, Any]) -> str:
    md = render_markdown(report)
    body = "<br>\n".join(html.escape(line) for line in md.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Incident Review Bridge v1</title></head><body><pre>{body}</pre></body></html>"


def build_incident_review_bridge(
    *,
    output_dir: Path,
    database_url: str | None = None,
    postgres_table: str = DEFAULT_POSTGRES_TABLE,
    incidents_jsonl: Path | None = None,
    incident_report: Path | None = None,
    postgres_limit: int | None = None,
    min_incidents: int = 1,
    min_review_tasks: int = 1,
    min_high_priority_tasks: int = 0,
    write_quality: bool = False,
) -> dict[str, Any]:
    incidents, source_meta = load_incidents(
        database_url=database_url,
        postgres_table=postgres_table,
        incidents_jsonl=incidents_jsonl,
        incident_report=incident_report,
        postgres_limit=postgres_limit,
    )
    tasks = [make_review_task(incident) for incident in incidents]
    summary = summarize_tasks(incidents, tasks, source_meta)
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "INCIDENT_REVIEW_BRIDGE_BUILT",
        "generated_at": utc_now_iso(),
        "writeback_mode": "read_only_review_task_plan",
        "storage_source": source_meta.get("incident_sources", []),
        "incidents": incidents,
        "review_tasks": tasks,
        "summary": summary,
    }
    quality = evaluate_quality(
        report,
        min_incidents=min_incidents,
        min_review_tasks=min_review_tasks,
        min_high_priority_tasks=min_high_priority_tasks,
    )
    report["quality"] = quality
    report["quality_status"] = quality["status"]
    report["summary"]["status"] = quality["status"]

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_incident_review_bridge_v1.json"
    tasks_path = output_dir / "trace_net_incident_review_bridge_v1_tasks.jsonl"
    incidents_path = output_dir / "trace_net_incident_review_bridge_v1_incidents.jsonl"
    summary_path = output_dir / "trace_net_incident_review_bridge_v1_summary.json"
    quality_path = output_dir / "trace_net_incident_review_bridge_v1_quality.json"
    manifest_path = output_dir / "trace_net_incident_review_bridge_v1_manifest.json"
    md_path = output_dir / "trace_net_incident_review_bridge_v1.md"
    html_path = output_dir / "trace_net_incident_review_bridge_v1.html"

    write_json(report_path, report)
    write_jsonl(tasks_path, tasks)
    write_jsonl(incidents_path, incidents)
    write_json(summary_path, report["summary"])
    if write_quality:
        write_json(quality_path, quality)
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "generated_at": report["generated_at"],
        "report_path": str(report_path),
        "tasks_path": str(tasks_path),
        "incidents_path": str(incidents_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "writeback_mode": report["writeback_mode"],
    })
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")

    report.update({
        "report_path": str(report_path),
        "tasks_path": str(tasks_path),
        "incidents_path": str(incidents_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "manifest_path": str(manifest_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
    })
    write_json(report_path, report)
    return report


def quality_report(report_path: Path, *, min_incidents: int = 1, min_review_tasks: int = 1, min_high_priority_tasks: int = 0, write_json_report: bool = False) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    quality = evaluate_quality(
        report,
        min_incidents=min_incidents,
        min_review_tasks=min_review_tasks,
        min_high_priority_tasks=min_high_priority_tasks,
    )
    if write_json_report:
        quality_path = report_path.with_name("trace_net_incident_review_bridge_v1_quality.json")
        write_json(quality_path, quality)
        quality["quality_path"] = str(quality_path)
    return quality


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Incident -> Review Task Bridge v1")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""))
    parser.add_argument("--postgres-table", default=DEFAULT_POSTGRES_TABLE)
    parser.add_argument("--postgres-limit", type=int, default=0)
    parser.add_argument("--incidents-jsonl", type=Path)
    parser.add_argument("--incident-report", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("local_data/organization/trace_net/incident_review_bridge"))
    parser.add_argument("--min-incidents", type=int, default=1)
    parser.add_argument("--min-review-tasks", type=int, default=1)
    parser.add_argument("--min-high-priority-tasks", type=int, default=0)
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not args.database_url and not args.incidents_jsonl and not args.incident_report:
        parser.error("Provide --database-url, --incidents-jsonl, or --incident-report")
    try:
        report = build_incident_review_bridge(
            output_dir=args.output_dir,
            database_url=args.database_url or None,
            postgres_table=args.postgres_table,
            incidents_jsonl=args.incidents_jsonl,
            incident_report=args.incident_report,
            postgres_limit=args.postgres_limit or None,
            min_incidents=args.min_incidents,
            min_review_tasks=args.min_review_tasks,
            min_high_priority_tasks=args.min_high_priority_tasks,
            write_quality=args.quality,
        )
    except Exception as exc:
        print(f"TRACE-Net incident review bridge failed: {exc}")
        return 1

    summary = report["summary"]
    print("TRACE-Net incident review bridge v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "incident_count",
        "review_task_count",
        "critical_priority_review_task_count",
        "high_priority_review_task_count",
        "medium_priority_review_task_count",
        "low_priority_review_task_count",
        "unsafe_review_task_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" tasks_path: {report['tasks_path']}")
    if args.quality:
        print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
