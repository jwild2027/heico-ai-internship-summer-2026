"""TRACE-Net Synthetic Incident Console v1.

A small local/admin incident console for testing TRACE-Net IT alert flows.

The module is intentionally synthetic-only:
- it does not write to Qdrant, OpenSearch, or source files;
- it can store incidents in local JSONL or Postgres;
- it does not mutate source truth;
- it does not create answer-authoritative records;
- local JSON/JSONL artifacts remain available as snapshots/reports.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import random
import re
import sys
import time
import webbrowser
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

SCHEMA_VERSION = "trace_net_synthetic_incident_console_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/synthetic_incident_console")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8011
DEFAULT_STORAGE_MODE = "local"
LOCAL_STORAGE_MODE = "local"
POSTGRES_STORAGE_MODE = "postgres"
DEFAULT_INCIDENT_TABLE = "trace_net_synthetic_incident_events"

ALLOWED_SEVERITIES = {"critical", "warning", "review", "info"}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "review": 2, "info": 3}

INCIDENT_ORIGINS: dict[str, dict[str, str]] = {
    "source_ingest": {
        "label": "Source ingest",
        "default_severity": "warning",
        "message": "Synthetic source-ingest issue: a new source file needs trace validation.",
        "recommended_action": "Check source manifest, page mapping, and source trace before promotion.",
    },
    "ocr_text": {
        "label": "OCR text",
        "default_severity": "warning",
        "message": "Synthetic OCR issue: OCR quality may be weak or missing on a page.",
        "recommended_action": "Schedule OCR cleanup or region OCR retry through fishnet.",
    },
    "page_registry": {
        "label": "Page registry",
        "default_severity": "review",
        "message": "Synthetic page-registry issue: page route/trait classification needs review.",
        "recommended_action": "Inspect page traits, detected elements, and route recommendations.",
    },
    "table_extraction": {
        "label": "Table extraction",
        "default_severity": "warning",
        "message": "Synthetic table issue: normalized rows/cells need table repair review.",
        "recommended_action": "Review table rows/cells and compare part numbers against catalog/graph.",
    },
    "visual_diagram": {
        "label": "Visual / diagram",
        "default_severity": "review",
        "message": "Synthetic visual issue: callout or visual part candidate needs verification.",
        "recommended_action": "Verify callouts against OCR, table rows, catalog, graph, and source page.",
    },
    "graph_integrity": {
        "label": "Graph integrity",
        "default_severity": "critical",
        "message": "Synthetic graph issue: possible orphan edge or missing graph lineage.",
        "recommended_action": "Run graph quality checks and block writeback until orphan edges are resolved.",
    },
    "semantic_vector": {
        "label": "Semantic vector / Qdrant",
        "default_severity": "warning",
        "message": "Synthetic vector issue: embedding or Qdrant payload should be checked.",
        "recommended_action": "Verify vector dimension, payload safety flags, and collection counts.",
    },
    "keyword_search": {
        "label": "Keyword / OpenSearch",
        "default_severity": "warning",
        "message": "Synthetic keyword-search issue: OpenSearch index document needs validation.",
        "recommended_action": "Verify index documents are safe, traced, and not raw OCR/feedback/model output.",
    },
    "retrieval": {
        "label": "Retrieval",
        "default_severity": "warning",
        "message": "Synthetic retrieval issue: ranking or evidence grouping needs validation.",
        "recommended_action": "Run retrieval smoke/regression and inspect citation/trust groups.",
    },
    "answer_gate": {
        "label": "Answer gate",
        "default_severity": "critical",
        "message": "Synthetic answer-gate issue: final answer claim must be blocked until citations pass.",
        "recommended_action": "Check final answer gate, uncited claims, authority, and leak counters.",
    },
    "feedback_memory": {
        "label": "Feedback memory",
        "default_severity": "review",
        "message": "Synthetic feedback issue: feedback memory requires review before advisory use.",
        "recommended_action": "Sanitize feedback and confirm it remains advisory-only.",
    },
    "incremental_ops": {
        "label": "Incremental ops",
        "default_severity": "warning",
        "message": "Synthetic incremental issue: changed files need dependency-aware rerun planning.",
        "recommended_action": "Inspect manifest/orchestrator dirty pages and avoid full rescan.",
    },
    "llm_advisory": {
        "label": "LLM advisory",
        "default_severity": "warning",
        "message": "Synthetic LLM advisory issue: model output must remain non-authoritative.",
        "recommended_action": "Ensure LLM output is advisory and final gate controls user-facing claims.",
    },
    "security_leakage": {
        "label": "Security / leakage",
        "default_severity": "critical",
        "message": "Synthetic leakage issue: possible local path, raw byte, or prompt/debug leak.",
        "recommended_action": "Block publication and run snippet/leakage cleaners before exposure.",
    },
    "trust_authority": {
        "label": "Trust authority",
        "default_severity": "critical",
        "message": "Synthetic trust-authority issue: evidence authority must be checked.",
        "recommended_action": "Verify trust tier, authority, citation, and allowed-use fields.",
    },
    "community_graph": {
        "label": "Graph community",
        "default_severity": "review",
        "message": "Synthetic community issue: community hint must remain advisory-only.",
        "recommended_action": "Check community overlay and confirm community is not used as proof.",
    },
    "human_review": {
        "label": "Human review",
        "default_severity": "review",
        "message": "Synthetic human-review issue: triage card needs reviewer action.",
        "recommended_action": "Open review triage and record a safe reviewer decision.",
    },
}


RANDOM_INCIDENT_SCENARIOS: list[dict[str, str]] = [
    {
        "origin_category": "source_ingest",
        "severity": "warning",
        "message": "Random synthetic source ingest incident: new file arrived without a confirmed page mapping.",
        "target_type": "source_manifest",
        "target_id": "random_source_arrival",
        "incident_tag": "random_source_mapping",
    },
    {
        "origin_category": "ocr_text",
        "severity": "warning",
        "message": "Random synthetic OCR incident: page OCR confidence looks weak and should be retried.",
        "target_type": "ocr_page",
        "target_id": "random_ocr_page",
        "incident_tag": "random_ocr_retry",
    },
    {
        "origin_category": "table_extraction",
        "severity": "review",
        "message": "Random synthetic table incident: table row/cell extraction needs normalization review.",
        "target_type": "table_row",
        "target_id": "random_table_row",
        "incident_tag": "random_table_review",
    },
    {
        "origin_category": "visual_diagram",
        "severity": "review",
        "message": "Random synthetic visual incident: diagram callout candidates need catalog/graph verification.",
        "target_type": "visual_region",
        "target_id": "random_visual_region",
        "incident_tag": "random_visual_review",
    },
    {
        "origin_category": "graph_integrity",
        "severity": "critical",
        "message": "Random synthetic graph incident: possible orphan edge detected in graph writeback dry run.",
        "target_type": "graph_edge",
        "target_id": "random_graph_edge",
        "incident_tag": "random_graph_integrity",
    },
    {
        "origin_category": "semantic_vector",
        "severity": "warning",
        "message": "Random synthetic vector incident: Qdrant payload or embedding dimension should be checked.",
        "target_type": "qdrant_point",
        "target_id": "random_qdrant_point",
        "incident_tag": "random_vector_check",
    },
    {
        "origin_category": "retrieval",
        "severity": "warning",
        "message": "Random synthetic retrieval incident: top result changed and needs regression review.",
        "target_type": "retrieval_result",
        "target_id": "random_retrieval_group",
        "incident_tag": "random_retrieval_regression",
    },
    {
        "origin_category": "answer_gate",
        "severity": "critical",
        "message": "Random synthetic answer gate incident: final claim is missing citation and must be blocked.",
        "target_type": "final_claim",
        "target_id": "random_final_claim",
        "incident_tag": "random_answer_gate_block",
    },
    {
        "origin_category": "feedback_memory",
        "severity": "review",
        "message": "Random synthetic feedback incident: feedback memory needs sanitization before advisory use.",
        "target_type": "feedback_memory",
        "target_id": "random_feedback_record",
        "incident_tag": "random_feedback_review",
    },
    {
        "origin_category": "incremental_ops",
        "severity": "warning",
        "message": "Random synthetic incremental incident: changed pages need dependency-aware orchestration.",
        "target_type": "incremental_manifest",
        "target_id": "random_dirty_manifest",
        "incident_tag": "random_incremental_plan",
    },
    {
        "origin_category": "security_leakage",
        "severity": "critical",
        "message": "Random synthetic leakage incident: local path or raw byte leak needs blocking before publication.",
        "target_type": "clean_snippet",
        "target_id": "random_snippet",
        "incident_tag": "random_leakage_block",
    },
    {
        "origin_category": "trust_authority",
        "severity": "critical",
        "message": "Random synthetic trust incident: evidence authority must be checked before answer support.",
        "target_type": "trust_authority",
        "target_id": "random_trust_record",
        "incident_tag": "random_trust_gate",
    },
    {
        "origin_category": "community_graph",
        "severity": "review",
        "message": "Random synthetic community incident: community hint should remain advisory-only.",
        "target_type": "leiden_community",
        "target_id": "random_community",
        "incident_tag": "random_community_review",
    },
    {
        "origin_category": "human_review",
        "severity": "review",
        "message": "Random synthetic human-review incident: triage card needs reviewer action.",
        "target_type": "triage_card",
        "target_id": "random_triage_card",
        "incident_tag": "random_review_task",
    },
]

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"developer\s*message", re.I),
    re.compile(r"always\s+trust", re.I),
    re.compile(r"bypass\s+(the\s+)?gate", re.I),
]

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def postgres_schema_sql(table_name: str = DEFAULT_INCIDENT_TABLE) -> str:
    """Return the Postgres schema for server-side synthetic incident storage."""
    safe_table = re.sub(r"[^a-zA-Z0-9_]", "", table_name or DEFAULT_INCIDENT_TABLE)
    return f"""create table if not exists {safe_table} (
  incident_id text primary key,
  created_at timestamptz not null,
  updated_at timestamptz not null default now(),
  environment text not null default 'local',
  incident_source text not null default 'synthetic_console',
  synthetic_only boolean not null default true,
  origin_category text not null,
  origin_label text,
  severity text not null,
  status text not null default 'open',
  message text not null,
  recommended_action text,
  target_type text,
  target_id text,
  incident_tag text,
  randomly_generated boolean not null default false,
  random_template_id text,
  prompt_injection_flagged boolean not null default false,
  prompt_injection_reasons jsonb not null default '[]'::jsonb,
  affects_real_pipeline boolean not null default false,
  can_answer_directly boolean not null default false,
  can_prove_claims boolean not null default false,
  can_mutate_source_truth boolean not null default false,
  source_truth_mutation_allowed boolean not null default false,
  source_truth_mutations_performed integer not null default 0,
  raw_feedback_direct_to_llm boolean not null default false,
  retrieval_only_answer_allowed boolean not null default false,
  community_as_proof boolean not null default false,
  feedback_as_proof boolean not null default false,
  actor_id text,
  acknowledged_by text,
  acknowledged_at timestamptz,
  resolved_by text,
  resolved_at timestamptz,
  resolution_note text,
  payload jsonb not null default '{{}}'::jsonb
);

