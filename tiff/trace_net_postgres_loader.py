"""TRACE-Net PostgreSQL loader v1.

This module imports local TRACE-Net development artifacts into a local
PostgreSQL database for testing before the production PostgreSQL/OpenSearch/
Qdrant stack is ready.

Important design rule: large binary files stay on disk. PostgreSQL stores
paths, OCR text, graph metadata, evidence records, candidate chunks, citations,
feedback, and quality/run summaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VERSION = "trace_net_postgres_loader_v1"
DEFAULT_OCR_EXPORT_DIR = Path("local_data/ocr/full_509_psm3")
DEFAULT_ORGANIZATION_DIR = Path("local_data/organization")
DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/postgres")

SCHEMA_VERSION = "trace_net_postgres_schema_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_id(*parts: Any, prefix: str = "id") -> str:
    text = "|".join(str(p) for p in parts if p not in (None, ""))
    digest = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, Mapping):
                rows.append(dict(obj))
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")


def _as_list(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [dict(x) for x in obj if isinstance(x, Mapping)]
    if isinstance(obj, Mapping):
        for key in ("pages", "records", "items", "nodes", "edges", "data"):
            value = obj.get(key)
            if isinstance(value, list):
                return [dict(x) for x in value if isinstance(x, Mapping)]
    return []


def _first(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return default


def _rel_or_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _read_text(path_value: Any, max_chars: int | None = None) -> str:
    if path_value in (None, ""):
        return ""
    path = Path(str(path_value))
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return text[:max_chars] if max_chars is not None else text


def _count_words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def _count_lines(text: str) -> int:
    return len([line for line in (text or "").splitlines() if line.strip()])


@dataclass(frozen=True)
class PostgresLoaderPaths:
    ocr_export_dir: Path = DEFAULT_OCR_EXPORT_DIR
    organization_dir: Path = DEFAULT_ORGANIZATION_DIR
    trace_net_dir: Path = DEFAULT_TRACE_NET_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    ocr_depth_audit_path: Path | None = None
    source_zip_path: Path | None = None

    @property
    def page_index(self) -> Path:
        return self.ocr_export_dir / "page_index.json"

    @property
    def ocr_report(self) -> Path:
        return self.ocr_export_dir / "reports" / "ocr_pilot_report.json"

    @property
    def ocr_depth_audit(self) -> Path | None:
        if self.ocr_depth_audit_path:
            return self.ocr_depth_audit_path
        candidate = self.ocr_export_dir.parent / f"{self.ocr_export_dir.name}_depth_audit.json"
        return candidate if candidate.exists() else None

    @property
    def load_summary(self) -> Path:
        return self.output_dir / "trace_net_postgres_load_summary.json"

    @property
    def load_manifest(self) -> Path:
        return self.output_dir / "trace_net_postgres_load_manifest.json"

    @property
    def init_summary(self) -> Path:
        return self.output_dir / "trace_net_postgres_init_summary.json"

    @property
    def ddl_path(self) -> Path:
        return self.output_dir / "trace_net_postgres_schema.sql"


# ---------------------------------------------------------------------------
# PostgreSQL connector
# ---------------------------------------------------------------------------


def _import_psycopg():
    try:
        import psycopg  # type: ignore
        return "psycopg3", psycopg
    except Exception:
        pass
    try:
        import psycopg2  # type: ignore
        return "psycopg2", psycopg2
    except Exception as exc:
        raise RuntimeError(
            "PostgreSQL loader requires psycopg. Install with: pip install 'psycopg[binary]' "
            "or pip install psycopg2-binary"
        ) from exc


def connect(database_url: str):
    _kind, module = _import_psycopg()
    return module.connect(database_url)


def _json_param(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def schema_sql() -> str:
    return r'''
create table if not exists trace_net_schema_version (
  schema_version text primary key,
  created_at timestamptz not null default now()
);

create table if not exists trace_net_load_runs (
  load_id text primary key,
  version text not null,
  source_zip_path text,
  ocr_export_dir text,
  organization_dir text,
  trace_net_dir text,
  summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists source_packages (
  source_package_id text primary key,
  source_zip_path text,
  page_count integer,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists documents (
  document_id text primary key,
  source_package_id text,
  title text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists pages (
  page_id text primary key,
  document_id text,
  page_number integer,
  page_label text,
  ata_code text,
  source_url text,
  tiff_path text,
  ocr_path text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists ocr_records (
  page_id text primary key references pages(page_id) on delete cascade,
  ocr_path text,
  status text,
  classification text,
  text text,
  chars integer,
  lines integer,
  words integer,
  part_like_count integer,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists graph_nodes (
  node_id text primary key,
  node_type text,
  label text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists graph_edges (
  edge_id text primary key,
  source_id text,
  target_id text,
  edge_type text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists evidence_consensus_records (
  record_id text primary key,
  page_id text,
  evidence_layer text,
  trust_tier text,
  rag_action text,
  repair_action text,
  usable_confidence numeric,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists stage5_decision_records (
  record_id text primary key,
  page_id text,
  evidence_layer text,
  selected_trust_tier text,
  selected_rag_action text,
  policy_controlled boolean,
  usable_confidence numeric,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists rag_eligibility_records (
  record_id text primary key,
  page_id text,
  rag_bucket text,
  rag_action text,
  trust_tier text,
  evidence_layer text,
  safe_for_rag boolean,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists rag_candidate_chunks (
  candidate_id text primary key,
  page_id text,
  candidate_type text,
  rag_bucket text,
  evidence_layer text,
  trust_tier text,
  usable_confidence numeric,
  text text,
  source_url text,
  tiff_path text,
  ocr_path text,
  safe_for_rag boolean,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists source_citations (
  citation_id text primary key,
  candidate_id text,
  page_id text,
  citation_text text,
  source_url text,
  tiff_path text,
  ocr_path text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists ask_runs (
  ask_run_id text primary key,
  query text,
  query_fingerprint text,
  feedback_mode text,
  answer_page_records integer,
  answer_evidence_records integer,
  unsafe_answer_groups integer,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists feedback_events (
  feedback_id text primary key,
  ask_run_id text,
  query_fingerprint text,
  rating text,
  reason_codes jsonb not null default '[]'::jsonb,
  affected_page_ids jsonb not null default '[]'::jsonb,
  expected_page_ids jsonb not null default '[]'::jsonb,
  context_status text,
  policy_signal_eligible boolean,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists feedback_policy_signals (
  signal_id text primary key,
  feedback_id text,
  query_fingerprint text,
  page_id text,
  signal_type text,
  weight numeric,
  reason text,
  context_status text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists quality_runs (
  quality_id text primary key,
  stage text,
  status text,
  summary jsonb not null default '{}'::jsonb,
  source_path text,
  created_at timestamptz not null default now()
);

create index if not exists idx_pages_document on pages(document_id);
create index if not exists idx_pages_source_url on pages(source_url);
create index if not exists idx_ocr_classification on ocr_records(classification);
create index if not exists idx_rag_candidates_page on rag_candidate_chunks(page_id);
create index if not exists idx_rag_candidates_bucket on rag_candidate_chunks(rag_bucket);
create index if not exists idx_rag_candidates_safe on rag_candidate_chunks(safe_for_rag);
create index if not exists idx_feedback_query on feedback_events(query_fingerprint);
create index if not exists idx_feedback_signals_query on feedback_policy_signals(query_fingerprint);
'''.strip() + "\n"


def init_schema(database_url: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ddl = schema_sql()
    ddl_path = output_dir / "trace_net_postgres_schema.sql"
    ddl_path.write_text(ddl, encoding="utf-8")
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            cur.execute(
                "insert into trace_net_schema_version(schema_version) values (%s) "
                "on conflict(schema_version) do nothing",
                (SCHEMA_VERSION,),
            )
        conn.commit()
    summary = {
        "status": "OK",
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc_now(),
        "ddl_path": str(ddl_path),
    }
    _write_json(output_dir / "trace_net_postgres_init_summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# Artifact collection
# ---------------------------------------------------------------------------


def _normalize_page_rows(page_index: Any) -> list[dict[str, Any]]:
    rows = _as_list(page_index)
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        page_id = str(_first(row, "page_id", "id", "node_id", default=f"page_{idx:06d}"))
        label = _first(row, "page_label", "label", "page", default=str(idx))
        try:
            page_num = int(str(label))
        except Exception:
            page_num = idx
        out.append({
            "page_id": page_id,
            "document_id": str(_first(row, "document_id", "doc_id", default="t_p_120_1176")),
            "page_number": page_num,
            "page_label": str(label) if label not in (None, "") else str(idx),
            "ata_code": _rel_or_str(_first(row, "ata_code", "ata")),
            "source_url": _rel_or_str(_first(row, "source_url", "url", "rescarta_url")),
            "tiff_path": _rel_or_str(_first(row, "source_image_path", "tiff_path", "image_path", "source_tiff_path", "tiff")),
            "ocr_path": _rel_or_str(_first(row, "ocr_text_path", "ocr_path", "ocr", "ocr_file", "ocr_file_path")),
            "payload": row,
        })
    return out


def _ocr_audit_by_page(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    obj = _read_json(path, {})
    rows = _as_list(obj)
    by: dict[str, dict[str, Any]] = {}
    for row in rows:
        page_id = str(_first(row, "page_id", "page", "id", default=""))
        if page_id:
            by[page_id] = row
    return by


def collect_ocr_records(paths: PostgresLoaderPaths) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    page_index = _read_json(paths.page_index, {})
    pages = _normalize_page_rows(page_index)
    audit = _ocr_audit_by_page(paths.ocr_depth_audit)
    ocr_records: list[dict[str, Any]] = []
    for page in pages:
        page_id = page["page_id"]
        ocr_path = page.get("ocr_path")
        text = _read_text(ocr_path)
        audit_row = audit.get(page_id, {})
        classification = _first(audit_row, "classification", "ocr_depth_classification", "status") or _first(page.get("payload", {}), "ocr_depth_classification")
        chars = int(_first(audit_row, "visible_chars", "chars", default=len(text)) or 0)
        lines = int(_first(audit_row, "line_count", "lines", default=_count_lines(text)) or 0)
        words = int(_first(audit_row, "word_count", "words", default=_count_words(text)) or 0)
        parts = int(_first(audit_row, "part_number_hits", "part_like_count", "parts", default=0) or 0)
        if not chars and text:
            chars = len(text)
        if not lines and text:
            lines = _count_lines(text)
        if not words and text:
            words = _count_words(text)
        ocr_records.append({
            "page_id": page_id,
            "ocr_path": ocr_path,
            "status": _first(page.get("payload", {}), "ocr_pilot_status", default="unknown"),
            "classification": classification or _first(page.get("payload", {}), "ocr_depth_classification", default="unknown"),
            "text": text,
            "chars": chars,
            "lines": lines,
            "words": words,
            "part_like_count": parts,
            "payload": {"page_index": page.get("payload", {}), "ocr_audit": audit_row},
        })
    return pages, ocr_records


def _iter_json_files(root: Path, suffix: str) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob(f"*{suffix}"))


def collect_graph_records(organization_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    for path in _iter_json_files(organization_dir, "graph_nodes.json"):
        for row in _as_list(_read_json(path, [])):
            node_id = str(_first(row, "node_id", "id", "key", default=_stable_id(path, row, prefix="node")))
            nodes[node_id] = {
                "node_id": node_id,
                "node_type": _rel_or_str(_first(row, "node_type", "type", "kind")),
                "label": _rel_or_str(_first(row, "label", "name", "title", default=node_id)),
                "payload": {"source_path": str(path), **row},
            }
    for path in _iter_json_files(organization_dir, "graph_edges.json"):
        for row in _as_list(_read_json(path, [])):
            source_id = _rel_or_str(_first(row, "source_id", "source", "from", "src"))
            target_id = _rel_or_str(_first(row, "target_id", "target", "to", "dst"))
            edge_type = _rel_or_str(_first(row, "edge_type", "type", "relation", "label"))
            edge_id = str(_first(row, "edge_id", "id", default=_stable_id(source_id, target_id, edge_type, row, prefix="edge")))
            edges[edge_id] = {
                "edge_id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "edge_type": edge_type,
                "payload": {"source_path": str(path), **row},
            }
    return list(nodes.values()), list(edges.values())


def collect_jsonl(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def _record_id(row: Mapping[str, Any], prefix: str, *names: str) -> str:
    val = _first(row, *names)
    if val not in (None, ""):
        return str(val)
    page_id = _first(row, "page_id", "page")
    layer = _first(row, "evidence_layer", "layer", "record_layer")
    candidate = _first(row, "candidate_id", "id")
    return _stable_id(page_id, layer, candidate, row, prefix=prefix)


def collect_payloads(paths: PostgresLoaderPaths) -> dict[str, Any]:
    pages, ocr_records = collect_ocr_records(paths)
    graph_nodes, graph_edges = collect_graph_records(paths.organization_dir)
    trace = paths.trace_net_dir
    payloads = {
        "pages": pages,
        "ocr_records": ocr_records,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "evidence_consensus_records": collect_jsonl(trace / "evidence_consensus" / "evidence_consensus_records.jsonl"),
        "stage5_decision_records": collect_jsonl(trace / "confidence" / "stage5_control" / "trace_lc_stage5_policy_control_records.jsonl"),
        "rag_eligibility_records": collect_jsonl(trace / "rag_eligibility" / "rag_eligibility_records.jsonl"),
        "rag_candidate_chunks": collect_jsonl(trace / "rag_candidates" / "rag_candidate_chunks.jsonl"),
        "source_citations": collect_jsonl(trace / "citations" / "trace_net_source_citations.jsonl"),
        "ask_runs": [_read_json(trace / "ask" / "trace_net_ask_summary.json", {})],
        "feedback_events": collect_jsonl(trace / "feedback" / "feedback_events.jsonl"),
        "feedback_policy_signals": collect_jsonl(trace / "feedback" / "feedback_policy_signals.jsonl"),
        "quality_runs": collect_quality_runs(paths.organization_dir),
    }
    payloads["ask_runs"] = [x for x in payloads["ask_runs"] if isinstance(x, Mapping) and x]
    return payloads


def collect_quality_runs(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*quality.json")):
        data = _read_json(path, {})
        if not isinstance(data, Mapping):
            continue
        stage = path.stem.replace("_quality", "")
        rows.append({
            "quality_id": _stable_id(str(path), prefix="quality"),
            "stage": stage,
            "status": str(_first(data, "status", "Status", default=data.get("quality_status", "unknown"))),
            "summary": data,
            "source_path": str(path),
        })
    return rows


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------


def _execute_many(conn, sql: str, rows: Sequence[Sequence[Any]]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).lower() in {"1", "true", "yes", "ok"}


def load_payloads(database_url: str, paths: PostgresLoaderPaths, *, upsert: bool = True) -> dict[str, Any]:
    payloads = collect_payloads(paths)
    load_id = _stable_id(paths.ocr_export_dir, paths.trace_net_dir, _utc_now(), prefix="load")
    counts: dict[str, int] = {k: len(v) if isinstance(v, list) else 0 for k, v in payloads.items()}

    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql())
            cur.execute("insert into trace_net_schema_version(schema_version) values (%s) on conflict(schema_version) do nothing", (SCHEMA_VERSION,))

        source_package_id = "source_package:default"
        if paths.source_zip_path:
            source_package_id = _stable_id(paths.source_zip_path, prefix="source_package")
        _execute_many(conn,
            "insert into source_packages(source_package_id, source_zip_path, page_count, payload) values (%s,%s,%s,%s::jsonb) "
            "on conflict(source_package_id) do update set source_zip_path=excluded.source_zip_path, page_count=excluded.page_count, payload=excluded.payload",
            [(source_package_id, str(paths.source_zip_path) if paths.source_zip_path else None, len(payloads["pages"]), _json_param({"ocr_export_dir": str(paths.ocr_export_dir)}))],
        )
        doc_ids = sorted({str(p.get("document_id") or "t_p_120_1176") for p in payloads["pages"]}) or ["t_p_120_1176"]
        _execute_many(conn,
            "insert into documents(document_id, source_package_id, title, payload) values (%s,%s,%s,%s::jsonb) "
            "on conflict(document_id) do update set source_package_id=excluded.source_package_id, title=excluded.title, payload=excluded.payload",
            [(doc_id, source_package_id, doc_id, _json_param({"source": "trace_net_postgres_loader"})) for doc_id in doc_ids],
        )
        _execute_many(conn,
            "insert into pages(page_id, document_id, page_number, page_label, ata_code, source_url, tiff_path, ocr_path, payload, updated_at) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(page_id) do update set document_id=excluded.document_id, page_number=excluded.page_number, page_label=excluded.page_label, ata_code=excluded.ata_code, source_url=excluded.source_url, tiff_path=excluded.tiff_path, ocr_path=excluded.ocr_path, payload=excluded.payload, updated_at=now()",
            [(p["page_id"], p.get("document_id"), p.get("page_number"), p.get("page_label"), p.get("ata_code"), p.get("source_url"), p.get("tiff_path"), p.get("ocr_path"), _json_param(p.get("payload", {}))) for p in payloads["pages"]],
        )
        _execute_many(conn,
            "insert into ocr_records(page_id, ocr_path, status, classification, text, chars, lines, words, part_like_count, payload, updated_at) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(page_id) do update set ocr_path=excluded.ocr_path, status=excluded.status, classification=excluded.classification, text=excluded.text, chars=excluded.chars, lines=excluded.lines, words=excluded.words, part_like_count=excluded.part_like_count, payload=excluded.payload, updated_at=now()",
            [(r["page_id"], r.get("ocr_path"), r.get("status"), r.get("classification"), r.get("text"), r.get("chars"), r.get("lines"), r.get("words"), r.get("part_like_count"), _json_param(r.get("payload", {}))) for r in payloads["ocr_records"]],
        )
        _execute_many(conn,
            "insert into graph_nodes(node_id, node_type, label, payload, updated_at) values (%s,%s,%s,%s::jsonb, now()) "
            "on conflict(node_id) do update set node_type=excluded.node_type, label=excluded.label, payload=excluded.payload, updated_at=now()",
            [(r["node_id"], r.get("node_type"), r.get("label"), _json_param(r.get("payload", {}))) for r in payloads["graph_nodes"]],
        )
        _execute_many(conn,
            "insert into graph_edges(edge_id, source_id, target_id, edge_type, payload, updated_at) values (%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(edge_id) do update set source_id=excluded.source_id, target_id=excluded.target_id, edge_type=excluded.edge_type, payload=excluded.payload, updated_at=now()",
            [(r["edge_id"], r.get("source_id"), r.get("target_id"), r.get("edge_type"), _json_param(r.get("payload", {}))) for r in payloads["graph_edges"]],
        )

        ec_rows = []
        for r in payloads["evidence_consensus_records"]:
            ec_rows.append((_record_id(r, "ec", "record_id", "id", "consensus_id"), _first(r, "page_id", "page"), _first(r, "evidence_layer", "layer"), _first(r, "trust_tier", "trust"), _first(r, "rag_action"), _first(r, "repair_action"), _first(r, "usable_confidence", "confidence", "trace_lc_usable_confidence"), _json_param(r)))
        _execute_many(conn,
            "insert into evidence_consensus_records(record_id, page_id, evidence_layer, trust_tier, rag_action, repair_action, usable_confidence, payload, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(record_id) do update set page_id=excluded.page_id, evidence_layer=excluded.evidence_layer, trust_tier=excluded.trust_tier, rag_action=excluded.rag_action, repair_action=excluded.repair_action, usable_confidence=excluded.usable_confidence, payload=excluded.payload, updated_at=now()",
            ec_rows,
        )
        st_rows = []
        for r in payloads["stage5_decision_records"]:
            st_rows.append((_record_id(r, "stage5", "record_id", "id"), _first(r, "page_id", "page"), _first(r, "evidence_layer", "layer"), _first(r, "selected_trust_tier", "trust_tier"), _first(r, "selected_rag_action", "rag_action"), _safe_bool(_first(r, "policy_controlled", "controlled")), _first(r, "usable_confidence", "confidence"), _json_param(r)))
        _execute_many(conn,
            "insert into stage5_decision_records(record_id, page_id, evidence_layer, selected_trust_tier, selected_rag_action, policy_controlled, usable_confidence, payload, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(record_id) do update set page_id=excluded.page_id, evidence_layer=excluded.evidence_layer, selected_trust_tier=excluded.selected_trust_tier, selected_rag_action=excluded.selected_rag_action, policy_controlled=excluded.policy_controlled, usable_confidence=excluded.usable_confidence, payload=excluded.payload, updated_at=now()",
            st_rows,
        )
        rag_rows = []
        for r in payloads["rag_eligibility_records"]:
            bucket = _first(r, "rag_bucket", "bucket")
            safe_for_rag = bucket not in (None, "", "excluded") and str(bucket) != "excluded"
            rag_rows.append((_record_id(r, "rag", "record_id", "id"), _first(r, "page_id", "page"), bucket, _first(r, "rag_action"), _first(r, "trust_tier", "trust"), _first(r, "evidence_layer", "layer"), safe_for_rag, _json_param(r)))
        _execute_many(conn,
            "insert into rag_eligibility_records(record_id, page_id, rag_bucket, rag_action, trust_tier, evidence_layer, safe_for_rag, payload, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(record_id) do update set page_id=excluded.page_id, rag_bucket=excluded.rag_bucket, rag_action=excluded.rag_action, trust_tier=excluded.trust_tier, evidence_layer=excluded.evidence_layer, safe_for_rag=excluded.safe_for_rag, payload=excluded.payload, updated_at=now()",
            rag_rows,
        )
        cand_rows = []
        for r in payloads["rag_candidate_chunks"]:
            bucket = _first(r, "rag_bucket", "bucket", "candidate_type")
            cand_id = str(_first(r, "candidate_id", "id", default=_record_id(r, "cand", "record_id")))
            cand_rows.append((cand_id, _first(r, "page_id", "page"), _first(r, "candidate_type", default=bucket), bucket, _first(r, "evidence_layer", "layer"), _first(r, "trust_tier", "trust"), _first(r, "usable_confidence", "confidence"), _first(r, "text", "chunk_text", "content", default=""), _first(r, "source_url"), _first(r, "tiff_path", "source_image_path"), _first(r, "ocr_path", "ocr_text_path"), _safe_bool(_first(r, "safe_for_rag"), default=True), _json_param(r)))
        _execute_many(conn,
            "insert into rag_candidate_chunks(candidate_id, page_id, candidate_type, rag_bucket, evidence_layer, trust_tier, usable_confidence, text, source_url, tiff_path, ocr_path, safe_for_rag, payload, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(candidate_id) do update set page_id=excluded.page_id, candidate_type=excluded.candidate_type, rag_bucket=excluded.rag_bucket, evidence_layer=excluded.evidence_layer, trust_tier=excluded.trust_tier, usable_confidence=excluded.usable_confidence, text=excluded.text, source_url=excluded.source_url, tiff_path=excluded.tiff_path, ocr_path=excluded.ocr_path, safe_for_rag=excluded.safe_for_rag, payload=excluded.payload, updated_at=now()",
            cand_rows,
        )
        cit_rows = []
        for r in payloads["source_citations"]:
            cit_id = str(_first(r, "citation_id", "id", default=_record_id(r, "citation")))
            cit_rows.append((cit_id, _first(r, "candidate_id"), _first(r, "page_id", "page"), _first(r, "citation_text", "citation_markdown", "text"), _first(r, "source_url"), _first(r, "tiff_path"), _first(r, "ocr_path"), _json_param(r)))
        _execute_many(conn,
            "insert into source_citations(citation_id, candidate_id, page_id, citation_text, source_url, tiff_path, ocr_path, payload, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(citation_id) do update set candidate_id=excluded.candidate_id, page_id=excluded.page_id, citation_text=excluded.citation_text, source_url=excluded.source_url, tiff_path=excluded.tiff_path, ocr_path=excluded.ocr_path, payload=excluded.payload, updated_at=now()",
            cit_rows,
        )
        ask_rows = []
        for r in payloads["ask_runs"]:
            ask_id = str(_first(r, "ask_run_id", "run_id", default=_stable_id(_first(r, "query"), _first(r, "created_at"), prefix="ask")))
            ask_rows.append((ask_id, _first(r, "query", "effective_query"), _first(r, "query_fingerprint"), _first(r, "feedback_mode"), _first(r, "answer_page_records"), _first(r, "answer_evidence_records"), _first(r, "unsafe_answer_groups"), _json_param(r)))
        _execute_many(conn,
            "insert into ask_runs(ask_run_id, query, query_fingerprint, feedback_mode, answer_page_records, answer_evidence_records, unsafe_answer_groups, payload) values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) "
            "on conflict(ask_run_id) do update set query=excluded.query, query_fingerprint=excluded.query_fingerprint, feedback_mode=excluded.feedback_mode, answer_page_records=excluded.answer_page_records, answer_evidence_records=excluded.answer_evidence_records, unsafe_answer_groups=excluded.unsafe_answer_groups, payload=excluded.payload",
            ask_rows,
        )
        fb_rows = []
        for r in payloads["feedback_events"]:
            fb_id = str(_first(r, "feedback_id", "id", default=_record_id(r, "feedback")))
            fb_rows.append((fb_id, _first(r, "ask_run_id"), _first(r, "query_fingerprint"), _first(r, "rating"), _json_param(_first(r, "reason_codes", "reasons", default=[])), _json_param(_first(r, "affected_page_ids", "affected_pages", default=[])), _json_param(_first(r, "expected_page_ids", "expected_pages", default=[])), _first(r, "context_status"), _safe_bool(_first(r, "policy_signal_eligible")), _json_param(r)))
        _execute_many(conn,
            "insert into feedback_events(feedback_id, ask_run_id, query_fingerprint, rating, reason_codes, affected_page_ids, expected_page_ids, context_status, policy_signal_eligible, payload, updated_at) values (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb, now()) "
            "on conflict(feedback_id) do update set ask_run_id=excluded.ask_run_id, query_fingerprint=excluded.query_fingerprint, rating=excluded.rating, reason_codes=excluded.reason_codes, affected_page_ids=excluded.affected_page_ids, expected_page_ids=excluded.expected_page_ids, context_status=excluded.context_status, policy_signal_eligible=excluded.policy_signal_eligible, payload=excluded.payload, updated_at=now()",
            fb_rows,
        )
        sig_rows = []
        for r in payloads["feedback_policy_signals"]:
            sig_id = str(_first(r, "signal_id", "id", default=_record_id(r, "signal")))
            sig_rows.append((sig_id, _first(r, "feedback_id"), _first(r, "query_fingerprint"), _first(r, "page_id", "affected_page_id"), _first(r, "signal_type", "signal"), _first(r, "weight", "score", "strength"), _first(r, "reason", "reason_code"), _first(r, "context_status"), _json_param(r)))
        _execute_many(conn,
            "insert into feedback_policy_signals(signal_id, feedback_id, query_fingerprint, page_id, signal_type, weight, reason, context_status, payload, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now()) "
            "on conflict(signal_id) do update set feedback_id=excluded.feedback_id, query_fingerprint=excluded.query_fingerprint, page_id=excluded.page_id, signal_type=excluded.signal_type, weight=excluded.weight, reason=excluded.reason, context_status=excluded.context_status, payload=excluded.payload, updated_at=now()",
            sig_rows,
        )
        quality_rows = [(r["quality_id"], r.get("stage"), r.get("status"), _json_param(r.get("summary", {})), r.get("source_path")) for r in payloads["quality_runs"]]
        _execute_many(conn,
            "insert into quality_runs(quality_id, stage, status, summary, source_path) values (%s,%s,%s,%s::jsonb,%s) "
            "on conflict(quality_id) do update set stage=excluded.stage, status=excluded.status, summary=excluded.summary, source_path=excluded.source_path",
            quality_rows,
        )
        summary = {
            "status": "OK",
            "version": VERSION,
            "schema_version": SCHEMA_VERSION,
            "load_id": load_id,
            "created_at": _utc_now(),
            "source_zip_path": str(paths.source_zip_path) if paths.source_zip_path else None,
            "ocr_export_dir": str(paths.ocr_export_dir),
            "organization_dir": str(paths.organization_dir),
            "trace_net_dir": str(paths.trace_net_dir),
            "counts": counts,
        }
        with conn.cursor() as cur:
            cur.execute(
                "insert into trace_net_load_runs(load_id, version, source_zip_path, ocr_export_dir, organization_dir, trace_net_dir, summary) values (%s,%s,%s,%s,%s,%s,%s::jsonb) on conflict(load_id) do nothing",
                (load_id, VERSION, str(paths.source_zip_path) if paths.source_zip_path else None, str(paths.ocr_export_dir), str(paths.organization_dir), str(paths.trace_net_dir), _json_param(summary)),
            )
        conn.commit()
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(paths.load_summary, summary)
    _write_json(paths.load_manifest, {"payload_counts": counts, "paths": {"ocr_export_dir": str(paths.ocr_export_dir), "organization_dir": str(paths.organization_dir), "trace_net_dir": str(paths.trace_net_dir)}})
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _database_url_from_args(value: str | None) -> str:
    url = value or os.environ.get("TRACE_NET_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Database URL required. Pass --database-url or set TRACE_NET_DATABASE_URL.")
    return url


def init_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize TRACE-Net PostgreSQL schema")
    parser.add_argument("--database-url")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--emit-sql", action="store_true", help="Write schema SQL without connecting")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.emit_sql:
        ddl_path = output_dir / "trace_net_postgres_schema.sql"
        ddl_path.write_text(schema_sql(), encoding="utf-8")
        summary = {"status": "OK", "version": VERSION, "schema_version": SCHEMA_VERSION, "emit_sql_only": True, "ddl_path": str(ddl_path)}
        _write_json(output_dir / "trace_net_postgres_init_summary.json", summary)
    else:
        summary = init_schema(_database_url_from_args(args.database_url), output_dir)
    print("TRACE-Net PostgreSQL schema init")
    print(f"  Status: {summary.get('status')}")
    print(f"  Schema version: {summary.get('schema_version')}")
    print(f"  DDL: {summary.get('ddl_path')}")
    return 0


def load_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load local TRACE-Net artifacts into PostgreSQL")
    parser.add_argument("--database-url")
    parser.add_argument("--ocr-export-dir", default=str(DEFAULT_OCR_EXPORT_DIR))
    parser.add_argument("--ocr-depth-audit")
    parser.add_argument("--organization-dir", default=str(DEFAULT_ORGANIZATION_DIR))
    parser.add_argument("--trace-net-dir", default=str(DEFAULT_TRACE_NET_DIR))
    parser.add_argument("--source-zip")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--upsert", action="store_true", help="Accepted for readability; loader always upserts in v1")
    parser.add_argument("--dry-run", action="store_true", help="Collect payload counts without connecting/loading")
    args = parser.parse_args(argv)
    paths = PostgresLoaderPaths(
        ocr_export_dir=Path(args.ocr_export_dir),
        ocr_depth_audit_path=Path(args.ocr_depth_audit) if args.ocr_depth_audit else None,
        organization_dir=Path(args.organization_dir),
        trace_net_dir=Path(args.trace_net_dir),
        source_zip_path=Path(args.source_zip) if args.source_zip else None,
        output_dir=Path(args.output_dir),
    )
    if args.dry_run:
        payloads = collect_payloads(paths)
        summary = {"status": "OK", "version": VERSION, "dry_run": True, "counts": {k: len(v) if isinstance(v, list) else 0 for k, v in payloads.items()}}
        paths.output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(paths.load_summary, summary)
    else:
        summary = load_payloads(_database_url_from_args(args.database_url), paths, upsert=True)
    counts = summary.get("counts", {})
    print("TRACE-Net PostgreSQL loader")
    print(f"  Status: {summary.get('status')}")
    print(f"  Version: {summary.get('version')}")
    print(f"  OCR export: {paths.ocr_export_dir}")
    print(f"  Trace-Net dir: {paths.trace_net_dir}")
    print("  Counts:")
    for key in sorted(counts):
        print(f"    {key}: {counts[key]}")
    print("Files written:")
    print(f"  summary: {paths.load_summary}")
    print(f"  manifest: {paths.load_manifest}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(load_main())
