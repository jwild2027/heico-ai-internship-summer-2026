"""TRACE-Net Synthetic Incident Console Postgres smoke verification v1.

This module verifies that the synthetic incident console can use Postgres as its
server-side source of truth for synthetic/admin incident records.

Safety contract:
- creates synthetic incident records only
- does not mutate graph/source/trust/citation truth
- does not write Qdrant/OpenSearch
- does not grant answer/proof authority
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tiff.trace_net_synthetic_incident_console_v1 import (
    DEFAULT_INCIDENT_TABLE,
    POSTGRES_STORAGE_MODE,
    build_console_report,
    init_postgres_storage,
    make_random_synthetic_incident,
    save_incident_for_storage,
)

SCHEMA_VERSION = "trace_net_synthetic_incident_postgres_smoke_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/synthetic_incident_console_postgres_smoke")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_table_name(table_name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "", table_name or DEFAULT_INCIDENT_TABLE)
    return safe or DEFAULT_INCIDENT_TABLE


def require_psycopg():
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on user env
        raise RuntimeError("psycopg is required for Postgres smoke verification") from exc
    return psycopg


def postgres_count(database_url: str, table_name: str) -> int:
    psycopg = require_psycopg()
    table = safe_table_name(table_name)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"select count(*) from {table}")
            row = cur.fetchone()
    return int(row[0] if row else 0)


def postgres_fetch_incidents(database_url: str, table_name: str, incident_ids: list[str]) -> list[dict[str, Any]]:
    if not incident_ids:
        return []
    psycopg = require_psycopg()
    table = safe_table_name(table_name)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"select incident_id, severity, origin_category, target_type, target_id, synthetic_only, payload "
                f"from {table} where incident_id = any(%s) order by created_at asc",
                (incident_ids,),
            )
            rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = row[6]
        if isinstance(payload, str):
            payload_dict = json.loads(payload)
        elif isinstance(payload, dict):
            payload_dict = payload
        else:
            payload_dict = {}
        out.append(
            {
                "incident_id": row[0],
                "severity": row[1],
                "origin_category": row[2],
                "target_type": row[3],
                "target_id": row[4],
                "synthetic_only": bool(row[5]),
                "payload": payload_dict,
            }
        )
    return out


def artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "report": output_dir / "trace_net_synthetic_incident_postgres_smoke_v1.json",
        "summary": output_dir / "trace_net_synthetic_incident_postgres_smoke_v1_summary.json",
        "quality": output_dir / "trace_net_synthetic_incident_postgres_smoke_v1_quality.json",
        "manifest": output_dir / "trace_net_synthetic_incident_postgres_smoke_v1_manifest.json",
        "md": output_dir / "trace_net_synthetic_incident_postgres_smoke_v1.md",
    }


def quality_report(report: dict[str, Any], *, min_inserted_incidents: int = 1) -> dict[str, Any]:
    summary = report.get("summary", report)
    checks = {
        "status_is_smoke_ran": report.get("status") == "POSTGRES_SMOKE_RAN",
        "storage_mode_postgres": summary.get("storage_mode") == POSTGRES_STORAGE_MODE,
        "postgres_table_present": bool(summary.get("postgres_table")),
        "inserted_incident_count_min": int(summary.get("inserted_incident_count", 0)) >= min_inserted_incidents,
        "created_incidents_found_in_postgres": int(summary.get("created_incident_found_count", 0)) >= min_inserted_incidents,
        "unsafe_incident_count_zero": int(summary.get("unsafe_incident_count", 0)) == 0,
        "source_truth_mutation_allowed_zero": int(summary.get("source_truth_mutation_allowed_count", 0)) == 0,
        "raw_feedback_direct_to_llm_zero": int(summary.get("raw_feedback_direct_to_llm_count", 0)) == 0,
        "affects_real_pipeline_zero": int(summary.get("affects_real_pipeline_count", 0)) == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "checks": checks,
        "storage_mode": summary.get("storage_mode"),
        "postgres_table": summary.get("postgres_table"),
        "inserted_incident_count": int(summary.get("inserted_incident_count", 0)),
        "created_incident_found_count": int(summary.get("created_incident_found_count", 0)),
        "unsafe_incident_count": int(summary.get("unsafe_incident_count", 0)),
        "source_truth_mutation_allowed_count": int(summary.get("source_truth_mutation_allowed_count", 0)),
        "raw_feedback_direct_to_llm_count": int(summary.get("raw_feedback_direct_to_llm_count", 0)),
    }


def summarize_created_incidents(created: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "created_incident_count": len(created),
        "created_incident_ids": [i.get("incident_id") for i in created],
        "randomly_generated_incident_count": sum(1 for i in created if i.get("randomly_generated")),
        "unsafe_incident_count": sum(
            1
            for i in created
            if i.get("can_answer_directly")
            or i.get("can_prove_claims")
            or i.get("can_mutate_source_truth")
            or i.get("source_truth_mutation_allowed")
            or i.get("raw_feedback_direct_to_llm")
            or i.get("affects_real_pipeline")
        ),
        "source_truth_mutation_allowed_count": sum(1 for i in created if i.get("source_truth_mutation_allowed")),
        "raw_feedback_direct_to_llm_count": sum(1 for i in created if i.get("raw_feedback_direct_to_llm")),
        "affects_real_pipeline_count": sum(1 for i in created if i.get("affects_real_pipeline")),
    }


def run_postgres_smoke(
    *,
    database_url: str,
    output_dir: Path,
    postgres_table: str = DEFAULT_INCIDENT_TABLE,
    random_incident_count: int = 1,
    min_inserted_incidents: int = 1,
    actor_id: str = "postgres_smoke",
) -> dict[str, Any]:
    if not database_url:
        raise ValueError("database_url is required for Postgres smoke verification")
    if random_incident_count < 1:
        raise ValueError("random_incident_count must be at least 1")

    paths = artifact_paths(output_dir)
    ensure_dir(output_dir)

    init_postgres_storage(database_url, table_name=postgres_table)
    before_count = postgres_count(database_url, postgres_table)

    created: list[dict[str, Any]] = []
    for _ in range(random_incident_count):
        incident = make_random_synthetic_incident(actor_id=actor_id)
        save_incident_for_storage(
            output_dir,
            incident,
            storage_mode=POSTGRES_STORAGE_MODE,
            database_url=database_url,
            table_name=postgres_table,
        )
        created.append(incident)

    after_count = postgres_count(database_url, postgres_table)
    found = postgres_fetch_incidents(database_url, postgres_table, [str(i.get("incident_id")) for i in created])
    console_report = build_console_report(
        output_dir,
        storage_mode=POSTGRES_STORAGE_MODE,
        database_url=database_url,
        table_name=postgres_table,
    )

    created_summary = summarize_created_incidents(created)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "storage_mode": POSTGRES_STORAGE_MODE,
        "postgres_table": safe_table_name(postgres_table),
        "before_count": before_count,
        "after_count": after_count,
        "inserted_incident_count": max(0, after_count - before_count),
        "created_incident_count": len(created),
        "created_incident_found_count": len(found),
        "console_report_incident_count": int(console_report.get("summary", {}).get("incident_count", 0)),
        **created_summary,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "POSTGRES_SMOKE_RAN",
        "quality_status": "UNKNOWN",
        "generated_at": utc_now(),
        "summary": summary,
        "created_incidents": created,
        "postgres_found_incidents": found,
        "console_report_path": str(output_dir / "trace_net_synthetic_incident_console_v1.json"),
        "safety_contract": {
            "synthetic_only": True,
            "affects_real_pipeline": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
            "raw_feedback_direct_to_llm": False,
            "no_graph_write": True,
            "no_qdrant_write": True,
            "no_opensearch_write": True,
        },
    }
    quality = quality_report(report, min_inserted_incidents=min_inserted_incidents)
    report["quality_status"] = quality["status"]
    write_json(paths["report"], report)
    write_json(paths["summary"], summary)
    write_json(paths["quality"], quality)
    write_json(paths["manifest"], {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "artifact_paths": {k: str(v) for k, v in paths.items()},
        "quality_status": quality["status"],
        "postgres_table": safe_table_name(postgres_table),
    })
    paths["md"].write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# TRACE-Net Synthetic Incident Postgres Smoke v1",
        "",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "storage_mode",
        "postgres_table",
        "before_count",
        "after_count",
        "inserted_incident_count",
        "created_incident_count",
        "created_incident_found_count",
        "unsafe_incident_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Created incidents", ""])
    for incident in report.get("created_incidents", []):
        lines.append(
            f"- `{incident.get('incident_id')}` {str(incident.get('severity')).upper()} "
            f"{incident.get('origin_category')}: {incident.get('message')}"
        )
    return "\n".join(lines) + "\n"


def check_quality_file(report_path: Path, *, min_inserted_incidents: int = 1, write_json_report: bool = False) -> dict[str, Any]:
    report = read_json(report_path)
    quality = quality_report(report, min_inserted_incidents=min_inserted_incidents)
    if write_json_report:
        quality_path = report_path.with_name("trace_net_synthetic_incident_postgres_smoke_v1_quality.json")
        write_json(quality_path, quality)
    return quality


def print_run_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    print("TRACE-Net synthetic incident Postgres smoke v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "storage_mode",
        "postgres_table",
        "before_count",
        "after_count",
        "inserted_incident_count",
        "created_incident_found_count",
        "unsafe_incident_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {artifact_paths(Path(DEFAULT_OUTPUT_DIR))['report'] if False else ''}".rstrip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net synthetic incident Postgres smoke verification v1")
    parser.add_argument("--database-url", default="", help="Postgres URL, or use TRACE_NET_DATABASE_URL env var via shell expansion")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--postgres-table", default=DEFAULT_INCIDENT_TABLE)
    parser.add_argument("--random-incident-count", type=int, default=1)
    parser.add_argument("--min-inserted-incidents", type=int, default=1)
    parser.add_argument("--actor-id", default="postgres_smoke")
    parser.add_argument("--quality", action="store_true", help="Exit nonzero if quality fails")
    args = parser.parse_args(argv)

    database_url = args.database_url.strip()
    if not database_url:
        import os
        database_url = os.environ.get("TRACE_NET_DATABASE_URL", "").strip()
    if not database_url:
        print("--database-url or TRACE_NET_DATABASE_URL is required")
        return 2

    report = run_postgres_smoke(
        database_url=database_url,
        output_dir=args.output_dir,
        postgres_table=args.postgres_table,
        random_incident_count=args.random_incident_count,
        min_inserted_incidents=args.min_inserted_incidents,
        actor_id=args.actor_id,
    )
    s = report["summary"]
    print("TRACE-Net synthetic incident Postgres smoke v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "storage_mode",
        "postgres_table",
        "before_count",
        "after_count",
        "inserted_incident_count",
        "created_incident_found_count",
        "unsafe_incident_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {artifact_paths(args.output_dir)['report']}")
    print(f" quality_path: {artifact_paths(args.output_dir)['quality']}")
    if args.quality and report["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