create index if not exists idx_{safe_table}_created_at on {safe_table} (created_at desc);
create index if not exists idx_{safe_table}_severity on {safe_table} (severity);
create index if not exists idx_{safe_table}_status on {safe_table} (status);
create index if not exists idx_{safe_table}_origin_category on {safe_table} (origin_category);
"""


def write_postgres_schema_file(output_dir: Path, table_name: str = DEFAULT_INCIDENT_TABLE) -> Path:
    path = output_dir / "trace_net_synthetic_incident_console_v1_postgres_schema.sql"
    ensure_dir(path.parent)
    path.write_text(postgres_schema_sql(table_name), encoding="utf-8")
    return path


def _require_psycopg():
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on user environment
        raise RuntimeError("psycopg is required for Postgres storage. Install/use your repo environment with psycopg.") from exc
    return psycopg


def init_postgres_storage(database_url: str, *, table_name: str = DEFAULT_INCIDENT_TABLE) -> None:
    if not database_url:
        raise ValueError("database_url is required for Postgres storage")
    psycopg = _require_psycopg()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(postgres_schema_sql(table_name))
        conn.commit()


def _postgres_row_from_incident(incident: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": incident.get("incident_id"),
        "created_at": incident.get("created_at") or utc_now(),
        "origin_category": incident.get("origin_category"),
        "origin_label": incident.get("origin_label"),
        "severity": incident.get("severity"),
        "message": incident.get("message"),
        "recommended_action": incident.get("recommended_action"),
        "target_type": incident.get("target_type"),
        "target_id": incident.get("target_id"),
        "incident_tag": incident.get("incident_tag"),
        "randomly_generated": bool(incident.get("randomly_generated")),
        "random_template_id": incident.get("random_template_id"),
        "prompt_injection_flagged": bool(incident.get("prompt_injection_flagged")),
        "prompt_injection_reasons": json.dumps(incident.get("prompt_injection_reasons") or []),
        "synthetic_only": bool(incident.get("synthetic_only", True)),
        "affects_real_pipeline": bool(incident.get("affects_real_pipeline")),
        "can_answer_directly": bool(incident.get("can_answer_directly")),
        "can_prove_claims": bool(incident.get("can_prove_claims")),
        "can_mutate_source_truth": bool(incident.get("can_mutate_source_truth")),
        "source_truth_mutation_allowed": bool(incident.get("source_truth_mutation_allowed")),
        "source_truth_mutations_performed": int(incident.get("source_truth_mutations_performed") or 0),
        "raw_feedback_direct_to_llm": bool(incident.get("raw_feedback_direct_to_llm")),
        "retrieval_only_answer_allowed": bool(incident.get("retrieval_only_answer_allowed")),
        "community_as_proof": bool(incident.get("community_as_proof")),
        "feedback_as_proof": bool(incident.get("feedback_as_proof")),
        "actor_id": incident.get("actor_id"),
        "payload": json.dumps(incident, sort_keys=True),
    }


def save_incident_postgres(
    database_url: str,
    incident: dict[str, Any],
    *,
    table_name: str = DEFAULT_INCIDENT_TABLE,
) -> dict[str, Any]:
    if not database_url:
        raise ValueError("database_url is required for Postgres storage")
    init_postgres_storage(database_url, table_name=table_name)
    row = _postgres_row_from_incident(incident)
    psycopg = _require_psycopg()
    safe_table = re.sub(r"[^a-zA-Z0-9_]", "", table_name or DEFAULT_INCIDENT_TABLE)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                insert into {safe_table} (
                  incident_id, created_at, origin_category, origin_label, severity, message,
                  recommended_action, target_type, target_id, incident_tag, randomly_generated,
                  random_template_id, prompt_injection_flagged, prompt_injection_reasons, synthetic_only,
                  affects_real_pipeline, can_answer_directly, can_prove_claims, can_mutate_source_truth,
                  source_truth_mutation_allowed, source_truth_mutations_performed, raw_feedback_direct_to_llm,
                  retrieval_only_answer_allowed, community_as_proof, feedback_as_proof, actor_id, payload
                ) values (
                  %(incident_id)s, %(created_at)s, %(origin_category)s, %(origin_label)s, %(severity)s, %(message)s,
                  %(recommended_action)s, %(target_type)s, %(target_id)s, %(incident_tag)s, %(randomly_generated)s,
                  %(random_template_id)s, %(prompt_injection_flagged)s, %(prompt_injection_reasons)s::jsonb, %(synthetic_only)s,
                  %(affects_real_pipeline)s, %(can_answer_directly)s, %(can_prove_claims)s, %(can_mutate_source_truth)s,
                  %(source_truth_mutation_allowed)s, %(source_truth_mutations_performed)s, %(raw_feedback_direct_to_llm)s,
                  %(retrieval_only_answer_allowed)s, %(community_as_proof)s, %(feedback_as_proof)s, %(actor_id)s, %(payload)s::jsonb
                )
                on conflict (incident_id) do update set
                  updated_at = now(),
                  severity = excluded.severity,
                  message = excluded.message,
                  recommended_action = excluded.recommended_action,
                  payload = excluded.payload
                """,
                row,
            )
        conn.commit()
    return incident


