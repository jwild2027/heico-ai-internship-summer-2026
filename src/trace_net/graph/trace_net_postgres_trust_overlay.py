"""TRACE-Net PostgreSQL trust overlay builder.

This module normalizes trust tiers from local TRACE-Net PostgreSQL rows into
queryable SQL columns and trust overlay tables.  It is intentionally conservative:
it does not change source truth, RAG eligibility, or candidate safety flags.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

VERSION = "trace_net_postgres_trust_overlay_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/trust_overlay")
VALID_TIERS = {"A", "B", "C", "D"}

TRUST_KEYS = (
    "trust_tier",
    "selected_trust_tier",
    "final_trust_tier",
    "policy_trust_tier",
    "stage5_trust_tier",
    "confidence_tier",
    "trust",
    "tier",
)
RAG_ACTION_KEYS = (
    "rag_action",
    "selected_rag_action",
    "final_rag_action",
    "policy_rag_action",
    "stage5_rag_action",
)
REPAIR_ACTION_KEYS = (
    "repair_action",
    "selected_repair_action",
    "final_repair_action",
    "policy_repair_action",
    "stage5_repair_action",
)


@dataclass(frozen=True)
class TrustRecord:
    trust_record_id: str
    source_table: str
    source_record_id: str
    page_id: str
    evidence_layer: str
    rag_bucket: str
    trust_tier: str
    rag_action: str
    repair_action: str
    usable_confidence: Optional[float]
    safe_for_rag: bool
    source_url: str
    payload: Dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_tier(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in VALID_TIERS:
        return text
    # Common shapes such as "tier=A" or "Trust: B".
    match = re.search(r"\b([ABCD])\b", text)
    if match:
        return match.group(1)
    return None


def normalize_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "safe", "ok"}:
        return True
    if text in {"0", "false", "f", "no", "n", "unsafe", "excluded"}:
        return False
    return default


def get_nested(payload: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    # Common nested containers.
    for parent in ("decision", "selected", "stage5", "confidence", "trust", "trace_lc"):
        child = payload.get(parent)
        if isinstance(child, Mapping):
            for key in keys:
                if key in child and child.get(key) not in (None, ""):
                    return child.get(key)
    return None


def derive_trust_tier(
    *,
    explicit: Any = None,
    payload: Optional[Mapping[str, Any]] = None,
    rag_bucket: str = "",
    evidence_layer: str = "",
    usable_confidence: Any = None,
) -> str:
    """Derive a conservative trust tier.

    The first choice is any explicit trust value already stored in the record or
    payload.  Fallbacks are layer/bucket-specific and match the current TRACE-Net
    policy: source/verified evidence is A, derived context uses confidence
    thresholds, routing-only artifacts do not get promoted into RAG.
    """
    tier = normalize_tier(explicit)
    if tier:
        return tier
    payload = payload or {}
    tier = normalize_tier(get_nested(payload, TRUST_KEYS))
    if tier:
        return tier

    bucket = str(rag_bucket or "").strip().lower()
    layer = str(evidence_layer or "").strip().lower()
    confidence = normalize_float(usable_confidence)
    if confidence is None:
        confidence = normalize_float(get_nested(payload, ("usable_confidence", "confidence", "score")))

    if bucket == "source_evidence" or layer in {"source_trace", "source_evidence"}:
        return "A"
    if bucket == "verified_part_evidence" or layer in {"part_catalog", "verified_part_evidence"}:
        return "A"
    if bucket == "source_text_evidence" or layer in {"source_text", "source_text_evidence"}:
        # Source text is source-backed OCR.  If it is present in the safe RAG
        # candidate index, keep it as A unless an upstream explicit tier says
        # otherwise.
        return "A"
    if bucket == "derived_context" or layer in {"table_tile_text_refined", "derived_context"}:
        if confidence is not None:
            if confidence >= 0.82:
                return "A"
            if confidence >= 0.64:
                return "B"
        return "B"
    if bucket in {"excluded", "exclude", "unsafe"}:
        return "C"
    if layer in {"table_candidate", "table_tiles", "visual_text"}:
        return "C"
    return "C"


def derive_rag_action(explicit: Any = None, payload: Optional[Mapping[str, Any]] = None, rag_bucket: str = "", evidence_layer: str = "") -> str:
    if explicit not in (None, ""):
        return str(explicit)
    payload = payload or {}
    nested = get_nested(payload, RAG_ACTION_KEYS)
    if nested not in (None, ""):
        return str(nested)
    bucket = str(rag_bucket or "").lower()
    layer = str(evidence_layer or "").lower()
    if bucket == "source_evidence" or layer == "source_trace":
        return "include_as_source_evidence"
    if bucket == "source_text_evidence" or layer == "source_text":
        return "include_as_source_text_evidence"
    if bucket == "verified_part_evidence" or layer == "part_catalog":
        return "include_as_verified_part_evidence"
    if bucket == "derived_context" or layer == "table_tile_text_refined":
        return "include_as_derived_context"
    return "exclude_from_rag"


def derive_repair_action(explicit: Any = None, payload: Optional[Mapping[str, Any]] = None) -> str:
    if explicit not in (None, ""):
        return str(explicit)
    payload = payload or {}
    nested = get_nested(payload, REPAIR_ACTION_KEYS)
    if nested not in (None, ""):
        return str(nested)
    return "none"


def record_id(*parts: Any) -> str:
    joined = "|".join(str(p or "") for p in parts)
    return hashlib.sha1(joined.encode("utf-8", errors="ignore")).hexdigest()[:24]


def connect(database_url: str):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError("psycopg is required. Install with: pip install 'psycopg[binary]' or psycopg2-binary") from exc
    return psycopg.connect(database_url, row_factory=dict_row)


def table_exists(cur, table: str) -> bool:
    cur.execute("select to_regclass(%s) is not null as exists", (table,))
    row = cur.fetchone() or {}
    return bool(row.get("exists"))


def table_columns(cur, table: str) -> set[str]:
    cur.execute(
        """
        select column_name from information_schema.columns
        where table_schema='public' and table_name=%s
        """,
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def ensure_schema(cur) -> None:
    cur.execute(
        """
        create table if not exists evidence_trust_records(
          trust_record_id text primary key,
          source_table text not null,
          source_record_id text,
          page_id text,
          evidence_layer text,
          rag_bucket text,
          trust_tier text,
          rag_action text,
          repair_action text,
          usable_confidence double precision,
          safe_for_rag boolean default true,
          source_url text,
          payload jsonb default '{}'::jsonb,
          updated_at timestamptz default now()
        )
        """
    )
    cur.execute(
        """
        create table if not exists page_trust_traits(
          trait_id text primary key,
          page_id text not null,
          evidence_layer text,
          rag_bucket text,
          trust_tier text,
          rag_action text,
          record_count integer default 0,
          safe_for_rag_count integer default 0,
          payload jsonb default '{}'::jsonb,
          updated_at timestamptz default now()
        )
        """
    )
    cur.execute("create index if not exists idx_evidence_trust_page on evidence_trust_records(page_id)")
    cur.execute("create index if not exists idx_evidence_trust_layer on evidence_trust_records(evidence_layer)")
    cur.execute("create index if not exists idx_page_trust_page on page_trust_traits(page_id)")


def select_expr(cols: set[str], col: str, alias: str, type_name: str = "text") -> str:
    if col in cols:
        return f"{col} as {alias}"
    if type_name == "jsonb":
        return f"'{{}}'::jsonb as {alias}"
    if type_name == "double":
        return f"NULL::double precision as {alias}"
    if type_name == "bool":
        return f"NULL::boolean as {alias}"
    return f"NULL::{type_name} as {alias}"


def first_existing(cols: set[str], names: Sequence[str]) -> Optional[str]:
    for name in names:
        if name in cols:
            return name
    return None


def load_rows_from_table(cur, table: str) -> List[TrustRecord]:
    if not table_exists(cur, table):
        return []
    cols = table_columns(cur, table)
    payload_expr = select_expr(cols, "payload", "payload", "jsonb")
    confidence_col = first_existing(cols, ["usable_confidence", "confidence", "score"])
    trust_col = first_existing(cols, ["trust_tier", "selected_trust_tier", "final_trust_tier", "policy_trust_tier"])
    action_col = first_existing(cols, ["rag_action", "selected_rag_action", "final_rag_action", "policy_rag_action"])
    repair_col = first_existing(cols, ["repair_action", "selected_repair_action", "final_repair_action", "policy_repair_action"])
    id_col = first_existing(cols, ["candidate_id", "record_id", "id", "eligibility_id", "decision_id"])
    page_expr = select_expr(cols, "page_id", "page_id")
    layer_expr = select_expr(cols, "evidence_layer", "evidence_layer")
    bucket_expr = select_expr(cols, "rag_bucket", "rag_bucket")
    source_expr = select_expr(cols, "source_url", "source_url")
    safe_expr = select_expr(cols, "safe_for_rag", "safe_for_rag", "bool")
    if table == "rag_candidate_chunks" and "safe_for_rag" not in cols:
        safe_expr = "true as safe_for_rag"
    elif table != "rag_candidate_chunks" and "safe_for_rag" not in cols:
        safe_expr = "NULL::boolean as safe_for_rag"

    select_parts = [
        f"{id_col} as source_record_id" if id_col else "NULL::text as source_record_id",
        page_expr,
        layer_expr,
        bucket_expr,
        f"{trust_col} as explicit_trust_tier" if trust_col else "NULL::text as explicit_trust_tier",
        f"{action_col} as explicit_rag_action" if action_col else "NULL::text as explicit_rag_action",
        f"{repair_col} as explicit_repair_action" if repair_col else "NULL::text as explicit_repair_action",
        f"{confidence_col} as usable_confidence" if confidence_col else "NULL::double precision as usable_confidence",
        safe_expr,
        source_expr,
        payload_expr,
    ]
    cur.execute(f"select {', '.join(select_parts)} from {table}")
    rows = cur.fetchall()
    out: List[TrustRecord] = []
    for i, row in enumerate(rows):
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {"raw_payload": payload}
        if not isinstance(payload, dict):
            payload = {"payload": payload}
        source_record_id = str(row.get("source_record_id") or record_id(table, i, row.get("page_id"), row.get("rag_bucket")))
        page_id = str(row.get("page_id") or payload.get("page_id") or "")
        rag_bucket = str(row.get("rag_bucket") or payload.get("rag_bucket") or "")
        evidence_layer = str(row.get("evidence_layer") or payload.get("evidence_layer") or "")
        if not evidence_layer:
            if rag_bucket == "source_evidence":
                evidence_layer = "source_trace"
            elif rag_bucket == "source_text_evidence":
                evidence_layer = "source_text"
            elif rag_bucket == "verified_part_evidence":
                evidence_layer = "part_catalog"
            elif rag_bucket == "derived_context":
                evidence_layer = "table_tile_text_refined"
        confidence = normalize_float(row.get("usable_confidence"))
        trust_tier = derive_trust_tier(
            explicit=row.get("explicit_trust_tier"),
            payload=payload,
            rag_bucket=rag_bucket,
            evidence_layer=evidence_layer,
            usable_confidence=confidence,
        )
        rag_action = derive_rag_action(row.get("explicit_rag_action"), payload, rag_bucket, evidence_layer)
        repair_action = derive_repair_action(row.get("explicit_repair_action"), payload)
        safe_for_rag = normalize_bool(row.get("safe_for_rag"), default=(rag_action.startswith("include_") or table == "rag_candidate_chunks"))
        source_url = str(row.get("source_url") or payload.get("source_url") or "")
        trust_id = f"trust:{record_id(table, source_record_id, page_id, rag_bucket, evidence_layer, trust_tier)}"
        out.append(
            TrustRecord(
                trust_record_id=trust_id,
                source_table=table,
                source_record_id=source_record_id,
                page_id=page_id,
                evidence_layer=evidence_layer,
                rag_bucket=rag_bucket,
                trust_tier=trust_tier,
                rag_action=rag_action,
                repair_action=repair_action,
                usable_confidence=confidence,
                safe_for_rag=safe_for_rag,
                source_url=source_url,
                payload=payload,
            )
        )
    return out


def update_candidate_trust_tiers(cur, records: Sequence[TrustRecord]) -> int:
    if not table_exists(cur, "rag_candidate_chunks"):
        return 0
    cols = table_columns(cur, "rag_candidate_chunks")
    if "trust_tier" not in cols or "candidate_id" not in cols:
        return 0
    updated = 0
    for rec in records:
        if rec.source_table != "rag_candidate_chunks":
            continue
        cur.execute(
            """
            update rag_candidate_chunks
            set trust_tier=%s
            where candidate_id=%s and (trust_tier is null or btrim(trust_tier)='')
            """,
            (rec.trust_tier, rec.source_record_id),
        )
        updated += int(cur.rowcount or 0)
    return updated


def insert_trust_records(cur, records: Sequence[TrustRecord]) -> None:
    cur.execute("delete from evidence_trust_records")
    for rec in records:
        cur.execute(
            """
            insert into evidence_trust_records(
                trust_record_id, source_table, source_record_id, page_id, evidence_layer,
                rag_bucket, trust_tier, rag_action, repair_action, usable_confidence,
                safe_for_rag, source_url, payload, updated_at
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
            on conflict (trust_record_id) do update set
                source_table=excluded.source_table,
                source_record_id=excluded.source_record_id,
                page_id=excluded.page_id,
                evidence_layer=excluded.evidence_layer,
                rag_bucket=excluded.rag_bucket,
                trust_tier=excluded.trust_tier,
                rag_action=excluded.rag_action,
                repair_action=excluded.repair_action,
                usable_confidence=excluded.usable_confidence,
                safe_for_rag=excluded.safe_for_rag,
                source_url=excluded.source_url,
                payload=excluded.payload,
                updated_at=now()
            """,
            (
                rec.trust_record_id,
                rec.source_table,
                rec.source_record_id,
                rec.page_id,
                rec.evidence_layer,
                rec.rag_bucket,
                rec.trust_tier,
                rec.rag_action,
                rec.repair_action,
                rec.usable_confidence,
                rec.safe_for_rag,
                rec.source_url,
                json.dumps(rec.payload, ensure_ascii=False),
            ),
        )


def build_page_traits(cur, records: Sequence[TrustRecord]) -> int:
    cur.execute("delete from page_trust_traits")
    grouped: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for rec in records:
        if not rec.page_id:
            continue
        key = (rec.page_id, rec.evidence_layer, rec.rag_bucket, rec.trust_tier, rec.rag_action)
        item = grouped.setdefault(
            key,
            {
                "record_count": 0,
                "safe_for_rag_count": 0,
                "source_tables": Counter(),
                "sample_records": [],
            },
        )
        item["record_count"] += 1
        if rec.safe_for_rag:
            item["safe_for_rag_count"] += 1
        item["source_tables"][rec.source_table] += 1
        if len(item["sample_records"]) < 5:
            item["sample_records"].append(rec.source_record_id)
    for (page_id, layer, bucket, tier, action), item in grouped.items():
        trait_id = f"page_trust:{record_id(page_id, layer, bucket, tier, action)}"
        payload = {
            "source_tables": dict(item["source_tables"]),
            "sample_records": item["sample_records"],
            "version": VERSION,
        }
        cur.execute(
            """
            insert into page_trust_traits(
                trait_id, page_id, evidence_layer, rag_bucket, trust_tier, rag_action,
                record_count, safe_for_rag_count, payload, updated_at
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
            on conflict (trait_id) do update set
                page_id=excluded.page_id,
                evidence_layer=excluded.evidence_layer,
                rag_bucket=excluded.rag_bucket,
                trust_tier=excluded.trust_tier,
                rag_action=excluded.rag_action,
                record_count=excluded.record_count,
                safe_for_rag_count=excluded.safe_for_rag_count,
                payload=excluded.payload,
                updated_at=now()
            """,
            (trait_id, page_id, layer, bucket, tier, action, item["record_count"], item["safe_for_rag_count"], json.dumps(payload)),
        )
    return len(grouped)


def scalar(cur, sql: str, params: Sequence[Any] = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def collect_summary(cur, records: Sequence[TrustRecord], candidate_updates: int, output_dir: Path) -> Dict[str, Any]:
    source_counts = Counter(r.source_table for r in records)
    tier_counts = Counter(r.trust_tier for r in records)
    layer_counts = Counter(r.evidence_layer for r in records)
    bucket_counts = Counter(r.rag_bucket for r in records)
    action_counts = Counter(r.rag_action for r in records)
    pages_with_traits = int(scalar(cur, "select count(distinct page_id) from page_trust_traits") or 0)
    page_trait_records = int(scalar(cur, "select count(*) from page_trust_traits") or 0)
    trust_records = int(scalar(cur, "select count(*) from evidence_trust_records") or 0)
    candidate_missing = 0
    candidate_records = 0
    source_trace_a = 0
    verified_part_a = 0
    derived_context = 0
    source_text_a = 0
    unsafe_trusted = 0
    if table_exists(cur, "rag_candidate_chunks"):
        candidate_records = int(scalar(cur, "select count(*) from rag_candidate_chunks") or 0)
        cols = table_columns(cur, "rag_candidate_chunks")
        if "trust_tier" in cols:
            candidate_missing = int(scalar(cur, "select count(*) from rag_candidate_chunks where trust_tier is null or btrim(trust_tier)='' ") or 0)
            source_trace_a = int(scalar(cur, "select count(*) from rag_candidate_chunks where rag_bucket='source_evidence' and trust_tier='A'") or 0)
            source_text_a = int(scalar(cur, "select count(*) from rag_candidate_chunks where rag_bucket='source_text_evidence' and trust_tier='A'") or 0)
            verified_part_a = int(scalar(cur, "select count(*) from rag_candidate_chunks where rag_bucket='verified_part_evidence' and trust_tier='A'") or 0)
            derived_context = int(scalar(cur, "select count(*) from rag_candidate_chunks where rag_bucket='derived_context'") or 0)
        if "safe_for_rag" in cols and "trust_tier" in cols:
            unsafe_trusted = int(scalar(cur, "select count(*) from rag_candidate_chunks where coalesce(safe_for_rag,false)=false and trust_tier in ('A','B')") or 0)
        else:
            unsafe_trusted = 0
    pages = int(scalar(cur, "select count(*) from pages") or 0) if table_exists(cur, "pages") else 0
    graph_nodes = int(scalar(cur, "select count(*) from graph_nodes") or 0) if table_exists(cur, "graph_nodes") else 0
    graph_edges = int(scalar(cur, "select count(*) from graph_edges") or 0) if table_exists(cur, "graph_edges") else 0
    summary = {
        "status": "OK",
        "version": VERSION,
        "created_at": utc_now_iso(),
        "output_dir": str(output_dir),
        "pages": pages,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "trust_overlay_records": trust_records,
        "page_trust_trait_records": page_trait_records,
        "pages_with_trust_traits": pages_with_traits,
        "rag_candidate_records": candidate_records,
        "rag_candidate_trust_updates": candidate_updates,
        "rag_candidate_missing_trust_tier": candidate_missing,
        "source_trace_A_records": source_trace_a,
        "source_text_A_records": source_text_a,
        "verified_part_A_records": verified_part_a,
        "derived_context_records": derived_context,
        "unsafe_trusted_rag_records": unsafe_trusted,
        "source_table_counts": dict(sorted(source_counts.items())),
        "trust_tier_counts": dict(sorted(tier_counts.items())),
        "evidence_layer_counts": dict(sorted(layer_counts.items())),
        "rag_bucket_counts": dict(sorted(bucket_counts.items())),
        "rag_action_counts": dict(sorted(action_counts.items())),
        "source_truth_mutation_records": 0,
        "production_ranking_changed": False,
    }
    return summary


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_graph_artifacts(records: Sequence[TrustRecord], max_records: int = 5000) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    for rec in records[:max_records]:
        page_node = f"page:{rec.page_id}" if rec.page_id else "page:unknown"
        trust_node = f"trust:{rec.evidence_layer or 'unknown'}:{rec.trust_tier}"
        action_node = f"rag_action:{rec.rag_action}"
        rec_node = rec.trust_record_id
        nodes.setdefault(page_node, {"id": page_node, "type": "page", "label": rec.page_id})
        nodes.setdefault(trust_node, {"id": trust_node, "type": "trust_trait", "label": trust_node})
        nodes.setdefault(action_node, {"id": action_node, "type": "rag_action", "label": rec.rag_action})
        nodes.setdefault(rec_node, {"id": rec_node, "type": "evidence_trust_record", "label": rec.source_record_id, "source_table": rec.source_table})
        edges.append({"source": rec_node, "target": page_node, "type": "TRUST_RECORD_FOR_PAGE"})
        edges.append({"source": page_node, "target": trust_node, "type": "HAS_TRUST_TIER"})
        edges.append({"source": page_node, "target": action_node, "type": "HAS_RAG_ACTION"})
    return list(nodes.values()), edges


def write_report(summary: Mapping[str, Any], output_dir: Path) -> None:
    rows = []
    for key in [
        "pages",
        "rag_candidate_records",
        "trust_overlay_records",
        "page_trust_trait_records",
        "pages_with_trust_traits",
        "rag_candidate_trust_updates",
        "rag_candidate_missing_trust_tier",
        "source_trace_A_records",
        "source_text_A_records",
        "verified_part_A_records",
        "derived_context_records",
        "unsafe_trusted_rag_records",
        "source_truth_mutation_records",
    ]:
        rows.append(f"<tr><th>{html.escape(key)}</th><td>{html.escape(str(summary.get(key)))}</td></tr>")
    html_doc = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Postgres Trust Overlay</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}} table{{border-collapse:collapse}} th,td{{border:1px solid #ccc;padding:6px 10px;text-align:left}} pre{{background:#f5f5f5;padding:12px}}</style></head>
<body>
<h1>TRACE-Net Postgres Trust Overlay</h1>
<p>Status: <b>{html.escape(str(summary.get('status')))}</b> &nbsp; Version: <code>{html.escape(str(summary.get('version')))}</code></p>
<table>{''.join(rows)}</table>
<h2>Trust tiers</h2><pre>{html.escape(json.dumps(summary.get('trust_tier_counts', {}), indent=2))}</pre>
<h2>RAG buckets</h2><pre>{html.escape(json.dumps(summary.get('rag_bucket_counts', {}), indent=2))}</pre>
<h2>Evidence layers</h2><pre>{html.escape(json.dumps(summary.get('evidence_layer_counts', {}), indent=2))}</pre>
<p>This overlay normalizes trust tiers for SQL/graph testing. It does not mutate source truth, RAG eligibility, or production ranking.</p>
</body></html>"""
    (output_dir / "trace_net_postgres_trust_overlay_report.html").write_text(html_doc, encoding="utf-8")
    md = [
        "# TRACE-Net Postgres Trust Overlay v1",
        "",
        f"Status: **{summary.get('status')}**",
        f"Version: `{summary.get('version')}`",
        "",
        "## Summary",
    ]
    for key in ["pages", "trust_overlay_records", "page_trust_trait_records", "rag_candidate_missing_trust_tier", "source_trace_A_records", "verified_part_A_records", "derived_context_records", "unsafe_trusted_rag_records"]:
        md.append(f"- **{key}**: {summary.get(key)}")
    (output_dir / "trace_net_postgres_trust_overlay_report.md").write_text("\n".join(md), encoding="utf-8")


def build_postgres_trust_overlay(database_url: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_tables = [
        "rag_candidate_chunks",
        "evidence_consensus_records",
        "stage5_decision_records",
        "rag_eligibility_records",
    ]
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            records: List[TrustRecord] = []
            for table in source_tables:
                records.extend(load_rows_from_table(cur, table))
            candidate_updates = update_candidate_trust_tiers(cur, records)
            insert_trust_records(cur, records)
            build_page_traits(cur, records)
            conn.commit()
            summary = collect_summary(cur, records, candidate_updates, output_dir)
    record_rows = [
        {
            "trust_record_id": r.trust_record_id,
            "source_table": r.source_table,
            "source_record_id": r.source_record_id,
            "page_id": r.page_id,
            "evidence_layer": r.evidence_layer,
            "rag_bucket": r.rag_bucket,
            "trust_tier": r.trust_tier,
            "rag_action": r.rag_action,
            "repair_action": r.repair_action,
            "usable_confidence": r.usable_confidence,
            "safe_for_rag": r.safe_for_rag,
            "source_url": r.source_url,
        }
        for r in records
    ]
    nodes, edges = build_graph_artifacts(records)
    write_json(output_dir / "trace_net_postgres_trust_overlay_summary.json", summary)
    write_jsonl(output_dir / "trace_net_postgres_trust_overlay_records.jsonl", record_rows)
    write_json(output_dir / "trace_net_postgres_trust_overlay_graph_nodes.json", nodes)
    write_json(output_dir / "trace_net_postgres_trust_overlay_graph_edges.json", edges)
    write_report(summary, output_dir)
    return summary


def maybe_open(path: Path) -> None:
    if not path.exists():
        return
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f"open {json.dumps(str(path))}")
    else:
        os.system(f"xdg-open {json.dumps(str(path))} >/dev/null 2>&1 &")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net PostgreSQL trust overlay")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""), help="PostgreSQL connection string")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        print("ERROR: --database-url or TRACE_NET_DATABASE_URL is required", file=sys.stderr)
        return 2
    summary = build_postgres_trust_overlay(args.database_url, Path(args.output_dir))
    print("TRACE-Net PostgreSQL trust overlay")
    print(f"  Status: {summary.get('status')}")
    print(f"  Version: {summary.get('version')}")
    print(f"  Output dir: {args.output_dir}")
    print("  Summary:")
    for key in [
        "pages",
        "trust_overlay_records",
        "page_trust_trait_records",
        "pages_with_trust_traits",
        "rag_candidate_records",
        "rag_candidate_trust_updates",
        "rag_candidate_missing_trust_tier",
        "source_trace_A_records",
        "source_text_A_records",
        "verified_part_A_records",
        "derived_context_records",
        "unsafe_trusted_rag_records",
    ]:
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    out = Path(args.output_dir)
    for label, rel in [
        ("summary", "trace_net_postgres_trust_overlay_summary.json"),
        ("records", "trace_net_postgres_trust_overlay_records.jsonl"),
        ("report_html", "trace_net_postgres_trust_overlay_report.html"),
        ("graph_nodes", "trace_net_postgres_trust_overlay_graph_nodes.json"),
        ("graph_edges", "trace_net_postgres_trust_overlay_graph_edges.json"),
    ]:
        print(f"  {label}: {out / rel}")
    if args.open:
        maybe_open(out / "trace_net_postgres_trust_overlay_report.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