def load_incidents_postgres(database_url: str, *, table_name: str = DEFAULT_INCIDENT_TABLE) -> list[dict[str, Any]]:
    if not database_url:
        raise ValueError("database_url is required for Postgres storage")
    init_postgres_storage(database_url, table_name=table_name)
    psycopg = _require_psycopg()
    safe_table = re.sub(r"[^a-zA-Z0-9_]", "", table_name or DEFAULT_INCIDENT_TABLE)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"select payload from {safe_table} order by created_at asc, incident_id asc")
            rows = cur.fetchall()
    incidents: list[dict[str, Any]] = []
    for (payload,) in rows:
        incidents.append(json.loads(payload) if isinstance(payload, str) else dict(payload))
    return incidents


def clear_incidents_postgres(database_url: str, *, table_name: str = DEFAULT_INCIDENT_TABLE) -> None:
    if not database_url:
        raise ValueError("database_url is required for Postgres storage")
    init_postgres_storage(database_url, table_name=table_name)
    psycopg = _require_psycopg()
    safe_table = re.sub(r"[^a-zA-Z0-9_]", "", table_name or DEFAULT_INCIDENT_TABLE)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"delete from {safe_table}")
        conn.commit()


def sanitize_message(message: str) -> tuple[str, bool, list[str]]:
    text = (message or "").strip()
    flagged: list[str] = []
    for idx, pattern in enumerate(PROMPT_INJECTION_PATTERNS, start=1):
        if pattern.search(text):
            flagged.append(f"prompt_injection_pattern_{idx}")
    sanitized = text
    if flagged:
        sanitized = "[REDACTED: synthetic incident message contained instruction-manipulation language]"
    return sanitized[:1000], bool(flagged), flagged


def artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "report": output_dir / "trace_net_synthetic_incident_console_v1.json",
        "incidents": output_dir / "trace_net_synthetic_incidents_v1.jsonl",
        "alerts": output_dir / "trace_net_synthetic_alerts_v1.jsonl",
        "summary": output_dir / "trace_net_synthetic_incident_console_v1_summary.json",
        "quality": output_dir / "trace_net_synthetic_incident_console_v1_quality.json",
        "manifest": output_dir / "trace_net_synthetic_incident_console_v1_manifest.json",
        "html": output_dir / "trace_net_synthetic_incident_console_v1.html",
        "md": output_dir / "trace_net_synthetic_incident_console_v1.md",
    }


def make_synthetic_incident(
    origin_category: str,
    severity: str | None = None,
    message: str | None = None,
    target_type: str = "synthetic_trace_net_stage",
    target_id: str | None = None,
    actor_id: str = "local_admin",
    incident_tag: str | None = None,
    randomly_generated: bool = False,
    random_template_id: str | None = None,
) -> dict[str, Any]:
    if origin_category not in INCIDENT_ORIGINS:
        raise ValueError(f"unknown origin_category: {origin_category}")
    origin = INCIDENT_ORIGINS[origin_category]
    severity = (severity or origin["default_severity"]).lower().strip()
    if severity not in ALLOWED_SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(ALLOWED_SEVERITIES)}")
    sanitized_message, prompt_flagged, prompt_reasons = sanitize_message(message or origin["message"])
    seed = {
        "origin_category": origin_category,
        "severity": severity,
        "message": sanitized_message,
        "target_type": target_type,
        "target_id": target_id or origin_category,
        "created_at": utc_now(),
        "actor_id": actor_id,
    }
    incident_id = stable_id("syninc", seed)
    alert_id = stable_id("synalert", {"incident_id": incident_id, "severity": severity})
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "synthetic_incident",
        "incident_id": incident_id,
        "alert_id": alert_id,
        "created_at": seed["created_at"],
        "origin_category": origin_category,
        "origin_label": origin["label"],
        "severity": severity,
        "target_type": target_type,
        "target_id": seed["target_id"],
        "incident_tag": incident_tag or origin_category,
        "randomly_generated": randomly_generated,
        "random_template_id": random_template_id,
        "message": sanitized_message,
        "recommended_action": origin["recommended_action"],
        "prompt_injection_flagged": prompt_flagged,
        "prompt_injection_reasons": prompt_reasons,
        "synthetic_only": True,
        "affects_real_pipeline": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutations_performed": 0,
        "source_truth_mutation_allowed": False,
        "raw_feedback_direct_to_llm": False,
        "retrieval_only_answer_allowed": False,
        "community_as_proof": False,
        "feedback_as_proof": False,
        "writeback_mode": "local_synthetic_only",
        "actor_id": actor_id,
    }



def make_random_synthetic_incident(
    rng: random.Random | None = None,
    *,
    actor_id: str = "local_admin",
) -> dict[str, Any]:
    """Create one safe synthetic incident from a random scenario template."""
    chooser = rng or random.SystemRandom()
    scenario = dict(chooser.choice(RANDOM_INCIDENT_SCENARIOS))
    template_id = stable_id("syntpl", scenario)
    return make_synthetic_incident(
        origin_category=scenario["origin_category"],
        severity=scenario.get("severity"),
        message=scenario.get("message"),
        target_type=scenario.get("target_type", "synthetic_trace_net_stage"),
        target_id=scenario.get("target_id"),
        actor_id=actor_id,
        incident_tag=scenario.get("incident_tag"),
        randomly_generated=True,
        random_template_id=template_id,
    )

def load_incidents(output_dir: Path) -> list[dict[str, Any]]:
    return read_jsonl(artifact_paths(output_dir)["incidents"])


def load_incidents_for_storage(
    output_dir: Path,
    *,
    storage_mode: str = LOCAL_STORAGE_MODE,
    database_url: str | None = None,
    table_name: str = DEFAULT_INCIDENT_TABLE,
) -> list[dict[str, Any]]:
    if storage_mode == POSTGRES_STORAGE_MODE:
        return load_incidents_postgres(database_url or "", table_name=table_name)
    return load_incidents(output_dir)


def save_incident(output_dir: Path, incident: dict[str, Any]) -> dict[str, Any]:
    paths = artifact_paths(output_dir)
    ensure_dir(output_dir)
    incidents = load_incidents(output_dir)
    incidents.append(incident)
    incidents.sort(key=lambda item: (item.get("created_at", ""), item.get("incident_id", "")))
    write_jsonl(paths["incidents"], incidents)
    build_console_report(output_dir)
    return incident


def save_incident_for_storage(
    output_dir: Path,
    incident: dict[str, Any],
    *,
    storage_mode: str = LOCAL_STORAGE_MODE,
    database_url: str | None = None,
    table_name: str = DEFAULT_INCIDENT_TABLE,
) -> dict[str, Any]:
    if storage_mode == POSTGRES_STORAGE_MODE:
        save_incident_postgres(database_url or "", incident, table_name=table_name)
        build_console_report(output_dir, storage_mode=storage_mode, database_url=database_url, table_name=table_name)
        return incident
    return save_incident(output_dir, incident)


def clear_incidents(output_dir: Path) -> None:
    paths = artifact_paths(output_dir)
    ensure_dir(output_dir)
    for key in ["incidents", "alerts"]:
        paths[key].write_text("", encoding="utf-8")
    build_console_report(output_dir)


def clear_incidents_for_storage(
    output_dir: Path,
    *,
    storage_mode: str = LOCAL_STORAGE_MODE,
    database_url: str | None = None,
    table_name: str = DEFAULT_INCIDENT_TABLE,
) -> None:
    if storage_mode == POSTGRES_STORAGE_MODE:
        clear_incidents_postgres(database_url or "", table_name=table_name)
        build_console_report(output_dir, storage_mode=storage_mode, database_url=database_url, table_name=table_name)
        return
    clear_incidents(output_dir)


def summarize_incidents(incidents: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counts = Counter(i.get("severity") for i in incidents)
    origin_counts = Counter(i.get("origin_category") for i in incidents)
    prompt_injection_count = sum(1 for i in incidents if i.get("prompt_injection_flagged"))
    unsafe_incident_count = sum(
        1
        for i in incidents
        if i.get("can_answer_directly")
        or i.get("can_prove_claims")
        or i.get("can_mutate_source_truth")
        or i.get("source_truth_mutation_allowed")
        or i.get("raw_feedback_direct_to_llm")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if unsafe_incident_count == 0 else "FAIL",
        "incident_count": len(incidents),
        "alert_count": len(incidents),
        "severity_counts": dict(sorted(severity_counts.items())),
        "origin_counts": dict(sorted(origin_counts.items())),
        "critical_incident_count": severity_counts.get("critical", 0),
        "warning_incident_count": severity_counts.get("warning", 0),
        "review_incident_count": severity_counts.get("review", 0),
        "info_incident_count": severity_counts.get("info", 0),
        "prompt_injection_flagged_count": prompt_injection_count,
        "randomly_generated_incident_count": sum(1 for i in incidents if i.get("randomly_generated") is True),
        "random_template_count": len({i.get("random_template_id") for i in incidents if i.get("random_template_id")}),
        "unsafe_incident_count": unsafe_incident_count,
        "synthetic_only_count": sum(1 for i in incidents if i.get("synthetic_only") is True),
        "affects_real_pipeline_count": sum(1 for i in incidents if i.get("affects_real_pipeline") is True),
        "source_truth_mutation_allowed_count": sum(1 for i in incidents if i.get("source_truth_mutation_allowed") is True),
        "source_truth_mutations_performed": sum(int(i.get("source_truth_mutations_performed") or 0) for i in incidents),
        "raw_feedback_direct_to_llm_count": sum(1 for i in incidents if i.get("raw_feedback_direct_to_llm") is True),
        "incident_origin_category_count": len([k for k, v in origin_counts.items() if v > 0]),
        "available_origin_category_count": len(INCIDENT_ORIGINS),
    }


def quality_report(report: dict[str, Any], *, min_incidents: int = 0, max_unsafe_incidents: int = 0) -> dict[str, Any]:
    summary = report.get("summary", report)
    checks = {
        "incident_count_min": int(summary.get("incident_count", 0)) >= min_incidents,
        "unsafe_incident_count_within_limit": int(summary.get("unsafe_incident_count", 0)) <= max_unsafe_incidents,
        "source_truth_mutation_allowed_zero": int(summary.get("source_truth_mutation_allowed_count", 0)) == 0,
        "source_truth_mutations_performed_zero": int(summary.get("source_truth_mutations_performed", 0)) == 0,
        "raw_feedback_direct_to_llm_zero": int(summary.get("raw_feedback_direct_to_llm_count", 0)) == 0,
        "affects_real_pipeline_zero": int(summary.get("affects_real_pipeline_count", 0)) == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "checks": checks,
        "incident_count": int(summary.get("incident_count", 0)),
        "unsafe_incident_count": int(summary.get("unsafe_incident_count", 0)),
        "source_truth_mutation_allowed_count": int(summary.get("source_truth_mutation_allowed_count", 0)),
        "raw_feedback_direct_to_llm_count": int(summary.get("raw_feedback_direct_to_llm_count", 0)),
    }


def incident_to_alert(incident: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "synthetic_alert",
        "alert_id": incident["alert_id"],
        "incident_id": incident["incident_id"],
        "created_at": incident["created_at"],
        "severity": incident["severity"],
        "origin_category": incident["origin_category"],
        "origin_label": incident["origin_label"],
        "target_type": incident["target_type"],
        "target_id": incident["target_id"],
        "message": incident["message"],
        "recommended_action": incident["recommended_action"],
        "synthetic_only": True,
        "ack_status": "unacknowledged",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
    }


def build_console_report(
    output_dir: Path,
    *,
    storage_mode: str = LOCAL_STORAGE_MODE,
    database_url: str | None = None,
    table_name: str = DEFAULT_INCIDENT_TABLE,
) -> dict[str, Any]:
    paths = artifact_paths(output_dir)
    ensure_dir(output_dir)
    incidents = load_incidents_for_storage(output_dir, storage_mode=storage_mode, database_url=database_url, table_name=table_name)
    alerts = [incident_to_alert(i) for i in incidents]
    summary = summarize_incidents(incidents)
    quality = quality_report({"summary": summary})
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "SYNTHETIC_INCIDENT_CONSOLE_BUILT",
        "quality_status": quality["status"],
        "generated_at": utc_now(),
        "storage_mode": storage_mode,
        "postgres_storage_enabled": storage_mode == POSTGRES_STORAGE_MODE,
        "postgres_table": table_name if storage_mode == POSTGRES_STORAGE_MODE else None,
        "server_hint": {"host": DEFAULT_HOST, "port": DEFAULT_PORT},
        "docker_port_notes": {
            "reserved_ports_observed": [5432, 6333, 6334, 8000, 3000],
            "default_console_port": DEFAULT_PORT,
            "note": "The console defaults to 8011 to avoid Postgres, Qdrant, Chroma, and Open WebUI ports.",
        },
        "summary": {
            **summary,
            "storage_mode": storage_mode,
            "postgres_storage_enabled": storage_mode == POSTGRES_STORAGE_MODE,
            "postgres_table": table_name if storage_mode == POSTGRES_STORAGE_MODE else None,
        },
        "incident_origins": INCIDENT_ORIGINS,
        "incidents": incidents,
        "alerts": alerts,
        "safety_contract": {
            "synthetic_only": True,
            "postgres_incident_storage_only": storage_mode == POSTGRES_STORAGE_MODE,
            "no_postgres_source_truth_write": True,
            "no_qdrant_write": True,
            "no_opensearch_write": True,
            "no_source_truth_mutation": True,
            "no_answer_authority": True,
        },
    }
    write_json(paths["report"], report)
    write_json(paths["summary"], report["summary"])
    write_json(paths["quality"], quality)
    write_jsonl(paths["incidents"], incidents)
    write_jsonl(paths["alerts"], alerts)
    write_json(paths["manifest"], {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "artifact_paths": {k: str(v) for k, v in paths.items()},
        "quality_status": quality["status"],
    })
    paths["html"].write_text(render_console_html(report), encoding="utf-8")
    paths["md"].write_text(render_markdown_report(report), encoding="utf-8")
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRACE-Net Synthetic Incident Console v1",
        "",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "incident_count",
        "critical_incident_count",
        "warning_incident_count",
        "review_incident_count",
        "info_incident_count",
        "prompt_injection_flagged_count",
        "randomly_generated_incident_count",
        "unsafe_incident_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.extend(["", "## Recent alerts", ""])
    for alert in sorted(report["alerts"], key=lambda a: (SEVERITY_ORDER.get(a.get("severity"), 99), a.get("created_at", "")))[:50]:
        lines.append(f"- **{alert['severity'].upper()}** `{alert['origin_category']}`: {alert['message']}")
    return "\n".join(lines) + "\n"


def render_console_html(report: dict[str, Any]) -> str:
    origins = report["incident_origins"]
    origin_buttons = "\n".join(
        f'<button class="origin-btn" data-origin="{html.escape(origin)}" data-severity="{html.escape(meta["default_severity"])}">{html.escape(meta["label"])}</button>'
        for origin, meta in origins.items()
    )
    origin_options = "\n".join(
        f'<option value="{html.escape(origin)}">{html.escape(meta["label"])}</option>'
        for origin, meta in origins.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TRACE-Net Synthetic Incident Console</title>
  <style>
    :root {{ font-family: Inter, Segoe UI, Arial, sans-serif; color: #172033; background: #f5f7fb; }}
    body {{ margin: 0; }}
    header {{ background: #101828; color: white; padding: 24px 32px; }}
    header h1 {{ margin: 0 0 6px; font-size: 26px; }}
    header p {{ margin: 0; color: #d0d5dd; }}
    main {{ padding: 24px 32px 60px; max-width: 1440px; margin: 0 auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 22px; }}
    .metric {{ background: white; border: 1px solid #e4e7ec; border-radius: 14px; padding: 16px; box-shadow: 0 1px 2px #0000000d; }}
    .metric .label {{ color: #667085; font-size: 13px; }}
    .metric .value {{ font-size: 28px; font-weight: 800; margin-top: 6px; }}
    .panel {{ background: white; border: 1px solid #e4e7ec; border-radius: 14px; padding: 18px; margin-bottom: 20px; box-shadow: 0 1px 2px #0000000d; }}
    .panel h2 {{ margin: 0 0 14px; font-size: 18px; }}
    .buttons {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    button {{ cursor: pointer; border: 0; border-radius: 10px; padding: 10px 12px; font-weight: 700; }}
    .origin-btn {{ background: #e8f0ff; color: #1d4ed8; }}
    .origin-btn:hover {{ background: #dbeafe; }}
    .danger {{ background: #fee4e2; color: #b42318; }}
    .secondary {{ background: #f2f4f7; color: #344054; }}
    .form-row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 10px; }}
    input, select, textarea {{ width: 100%; box-sizing: border-box; border: 1px solid #d0d5dd; border-radius: 10px; padding: 10px; font: inherit; }}
    textarea {{ min-height: 80px; resize: vertical; }}
    .alerts {{ display: grid; gap: 10px; }}
    .alert {{ border: 1px solid #e4e7ec; border-left-width: 8px; border-radius: 12px; padding: 14px; background: white; }}
    .alert.critical {{ border-left-color: #d92d20; }}
    .alert.warning {{ border-left-color: #f79009; }}
    .alert.review {{ border-left-color: #7a5af8; }}
    .alert.info {{ border-left-color: #2e90fa; }}
    .alert .top {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; }}
    .badge {{ display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    .badge.critical {{ background: #fee4e2; color: #b42318; }}
    .badge.warning {{ background: #fef0c7; color: #b54708; }}
    .badge.review {{ background: #ebe9fe; color: #5925dc; }}
    .badge.info {{ background: #d1e9ff; color: #175cd3; }}
    .muted {{ color: #667085; font-size: 13px; }}
    .safety {{ color: #027a48; font-weight: 700; }}
    @media (max-width: 900px) {{ .grid, .form-row {{ grid-template-columns: 1fr; }} main {{ padding: 18px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>TRACE-Net Synthetic Incident Console</h1>
    <p>Local synthetic alert testing. No Postgres, Qdrant, OpenSearch, or source-truth writes.</p>
  </header>
  <main>
    <section class="grid" id="metrics"></section>
    <section class="panel">
      <h2>Create synthetic incident</h2>
      <p class="muted">Buttons create fake incidents for IT alert testing only. They do not affect the real TRACE-Net pipeline.</p>
      <div style="margin-bottom:12px; display:flex; gap:8px; flex-wrap:wrap;">
        <button id="createRandom" class="danger">Create random incident</button>
        <span class="muted" style="align-self:center;">Random incidents use safe synthetic templates across TRACE-Net issue origins.</span>
      </div>
      <div class="buttons">{origin_buttons}</div>
    </section>
    <section class="panel">
      <h2>Custom synthetic incident</h2>
      <div class="form-row">
        <select id="origin">{origin_options}</select>
        <select id="severity"><option>critical</option><option>warning</option><option selected>review</option><option>info</option></select>
        <input id="target" placeholder="target id, optional" />
      </div>
      <textarea id="message" placeholder="Short incident message"></textarea>
      <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
        <button id="createCustom" class="origin-btn">Create custom incident</button>
        <button id="refresh" class="secondary">Refresh</button>
        <button id="clear" class="danger">Clear synthetic incidents</button>
      </div>
    </section>
    <section class="panel">
      <h2>Organized alerts</h2>
      <div id="alerts" class="alerts"></div>
    </section>
  </main>
<script>
async function api(path, options={{}}) {{
  const response = await fetch(path, {{headers: {{'Content-Type': 'application/json'}}, ...options}});
  if (!response.ok) throw new Error(await response.text());
  return await response.json();
}}
function metric(label, value) {{ return `<div class="metric"><div class="label">${{label}}</div><div class="value">${{value}}</div></div>`; }}
function render(data) {{
  const s = data.summary || {{}};
  document.getElementById('metrics').innerHTML = [
    metric('Incidents', s.incident_count || 0),
    metric('Critical', s.critical_incident_count || 0),
    metric('Warnings', s.warning_incident_count || 0),
    metric('Review', s.review_incident_count || 0),
  ].join('');
  const alerts = data.alerts || [];
  if (!alerts.length) {{
    document.getElementById('alerts').innerHTML = '<p class="muted">No synthetic alerts yet.</p>';
    return;
  }}
  const ordered = [...alerts].sort((a,b) => ({{critical:0, warning:1, review:2, info:3}}[a.severity] ?? 9) - ({{critical:0, warning:1, review:2, info:3}}[b.severity] ?? 9));
  document.getElementById('alerts').innerHTML = ordered.map(a => `
    <article class="alert ${{a.severity}}">
      <div class="top"><span class="badge ${{a.severity}}">${{a.severity}}</span><span class="muted">${{a.created_at}}</span></div>
      <h3>${{a.origin_label || a.origin_category}}</h3>
      <p>${{a.message}}</p>
      <p><strong>Target:</strong> ${{a.target_type}} / ${{a.target_id}}</p>
      <p><strong>Action:</strong> ${{a.recommended_action}}</p>
      <p class="safety">Synthetic only. Cannot answer, prove claims, or mutate source truth.</p>
    </article>`).join('');
}}
async function refresh() {{ render(await api('/api/incidents')); }}
async function createIncident(origin, severity, message, target) {{
  await api('/api/incidents', {{method:'POST', body: JSON.stringify({{origin_category: origin, severity, message, target_id: target}})}});
  await refresh();
}}
document.querySelectorAll('.origin-btn[data-origin]').forEach(btn => btn.addEventListener('click', () => createIncident(btn.dataset.origin, btn.dataset.severity)));
document.getElementById('createRandom').addEventListener('click', async () => {{ await api('/api/incidents/random', {{method:'POST'}}); await refresh(); }});
document.getElementById('createCustom').addEventListener('click', () => createIncident(
  document.getElementById('origin').value,
  document.getElementById('severity').value,
  document.getElementById('message').value,
  document.getElementById('target').value
));
document.getElementById('refresh').addEventListener('click', refresh);
document.getElementById('clear').addEventListener('click', async () => {{ await api('/api/incidents/clear', {{method:'POST'}}); await refresh(); }});
refresh().catch(err => {{ document.getElementById('alerts').innerHTML = `<pre>${{err}}</pre>`; }});
</script>
</body>
</html>"""


class IncidentConsoleHandler(BaseHTTPRequestHandler):
    output_dir: Path = DEFAULT_OUTPUT_DIR
    storage_mode: str = LOCAL_STORAGE_MODE
    database_url: str | None = None
    table_name: str = DEFAULT_INCIDENT_TABLE

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_text: str, status: int = 200) -> None:
        body = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            report = build_console_report(self.output_dir)
            self._send_html(render_console_html(report))
            return
        if parsed.path == "/api/health":
            self._send_json({"status": "ok", "schema_version": SCHEMA_VERSION, "output_dir": str(self.output_dir), "storage_mode": self.storage_mode, "postgres_table": self.table_name if self.storage_mode == POSTGRES_STORAGE_MODE else None})
            return
        if parsed.path == "/api/incidents":
            self._send_json(build_console_report(self.output_dir, storage_mode=self.storage_mode, database_url=self.database_url, table_name=self.table_name))
            return
        if parsed.path == "/api/simulate/random":
            incident = save_incident_for_storage(self.output_dir, make_random_synthetic_incident(), storage_mode=self.storage_mode, database_url=self.database_url, table_name=self.table_name)
            self._send_json({"status": "recorded", "incident": incident})
            return
        if parsed.path.startswith("/api/simulate/"):
            origin = parsed.path.rsplit("/", 1)[-1]
            try:
                incident = save_incident_for_storage(self.output_dir, make_synthetic_incident(origin), storage_mode=self.storage_mode, database_url=self.database_url, table_name=self.table_name)
            except Exception as exc:  # pragma: no cover - HTTP boundary
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"status": "recorded", "incident": incident})
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            body = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            body = {}
        if parsed.path == "/api/incidents/random":
            try:
                incident = make_random_synthetic_incident(actor_id=body.get("actor_id", "local_admin"))
                save_incident_for_storage(self.output_dir, incident, storage_mode=self.storage_mode, database_url=self.database_url, table_name=self.table_name)
            except Exception as exc:  # pragma: no cover - HTTP boundary
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"status": "recorded", "incident": incident})
            return
        if parsed.path == "/api/incidents":
            try:
                incident = make_synthetic_incident(
                    origin_category=body.get("origin_category", "source_ingest"),
                    severity=body.get("severity"),
                    message=body.get("message"),
                    target_type=body.get("target_type", "synthetic_trace_net_stage"),
                    target_id=body.get("target_id"),
                    actor_id=body.get("actor_id", "local_admin"),
                    incident_tag=body.get("incident_tag"),
                )
                save_incident_for_storage(self.output_dir, incident, storage_mode=self.storage_mode, database_url=self.database_url, table_name=self.table_name)
            except Exception as exc:  # pragma: no cover - HTTP boundary
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"status": "recorded", "incident": incident})
            return
        if parsed.path == "/api/incidents/clear":
            clear_incidents_for_storage(self.output_dir, storage_mode=self.storage_mode, database_url=self.database_url, table_name=self.table_name)
            self._send_json({"status": "cleared", "storage_mode": self.storage_mode})
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("TRACE-Net incident console: " + fmt % args + "\n")


def run_server(
    host: str,
    port: int,
    output_dir: Path,
    open_browser: bool = False,
    *,
    storage_mode: str = LOCAL_STORAGE_MODE,
    database_url: str | None = None,
    table_name: str = DEFAULT_INCIDENT_TABLE,
) -> None:
    ensure_dir(output_dir)
    if storage_mode == POSTGRES_STORAGE_MODE:
        init_postgres_storage(database_url or "", table_name=table_name)
        write_postgres_schema_file(output_dir, table_name)
    build_console_report(output_dir, storage_mode=storage_mode, database_url=database_url, table_name=table_name)
    handler_cls = type("BoundIncidentConsoleHandler", (IncidentConsoleHandler,), {"output_dir": output_dir, "storage_mode": storage_mode, "database_url": database_url, "table_name": table_name})
    server = ThreadingHTTPServer((host, port), handler_cls)
    url = f"http://{host}:{port}/"
    print("TRACE-Net synthetic incident console v1")
    print(" Status: SERVER_RUNNING")
    print(f" url: {url}")
    print(f" output_dir: {output_dir}")
    print(f" storage_mode: {storage_mode}")
    if storage_mode == POSTGRES_STORAGE_MODE:
        print(f" postgres_table: {table_name}")
    print(" safety: synthetic only; no vector/source/graph-truth writes")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("\nTRACE-Net synthetic incident console stopped")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net synthetic incident console v1")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--seed-samples", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--storage-mode", choices=[LOCAL_STORAGE_MODE, POSTGRES_STORAGE_MODE], default=DEFAULT_STORAGE_MODE)
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL"))
    parser.add_argument("--postgres-table", default=DEFAULT_INCIDENT_TABLE)
    parser.add_argument("--init-postgres", action="store_true")
    args = parser.parse_args(argv)

    ensure_dir(args.output_dir)
    if args.storage_mode == POSTGRES_STORAGE_MODE or args.init_postgres:
        init_postgres_storage(args.database_url or "", table_name=args.postgres_table)
        schema_path = write_postgres_schema_file(args.output_dir, args.postgres_table)
        if args.init_postgres and args.build_only and not args.seed_samples and not args.clear:
            report = build_console_report(args.output_dir, storage_mode=args.storage_mode, database_url=args.database_url, table_name=args.postgres_table)
            print("TRACE-Net synthetic incident console v1 Postgres schema")
            print(" Status: POSTGRES_SCHEMA_READY")
            print(f" storage_mode: {args.storage_mode}")
            print(f" postgres_table: {args.postgres_table}")
            print(f" schema_path: {schema_path}")
            print(f" report_path: {artifact_paths(args.output_dir)['report']}")
            return 0 if report["quality_status"] == "PASS" else 1
    if args.clear:
        clear_incidents_for_storage(args.output_dir, storage_mode=args.storage_mode, database_url=args.database_url, table_name=args.postgres_table)
    if args.seed_samples:
        for origin in ["source_ingest", "visual_diagram", "answer_gate", "feedback_memory", "security_leakage"]:
            save_incident_for_storage(args.output_dir, make_synthetic_incident(origin), storage_mode=args.storage_mode, database_url=args.database_url, table_name=args.postgres_table)
    report = build_console_report(args.output_dir, storage_mode=args.storage_mode, database_url=args.database_url, table_name=args.postgres_table)
    if args.build_only:
        print("TRACE-Net synthetic incident console v1")
        print(" Status: CONSOLE_ARTIFACTS_BUILT")
        print(f" Quality status: {report['quality_status']}")
        print(f" incident_count: {report['summary']['incident_count']}")
        print(f" storage_mode: {args.storage_mode}")
        if args.storage_mode == POSTGRES_STORAGE_MODE:
            print(f" postgres_table: {args.postgres_table}")
        print(f" html_path: {artifact_paths(args.output_dir)['html']}")
        print(f" report_path: {artifact_paths(args.output_dir)['report']}")
        return 0 if report["quality_status"] == "PASS" else 1
    run_server(args.host, args.port, args.output_dir, args.open_browser, storage_mode=args.storage_mode, database_url=args.database_url, table_name=args.postgres_table)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
